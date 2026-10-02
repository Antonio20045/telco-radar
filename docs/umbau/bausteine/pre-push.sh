#!/bin/sh
git fetch --quiet origin main || exit 1
if ! git merge-base --is-ancestor origin/main HEAD; then
  echo "pre-push: origin/main ist neuer, erst git pull --rebase origin main"
  exit 1
fi
exec .venv/bin/python scripts/pruefleiter.py --voll
