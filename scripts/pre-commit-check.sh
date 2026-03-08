#!/usr/bin/env bash
set -e

ROOT=$(git rev-parse --show-toplevel)

# Format and lint staged Python files
PYTHON_FILES=$(git diff --cached --name-only --diff-filter=ACM -- '*.py')
if [ -n "$PYTHON_FILES" ]; then
    echo "Formatting Python files..."
    echo "$PYTHON_FILES" | xargs uv run ruff format
    echo "$PYTHON_FILES" | xargs uv run ruff check --fix || true
    echo "$PYTHON_FILES" | xargs git add
fi

# Format staged TS/TSX files in dashboard
TS_FILES=$(git diff --cached --name-only --diff-filter=ACM -- 'dashboard/**/*.ts' 'dashboard/**/*.tsx')
if [ -n "$TS_FILES" ]; then
    echo "Formatting TypeScript files..."
    # oxfmt needs relative paths from dashboard dir, writes in place (no --write flag)
    RELATIVE=$(echo "$TS_FILES" | sed 's|^dashboard/||')
    (cd "$ROOT/dashboard" && echo "$RELATIVE" | xargs pnpm oxfmt)
    echo "$TS_FILES" | xargs git add
fi
