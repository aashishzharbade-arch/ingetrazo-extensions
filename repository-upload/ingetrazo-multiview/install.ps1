# IngeTrazo MultiView PowerShell Installer
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  IngeTrazo MultiView Extension Installer" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$pluginsDir = Join-Path $env:APPDATA "ingetrazo\plugins"
if (-not (Test-Path $pluginsDir)) {
    New-Item -ItemType Directory -Path $pluginsDir -Force | Out-Null
    Write-Host "Created plugins directory: $pluginsDir" -ForegroundColor Yellow
}

$sourceFile = Join-Path $PSScriptRoot "ingetrazo_multiview.py"
$destFile = Join-Path $pluginsDir "ingetrazo_multiview.py"

try {
    Copy-Item -Path $sourceFile -Destination $destFile -Force
    Write-Host "[SUCCESS] IngeTrazo MultiView installed successfully!" -ForegroundColor Green
    Write-Host "Destination: $destFile" -ForegroundColor Gray
    Write-Host "Start or restart IngeTrazo to use the new MultiView extension." -ForegroundColor White
} catch {
    Write-Host "[ERROR] Failed to install: $_" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit..."
