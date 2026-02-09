# Open Qt Designer from Virtual Environment
# This script launches Qt Designer directly from the qt6-applications package
# without using the pyqt6-tools wrapper (which has pkg_resources issues)

# Dynamically determine project root (script is in scripts/powershell/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "code"

# Path to Qt Designer executable in the virtual environment
$DesignerPath = Join-Path $ProjectRoot ".venv\Lib\site-packages\qt6_applications\Qt\bin\designer.exe"

# Check if Designer executable exists
if (-Not (Test-Path $DesignerPath)) {
    Write-Host "Error: Qt Designer not found at:" -ForegroundColor Red
    Write-Host $DesignerPath -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please ensure the virtual environment is set up correctly." -ForegroundColor Yellow
    Write-Host "Run: cd '$ProjectRoot' && uv pip install qt6-applications" -ForegroundColor Cyan
    exit 1
}

# Launch Qt Designer
Write-Host "Launching Qt Designer..." -ForegroundColor Green
Write-Host "Executable: $DesignerPath" -ForegroundColor Gray
Write-Host ""

# Start Designer (using & to run in background)
Start-Process -FilePath $DesignerPath

Write-Host "Qt Designer launched successfully!" -ForegroundColor Green
