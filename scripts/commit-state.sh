#!/usr/bin/env bash
set -euo pipefail

git add -- data/ state/ alerts/
if git diff --cached --quiet; then
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "data: update official lotto monitor state"

git pull --rebase origin main
if git push origin HEAD:main; then
  exit 0
fi

git pull --rebase origin main
git push origin HEAD:main
