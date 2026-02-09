# Start Jupyter Server for MCP integration
# This runs JupyterLab with collaboration enabled for jupyter-mcp-server

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Navigate to project root (two directories up from scripts/powershell/)
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

Set-Location $ProjectRoot

# Activate virtual environment
$VenvPath = Join-Path $ProjectRoot "code\.venv\Scripts\Activate.ps1"
if (Test-Path $VenvPath) {
    & $VenvPath
} else {
    Write-Error "Virtual environment not found at: $VenvPath"
    Write-Error "Please create the virtual environment first."
    exit 1
}

# Start JupyterLab with collaboration features enabled
# Token must match the one in .mcp.json
jupyter lab --port 8888 `
    --IdentityProvider.token=my_secure_token_123 `
    --ServerApp.allow_origin='*' `
    --ServerApp.allow_remote_access=true `
    --ip=0.0.0.0 `
    --no-browser `
    --LabApp.collaborative=true
