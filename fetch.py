"""
fetch.py — Multi-source AI Vault builder (SQLite + FTS5)
Run: python fetch.py

Sources (priority order — earlier wins on dedup, keeps its slugs):
  levelup       leveluplearning.in            base, all 6 categories
  mcp-registry  registry.modelcontextprotocol.io/v0/servers   mcp_server
  openrouter    openrouter.ai/api/v1/models   llm
  awesome-mcp   punkpeye/awesome-mcp-servers  mcp_server
  awesome-agents e2b-dev/awesome-ai-agents     agent
  awesome-design VoltAgent/awesome-design-md   design
  skills.sh     public sitemaps (+ skills_sh_hf.json cache)   skill

Each adapter is fault-isolated: a failing source is logged and skipped.
Duplicates across sources are collapsed by a canonical identity key;
leveluplearning is canonical and its slugs are preserved.
"""
import json
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
import os
import re
import gzip
import time
import datetime

LEVELUP_BASE = "https://www.leveluplearning.in/aivault/data/ai-resources"
LEVELUP_CATEGORIES = ["skill", "mcp_server", "tool", "llm", "agent", "design"]

DB_PATH = os.path.join(os.path.dirname(__file__), "vault.db")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "update_history.log")
HF_CACHE_PATH = os.path.join(os.path.dirname(__file__), "skills_sh_hf.json")

# Dedup priority (first = canonical) and slug-collision suffixes.
SOURCE_ORDER = ["levelup", "mcp-registry", "openrouter", "awesome-mcp",
                "awesome-agents", "awesome-design", "skills.sh"]
SOURCE_SUFFIX = {"levelup": "lvl", "mcp-registry": "mcpreg", "openrouter": "or",
                 "awesome-mcp": "amcp", "awesome-agents": "aagent",
                 "awesome-design": "adesign", "skills.sh": "sh"}


