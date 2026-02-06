#!/bin/bash
# Wrapper script to launch Claude Code with environment variables from .env

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find .env file by walking up the directory tree from script location
CURRENT_DIR="$SCRIPT_DIR"
ENV_FILE=""
while [ "$CURRENT_DIR" != "/" ]; do
    if [ -f "$CURRENT_DIR/.env" ]; then
        ENV_FILE="$CURRENT_DIR/.env"
        break
    fi
    CURRENT_DIR="$(dirname "$CURRENT_DIR")"
done
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
    set -a  # automatically export all variables
    source "$ENV_FILE"
    set +a  # stop automatically exporting
    echo "Loaded environment variables from $ENV_FILE"
else
    echo "Warning: .env file not found in any parent directory"
fi

# Launch Claude Code with all passed arguments
claude "$@"