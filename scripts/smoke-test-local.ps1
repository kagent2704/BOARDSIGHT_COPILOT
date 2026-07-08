param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Running Python tests..."
& $Python -m pytest .\python-ai\tests -q

Write-Host "Compiling Python modules..."
& $Python -m compileall .\python-ai\boardsight_ai .\python-ai\tests

Write-Host "Building Java app..."
& (Join-Path $PSScriptRoot "build-java.ps1")

Write-Host "BoardSight local smoke test completed successfully."