# ---------------------------------------------------------------- HTTP helpers
def fetch_bytes(url, timeout=60, retries=3):
    """GET with retries — DNS on some networks is intermittent (getaddrinfo 11001)."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                return data
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(4 * (attempt + 1))
    raise last


def fetch_json(url, timeout=60):
    return json.loads(fetch_bytes(url, timeout).decode("utf-8", "replace"))


def fetch_text(url, timeout=60):
    return fetch_bytes(url, timeout).decode("utf-8", "replace")


# ---------------------------------------------------------------- identity helpers
def slugify(s):
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "item"


def gh_repo(url):
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", url or "")
    if not m:
        return None
    owner, repo = m.group(1).lower(), m.group(2).lower()
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"{owner}/{repo}"


def canon_key(item):
    """Canonical cross-source identity for dedup."""
    cat = item["category"]
    extra = item.get("extra", {}) or {}
    name = item.get("name", "")
    if cat == "skill":
        owner, repo = extra.get("owner"), extra.get("repo")
        sk = extra.get("skill_name") or name
        if owner and repo:
            return f"skill::{str(owner).lower()}/{str(repo).lower()}/{slugify(sk)}"
        r = gh_repo(item.get("external_url") or extra.get("github_url", ""))
        if r:
            return f"skill::{r}/{slugify(sk)}"
        return f"skill::{slugify(name)}"
    if cat == "mcp_server":
        r = gh_repo(item.get("external_url") or extra.get("github_url", "")
                    or item.get("primary_url", ""))
        return f"mcp::{r}" if r else f"mcp::{slugify(name)}"
    if cat == "llm":
        mid = extra.get("model_id") or name
        return f"llm::{slugify(str(mid).split('/')[-1])}"
    r = gh_repo(item.get("external_url") or extra.get("github_url", ""))
    return f"{cat}::{r}" if r else f"{cat}::{slugify(name)}"


def rec(category, slug, name, description, primary_url, external_url, extra, source):
    return {"category": category, "slug": slug, "name": name or "",
            "description": description or "", "primary_url": primary_url or "",
            "external_url": external_url or "", "extra": extra or {}, "source": source}


# ---------------------------------------------------------------- adapters
def fetch_levelup():
    """Base source. Returns (items, collections)."""
    items, collections = [], []
    for cat in LEVELUP_CATEGORIES:
        try:
            data = fetch_json(f"{LEVELUP_BASE}/{cat}.json")
            for it in data:
                items.append(rec(
                    it.get("category", cat), it.get("slug", ""), it.get("name", ""),
                    it.get("description", ""), it.get("primary_url", ""),
                    it.get("external_url", ""), it.get("extra", {}) or {}, "levelup"))
            print(f"  levelup/{cat}: {len(data)}")
        except urllib.error.HTTPError as e:
            print(f"  levelup/{cat}: skipped ({e.code})")
        except Exception as e:
            print(f"  levelup/{cat}: error — {e}")
    try:
        collections = fetch_json(f"{LEVELUP_BASE}/collections.json")
    except Exception as e:
        print(f"  levelup/collections: error — {e}")
    return items, collections


def fetch_mcp_registry(maxpages=800):
    out, cursor = [], None
    base = "https://registry.modelcontextprotocol.io/v0/servers"
    for _ in range(maxpages):
        url = base + "?limit=100" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        data = fetch_json(url)
        servers = data.get("servers", [])
        for s in servers:
            srv = s.get("server", s)
            repo = srv.get("repository") or {}
            name = srv.get("title") or srv.get("name", "")
            repo_url = repo.get("url", "")
            out.append(rec(
                "mcp_server", f"mcp_server/{slugify(name)}", name,
                srv.get("description", ""), repo_url, repo_url,
                {"registry_name": srv.get("name", ""), "version": srv.get("version", ""),
                 "github_url": repo_url}, "mcp-registry"))
        cursor = (data.get("metadata") or {}).get("nextCursor")
        if not cursor or not servers:
            break
    return out


def fetch_openrouter():
    data = fetch_json("https://openrouter.ai/api/v1/models")
    out = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        pricing = m.get("pricing", {}) or {}
        out.append(rec(
            "llm", f"llm/{slugify(mid)}", m.get("name") or mid, m.get("description", ""),
            f"https://openrouter.ai/{mid}", "",
            {"model_id": mid, "context_length": m.get("context_length"),
             "price_prompt": pricing.get("prompt"), "price_completion": pricing.get("completion")},
            "openrouter"))
    return out


def _clean_md(s):
    s = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", s)  # [![alt](img)](link)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)               # ![alt](img)
    return s.strip()


def fetch_awesome_md(raw_url, category, source, mode="bullet"):
    text = fetch_text(raw_url)
    lines = text.split("\n")
    out, seen = [], set()

    def emit(name, url, desc):
        name = name.replace("**", "").replace("`", "").strip()
        if not url.startswith("http") or url in seen:
            return
        seen.add(url)
        extra = {}
        r = gh_repo(url)
        if r:
            extra["github_url"] = url
        out.append(rec(category, f"{category}/{slugify(name)}", name,
                       desc.strip(), url, url, extra, source))

    if mode == "heading":
        for i, line in enumerate(lines):
            m = re.match(r"^##\s+\[(.+?)\]\((https?://[^)]+)\)", line)
            if not m:
                continue
            desc = ""
            for j in range(i + 1, min(i + 6, len(lines))):
                t = lines[j].strip()
                if not t:
                    continue
                if t.startswith("#") or t.startswith("<"):
                    break
                desc = t
                break
            emit(m.group(1), m.group(2), desc)
    else:  # bullet
        for line in lines:
            m = re.match(r"^\s*[-*]\s+\[(.+?)\]\((https?://[^)]+)\)(.*)$", line)
            if not m:
                continue
            rest = _clean_md(m.group(3))
            if " - " in rest:
                desc = rest.split(" - ", 1)[1]
            elif " — " in rest:
                desc = rest.split(" — ", 1)[1]
            else:
                desc = re.sub(r"^[\W_]+", "", rest)
            emit(m.group(1), m.group(2), desc)
    return out


def fetch_skills_sh():
    """Live sitemap enumeration, enriched by the one-time HF cache if present."""
    # HF cache: {owner, repo, skill, description}
    hf = {}
    if os.path.exists(HF_CACHE_PATH):
        try:
            for r in json.load(open(HF_CACHE_PATH, encoding="utf-8")):
                hf[(r["owner"], r["repo"], r["skill"])] = r
            print(f"  skills.sh: HF cache {len(hf)} records")
        except Exception as e:
            print(f"  skills.sh: HF cache unreadable — {e}")

    def make(owner, repo, skill, desc, url):
        # HF mirror rows sometimes carry shell quotes around the skill token.
        owner, repo, skill = (s.strip("'\"") for s in (owner, repo, skill))
        return rec("skill", f"skill/{slugify(skill)}", skill, desc, url,
                   f"https://github.com/{owner}/{repo}",
                   {"owner": owner, "repo": repo, "skill_name": skill,
                    "install_command": f"npx skills add https://github.com/{owner}/{repo} --skill {skill}"},
                   "skills.sh")

    out, seen = [], set()
    try:
        idx = fetch_text("https://www.skills.sh/sitemap.xml")
        submaps = [u for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", idx) if "skills" in u]
        for sm in submaps:
            try:
                xml = fetch_text(sm)
            except Exception as e:
                print(f"  skills.sh: submap error {sm} — {e}")
                continue
            for loc in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml):
                parts = [p for p in loc.split("skills.sh/", 1)[-1].split("/") if p]
                if len(parts) != 3:
                    continue
                owner, repo, skill = parts
                key = (owner, repo, skill)
                if key in seen:
                    continue
                seen.add(key)
                desc = hf.get(key, {}).get("description", "")
                out.append(make(owner, repo, skill, desc, loc))
        print(f"  skills.sh: sitemap {len(out)} skills")
    except Exception as e:
        print(f"  skills.sh: sitemap error — {e}")

    # HF-only records not present in the live sitemap
    extra_hf = 0
    for (owner, repo, skill), r in hf.items():
        if (owner, repo, skill) in seen:
            continue
        out.append(make(owner, repo, skill, r.get("description", ""),
                        f"https://www.skills.sh/{owner}/{repo}/{skill}"))
        extra_hf += 1
    if extra_hf:
        print(f"  skills.sh: +{extra_hf} HF-only skills")
    return out


# ---------------------------------------------------------------- quality pass
GITHUB_CACHE_PATH = os.path.join(os.path.dirname(__file__), "github_cache.json")
CANONICAL_OWNERS = {"anthropics", "vercel-labs", "obra", "modelcontextprotocol",
                    "e2b-dev", "punkpeye", "voltagent", "microsoft", "google",
                    "openai", "github", "supabase", "cloudflare", "aws"}
SOURCE_WEIGHT = {"levelup": 2.0, "mcp-registry": 2.0, "openrouter": 2.0,
                 "awesome-mcp": 1.5, "awesome-agents": 1.5, "awesome-design": 1.5,
                 "skills.sh": 1.0}

_JUNK_NAME = re.compile(r"^[\W\d_]*$")


def item_repo(item):
    """owner/repo for an item, or None."""
    extra = item.get("extra", {}) or {}
    for url in (extra.get("github_url", ""), item.get("external_url", ""),
                item.get("primary_url", "")):
        r = gh_repo(url)
        if r:
            return r
    owner, repo = extra.get("owner"), extra.get("repo")
    if owner and repo:
        return f"{str(owner).lower()}/{str(repo).lower()}"
    return None


def score_item(item):
    """Usefulness score 0-10: authority + popularity + liveness + completeness."""
    extra = item.get("extra", {}) or {}
    s = SOURCE_WEIGHT.get(item["source"], 1.0)
    import math
    stars = item.get("stars", 0) or 0
    s += min(4.0, math.log10(stars + 1) * 0.8)          # 100k stars -> +4
    if item.get("description"):
        s += 1.0
    if extra.get("install_command"):
        s += 1.0
    pushed = item.get("pushed", "") or ""
    if pushed:
        try:
            days = (datetime.datetime.now(datetime.timezone.utc)
                    - datetime.datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
            s += 1.0 if days <= 180 else (0.5 if days <= 730 else 0.0)
        except Exception:
            pass
    r = item_repo(item)
    if r and r.split("/")[0] in CANONICAL_OWNERS:
        s += 1.0
    return round(min(s, 10.0), 2)


def quality_pass(kept):
    """Enrich from github_cache.json, prune junk, score. Returns (items, stats)."""
    gcache = {}
    if os.path.exists(GITHUB_CACHE_PATH):
        try:
            gcache = json.load(open(GITHUB_CACHE_PATH, encoding="utf-8"))
        except Exception:
            gcache = {}

    stats = {"enriched": 0, "desc_backfilled": 0, "dead_repo": 0,
             "clones": 0, "junk_name": 0, "thin": 0, "cache_repos": len(gcache)}

    # 1. enrich + 2. drop dead repos
    # NOTE: clustering (step 3) must use the ORIGINAL description — repo-desc
    # backfill would make identical forks look distinct (each repo has its own
    # description) and let clones slip through.
    alive = []
    for it in kept:
        it["_orig_desc"] = it["description"]
        r = item_repo(it)
        meta = gcache.get(r) if r else None
        if meta is not None:
            if not meta.get("exists", True):
                stats["dead_repo"] += 1
                continue
            old = (it.get("extra", {}) or {}).get("stars")
            it["stars"] = max(meta.get("stars", 0),
                              old if isinstance(old, int) else 0)
            it["pushed"] = meta.get("pushed", "")
            stats["enriched"] += 1
            if not it["description"] and meta.get("desc"):
                it["description"] = meta["desc"]
                stats["desc_backfilled"] += 1
        else:
            old = (it.get("extra", {}) or {}).get("stars")
            it["stars"] = old if isinstance(old, int) else 0
            it["pushed"] = ""
        alive.append(it)

    # 3. collapse exact clones (same lowercased name + same ORIGINAL description)
    def keep_rank(it):
        r = item_repo(it) or ""
        return (1 if r.split("/")[0] in CANONICAL_OWNERS else 0,
                it.get("stars", 0),
                1 if it["source"] == "levelup" else 0)
    clusters = {}
    for it in alive:
        key = (it["name"].lower(), it["_orig_desc"]) if it["_orig_desc"] else None
        clusters.setdefault(key, []).append(it)
    survivors = []
    for key, group in clusters.items():
        if key is None or len(group) == 1:
            survivors.extend(group)
            continue
        group.sort(key=keep_rank, reverse=True)
        group[0]["extra"]["clone_count"] = len(group) - 1
        survivors.append(group[0])
        stats["clones"] += len(group) - 1

    # 4. junk names  +  5. hopeless thin entries
    described_names = {it["name"].lower() for it in survivors if it["description"]}
    final = []
    for it in survivors:
        if len(it["name"]) < 3 or _JUNK_NAME.match(it["name"]):
            stats["junk_name"] += 1
            continue
        if (not it["description"] and it.get("stars", 0) == 0
                and it["name"].lower() in described_names):
            stats["thin"] += 1
            continue
        final.append(it)

    # 6. score
    for it in final:
        it.pop("_orig_desc", None)
        it["score"] = score_item(it)
    return final, stats


# ---------------------------------------------------------------- merge / dedup
def merge(source_lists):
    """source_lists: dict source -> [records]. Returns (kept, per_source, dup_counts)."""
    seen, used_slugs, kept = {}, set(), []
    per_source = {s: 0 for s in source_lists}
    dup_counts = {s: 0 for s in source_lists}

    for source in SOURCE_ORDER:
        for item in source_lists.get(source, []):
            key = canon_key(item)
            if key in seen:
                canonical = seen[key]
                also = set(canonical["extra"].get("also_on", []))
                also.add(item["source"])
                canonical["extra"]["also_on"] = sorted(also)
                dup_counts[source] += 1
                continue
            slug = item["slug"]
            if slug in used_slugs:
                suf = SOURCE_SUFFIX.get(source, source)
                base, n = slug, 2
                slug = f"{base}-{suf}"
                while slug in used_slugs:
                    slug = f"{base}-{suf}{n}"
                    n += 1
                item["slug"] = slug
            used_slugs.add(slug)
            seen[key] = item
            kept.append(item)
            per_source[source] += 1
    return kept, per_source, dup_counts


# ---------------------------------------------------------------- persistence
def read_snapshot(db_path):
    if not os.path.exists(db_path):
        return None
    try:
        con = sqlite3.connect(db_path)
        rows = con.execute("SELECT slug, name, category FROM items").fetchall()
        con.close()
        return {r[0]: (r[1], r[2]) for r in rows}
    except Exception:
        return None


def build_db(items, collections):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            primary_url TEXT,
            external_url TEXT,
            extra TEXT,
            source TEXT DEFAULT 'levelup',
            stars INTEGER DEFAULT 0,
            pushed TEXT DEFAULT '',
            score REAL DEFAULT 0
        );
        CREATE INDEX idx_items_category ON items(category);
        CREATE INDEX idx_items_source ON items(source);
        CREATE INDEX idx_items_stars ON items(stars DESC);
        CREATE TABLE collections (
            id INTEGER PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            blurb TEXT,
            icon TEXT
        );
        CREATE TABLE collection_items (
            collection_id INTEGER REFERENCES collections(id),
            item_slug TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE items_fts USING fts5(
            name, description, category, slug,
            content=items, content_rowid=id
        );
    """)
    for it in items:
        cur.execute(
            "INSERT OR IGNORE INTO items (category, slug, name, description, primary_url, external_url, extra, source, stars, pushed, score) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (it["category"], it["slug"], it["name"], it["description"],
             it["primary_url"], it["external_url"], json.dumps(it["extra"]), it["source"],
             it.get("stars", 0), it.get("pushed", ""), it.get("score", 0)))
    cur.execute("INSERT INTO items_fts(items_fts) VALUES('rebuild')")
    for col in collections:
        cur.execute("INSERT OR IGNORE INTO collections (slug, title, blurb, icon) VALUES (?,?,?,?)",
                    (col["slug"], col["title"], col.get("blurb", ""), col.get("icon", "")))
        col_id = cur.lastrowid
        for it in col.get("items", []):
            cur.execute("INSERT INTO collection_items (collection_id, item_slug) VALUES (?,?)",
                        (col_id, it["slug"]))
    con.commit()
    con.close()
    return len(items)


