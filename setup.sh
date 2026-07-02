#!/usr/bin/env bash
# AI Vault setup — macOS (and Linux with cron fallback)
# Run from the cloned repo folder:  bash setup.sh
set -euo pipefail
REPO_SLUG="Aaryajain101/ai-vault"
VAULT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v gh >/dev/null || { echo "GitHub CLI missing. Install: brew install gh — then re-run."; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Not logged in. Run: gh auth login — then re-run."; exit 1; }
PY="$(command -v python3 || command -v python)" || { echo "Python missing. Install python3 — then re-run."; exit 1; }

echo "1/4 Downloading latest vault.db..."
gh release download latest --pattern "vault.db" --clobber -R "$REPO_SLUG" --dir "$VAULT_DIR"

echo "2/4 Installing the /vault-search skill for Claude Code..."
SKILL_DIR="$HOME/.claude/skills"
mkdir -p "$SKILL_DIR"
cat > "$SKILL_DIR/vault-search.md" <<EOF
---
name: vault-search
description: Search the local AI Vault (30K+ skills, tools, MCP servers, LLMs, agents, designs) and install items automatically. Use when the user wants to find or install an AI tool, skill, MCP server, LLM, agent, or design.
---

# AI Vault Search & Install

Local database: \`$VAULT_DIR/vault.db\` (30K+ AI resources from 7 upstream sources, deduplicated).

**Search:**   \`$PY "$VAULT_DIR/vault_search.py" <query> [--cat skill|mcp_server|tool|llm|agent|design] [--source <name>] [--limit N]\`
**Install:**  \`$PY "$VAULT_DIR/vault_search.py" --install <slug>\`
**Details:**  \`$PY "$VAULT_DIR/vault_search.py" --get <slug>\`
**Stats:**    \`$PY "$VAULT_DIR/vault_search.py" --stats\`

Search proactively when the user needs a capability you don't have, asks about a tool by name, or asks "is there a skill/MCP for X?". Skills install via \`npx skills add\`; MCP servers via \`claude mcp add\`; other categories open their URL.
EOF

echo "3/4 Creating the daily auto-update job (7:00 AM)..."
cat > "$VAULT_DIR/pull.sh" <<EOF
#!/usr/bin/env bash
cd "$VAULT_DIR"
git pull --quiet || true
gh release download latest --pattern vault.db --clobber -R $REPO_SLUG
EOF
chmod +x "$VAULT_DIR/pull.sh"

if [[ "$(uname)" == "Darwin" ]]; then
  PLIST="$HOME/Library/LaunchAgents/com.aivault.update.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.aivault.update</string>
  <key>ProgramArguments</key><array><string>$VAULT_DIR/pull.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$VAULT_DIR/update.log</string>
  <key>StandardErrorPath</key><string>$VAULT_DIR/update.log</string>
</dict></plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
else
  ( crontab -l 2>/dev/null | grep -v aivault ; echo "0 7 * * * $VAULT_DIR/pull.sh # aivault" ) | crontab -
fi

echo "4/4 Testing search..."
"$PY" "$VAULT_DIR/vault_search.py" --stats

echo ""
echo "Done! The vault auto-updates daily at 7 AM. In Claude Code, just ask for any tool/skill/MCP."
