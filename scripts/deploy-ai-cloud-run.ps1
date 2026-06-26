param(
    [string]$ProjectId = "boardsight-agent",
    [string]$Region = "us-central1",
    [string]$ServiceName = "boardsight-ai",
    [string]$AgentApiKey = "",
    [string]$DatabaseUrl = "",
    [string]$GitLabBaseUrl = "",
    [string]$GitLabProjectId = "",
    [string]$GitLabPrivateToken = "",
    [string]$LlmProvider = "extractive",
    [string]$GeminiApiKey = "",
    [string]$GeminiModel = "gemini-3.1-flash-lite",
    [string]$Memory = "4Gi",
    [int]$Cpu = 2,
    [int]$TimeoutSeconds = 900,
    [int]$MaxInstances = 2,
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
if ($DatabaseUrl) {
    Write-Host "Database URL: configured"
}
if ($GitLabBaseUrl -or $GitLabProjectId -or $GitLabPrivateToken) {
    Write-Host "GitLab integration: configured"
}
if ($GeminiApiKey) {
    Write-Host "Gemini API: configured"
}

& $gcloudCmd config set project $ProjectId | Out-Null
& $gcloudCmd config set run/region $Region | Out-Null

$envVars = @(
    "PYTHONIOENCODING=UTF-8",
    "MPLBACKEND=Agg",
    "HF_HUB_DISABLE_SYMLINKS_WARNING=1",
    "BOARDSIGHT_WARM_MODELS=0",
    "BOARDSIGHT_LLM_PROVIDER=$LlmProvider"
)
if ($GeminiApiKey) {
    $envVars += "GEMINI_API_KEY=$GeminiApiKey"
    $envVars += "BOARDSIGHT_GEMINI_MODEL=$GeminiModel"
}
if ($AgentApiKey) {
    $envVars += "BOARDSIGHT_AGENT_API_KEY=$AgentApiKey"
}
if ($DatabaseUrl) {
    $envVars += "BOARDSIGHT_DATABASE_URL=$DatabaseUrl"
}
if ($GitLabBaseUrl) {
    $envVars += "BOARDSIGHT_GITLAB_BASE_URL=$GitLabBaseUrl"
}
if ($GitLabProjectId) {
    $envVars += "BOARDSIGHT_GITLAB_PROJECT_ID=$GitLabProjectId"
}
if ($GitLabPrivateToken) {
    $envVars += "BOARDSIGHT_GITLAB_PRIVATE_TOKEN=$GitLabPrivateToken"
}

& $gcloudCmd run deploy $ServiceName `
    --source $sourceRoot `
    --region $Region `
    --project $ProjectId `
    --port 8000 `
    --memory $Memory `
    --cpu $Cpu `
    --timeout $TimeoutSeconds `
    --max-instances $MaxInstances `
    --set-env-vars ($envVars -join ",") `
    $authFlag