def write_history(old_snap, kept, per_cat, per_source, dup_counts, ok=True, error="", qstats=None):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"===== {now} ====="]
    if not ok:
        lines += [f"FAILED  {error}", "  (database left unchanged)", ""]
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return
    new_snap = {it["slug"]: (it["name"], it["category"]) for it in kept}
    lines.append(f"SUCCESS  total={len(new_snap):,}   "
                 + "  ".join(f"{k}={v}" for k, v in per_cat.items()))
    lines.append("  sources: " + "  ".join(f"{s}={per_source.get(s, 0)}" for s in SOURCE_ORDER))
    if qstats:
        lines.append(f"  quality: enriched={qstats['enriched']:,} desc-backfilled={qstats['desc_backfilled']:,}"
                     f" | pruned dead={qstats['dead_repo']:,} clones={qstats['clones']:,}"
                     f" junk={qstats['junk_name']:,} thin={qstats['thin']:,}")
    dups = "  ".join(f"{s}={dup_counts.get(s, 0)}" for s in SOURCE_ORDER if dup_counts.get(s))
    if dups:
        lines.append("  dup-skipped: " + dups)
    if old_snap is None:
        lines.append("  initial build — no prior snapshot to diff")
    else:
        old_keys, new_keys = set(old_snap), set(new_snap)
        added, removed = sorted(new_keys - old_keys), sorted(old_keys - new_keys)
        if not added and not removed:
            lines.append("  no changes since last update")
        else:
            lines.append(f"  CHANGES: +{len(added)} added, -{len(removed)} removed")
            for s in added[:100]:
                nm, cat = new_snap[s]
                lines.append(f"    + [{cat}] {nm}  ({s})")
            if len(added) > 100:
                lines.append(f"    ... and {len(added) - 100} more added")
            for s in removed[:100]:
                nm, cat = old_snap[s]
                lines.append(f"    - [{cat}] {nm}  ({s})")
            if len(removed) > 100:
                lines.append(f"    ... and {len(removed) - 100} more removed")
    lines.append("")
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- main
def main():
    print("Fetching sources...")
    levelup_items, collections = fetch_levelup()

    # Base-source guard: never wipe the DB if leveluplearning failed.
    if not levelup_items:
        print("Base source (levelup) returned 0 items — keeping existing DB.")
        write_history(None, [], {}, {}, {}, ok=False, error="base source levelup empty")
        return

    source_lists = {"levelup": levelup_items}
    adapters = [
        ("mcp-registry", fetch_mcp_registry),
        ("openrouter", fetch_openrouter),
        ("awesome-mcp", lambda: fetch_awesome_md(
            "https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md",
            "mcp_server", "awesome-mcp", "bullet")),
        ("awesome-agents", lambda: fetch_awesome_md(
            "https://raw.githubusercontent.com/e2b-dev/awesome-ai-agents/main/README.md",
            "agent", "awesome-agents", "heading")),
        ("awesome-design", lambda: fetch_awesome_md(
            "https://raw.githubusercontent.com/VoltAgent/awesome-design-md/main/README.md",
            "design", "awesome-design", "bullet")),
        ("skills.sh", fetch_skills_sh),
    ]
    for name, fn in adapters:
        try:
            got = fn()
            source_lists[name] = got
            print(f"  {name}: {len(got)} items")
        except Exception as e:
            source_lists[name] = []
            print(f"  {name}: error — {e}")

    kept, per_source, dup_counts = merge(source_lists)

    print("Quality pass (enrich / prune / score)...")
    kept, qstats = quality_pass(kept)
    print(f"  cache={qstats['cache_repos']:,} repos  enriched={qstats['enriched']:,}"
          f"  desc-backfilled={qstats['desc_backfilled']:,}")
    print(f"  pruned: dead-repo={qstats['dead_repo']:,}  clones={qstats['clones']:,}"
          f"  junk-name={qstats['junk_name']:,}  thin={qstats['thin']:,}")

    per_cat, per_source = {}, {}
    for it in kept:
        per_cat[it["category"]] = per_cat.get(it["category"], 0) + 1
        per_source[it["source"]] = per_source.get(it["source"], 0) + 1

    old_snap = read_snapshot(DB_PATH)
    print("Building vault.db...")
    total = build_db(kept, collections)
    print(f"Done. {total:,} items indexed in {DB_PATH}")
    print("  per source: " + ", ".join(f"{s}={per_source.get(s,0)}" for s in SOURCE_ORDER))
    write_history(old_snap, kept, per_cat, per_source, dup_counts, ok=True, qstats=qstats)
    print(f"History appended to {HISTORY_PATH}")


if __name__ == "__main__":
    main()
