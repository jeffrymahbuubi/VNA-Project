#!/bin/bash
# Start Jupyter Server for MCP integration
# This runs JupyterLab with collaboration enabled for jupyter-mcp-server

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Navigate to project root (two directories up from scripts/bash/)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"
source code/.venv/bin/activate

# Start JupyterLab with collaboration features enabled
# Token must match the one in .mcp.json
jupyter lab --port 8888 \
    --IdentityProvider.token=my_secure_token_123 \
    --ServerApp.allow_origin='*' \
    --ServerApp.allow_remote_access=true \
    --ip=0.0.0.0 \
    --no-browser \
    --LabApp.collaborative=true
