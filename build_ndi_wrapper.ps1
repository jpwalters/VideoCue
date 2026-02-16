#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build NDI Python bindings from C++ source
.DESCRIPTION
    Builds the NDI wrapper (videocue/ndi_wrapper/src/main.cpp) using CMake and Visual Studio.
    Generates .pyd files for Python 3.10 and/or 3.12.
.PARAMETER PythonVersion
    Target Python version: "3.10", "3.12", or "all" (default: current environment)
.PARAMETER Clean
    Remove build artifacts before building
.PARAMETER Verbose
    Show detailed build output
.PARAMETER NDIPath
    Path to NDI SDK (auto-detected if not specified)
.EXAMPLE
    .\build_ndi_wrapper.ps1
    # Builds for current Python version
    
    .\build_ndi_wrapper.ps1 -PythonVersion 3.12
    # Builds specifically for Python 3.12
    
    .\build_ndi_wrapper.ps1 -PythonVersion all -Clean
    # Clean build for Python 3.10 and 3.12
#>

param(
    [ValidateSet('3.10', '3.12', 'all')]
    [string]$PythonVersion = 'auto',
    
    [switch]$Clean,
    [switch]$Verbose,
    [string]$NDIPath
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Section {
    param([string]$Title)
    Write-Host "`n" -NoNewline
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Test-Prerequisite {
    param(
        [string]$Name,
        [scriptblock]$Test,
        [string]$Website = $null
    )
    
    Write-Host "  Checking $Name... " -NoNewline
    
    try {
        $result = & $Test
        if ($result) {
            Write-Success $result
            return $true
        } else {
            Write-Error-Custom "Not found"
            if ($Website) {
                Write-Host "    Download from: $Website" -ForegroundColor Yellow
            }
            return $false
        }
    } catch {
        Write-Error-Custom "Error: $($_.Exception.Message)"
        return $false
    }
}

function Get-MSVCVersion {
    $vs2022Path = "C:\Program Files\Microsoft Visual Studio\2022"
    $vs2019Path = "C:\Program Files (x86)\Microsoft Visual Studio\2019"
    
    if (Test-Path $vs2022Path) {
        return @{ Version = "2022"; Generator = "Visual Studio 17 2022"; Path = $vs2022Path }
    }
    if (Test-Path $vs2019Path) {
        return @{ Version = "2019"; Generator = "Visual Studio 16 2019"; Path = $vs2019Path }
    }
    return $null
}

function Get-Python-Executable {
    param([string]$Version)
    
    if ($Version -eq 'auto') {
        return (Get-Command python -ErrorAction SilentlyContinue).Source
    }
    
    # Try common Python install locations
    $paths = @(
        "C:\Python$($Version.Replace('.', ''))\python.exe",
        "C:\Program Files\Python$($Version.Replace('.', ''))\python.exe",
        "C:\Program Files (x86)\Python$($Version.Replace('.', ''))\python.exe"
    )
    
    foreach ($path in $paths) {
        if (Test-Path $path) {
            return $path
        }
    }
    
    # Try py launcher
    $pyExe = (Get-Command py -ErrorAction SilentlyContinue).Source
    if ($pyExe) {
        $pyVersion = & $pyExe -$Version --version 2>&1
        if ($pyVersion -match 'Python') {
            return "$pyExe -$Version"
        }
    }
    
    return $null
}

function Find-NDI-SDK {
    if ($NDIPath -and (Test-Path $NDIPath)) {
        return $NDIPath
    }
    
    # Common NDI installation paths
    $paths = @(
        "C:\Program Files\NDI\NDI 6 SDK",
        "C:\NDI SDK 6",
        "C:\Program Files\NDI\NDI 6",
        "C:\Program Files\NewTek\NDI SDK",
        "C:\Program Files (x86)\NewTek\NDI SDK"
    )
    
    foreach ($path in $paths) {
        if (Test-Path "$path\Include\Processing.NDI.Lib.h") {
            return $path
        }
    }
    
    # Check registry
    $regPath = Get-ItemProperty "HKLM:\SOFTWARE\NewTek\NDI" -ErrorAction SilentlyContinue
    if ($regPath.PathToApp) {
        return $regPath.PathToApp
    }
    
    # Try downloading NDI SDK as fallback
    Write-Host "`n[INFO] NDI SDK not found locally. Attempting to download..." -ForegroundColor Yellow
    $ndiInstallerPath = "$env:TEMP\NDI_SDK_installer.exe"
    $ndiUrl = "https://get.ndi.video/e/1092312/SDK-NDI-SDK-NDI20620SDK-exe/lygzhs/2113259237/h/_EdCdLDbOZNnTUt1jV6oEEaEJSSk9VwcAM4agxRzmYs"
    
    try {
        Write-Host "Downloading NDI SDK from get.ndi.video..."
        Invoke-WebRequest -Uri $ndiUrl -OutFile $ndiInstallerPath -TimeoutSec 300 -ErrorAction Stop
        Write-Success "Downloaded to $ndiInstallerPath"
        
        Write-Host "Installing NDI SDK (this may take a few minutes)..."
        & $ndiInstallerPath /S /D="C:\NDI SDK 6" | Out-Null
        Start-Sleep -Seconds 5
        
        if (Test-Path "C:\NDI SDK 6\Include\Processing.NDI.Lib.h") {
            Write-Success "NDI SDK installed successfully at C:\NDI SDK 6"
            return "C:\NDI SDK 6"
        }
    } catch {
        Write-Host "Download/install failed: $_" -ForegroundColor DarkGray
    }
    
    return $null
}

# ============================================================================
# MAIN SCRIPT
# ============================================================================

Write-Section "NDI Wrapper Build Script"

# Determine working directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wrapperDir = Join-Path (Join-Path $scriptDir "videocue") "ndi_wrapper"
$buildDir = Join-Path $wrapperDir "build"

Write-Host "Wrapper directory: $wrapperDir"
Write-Host "Build directory:   $buildDir"

# Check prerequisites
Write-Section "Checking Prerequisites"

$prereqsOK = $true

# Check Python
if ($PythonVersion -eq 'auto' -or $PythonVersion -eq 'all') {
    $pyExe = Get-Python-Executable 'auto'
    if ($pyExe) {
        Write-Success "Python: $pyExe"
    } else {
        Write-Error-Custom "Python not found"
        $prereqsOK = $false
    }
} else {
    $pyExe = Get-Python-Executable $PythonVersion
    if ($pyExe) {
        Write-Success "Python $PythonVersion`:`n    $pyExe"
    } else {
        Write-Error-Custom "Python $PythonVersion not found"
        $prereqsOK = $false
    }
}

# Check CMake
$cmakePath = Get-Command cmake -ErrorAction SilentlyContinue
if ($cmakePath) {
    $cmakeVersion = & cmake --version | Select-Object -First 1
    Write-Success $cmakeVersion
} else {
    Write-Error-Custom "CMake not found"
    Write-Host "    Download from: https://cmake.org/download/" -ForegroundColor Yellow
    Write-Host "    Or install via: choco install cmake" -ForegroundColor Yellow
    $prereqsOK = $false
}

# Check Visual Studio
$vs = Get-MSVCVersion
if ($vs) {
    Write-Success "Visual Studio $($vs.Version) found`n    Generator: $($vs.Generator)"
} else {
    Write-Error-Custom "Visual Studio 2019+ not found"
    Write-Host "    Download from: https://visualstudio.microsoft.com/downloads/" -ForegroundColor Yellow
    $prereqsOK = $false
}

# Check NDI SDK
$ndiPath = Find-NDI-SDK
if ($ndiPath) {
    Write-Success "NDI SDK found`n    $ndiPath"
} else {
    Write-Error-Custom "NDI SDK not found"
    Write-Host "    Download from: https://ndi.tv/tools/" -ForegroundColor Yellow
    $prereqsOK = $false
}

# Check pybind11
if ($pyExe) {
    $pybind11Dir = & $pyExe -c 'import pybind11; print(pybind11.get_cmake_dir())' 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "pybind11 module found"
        Write-Host "    CMake dir: $pybind11Dir" -ForegroundColor Gray
    } else {
        Write-Error-Custom "pybind11 not installed"
        Write-Host "    Install via: pip install pybind11" -ForegroundColor Yellow
        $prereqsOK = $false
    }
}

if (-not $prereqsOK) {
    Write-Host "`n" -NoNewline
    Write-Error-Custom "Prerequisites check failed. Please install missing components."
    exit 1
}

# Clean if requested
if ($Clean) {
    Write-Section "Cleaning Build Artifacts"
    if (Test-Path $buildDir) {
        Remove-Item $buildDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Success "Removed build directory"
    }
}

# Create build directory
if (-not (Test-Path $buildDir)) {
    New-Item $buildDir -ItemType Directory -Force | Out-Null
    Write-Success "Created build directory"
}

# Configure CMake
Write-Section "Configuring CMake"

$configCmd = @(
    "cmake ..",
    "-G `"$($vs.Generator)`"",
    "-A x64",
    "-DNDI_PATH=`"$ndiPath`"",
    "-Dpybind11_DIR=`"$pybind11Dir`"",
    "-DCMAKE_BUILD_TYPE=Release"
)

if ($Verbose) {
    $configCmd += "--debug-output"
}

$configCmdStr = $configCmd -join " "
Write-Host "Command: $configCmdStr" -ForegroundColor DarkGray

Push-Location $buildDir
try {
    Invoke-Expression $configCmdStr
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "CMake configuration failed"
        exit 1
    }
    Write-Success "CMake configuration completed"
} finally {
    Pop-Location
}

# Build
Write-Section "Building NDI Wrapper"

$buildCmd = @(
    "cmake --build . --config Release"
)

if ($Verbose) {
    $buildCmd += "--verbose"
}

$buildCmdStr = $buildCmd -join " "
Write-Host "Command: $buildCmdStr" -ForegroundColor DarkGray

Push-Location $buildDir
try {
    Invoke-Expression $buildCmdStr
    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "Build failed"
        exit 1
    }
    Write-Success "Build completed"
} finally {
    Pop-Location
}

# Find and copy output
Write-Section "Installing Build Output"

$pydFiles = @()
$pydFiles += Get-ChildItem $buildDir -Filter "NDIlib.cp*.pyd" -Recurse -ErrorAction SilentlyContinue
$pydFiles += Get-ChildItem $buildDir -Filter "NDIlib*.pyd" -Recurse -ErrorAction SilentlyContinue

if ($pydFiles.Count -eq 0) {
    Write-Error-Custom "No .pyd files found in build directory"
    Write-Host "`nBuild output location: $buildDir" -ForegroundColor Yellow
    Get-ChildItem $buildDir -Recurse | Select-Object -ExpandProperty FullName | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
    exit 1
}

foreach ($pydFile in $pydFiles) {
    $destPath = Join-Path $wrapperDir (Split-Path -Leaf $pydFile.FullName)
    Copy-Item $pydFile.FullName $destPath -Force
    Write-Success "Installed: $(Split-Path -Leaf $pydFile.FullName)"
    Write-Host "           Size: $([math]::Round($pydFile.Length / 1KB)) KB" -ForegroundColor Gray
}

# Final verification
Write-Section "Verification"

Write-Host "Checking compiled bindings in $wrapperDir`:`n"

$pydFiles = Get-ChildItem $wrapperDir -Filter "NDIlib*.pyd" -ErrorAction SilentlyContinue
if ($pydFiles) {
    foreach ($pyd in $pydFiles) {
        $size = [math]::Round($pyd.Length / 1KB)
        $message = "{0} ({1} KB)" -f $pyd.Name, $size
        Write-Success $message
    }
    Write-Host "`n"
    Write-Host "[SUCCESS] NDI wrapper build successful!" -ForegroundColor Green
    Write-Host "`nTo use the rebuilt bindings, restart your Python interpreter or reinstall the package.`n"
} else {
    Write-Error-Custom "No .pyd files found in wrapper directory"
    exit 1
}

exit 0
