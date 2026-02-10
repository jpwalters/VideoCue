#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build VideoCue executable and installer in one step
.DESCRIPTION
    This script runs PyInstaller to build the executable, then runs Inno Setup
    to create the Windows installer. Checks for errors at each step.
.PARAMETER Version
    Version number to use for the build (e.g., "0.3.3"). If provided, updates version in all required files.
.PARAMETER SkipBuild
    Skip PyInstaller build (use existing dist/)
.PARAMETER SkipInstaller
    Skip Inno Setup installer creation
#>

param(
    [string]$Version,  # Version number to set (e.g., "0.3.3")
    [switch]$SkipBuild,  # Skip PyInstaller build (use existing dist/)
    [switch]$SkipInstaller  # Skip Inno Setup installer creation
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

# Update version in files if -Version parameter provided
if ($Version) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "Updating Version to $Version" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan
    
    $FilesToUpdate = @(
        @{
            Path = "$ScriptDir\videocue\__init__.py"
            Pattern = '__version__\s*=\s*[''"]([^''"]+)[''"]'
            Replacement = "__version__ = `"$Version`""
        },
        @{
            Path = "$ScriptDir\installer.iss"
            Pattern = '#define MyAppVersion\s+[''"]([^''"]+)[''"]'
            Replacement = "#define MyAppVersion `"$Version`""
        }
    )
    
    foreach ($file in $FilesToUpdate) {
        if (Test-Path $file.Path) {
            $content = Get-Content $file.Path -Raw
            $oldVersion = if ($content -match $file.Pattern) { $matches[1] } else { "unknown" }
            $newContent = $content -replace $file.Pattern, $file.Replacement
            
            if ($content -ne $newContent) {
                Set-Content -Path $file.Path -Value $newContent -NoNewline
                Write-Host "  Updated $(Split-Path $file.Path -Leaf): $oldVersion -> $Version" -ForegroundColor Green
            } else {
                Write-Host "  No change needed in $(Split-Path $file.Path -Leaf)" -ForegroundColor Gray
            }
        } else {
            Write-Host "  WARNING: File not found: $($file.Path)" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
}

# Get current version from videocue/__init__.py
$VersionMatch = Select-String -Path "$ScriptDir\videocue\__init__.py" -Pattern '__version__\s*=\s*[''"]([^''"]+)[''"]'
if ($VersionMatch) {
    $Version = $VersionMatch.Matches.Groups[1].Value
} else {
    Write-Host "ERROR: Could not determine version from videocue\__init__.py" -ForegroundColor Red
    exit 1
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "VideoCue Build Script v$Version" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Step 1: Run PyInstaller
if (-not $SkipBuild) {
    Write-Host "[1/2] Running PyInstaller..." -ForegroundColor Yellow
    Write-Host "Building executable from VideoCue.spec...`n" -ForegroundColor Gray
    
    # Clean dist folder before building to avoid confirmation prompt
    $DistPath = "$ScriptDir\dist\VideoCue"
    if (Test-Path $DistPath) {
        Write-Host "Removing existing dist folder..." -ForegroundColor Gray
        Remove-Item -Path $DistPath -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    $PyInstallerStart = Get-Date
    
    try {
        & "$ScriptDir\.venv\Scripts\pyinstaller.exe" VideoCue.spec --clean --noconfirm
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`nERROR: PyInstaller failed with exit code $LASTEXITCODE" -ForegroundColor Red
            exit 1
        }
        
        $PyInstallerEnd = Get-Date
        $PyInstallerDuration = ($PyInstallerEnd - $PyInstallerStart).TotalSeconds
        
        Write-Host "`nPyInstaller completed successfully in $([math]::Round($PyInstallerDuration, 1)) seconds" -ForegroundColor Green
        
        # Verify executable exists
        $ExePath = "$ScriptDir\dist\VideoCue\VideoCue.exe"
        if (-not (Test-Path $ExePath)) {
            Write-Host "ERROR: Expected executable not found at $ExePath" -ForegroundColor Red
            exit 1
        }
        
        $ExeSize = (Get-Item $ExePath).Length / 1MB
        Write-Host "Executable size: $([math]::Round($ExeSize, 2)) MB`n" -ForegroundColor Gray
        
    } catch {
        Write-Host "`nERROR: PyInstaller exception: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[1/2] Skipping PyInstaller (using existing dist/)...`n" -ForegroundColor Yellow
}

# Step 2: Run Inno Setup
if (-not $SkipInstaller) {
    Write-Host "[2/2] Running Inno Setup..." -ForegroundColor Yellow
    Write-Host "Creating installer from installer.iss...`n" -ForegroundColor Gray
    
    $InnoSetupStart = Get-Date
    
    # Locate Inno Setup compiler
    $ISCCPath = "C:\Users\jawalter\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
    
    if (-not (Test-Path $ISCCPath)) {
        # Try common alternative locations
        $AlternativePaths = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe"
        )
        
        foreach ($path in $AlternativePaths) {
            if (Test-Path $path) {
                $ISCCPath = $path
                break
            }
        }
        
        if (-not (Test-Path $ISCCPath)) {
            Write-Host "ERROR: Inno Setup compiler not found" -ForegroundColor Red
            Write-Host "Please install Inno Setup 6 or update the path in this script" -ForegroundColor Red
            exit 1
        }
    }
    
    try {
        & $ISCCPath "$ScriptDir\installer.iss"
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`nERROR: Inno Setup failed with exit code $LASTEXITCODE" -ForegroundColor Red
            exit 1
        }
        
        $InnoSetupEnd = Get-Date
        $InnoSetupDuration = ($InnoSetupEnd - $InnoSetupStart).TotalSeconds
        
        Write-Host "`nInno Setup completed successfully in $([math]::Round($InnoSetupDuration, 1)) seconds" -ForegroundColor Green
        
        # Find the created installer
        $InstallerPattern = "$ScriptDir\installer_output\VideoCue-*-Setup.exe"
        $Installer = Get-ChildItem $InstallerPattern | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        
        if ($Installer) {
            $InstallerSize = $Installer.Length / 1MB
            Write-Host "Installer: $($Installer.Name) ($([math]::Round($InstallerSize, 2)) MB)" -ForegroundColor Gray
            Write-Host "Location: $($Installer.FullName)`n" -ForegroundColor Gray
        }
        
    } catch {
        Write-Host "`nERROR: Inno Setup exception: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[2/2] Skipping Inno Setup installer creation...`n" -ForegroundColor Yellow
}

# Step 3: Create Portable ZIP
Write-Host "[3/3] Creating portable ZIP..." -ForegroundColor Yellow
Write-Host "Packaging portable distribution...`n" -ForegroundColor Gray

$PortableStart = Get-Date

try {
    $DistPath = "$ScriptDir\dist\VideoCue"
    $OutputPath = "$ScriptDir\installer_output"
    $ZipName = "VideoCue-$Version-portable.zip"
    $ZipPath = "$OutputPath\$ZipName"
    
    # Ensure output directory exists
    if (-not (Test-Path $OutputPath)) {
        New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
    }
    
    # Remove old portable ZIP if exists
    if (Test-Path $ZipPath) {
        Write-Host "Removing existing portable ZIP..." -ForegroundColor Gray
        Remove-Item $ZipPath -Force
    }
    
    # Verify dist folder exists
    if (-not (Test-Path $DistPath)) {
        Write-Host "ERROR: dist\VideoCue folder not found. Cannot create portable ZIP." -ForegroundColor Red
        exit 1
    }
    
    # Create temporary staging directory
    $StagingDir = "$ScriptDir\dist\VideoCue-Portable-Staging"
    if (Test-Path $StagingDir) {
        Remove-Item $StagingDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
    
    # Copy VideoCue executable folder
    Write-Host "Copying executable files..." -ForegroundColor Gray
    Copy-Item -Path "$DistPath\*" -Destination $StagingDir -Recurse -Force
    
    # Copy portable README
    if (Test-Path "$ScriptDir\PORTABLE_README.txt") {
        Write-Host "Adding portable README..." -ForegroundColor Gray
        Copy-Item -Path "$ScriptDir\PORTABLE_README.txt" -Destination "$StagingDir\README.txt" -Force
    }
    
    # Create ZIP file
    Write-Host "Creating ZIP archive..." -ForegroundColor Gray
    Compress-Archive -Path "$StagingDir\*" -DestinationPath $ZipPath -Force
    
    # Clean up staging directory
    Remove-Item $StagingDir -Recurse -Force
    
    $PortableEnd = Get-Date
    $PortableDuration = ($PortableEnd - $PortableStart).TotalSeconds
    
    Write-Host "`nPortable ZIP created successfully in $([math]::Round($PortableDuration, 1)) seconds" -ForegroundColor Green
    
    if (Test-Path $ZipPath) {
        $ZipSize = (Get-Item $ZipPath).Length / 1MB
        Write-Host "Portable ZIP: $ZipName ($([math]::Round($ZipSize, 2)) MB)" -ForegroundColor Gray
        Write-Host "Location: $ZipPath`n" -ForegroundColor Gray
    }
    
} catch {
    Write-Host "`nERROR: Portable ZIP creation exception: $_" -ForegroundColor Red
    exit 1
}

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

$OutputFiles = @()

if (-not $SkipInstaller) {
    $FinalInstaller = Get-ChildItem "$ScriptDir\installer_output\VideoCue-*-Setup.exe" | 
                      Sort-Object LastWriteTime -Descending | 
                      Select-Object -First 1
    
    if ($FinalInstaller) {
        $OutputFiles += $FinalInstaller
    }
}

$PortableZip = Get-ChildItem "$ScriptDir\installer_output\VideoCue-*-portable.zip" |
               Sort-Object LastWriteTime -Descending |
               Select-Object -First 1

if ($PortableZip) {
    $OutputFiles += $PortableZip
}

if ($OutputFiles.Count -gt 0) {
    Write-Host "Output files:" -ForegroundColor Green
    foreach ($file in $OutputFiles) {
        $size = $file.Length / 1MB
        Write-Host "  $($file.Name) ($([math]::Round($size, 2)) MB)" -ForegroundColor White
    }
    Write-Host "`nLocation: $ScriptDir\installer_output\" -ForegroundColor Gray
}

Write-Host ""
