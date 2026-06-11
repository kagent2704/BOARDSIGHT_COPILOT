param(
    [string]$ProjectId = "boardsight-agent",
    [string]$Region = "us-central1",
    [string]$ServiceName = "boardsight-ai",
    [string]$AgentApiKey = "",
    [switch]$AllowUnauthenticated
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = Join-Path $projectRoot "python-ai"
$gcloudCmd = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source

if (-not $gcloudCmd) {
    $candidate = "C:\Users\$env:USERNAME\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (Test-Path $candidate) {
        $gcloudCmd = $candidate
    }
}

if (-not (Test-Path $sourceRoot)) {
    throw "Unable to find python-ai source directory at $sourceRoot"
}
if (-not $gcloudCmd) {
    throw "Unable to locate gcloud.cmd. Install Google Cloud CLI or add it to PATH."
}

$authFlag = if ($AllowUnauthenticated) { "--allow-unauthenticated" } else { "--no-allow-unauthenticated" }

Write-Host "Deploying BoardSight AI service to Cloud Run..."
Write-Host "Project: $ProjectId"
Write-Host "Region: $Region"
Write-Host "Service: $ServiceName"
Write-Host "Source:  $sourceRoot"
if ($AgentApiKey) {
    Write-Host "Agent API key: configured"
}

& $gcloudCmd config set project $ProjectId | Out-Null
& $gcloudCmd config set run/region $Region | Out-Null

$envVars = "PYTHONIOENCODING=UTF-8,MPLBACKEND=Agg,HF_HUB_DISABLE_SYMLINKS_WARNING=1,BOARDSIGHT_WARM_MODELS=0"
if ($AgentApiKey) {
    $envVars = "$envVars,BOARDSIGHT_AGENT_API_KEY=$AgentApiKey"
}

& $gcloudCmd run deploy $ServiceName `
    --source $sourceRoot `
    --region $Region `
    --project $ProjectId `
    --port 8000 `
    --memory 4Gi `
    --cpu 2 `
    --timeout 900 `
    --max-instances 2 `
    --set-env-vars $envVars `
    $authFlag
