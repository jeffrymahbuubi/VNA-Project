#!/bin/bash
# Load .env file into the current terminal session
# Usage: source scripts/bash/load-env.sh   (or: . scripts/bash/load-env.sh)
# Note: Executing directly (bash load-env.sh) has no effect on the parent session.

# Guard: must be sourced, not executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Error: This script must be sourced, not executed directly."
    echo "Usage: source ${BASH_SOURCE[0]}"
    exit 1
fi

# Walk up from the current working directory to find .env
CURRENT_DIR="$(pwd)"
ENV_FILE=""

while [ "$CURRENT_DIR" != "/" ]; do
    if [ -f "$CURRENT_DIR/.env" ]; then
        ENV_FILE="$CURRENT_DIR/.env"
        break
    fi
    CURRENT_DIR="$(dirname "$CURRENT_DIR")"
done

if [ -n "$ENV_FILE" ]; then
    set -a  # automatically export all variables
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a  # stop automatically exporting
    echo "Loaded environment variables from $ENV_FILE"
else
    echo "Warning: .env file not found in current directory or any parent"
fi
