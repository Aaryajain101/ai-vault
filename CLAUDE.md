# AI Vault

## What this is
A local, searchable index (SQLite + FTS5, `vault.db`) of ~14,464 AI resources — skills, MCP servers, tools, LLMs, agents, design assets — sourced from leveluplearning.in/aivault. Supports one-click install into Claude Code.

See also the user memory `ai-vault-search.md` for prior session context on querying this catalog — this file covers operation/maintenance, not a duplicate of that.

## Usage
```
python vault_search.py "<query>"                 # full-text search
python vault_search.py "<query>" --cat tool       # filter by category (skill|tool|mcp|llm|agent|design)
python vault_search.py --install <slug>           # auto-runs `claude skills add` / `claude mcp add`
python vault_search.py --get <slug>                # show full item details
python vault_search.py --stats                     # category counts
python vault_search.py --collections                # list curated collections
```

## Refreshing the index
```
python fetch.py     # re-downloads all category JSONs from the source, rebuilds vault.db
```
`update.cmd` runs `fetch.py` and appends to `update.log` — wire this to Windows Task Scheduler for a daily refresh. Last known update: 2026-06-30, 14,464 items indexed.
