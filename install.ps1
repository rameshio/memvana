# Memvana one-command installer (Windows PowerShell)
#   irm https://raw.githubusercontent.com/rameshio/memvana/main/install.ps1 | iex
$ErrorActionPreference = "Stop"

$Repo = "https://github.com/rameshio/memvana"
$Raw = "https://raw.githubusercontent.com/rameshio/memvana/main"
$SkillDir = Join-Path $HOME ".claude\skills\memvana"

Write-Host "[1/3] Installing memvana CLI (pip)..."
pip install --quiet --upgrade "memvana[all] @ git+$Repo"

Write-Host "[2/3] Installing Claude Code skill -> $SkillDir"
New-Item -ItemType Directory -Force $SkillDir | Out-Null
Invoke-WebRequest -UseBasicParsing "$Raw/SKILL.md" -OutFile (Join-Path $SkillDir "SKILL.md")

Write-Host "[3/3] Verifying..."
memvana --version

Write-Host ""
Write-Host "Done. Restart your Claude Code session to load the skill."
Write-Host "Then drop any PDF/doc into chat, or ask how parts of your code connect."
