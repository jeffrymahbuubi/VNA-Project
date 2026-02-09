# Wrapper script to launch Claude Code with environment variables from .env

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Find .env file by walking up the directory tree
$CurrentDir = $ScriptDir
$EnvFile = $null

while ($CurrentDir -and (Test-Path $CurrentDir)) {
    $TestPath = Join-Path $CurrentDir ".env"
    if (Test-Path $TestPath) {
        $EnvFile = $TestPath
        break
    }
    $Parent = Split-Path -Parent $CurrentDir
    if ($Parent -eq $CurrentDir) { break }  # Reached root
    $CurrentDir = $Parent
}

if ($EnvFile -and (Test-Path $EnvFile)) {
    Write-Host "Loading environment variables from $EnvFile"

    # Load .env file and set environment variables
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        # Skip empty lines and comments
        if ($line -and !$line.StartsWith('#')) {
            # Parse KEY=VALUE format
            if ($line -match '^([^=]+)=(.*)$') {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                # Remove surrounding quotes if present
                $value = $value -replace '^["'']|["'']$', ''
                [Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
        }
    }
} else {
    Write-Host "Warning: .env file not found in any parent directory" -ForegroundColor Yellow
}

# Launch Claude Code with all passed arguments
& claude $args
