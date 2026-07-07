[CmdletBinding()]
param(
    [string]$ProjectName = "lost-found",
    [string]$BaseUrl = "http://localhost:8000",
    [ValidateRange(1, 10000)][int]$SampleCount = 20,
    [string]$OutputPath = "metrics/service-monitoring.json",
    [switch]$IncludeDockerStats
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Services = @("web-agent", "item-service", "claim-service", "handover-service")

function Measure-Endpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$Method = "GET",
        [object]$Body = $null,
        [string]$ContentType = "application/json; charset=utf-8",
        [int]$TimeoutSec = 10
    )

    $Stopwatch = [Diagnostics.Stopwatch]::StartNew()
    try {
        if ($null -eq $Body) {
            $Response = Invoke-WebRequest -Uri $Uri -Method $Method -TimeoutSec $TimeoutSec
        } else {
            $Payload = if ($Body -is [string]) {
                $Body
            } else {
                $Body | ConvertTo-Json -Compress
            }
            $Response = Invoke-WebRequest `
                -Uri $Uri `
                -Method $Method `
                -Body $Payload `
                -ContentType $ContentType `
                -TimeoutSec $TimeoutSec
        }
        $Stopwatch.Stop()
        return [pscustomobject]@{
            Name = $Name
            Uri = $Uri
            Method = $Method
            StatusCode = [int]$Response.StatusCode
            Success = $true
            LatencyMs = [math]::Round($Stopwatch.Elapsed.TotalMilliseconds, 2)
            Error = $null
        }
    } catch {
        $Stopwatch.Stop()
        $StatusCode = $null
        if ($_.Exception.Response) {
            $StatusCode = [int]$_.Exception.Response.StatusCode
        }
        return [pscustomobject]@{
            Name = $Name
            Uri = $Uri
            Method = $Method
            StatusCode = $StatusCode
            Success = $false
            LatencyMs = [math]::Round($Stopwatch.Elapsed.TotalMilliseconds, 2)
            Error = $_.Exception.Message
        }
    }
}

function Get-ComposeHealth {
    $Rows = @()
    foreach ($Service in $Services) {
        try {
            $ContainerIdRaw = docker compose -p $ProjectName ps -q $Service
            $ContainerIdLine = $ContainerIdRaw | Select-Object -First 1
            $ContainerId = if ($null -eq $ContainerIdLine) {
                ""
            } else {
                ([string]$ContainerIdLine).Trim()
            }
            if ([string]::IsNullOrWhiteSpace($ContainerId)) {
                $Rows += [pscustomobject]@{
                    Service = $Service
                    ContainerId = ""
                    Health = "missing"
                    Error = "No running container"
                }
                continue
            }
            $Health = docker inspect --format "{{.State.Health.Status}}" $ContainerId
            $Rows += [pscustomobject]@{
                Service = $Service
                ContainerId = $ContainerId
                Health = (($Health | Select-Object -First 1).Trim())
                Error = $null
            }
        } catch {
            $Rows += [pscustomobject]@{
                Service = $Service
                ContainerId = ""
                Health = "unknown"
                Error = $_.Exception.Message
            }
        }
    }
    return $Rows
}

function Get-DockerStats {
    try {
        $Lines = docker stats --no-stream --format "{{json .}}"
        $Rows = @()
        foreach ($Line in $Lines) {
            if (-not [string]::IsNullOrWhiteSpace($Line)) {
                $Rows += ($Line | ConvertFrom-Json)
            }
        }
        return $Rows
    } catch {
        return @([pscustomobject]@{
            Error = $_.Exception.Message
        })
    }
}

$HealthChecks = @(
    Measure-Endpoint -Name "web-health" -Uri "$BaseUrl/healthz"
)

$ChatBody = @{
    user_id = "u001"
    message = "帮我找图书馆发现的黑色耳机"
}
$ChatSamples = @()
$ThroughputWatch = [Diagnostics.Stopwatch]::StartNew()
for ($Index = 1; $Index -le $SampleCount; $Index++) {
    $ChatSamples += Measure-Endpoint `
        -Name "chat-$Index" `
        -Uri "$BaseUrl/api/chat" `
        -Method "POST" `
        -Body $ChatBody
}
$ThroughputWatch.Stop()

$Succeeded = @($ChatSamples | Where-Object { $_.Success }).Count
$Failed = $SampleCount - $Succeeded
$Seconds = [math]::Round($ThroughputWatch.Elapsed.TotalSeconds, 3)
$Throughput = [pscustomobject]@{
    TotalRequests = $SampleCount
    Success = $Succeeded
    Failed = $Failed
    Seconds = $Seconds
    RequestsPerSecond = if ($Seconds -gt 0) {
        [math]::Round($Succeeded / $Seconds, 2)
    } else {
        0
    }
    SuccessRate = [math]::Round($Succeeded / $SampleCount * 100, 2)
}

$Report = [ordered]@{
    Timestamp = (Get-Date).ToString("s")
    ProjectName = $ProjectName
    BaseUrl = $BaseUrl
    HealthChecks = $HealthChecks
    ComposeHealth = Get-ComposeHealth
    ChatSamples = $ChatSamples
    Throughput = $Throughput
    DockerStats = if ($IncludeDockerStats) { Get-DockerStats } else { @() }
}

$Parent = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($Parent) -and -not (Test-Path -LiteralPath $Parent)) {
    New-Item -ItemType Directory -Path $Parent | Out-Null
}

$Json = $Report | ConvertTo-Json -Depth 8
Set-Content -Path $OutputPath -Value $Json -Encoding UTF8
Write-Host "Service monitoring report written to $OutputPath"
Write-Output $Json
