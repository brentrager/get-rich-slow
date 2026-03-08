#!/bin/bash
# Auto-push to main after Claude commits

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

if echo "$COMMAND" | grep -q "git commit"; then
    BRANCH=$(git branch --show-current)
    if [ "$BRANCH" = "main" ]; then
        git push origin main 2>&1
    fi
fi

exit 0
