# AI Vault — Upstream Sources

All sources are merged into the **same** `vault.db` by `fetch.py`. Each item carries a
`source` column; duplicates across sources are collapsed by a canonical identity key
(`canon_key` in `fetch.py`). Priority order (earlier wins, keeps its slug):

`levelup → mcp-registry → openrouter → awesome-mcp → awesome-agents → awesome-design → skills.sh`

| source | category | access | endpoint | license | notes |
|--------|----------|--------|----------|---------|-------|
| `levelup` | all 6 | JSON files, no auth | `leveluplearning.in/aivault/data/ai-resources/{cat}.json` + `collections.json` | site data | **base**; canonical on conflict; slugs preserved (e.g. `skill/oracle`) |
| `mcp-registry` | mcp_server | JSON API, cursor pagination, no auth | `registry.modelcontextprotocol.io/v0/servers?limit=100&cursor=…` | open | official registry |
| `openrouter` | llm | JSON API, no auth | `openrouter.ai/api/v1/models` | open catalog | id, pricing, context length |
| `awesome-mcp` | mcp_server | raw README markdown (bullet) | `raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md` | community | `- [name](url) … - desc`, `###` category headings |
| `awesome-agents` | agent | raw README markdown (heading) | `raw.githubusercontent.com/e2b-dev/awesome-ai-agents/main/README.md` | open | `## [Name](url)` + next line = desc |
| `awesome-design` | design | raw README markdown (bullet) | `raw.githubusercontent.com/VoltAgent/awesome-design-md/main/README.md` | open | `- [**Name**](url) - desc` |
| `skills.sh` | skill | public sitemaps (+ HF cache) | `skills.sh/sitemap.xml → sitemap-skills-*.xml` | site data / MIT (HF) | **API is 401 (auth)** — use sitemaps + `skills_sh_hf.json` |

## skills.sh — two-part ingestion
- **Live (daily, in `fetch.py`):** parse `sitemap-skills-*.xml`. Skill URL = `skills.sh/{owner}/{repo}/{skill}` → name, GitHub URL, and `install_command` = `npx skills add https://github.com/{owner}/{repo} --skill {skill}`. Thin (no description).
- **Rich (one-time, `import_hf_skills.py`):** downloads the HF mirror `tickleliu/all-skills-from-skills-sh` (MIT, ~49.5k rows) via the HF datasets-server rows API, keeps `name/description/skill_name/code`, **discards `detail`**, and writes `skills_sh_hf.json`. `fetch.py` then enriches sitemap skills with those descriptions (matched on `owner/repo/skill`). Heavy; run manually, re-run only to refresh the snapshot.

## Quality pipeline (in `fetch.py`, after merge)

`enrich_github.py` maintains `github_cache.json` — stars / pushedAt / description / existence for every referenced GitHub repo (GraphQL, 100 repos/query, incremental with 7-day refresh; published as a release asset). `fetch.py` then:

1. **Enrich** — set `stars`/`pushed` columns, backfill empty descriptions from repo descriptions.
2. **Prune dead repos** — cache says repo no longer exists → item dropped.
3. **Collapse exact clones** — same (name, description): keep one, preferring canonical owners (`anthropics`, `vercel-labs`, `modelcontextprotocol`, …) > highest stars > levelup; survivor records `extra.clone_count`.
4. **Prune junk names** — <3 chars or punctuation-only.
5. **Prune hopeless thin entries** — no description after backfill, 0 stars, and a described twin with the same name exists.
6. **Score** (0–10, `score` column): source authority (≤2) + log-scaled stars (≤4) + description (1) + install command (1) + push recency (≤1) + canonical-owner bonus (1).

Search ranks by `bm25(fts) − 0.6·score` — relevance blended with usefulness. Prune/enrich counts are logged per run in `update_history.log` (`quality:` line).

## Excluded / gaps
- `theresanaiforthat` (tools): no public API → not automated. Tools stay covered by `levelup` (~3.5k).
- Skills that share a name but come from **different repos** are not merged (identity is repo+skill).

## Not used: cloud routine
A Claude Code cloud routine was considered but **cannot write the local `vault.db`** (it runs on Anthropic servers). We keep the local **Windows Task Scheduler** job "AI Vault Daily Update" (6 AM → `update.cmd` → `fetch.py`) as the sole updater.

## Adding a new source
1. Write a `fetch_<source>()` adapter in `fetch.py` returning `rec(...)` dicts with a unique `source` name.
2. Add it to `SOURCE_ORDER`, `SOURCE_SUFFIX`, and the `adapters` list in `main()`.
3. Extend `canon_key` if the category needs special identity handling.
