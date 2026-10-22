"""
vault_search.py — Search and install items from the AI Vault
Usage:
  python vault_search.py <query>                      # search all categories
  python vault_search.py <query> --cat skill          # filter by category
  python vault_search.py --install skill/oracle       # install by slug
  python vault_search.py --get skill/oracle           # show full details
  python vault_search.py --collections                # list collections
  python vault_search.py --stats                      # show counts by category
"""
import argparse
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
import webbrowser

DB_PATH = os.path.join(os.path.dirname(__file__), "vault.db")
USAGE_PATH = os.path.join(os.path.dirname(__file__), "usage_log.log")
# Pull mode since 22 Oct 2026: vault.db is built in the cloud (build-vault.yml) and published to
# the rolling "latest" release; update.cmd downloads it. These drive the once-a-day check below.
RELEASE_API = "https://api.github.com/repos/Aaryajain101/ai-vault/releases/tags/latest"
PULL_STAMP = os.path.join(os.path.dirname(__file__), ".last_pull")
UPDATE_CMD = os.path.join(os.path.dirname(__file__), "update.cmd")
PULL_INTERVAL_H = 20
CLAUDE_SETTINGS = os.path.expanduser(r"~\.claude\settings.json")


def log_usage(action, detail, result=""):
    """Append one line to usage_log.log recording use of the vault."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{now}  {action:<8} {detail}"
    if result:
        line += f"   -> {result}"
    try:
        with open(USAGE_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def maybe_refresh():
    """Once a day on first use: ask GitHub when the cloud-built vault.db in the 'latest' release
    was last updated; if it is newer than the local file, start update.cmd detached so the
    download (about 67 MB, a minute) runs in the background while this call uses the current
    copy. Silent when offline. VAULT_NO_PULL=1 skips. update.cmd also writes the stamp, so a
    search right after the 13:30 task does not ask again."""
    if os.environ.get("VAULT_NO_PULL") or os.name != "nt" or not os.path.exists(UPDATE_CMD):
        return
    try:
        if os.path.exists(PULL_STAMP) and time.time() - os.path.getmtime(PULL_STAMP) < PULL_INTERVAL_H * 3600:
            return
        with open(PULL_STAMP, "w", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n")
        req = urllib.request.Request(
            RELEASE_API, headers={"User-Agent": "ai-vault-search/1.0", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            release = json.load(r)
        asset = next((a for a in release.get("assets", []) if a.get("name") == "vault.db"), None)
        if not asset:
            return
        remote = datetime.datetime.strptime(asset["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
        remote = remote.replace(tzinfo=datetime.timezone.utc).timestamp()
        local = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0
        if remote > local:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen(
                ["cmd", "/c", UPDATE_CMD], creationflags=flags, close_fds=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            log_usage("PULL", "newer cloud build found; update.cmd started in the background")
            print("(AI Vault: a newer cloud build exists; vault.db is refreshing in the background, about a minute)",
                  file=sys.stderr)
    except Exception:
        pass


def get_db():
    if not os.path.exists(DB_PATH):
        print("vault.db not found. Run update.cmd (downloads the cloud build) or: python fetch.py")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def search(query, category=None, limit=10, source=None, min_stars=0, sort=None):
    con = get_db()
    cur = con.cursor()
    # Quote each token so FTS5 operators (- : * etc.) in plain queries don't error.
    fts_query = " ".join('"' + t.replace('"', "") + '"' for t in query.split())
    where = ["items_fts MATCH ?"]
    params = [fts_query]
    if category:
        where.append("i.category = ?")
        params.append(category)
    if source:
        where.append("i.source = ?")
        params.append(source)
    if min_stars:
        where.append("i.stars >= ?")
        params.append(min_stars)
    # Default ranking blends FTS relevance with the 0-10 usefulness score.
    # bm25 columns are weighted (name 10, desc 2, category 1, slug 5) so that
    # description-less forks can't win on shorter-document statistics, and the
    # 1.5x score term lets official/starred originals outrank clones.
    order = ("i.stars DESC" if sort == "stars"
             else "(bm25(items_fts, 10.0, 2.0, 1.0, 5.0) - i.score * 1.5)")
    params.append(limit)
    cur.execute(
        f"""
        SELECT i.category, i.slug, i.name, i.description, i.primary_url, i.extra,
               i.source, i.stars, i.score
        FROM items_fts f JOIN items i ON f.rowid = i.id
        WHERE {' AND '.join(where)}
        ORDER BY {order} LIMIT ?
        """,
        params,
    )
    rows = cur.fetchall()
    con.close()
    detail = f'"{query}"' + (f" --cat {category}" if category else "") + (f" --source {source}" if source else "")
    log_usage("SEARCH", detail, f"{len(rows)} results")
    return rows


def get_item(slug):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM items WHERE slug = ?", (slug,))
    row = cur.fetchone()
    con.close()
    return row


def stats():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT category, COUNT(*) FROM items GROUP BY category ORDER BY COUNT(*) DESC")
    rows = cur.fetchall()
    total = sum(r[1] for r in rows)
    cur.execute("SELECT source, COUNT(*) FROM items GROUP BY source ORDER BY COUNT(*) DESC")
    src_rows = cur.fetchall()
    con.close()
    print(f"\n{'Category':<15} {'Count':>7}")
    print("-" * 24)
    for cat, count in rows:
        print(f"  {cat:<13} {count:>7,}")
    print("-" * 24)
    print(f"  {'TOTAL':<13} {total:>7,}")
    print(f"\n{'Source':<15} {'Count':>7}")
    print("-" * 24)
    for src, count in src_rows:
        print(f"  {(src or '?'):<13} {count:>7,}")
    con2 = get_db()
    c2 = con2.cursor()
    starred = c2.execute("SELECT COUNT(*) FROM items WHERE stars > 0").fetchone()[0]
    described = c2.execute("SELECT COUNT(*) FROM items WHERE description != ''").fetchone()[0]
    avg_score = c2.execute("SELECT ROUND(AVG(score),2) FROM items").fetchone()[0]
    con2.close()
    print(f"\n  with stars:  {starred:>7,} ({100*starred//max(total,1)}%)")
    print(f"  described:   {described:>7,} ({100*described//max(total,1)}%)")
    print(f"  avg score:   {avg_score}")
    print()


def list_collections():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT icon, title, blurb FROM collections")
    rows = cur.fetchall()
    con.close()
    print()
    for icon, title, blurb in rows:
        print(f"  {icon}  {title}")
        print(f"     {blurb[:80]}")
        print()


def print_results(rows):
    if not rows:
        print("No results found.")
        return
    print()
    for cat, slug, name, desc, url, extra_json, source, stars, score in rows:
        stars_str = f"  ★{stars:,}" if stars else ""
        print(f"  [{cat}] {name}{stars_str}  ({source}, score {score})")
        print(f"    slug: {slug}")
        if desc:
            print(f"    {desc[:100]}")
        print()


def install(slug):
    row = get_item(slug)
    if not row:
        print(f"Slug not found: {slug}")
        sys.exit(1)

    _, category, slug_val, name, desc, primary_url, external_url, extra_json, source, stars, pushed, score = row
    extra = json.loads(extra_json) if extra_json else {}

    print(f"\nInstalling: {name}  [{category}]  (source: {source})")
    print(f"  {desc[:100] if desc else ''}\n")
    log_usage("INSTALL", f"{slug_val}", f"[{category}] {name}")

    if category == "skill":
        # Prefer the catalog's own install_command; fall back to owner/repo form.
        install_cmd = extra.get("install_command", "")
        owner = extra.get("owner", "")
        repo = extra.get("repo", "")
        skill_name = slug_val.split("/")[-1]

        if install_cmd:
            cmd = install_cmd
        elif owner and repo:
            cmd = f"claude skills add {owner}/{repo}/{skill_name}"
        else:
            cmd = ""

        if cmd:
            print(f"  Running: {cmd}")
            result = subprocess.run(cmd, shell=True)
            if result.returncode != 0:
                print(f"\n  Command failed. Manual: {cmd}")
                print(f"  Or open in browser: {primary_url}")
                webbrowser.open(primary_url)
        else:
            print(f"  No install command available. Open: {primary_url}")
            webbrowser.open(primary_url)

    elif category == "mcp_server":
        install_cmd = extra.get("install_command", "")
        github_url = extra.get("github_url", external_url or "")
        server_name = slug_val.split("/")[-1]

        if install_cmd:
            # If the catalog already gives a full `claude mcp add ...`, use it verbatim.
            if install_cmd.strip().startswith("claude mcp"):
                cmd = install_cmd
            else:
                cmd = f'claude mcp add {server_name} -- {install_cmd}'
            print(f"  Running: {cmd}")
            result = subprocess.run(cmd, shell=True)
            if result.returncode != 0:
                print(f"\n  Command failed. Manual install command: {install_cmd}")
        else:
            print(f"  No install_command in catalog. GitHub: {github_url}")
            if github_url:
                webbrowser.open(github_url)

    elif category in ("tool", "agent", "llm", "design"):
        url = primary_url or external_url or extra.get("github_url", "")
        print(f"  Opening: {url}")
        if url:
            webbrowser.open(url)
        else:
            print("  No URL available.")

    print("\nDone.")


def show_item(slug):
    row = get_item(slug)
    if not row:
        print(f"Not found: {slug}")
        log_usage("GET", slug, "not found")
        return
    log_usage("GET", slug)
    _, category, slug_val, name, desc, primary_url, external_url, extra_json, source, stars, pushed, score = row
    extra = json.loads(extra_json) if extra_json else {}
    print(f"\n{'='*50}")
    print(f"  {name}  [{category}]")
    print(f"{'='*50}")
    print(f"  slug:     {slug_val}")
    print(f"  source:   {source}")
    print(f"  stars:    {stars:,}   score: {score}   pushed: {pushed or '?'}")
    print(f"  desc:     {desc}")
    print(f"  url:      {primary_url}")
    if external_url:
        print(f"  external: {external_url}")
    for k, v in extra.items():
        print(f"  {k}: {v}")
    print()


def main():
    parser = argparse.ArgumentParser(description="AI Vault search & install")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--cat", help="Filter by category: skill, mcp_server, tool, llm, agent, design")
    parser.add_argument("--source", help="Filter by source: levelup, skills.sh, mcp-registry, openrouter, awesome-mcp, awesome-agents, awesome-design")
    parser.add_argument("--install", metavar="SLUG", help="Install item by slug")
    parser.add_argument("--get", metavar="SLUG", help="Show full details for a slug")
    parser.add_argument("--collections", action="store_true", help="List all collections")
    parser.add_argument("--stats", action="store_true", help="Show item counts by category")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default 10)")
    parser.add_argument("--min-stars", type=int, default=0, help="Only items with >= N GitHub stars")
    parser.add_argument("--sort", choices=["stars"], help="Sort by stars instead of blended relevance")
    args = parser.parse_args()
    maybe_refresh()

    if args.stats:
        stats()
    elif args.collections:
        list_collections()
    elif args.install:
        install(args.install)
    elif args.get:
        show_item(args.get)
    elif args.query:
        results = search(args.query, category=args.cat, limit=args.limit, source=args.source,
                         min_stars=args.min_stars, sort=args.sort)
        print_results(results)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
