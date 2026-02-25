# Load .env file into the current terminal session (Process scope)
# Usage: . .\scripts\powershell\load-env.ps1   (dot-source — the leading dot is required)
# Note: Running without dot-source (.\load-env.ps1) has no effect on the parent session.

# Walk up from the current working directory to find .env
$CurrentDir = $PWD.Path
$EnvFile = $null

while ($CurrentDir -and (Test-Path $CurrentDir)) {
    $TestPath = Join-Path $CurrentDir ".env"
    if (Test-Path $TestPath) {
        $EnvFile = $TestPath
        break
    }
    $Parent = Split-Path -Parent $CurrentDir
    if ($Parent -eq $CurrentDir) { break }  # Reached filesystem root
    $CurrentDir = $Parent
}

if ($EnvFile) {
    $count = 0
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        # Skip empty lines and comments
        if ($line -and !$line.StartsWith('#')) {
            if ($line -match '^([^=]+)=(.*)$') {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                # Strip surrounding quotes if present
                $value = $value -replace '^["'']|["'']$', ''
                [Environment]::SetEnvironmentVariable($key, $value, 'Process')
                $count++
            }
        }
    }
    Write-Host "Loaded $count environment variable(s) from $EnvFile" -ForegroundColor Green
} else {
    Write-Host "Warning: .env file not found in current directory or any parent" -ForegroundColor Yellow
}
