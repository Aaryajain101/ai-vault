# AI Vault

A local, searchable catalog of **30,000+ AI resources** — Claude Code skills, MCP servers, AI tools, LLMs, agents, and design systems — aggregated daily from 7 upstream sources, deduplicated, and wired into Claude Code for one-command install.

- **Search** anything by keyword (SQLite FTS5, instant, offline) — results ranked by relevance × usefulness (GitHub stars, source authority, liveness, completeness), so originals outrank forks
- **Filter** with `--min-stars N`, `--sort stars`, `--cat`, `--source`
- **Install** skills (`npx skills add …`) and MCP servers (`claude mcp add …`) straight from search results
- **Auto-updates daily** — GitHub Actions rebuilds the database every night and publishes it to the `latest` release; your machine pulls it automatically
- **Windows + macOS**

## Install (2 minutes)

Prereqs: [git](https://git-scm.com) and Python 3.10+. That's it — no GitHub account needed.

```bash
git clone https://github.com/Aaryajain101/ai-vault
cd ai-vault
```

**Windows:** `powershell -ExecutionPolicy Bypass -File setup.ps1`
**macOS:** `bash setup.sh`

The setup script downloads the latest `vault.db`, installs the `/vault-search` skill into your Claude Code, and schedules a daily 7 AM auto-update (Task Scheduler on Windows, launchd on Mac).

## Use it

In **Claude Code**, just ask — the skill triggers automatically:
> "Is there an MCP server for Postgres?" · "Find me a skill for writing PRDs" · "Install the playwright MCP"

Or from a terminal:
```bash
python vault_search.py "browser automation" --cat mcp_server
python vault_search.py "react" --source skills.sh --limit 5
python vault_search.py --install skill/frontend-design
python vault_search.py --get mcp_server/github
python vault_search.py --stats
```

## How it stays fresh

| When | What |
|------|------|
| Daily 00:30 UTC | GitHub Actions runs `fetch.py`: pulls all 7 sources, dedups, sanity-checks, publishes `vault.db` to the `latest` release |
| Daily 7 AM (your machine) | `pull` job downloads the new `vault.db` + `git pull`s script updates |

Sources: leveluplearning.in (base), official MCP Registry, OpenRouter, punkpeye/awesome-mcp-servers, e2b/awesome-ai-agents, VoltAgent/awesome-design-md, skills.sh. Details, endpoints, licenses, and dedup rules: [SOURCES.md](SOURCES.md).

## Repo layout

```
fetch.py             multi-source fetcher + dedup/merge  → vault.db
vault_search.py      search / details / install CLI
import_hf_skills.py  one-time skills.sh description enrichment (maintainer only)
setup.ps1 / setup.sh installer (DB download, skill, auto-update job)
.github/workflows/   daily cloud build
SOURCES.md           source registry & dedup documentation
```

## Cautions

- `--install` runs third-party install commands (`npx skills add` pulls remote code). Glance at the repo before installing unfamiliar items.
- Don't install third-party copies of skills Claude Code already ships first-party (pdf, docx, pptx, xlsx, deep-research, …).
