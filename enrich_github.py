"""
enrich_github.py — Build/refresh github_cache.json with repo metadata for ranking.

Collects every unique GitHub owner/repo referenced by vault items (from the
freshly-fetched sources, NOT the DB, so it also covers brand-new items), then
batch-queries the GitHub GraphQL API (100 repos per query) via the `gh` CLI
for: stargazerCount, pushedAt, description, and existence (null = deleted).

Cache format:  { "owner/repo": {"stars": int, "pushed": "...", "desc": "...",
                                 "exists": bool, "checked": "YYYY-MM-DD"} }

Incremental by default: repos checked within --refresh-days (7) are skipped.

Usage:
  python enrich_github.py                 # incremental (new + stale repos)
  python enrich_github.py --refresh-days 0   # refresh everything
  python enrich_github.py --limit 500     # test on first 500 repos
Auth: uses `gh` CLI auth locally, or GH_TOKEN env var (GitHub Actions).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

import fetch as vault_fetch  # reuse adapters + gh_repo()

CACHE_PATH = os.path.join(os.path.dirname(__file__), "github_cache.json")
BATCH = 100


def find_gh():
    exe = shutil.which("gh")
    if exe:
        return exe
    for p in (r"C:\Program Files\GitHub CLI\gh.exe",):
        if os.path.exists(p):
            return p
    sys.exit("gh CLI not found — install GitHub CLI and run `gh auth login`.")


def collect_repos():
    """Collect unique owner/repo from vault.db (fast). New repos added by the
    next fetch are enriched on the following enrich run — fine on a daily cycle."""
    import sqlite3
    db = os.path.join(os.path.dirname(__file__), "vault.db")
    if not os.path.exists(db):
        sys.exit("vault.db not found — run `python fetch.py` first.")
    print("Collecting repos from vault.db...")
    con = sqlite3.connect(db)
    repos = set()
    for ext, prim, extra_json in con.execute(
            "SELECT external_url, primary_url, extra FROM items"):
        extra = json.loads(extra_json) if extra_json else {}
        for url in (extra.get("github_url", ""), ext or "", prim or ""):
            r = vault_fetch.gh_repo(url)
            if r:
                repos.add(r)
                break
        else:
            owner, repo = extra.get("owner"), extra.get("repo")
            if owner and repo:
                repos.add(f"{str(owner).lower()}/{str(repo).lower()}")
    con.close()
    print(f"  {len(repos):,} unique repos referenced")
    return repos


SAFE = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


def gql_batch(gh, repos):
    """One GraphQL query for up to 100 repos. Returns {repo: record}."""
    parts = []
    for i, r in enumerate(repos):
        owner, name = r.split("/", 1)
        parts.append(
            f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
            "{ stargazerCount pushedAt description }")
    query = "query { " + " ".join(parts) + " }"
    proc = subprocess.run(
        [gh, "api", "graphql", "-f", f"query={query}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    today = datetime.date.today().isoformat()
    out = {}
    raw = proc.stdout or ""
    try:
        data = json.loads(raw).get("data") or {}
    except Exception:
        # whole batch failed (auth/network) — caller decides
        raise RuntimeError((proc.stderr or raw)[:300])
    for i, r in enumerate(repos):
        node = data.get(f"r{i}")
        if node:
            out[r] = {"stars": node.get("stargazerCount", 0),
                      "pushed": node.get("pushedAt", ""),
                      "desc": (node.get("description") or "").strip(),
                      "exists": True, "checked": today}
        else:
            out[r] = {"stars": 0, "pushed": "", "desc": "",
                      "exists": False, "checked": today}
    return out


def main():
    ap = argparse.ArgumentParser(description="GitHub metadata enrichment for the AI Vault")
    ap.add_argument("--refresh-days", type=int, default=7,
                    help="Re-check cached repos older than N days (default 7; 0 = all)")
    ap.add_argument("--limit", type=int, default=0, help="Only process first N repos (test)")
    args = ap.parse_args()

    gh = find_gh()
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
            print(f"Loaded cache: {len(cache):,} repos")
        except Exception:
            cache = {}

    repos = sorted(r for r in collect_repos() if SAFE.match(r))
    cutoff = (datetime.date.today() - datetime.timedelta(days=args.refresh_days)).isoformat()
    todo = [r for r in repos
            if r not in cache or (cache[r].get("checked", "") <= cutoff)]
    if args.limit:
        todo = todo[:args.limit]
    print(f"To query: {len(todo):,} repos ({len(repos) - len(todo):,} fresh in cache)")

    done = 0
    failures = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        try:
            cache.update(gql_batch(gh, chunk))
            done += len(chunk)
            failures = 0
        except RuntimeError as e:
            failures += 1
            print(f"  batch @{i} failed: {e}")
            if failures >= 3:
                print("  3 consecutive failures — saving progress and stopping.")
                break
            time.sleep(30)
            continue
        if done % 2000 < BATCH:
            json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"))
            print(f"  {done:,}/{len(todo):,} queried (checkpoint)")
        time.sleep(0.5)  # stay polite

    json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"))
    alive = sum(1 for v in cache.values() if v.get("exists"))
    print(f"Done. Cache: {len(cache):,} repos ({alive:,} exist, {len(cache) - alive:,} dead)")


if __name__ == "__main__":
    main()
