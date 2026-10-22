# AI Vault

## What this is
A local, searchable index (SQLite + FTS5, `vault.db`) of AI resources - skills, MCP servers, tools, LLMs, agents, design assets - aggregated from **multiple upstream sources** and merged into one deduplicated catalog. Supports one-click install into Claude Code.

See also the user memory `ai-vault-search.md` for prior session context, and `SOURCES.md` for the full source list, endpoints, and dedup rules.

## Sources (see SOURCES.md for details)
Merged in priority order (earlier wins on dedup): `levelup` (base, all 6 categories) → `mcp-registry` → `anthropic-skills` → `openrouter` → `models-dev` → `huggingface` → `awesome-mcp` → `smithery` → `awesome-agents` → `awesome-claude-subagents` → `awesome-design` → `skills.sh` (12 sources since 30 Aug 2026). Every item carries a `source` column; cross-source duplicates are collapsed by a canonical identity key. Per-source last-good fetches live in `snapshots/*.json.gz` (gitignored) and are used automatically when a source flakes; a sanity guard aborts any rebuild that would shrink the catalog below 60%.

## Usage

> **Python invocation:** call scripts with the full interpreter path
> `C:\Users\BusinessGovernanceOf\AppData\Local\Programs\Python\Python314\python.exe` - a bare `python`
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
`fetch.py` reads `skills_sh_hf.json` (if present) to enrich skills.sh entries with descriptions. `import_hf_skills.py` is heavy - run once, re-run only to refresh the skills.sh snapshot.

**Pull mode since 22 Oct 2026.** The database is built in the cloud by the GitHub Actions workflow `.github/workflows/build-vault.yml` (daily 00:30 UTC, 25 to 35 min, publishes `vault.db` to the rolling `latest` release) - the same build every other consumer gets. `update.cmd` no longer rebuilds: it runs `pull_release.ps1`, which downloads that `vault.db` to `vault.db.tmp`, checks it (at least 40 MB, at least 10,000 items, never below 60% of the current item count), swaps it in and writes the `.last_pull` stamp. The **Windows Task Scheduler** job "AI Vault Daily Update" (13:30 daily, `run_hidden.vbs` → `update.cmd`, hidden) runs it, and `vault_search.py` also checks the release once a day on first use and starts `update.cmd` in the background when a newer build exists (`VAULT_NO_PULL=1` skips). `fetch.py` remains for a manual local rebuild from the sources. History: until 22 Oct the local task rebuilt from all sources (13:30 since 30 Aug 2026; the earlier 6 AM slot was missed by the sleeping laptop and its catch-up console window kept getting closed, ^C entries in `update.log`, 22-30 Aug).

## Logs
- `update_history.log` - per-run: total, per-category, **per-source**, dup-skips, and added/removed diff.
- `usage_log.log` - SEARCH / GET / INSTALL activity via `vault_search.py`.
