#!/usr/bin/env pwsh

param(
    [string]$DistRoot = (Join-Path $PSScriptRoot "..\dist\VideoCue")
)

$ErrorActionPreference = "Stop"

function Fail {
    param([string]$Message)
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $DistRoot)) {
    Fail "Dist root not found: $DistRoot"
}

$internalDir = Join-Path $DistRoot "_internal"
if (-not (Test-Path $internalDir)) {
    Fail "_internal directory not found: $internalDir"
}

$requiredRuntimeNames = @(
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll"
)

$qtBinDir = Join-Path $internalDir "PyQt6\Qt6\bin"
$system32 = Join-Path $env:WINDIR "System32"

Write-Host "Verifying packaged VC runtime DLLs..." -ForegroundColor Cyan

foreach ($name in $requiredRuntimeNames) {
    $distPath = Join-Path $internalDir $name
    if (-not (Test-Path $distPath)) {
        Fail "Required runtime missing from dist: $distPath"
    }

    $distVersion = (Get-Item $distPath).VersionInfo.FileVersion
    Write-Host "  [OK] $name => $distVersion"

    $systemPath = Join-Path $system32 $name
    if (Test-Path $systemPath) {
        $systemVersion = (Get-Item $systemPath).VersionInfo.FileVersion
        if ($distVersion -ne $systemVersion) {
            Fail "Runtime version mismatch for $name (dist=$distVersion, system=$systemVersion)"
        }
    }

    $qtPath = Join-Path $qtBinDir $name
    if (Test-Path $qtPath) {
        $qtVersion = (Get-Item $qtPath).VersionInfo.FileVersion
        Fail "Unexpected Qt-local runtime found at $qtPath (version=$qtVersion)"
    }
}

Write-Host "Runtime DLL verification passed." -ForegroundColor Green
