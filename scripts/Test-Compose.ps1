[CmdletBinding()]
param(
    [string]$ProjectName = "lost-found",
    [string]$ComposeFile = "compose.yaml",
    [string]$BaseUrl = "http://localhost:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Services = @("web-agent", "item-service", "claim-service", "handover-service")
$InternalOnlyServices = @("item-service", "claim-service", "handover-service")

function Invoke-NativeOutput {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    $Output = & $Command
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        throw "$Name failed with exit code $ExitCode"
    }
    return $Output
}

function Get-ServiceContainerId {
    param([Parameter(Mandatory = $true)][string]$Service)

    $ContainerId = Invoke-NativeOutput "docker compose ps $Service" {
        docker compose -p $ProjectName -f $ComposeFile ps -q $Service
    }
    $ContainerId = ($ContainerId | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($ContainerId)) {
        throw "Compose service has no running container: $Service"
    }
    return $ContainerId
}

$ContainerIds = @{}
foreach ($Service in $Services) {
    $ContainerId = Get-ServiceContainerId -Service $Service
    $Health = Invoke-NativeOutput "docker inspect $Service health" {
        docker inspect --format "{{.State.Health.Status}}" $ContainerId
    }
    $Health = ($Health | Select-Object -First 1).Trim()
    if ($Health -ne "healthy") {
        throw "Compose service is not healthy: $Service ($Health)"
    }
    $ContainerIds[$Service] = $ContainerId
}

foreach ($Service in $InternalOnlyServices) {
    $Ports = Invoke-NativeOutput "docker port $Service" {
        docker port $ContainerIds[$Service]
    }
    if ($Ports) {
        throw "Internal service exposes a host port: $Service"
    }
}

# Default health check: http://localhost:8000/healthz
$HealthResult = Invoke-RestMethod -Uri "$BaseUrl/healthz" -TimeoutSec 10
if ($HealthResult.status -ne "ok") {
    throw "Unexpected /healthz response"
}

$HomeResponse = Invoke-WebRequest -Uri "$BaseUrl/" -TimeoutSec 10
if ($HomeResponse.Content -notlike "*寻迹校园*") {
    throw "Homepage smoke check did not find expected title"
}

$ChatBody = @{
    user_id = "u001"
    message = "帮我找图书馆发现的黑色耳机"
} | ConvertTo-Json -Compress
$ChatResult = Invoke-RestMethod `
    -Uri "$BaseUrl/api/chat" `
    -Method Post `
    -Body $ChatBody `
    -ContentType "application/json; charset=utf-8" `
    -TimeoutSec 10
if ($ChatResult.reply -notlike "*LF2026001*") {
    throw "Chat smoke check did not return LF2026001"
}

Write-Host "Compose smoke tests: PASS"
