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

foreach ($ImageName in $Images.Values) {
    Invoke-NativeChecked "docker image inspect $ImageName`:$Sha" {
        docker image inspect "$ImageName`:$Sha" | Out-Null
    }
}

$env:IMAGE_TAG = $Sha
Invoke-NativeChecked "docker compose rollback up" {
    docker compose -p $ProjectName -f $ComposeFile up -d --no-build --wait --remove-orphans
}
& "$PSScriptRoot/Test-Compose.ps1" -ProjectName $ProjectName -ComposeFile $ComposeFile

Write-Host "Rollback completed: $Sha"
