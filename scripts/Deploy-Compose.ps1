[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Sha,

    [string]$ProjectName = "lost-found",
    [string]$ComposeFile = "compose.yaml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Images = [ordered]@{
    "web-agent" = "lost-found/web-agent"
    "item-service" = "lost-found/item-service"
    "claim-service" = "lost-found/claim-service"
    "handover-service" = "lost-found/handover-service"
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    & $Command
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        throw "$Name failed with exit code $ExitCode"
    }
}

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

function Invoke-NativeBestEffort {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    try {
        & $Command
        $ExitCode = $LASTEXITCODE
        if ($ExitCode -ne 0) {
            Write-Warning "$Name failed with exit code $ExitCode"
        }
    } catch {
        Write-Warning "$Name failed: $_"
    }
}

Get-Command docker -ErrorAction Stop | Out-Null
Invoke-NativeChecked "docker compose version" { docker compose version }
$DockerOs = Invoke-NativeOutput "docker info" { docker info --format "{{.OSType}}" }
$DockerOs = ($DockerOs | Select-Object -First 1).Trim()
if ($DockerOs -ne "linux") {
    throw "Docker Desktop must use Linux containers; current OSType is $DockerOs"
}
Invoke-NativeChecked "docker compose config" {
    docker compose -p $ProjectName -f $ComposeFile config --quiet
}

$ExistingTags = @()
$ExistingCount = 0
foreach ($Service in $Images.Keys) {
    $ContainerId = Invoke-NativeOutput "docker compose ps $Service" {
        docker compose -p $ProjectName -f $ComposeFile ps -q $Service
    }
    $ContainerId = ($ContainerId | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($ContainerId)) {
        continue
    }

    $ExistingCount += 1
    $Image = Invoke-NativeOutput "docker inspect $Service image" {
        docker inspect --format "{{.Config.Image}}" $ContainerId
    }
    $Image = ($Image | Select-Object -First 1).Trim()
    $ExpectedPrefix = "$($Images[$Service]):"
    if (-not $Image.StartsWith($ExpectedPrefix)) {
        throw "Existing Compose deployment is partial, mutable, or uses mixed tags"
    }
    $ExistingTags += $Image.Substring($ExpectedPrefix.Length)
}

$PreviousTag = $null
if ($ExistingCount -ne 0) {
    $DistinctTags = @($ExistingTags | Select-Object -Unique)
    if (
        $ExistingCount -ne $Images.Count -or
        $DistinctTags.Count -ne 1 -or
        $DistinctTags[0] -notmatch '^[0-9a-f]{40}$'
    ) {
        throw "Existing Compose deployment is partial, mutable, or uses mixed tags"
    }
    $PreviousTag = $DistinctTags[0]
}

try {
    $env:IMAGE_TAG = $Sha
    Invoke-NativeChecked "docker compose build" {
        docker compose -p $ProjectName -f $ComposeFile build --pull
    }
    Invoke-NativeChecked "docker compose up" {
        docker compose -p $ProjectName -f $ComposeFile up -d --wait --remove-orphans
    }
    & "$PSScriptRoot/Test-Compose.ps1" -ProjectName $ProjectName -ComposeFile $ComposeFile
    Write-Host "Deployment completed: $Sha"
} catch {
    $OriginalError = $_
    Invoke-NativeBestEffort "docker compose ps" {
        docker compose -p $ProjectName -f $ComposeFile ps
    }
    Invoke-NativeBestEffort "docker compose logs" {
        docker compose -p $ProjectName -f $ComposeFile logs --tail 200
    }
    if ($PreviousTag) {
        Write-Warning "Deployment failed; rolling back to previous image tag $PreviousTag"
        $env:IMAGE_TAG = $PreviousTag
        Invoke-NativeChecked "docker compose rollback up" {
            docker compose -p $ProjectName -f $ComposeFile up -d --no-build --wait --remove-orphans
        }
        & "$PSScriptRoot/Test-Compose.ps1" -ProjectName $ProjectName -ComposeFile $ComposeFile
    }
    throw $OriginalError
}
