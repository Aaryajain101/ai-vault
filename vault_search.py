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
import webbrowser

DB_PATH = os.path.join(os.path.dirname(__file__), "vault.db")
USAGE_PATH = os.path.join(os.path.dirname(__file__), "usage_log.log")
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


def get_db():
    if not os.path.exists(DB_PATH):
        print("vault.db not found. Run: python fetch.py")
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def search(query, category=None, limit=10):
    con = get_db()
    cur = con.cursor()
    if category:
        cur.execute(
            """
            SELECT i.category, i.slug, i.name, i.description, i.primary_url, i.extra
            FROM items_fts f JOIN items i ON f.rowid = i.id
            WHERE items_fts MATCH ? AND i.category = ?
            ORDER BY rank LIMIT ?
            """,
            (query, category, limit),
        )
    else:
        cur.execute(
            """
            SELECT i.category, i.slug, i.name, i.description, i.primary_url, i.extra
            FROM items_fts f JOIN items i ON f.rowid = i.id
            WHERE items_fts MATCH ?
            ORDER BY rank LIMIT ?
            """,
            (query, limit),
        )
    rows = cur.fetchall()
    con.close()
    detail = f'"{query}"' + (f" --cat {category}" if category else "")
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
    con.close()
    print(f"\n{'Category':<15} {'Count':>7}")
    print("-" * 24)
    for cat, count in rows:
        print(f"  {cat:<13} {count:>7,}")
    print("-" * 24)
    print(f"  {'TOTAL':<13} {total:>7,}\n")


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
    for cat, slug, name, desc, url, extra_json in rows:
        extra = json.loads(extra_json) if extra_json else {}
        stars = extra.get("stars", "")
        stars_str = f"  ★{stars:,}" if isinstance(stars, int) and stars else ""
        print(f"  [{cat}] {name}{stars_str}")
        print(f"    slug: {slug}")
        if desc:
            print(f"    {desc[:100]}")
        print()


def install(slug):
    row = get_item(slug)
    if not row:
        print(f"Slug not found: {slug}")
        sys.exit(1)

    _, category, slug_val, name, desc, primary_url, external_url, extra_json = row
    extra = json.loads(extra_json) if extra_json else {}

    print(f"\nInstalling: {name}  [{category}]")
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
    _, category, slug_val, name, desc, primary_url, external_url, extra_json = row
    extra = json.loads(extra_json) if extra_json else {}
    print(f"\n{'='*50}")
    print(f"  {name}  [{category}]")
    print(f"{'='*50}")
    print(f"  slug:     {slug_val}")
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
    parser.add_argument("--install", metavar="SLUG", help="Install item by slug")
    parser.add_argument("--get", metavar="SLUG", help="Show full details for a slug")
    parser.add_argument("--collections", action="store_true", help="List all collections")
    parser.add_argument("--stats", action="store_true", help="Show item counts by category")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default 10)")
    args = parser.parse_args()

    if args.stats:
        stats()
    elif args.collections:
        list_collections()
    elif args.install:
        install(args.install)
    elif args.get:
        show_item(args.get)
    elif args.query:
        results = search(args.query, category=args.cat, limit=args.limit)
        print_results(results)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
