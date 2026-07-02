"""
import_hf_skills.py — ONE-TIME rich import of skills.sh via its Hugging Face mirror.

The skills.sh API needs auth, so for rich descriptions we use the public HF
mirror `tickleliu/all-skills-from-skills-sh` (MIT). We page the HF datasets-server
rows API, keep only the light fields, DISCARD the heavy `detail` column, parse
owner/repo/skill from the install command, and write skills_sh_hf.json.

fetch.py then loads that cache to enrich the live sitemap skills with descriptions.
This is a heavy one-off (the dataset is large); NOT part of the daily task.

Usage:
  python import_hf_skills.py                # full import
  python import_hf_skills.py --limit 500    # quick test (first 500 rows)
"""
import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request

DATASET = "tickleliu/all-skills-from-skills-sh"
DS_BASE = "https://datasets-server.huggingface.co"
OUT_PATH = os.path.join(os.path.dirname(__file__), "skills_sh_hf.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "skills_sh_hf.state")
PAGE = 100        # datasets-server max length per /rows call
PAGE_DELAY = 1.2  # polite pacing between pages (seconds)


def fetch_json(url, timeout=60, retries=6):
    """GET JSON with backoff; waits out 429s (long sleep) instead of dying."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"    429 rate-limited — sleeping {wait}s...")
                time.sleep(wait)
            else:
                time.sleep(2 * (attempt + 1))
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def resolve_split():
    """Return (config, split) for the dataset."""
    data = fetch_json(f"{DS_BASE}/splits?dataset={urllib.parse.quote(DATASET)}")
    splits = data.get("splits", [])
    if not splits:
        raise RuntimeError("no splits returned for dataset")
    # Prefer a 'train' split if present, else the first.
    for s in splits:
        if s.get("split") == "train":
            return s["config"], s["split"]
    return splits[0]["config"], splits[0]["split"]


def parse_owner_repo_skill(code, skill_name):
    """Extract (owner, repo, skill) from an `npx skills add ...` command."""
    owner = repo = None
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", code or "")
    if m:
        owner, repo = m.group(1), m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
    if not owner:
        m2 = re.search(r"add\s+(?:-g\s+)?([^/\s]+)/([^/\s@]+)", code or "")
        if m2:
            owner, repo = m2.group(1), m2.group(2)
    sm = re.search(r"--skill\s+(\S+)", code or "")
    skill = sm.group(1) if sm else (skill_name or None)
    # strip shell quotes that some dataset rows carry (--skill '.NET')
    if skill:
        skill = skill.strip("'\"")
    if owner:
        owner = owner.strip("'\"")
    if repo:
        repo = repo.strip("'\"")
    return owner, repo, skill


def main():
    ap = argparse.ArgumentParser(description="One-time skills.sh HF mirror import")
    ap.add_argument("--limit", type=int, default=0, help="Only import first N rows (test)")
    args = ap.parse_args()

    config, split = resolve_split()
    print(f"Dataset {DATASET}  config={config}  split={split}")

    # total row count
    info = fetch_json(f"{DS_BASE}/size?dataset={urllib.parse.quote(DATASET)}")
    total = (info.get("size", {}).get("config", {}) or {}).get("num_rows") \
        or (info.get("size", {}).get("dataset", {}) or {}).get("num_rows") or 0
    if args.limit:
        total = min(total or args.limit, args.limit)
    print(f"Importing {'up to ' + str(args.limit) if args.limit else str(total)} rows...")

    # Resume support: reload prior records + last offset if present.
    out, seen, offset = [], set(), 0
    if os.path.exists(OUT_PATH) and os.path.exists(STATE_PATH):
        try:
            out = json.load(open(OUT_PATH, encoding="utf-8"))
            seen = {(r["owner"], r["repo"], r["skill"]) for r in out}
            offset = int(open(STATE_PATH, encoding="utf-8").read().strip())
            print(f"Resuming from offset {offset} ({len(out)} records already saved)")
        except Exception:
            out, seen, offset = [], set(), 0

    def save(final=False):
        json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False)
        if final and os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)  # complete — no resume needed
        else:
            open(STATE_PATH, "w", encoding="utf-8").write(str(offset))

    while True:
        if args.limit and offset >= args.limit:
            break
        length = PAGE
        if args.limit:
            length = min(PAGE, args.limit - offset)
        url = (f"{DS_BASE}/rows?dataset={urllib.parse.quote(DATASET)}"
               f"&config={urllib.parse.quote(config)}&split={urllib.parse.quote(split)}"
               f"&offset={offset}&length={length}")
        try:
            data = fetch_json(url)
        except Exception as e:
            print(f"  page @{offset} failed: {e} — progress saved, re-run to resume")
            save()
            return
        rows = data.get("rows", [])
        if not rows:
            break
        for entry in rows:
            row = entry.get("row", {})
            code = row.get("code", "")
            skill_name = row.get("skill_name", "")
            owner, repo, skill = parse_owner_repo_skill(code, skill_name)
            if not (owner and repo and skill):
                continue
            key = (owner, repo, skill)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "owner": owner, "repo": repo, "skill": skill,
                "name": row.get("name", "") or skill,
                "description": (row.get("description", "") or "").strip(),
                "code": code,
            })  # NOTE: `detail` (full SKILL.md) is intentionally dropped
        offset += len(rows)
        if offset % 2000 == 0 or (args.limit and offset >= args.limit):
            print(f"  {offset} rows scanned, {len(out)} skills kept")
            save()  # checkpoint every ~2000 rows
        time.sleep(PAGE_DELAY)

    save(final=True)
    print(f"Done. Wrote {len(out):,} skill records to {OUT_PATH}")
    print("Now run: python fetch.py   (to merge these descriptions into vault.db)")


if __name__ == "__main__":
    main()
