# AI Vault

## What this is
A local, searchable index (SQLite + FTS5, `vault.db`) of AI resources — skills, MCP servers, tools, LLMs, agents, design assets — aggregated from **multiple upstream sources** and merged into one deduplicated catalog. Supports one-click install into Claude Code.

See also the user memory `ai-vault-search.md` for prior session context, and `SOURCES.md` for the full source list, endpoints, and dedup rules.

## Sources (see SOURCES.md for details)
Merged in priority order (earlier wins on dedup): `levelup` (base, all 6 categories) → `mcp-registry` → `openrouter` → `awesome-mcp` → `awesome-agents` → `awesome-design` → `skills.sh`. Every item carries a `source` column; cross-source duplicates are collapsed by a canonical identity key.

## Usage

> **Python invocation:** call scripts with the full interpreter path
> `C:\Users\aarya\AppData\Local\Python\pythoncore-3.14-64\python.exe` — a bare `python`
> (especially via the Bash tool) resolves to the disabled Windows Store alias and fails
> with "Python was not found". Don't pipe stderr to null while debugging, or failures
> look like empty results. (`python` below is shorthand for that full path.)

```
python vault_search.py "<query>"                    # full-text search
python vault_search.py "<query>" --cat tool          # filter by category (skill|mcp_server|tool|llm|agent|design)
python vault_search.py "<query>" --source skills.sh  # filter by provenance
python vault_search.py "<query>" --limit 20           # result count (default 10; it is --limit, NOT --n)
python vault_search.py "<query>" --min-stars 100 --sort stars   # quality-filter / rank by GitHub stars
python vault_search.py --install <slug>              # auto-runs `npx skills add` / `claude mcp add`, else opens URL
python vault_search.py --get <slug>                   # full item details (incl. source)
python vault_search.py --stats                        # counts by category AND by source
python vault_search.py --collections                  # list curated collections
```

## Refreshing the index
```
python fetch.py            # re-fetch ALL sources, dedup/merge, rebuild vault.db
python import_hf_skills.py # ONE-TIME: download skills.sh HF mirror -> skills_sh_hf.json (rich descriptions)
```
`fetch.py` reads `skills_sh_hf.json` (if present) to enrich skills.sh entries with descriptions. `import_hf_skills.py` is heavy — run once, re-run only to refresh the skills.sh snapshot.

`update.cmd` runs `fetch.py` and appends to `update.log`. The **Windows Task Scheduler** job "AI Vault Daily Update" (6 AM) triggers it — this is the sole updater. A cloud routine was considered but can't write the local DB, so it was not used.

## Logs
- `update_history.log` — per-run: total, per-category, **per-source**, dup-skips, and added/removed diff.
- `usage_log.log` — SEARCH / GET / INSTALL activity via `vault_search.py`.
