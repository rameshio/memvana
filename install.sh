#!/usr/bin/env bash
# Memvana one-command installer (macOS / Linux / Git Bash)
#   curl -fsSL https://raw.githubusercontent.com/rameshio/memvana/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/rameshio/memvana"
RAW="https://raw.githubusercontent.com/rameshio/memvana/main"
SKILL_DIR="${HOME}/.claude/skills/memvana"

echo "[1/3] Installing memvana CLI (pip)..."
pip install --quiet --upgrade "memvana[all] @ git+${REPO}"

echo "[2/3] Installing Claude Code skill -> ${SKILL_DIR}"
mkdir -p "${SKILL_DIR}"
curl -fsSL "${RAW}/SKILL.md" -o "${SKILL_DIR}/SKILL.md"

echo "[3/3] Verifying..."
memvana --version

echo
echo "Done. Restart your Claude Code session to load the skill."
echo "Then drop any PDF/doc into chat, or ask how parts of your code connect."
