#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Install NDI SDK with proper detection and error handling
.DESCRIPTION
    Checks for existing NDI SDK installation, downloads if needed, detects installer type,
    and installs with appropriate parameters. Includes timeout handling and logging.
.PARAMETER DoNotDownload
    If specified, only checks for existing installation and fails if not found
.PARAMETER OutputDir
    Directory to copy DLL to after installation (optional)
.EXAMPLE
    .\Install-NDI-SDK.ps1
    .\Install-NDI-SDK.ps1 -DoNotDownload
    .\Install-NDI-SDK.ps1 -OutputDir "videocue/ndi_wrapper"
#>
param(
    [switch]$DoNotDownload,
    [string]$OutputDir
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

# ============================================================================
# Check for existing NDI SDK
# ============================================================================

Write-Info "Checking for existing NDI SDK installation..."

$ndiPaths = @(
    "C:\Program Files\NDI\NDI 6 SDK",
    "C:\NDI SDK 6",
    "C:\Program Files\NDI\NDI 6",
    "C:\Program Files\NewTek\NDI SDK",
    "C:\Program Files (x86)\NewTek\NDI SDK"
)

$ndiPath = $null
foreach ($path in $ndiPaths) {
    if (Test-Path "$path\Include\Processing.NDI.Lib.h") {
        Write-Success "NDI SDK found at: $path"
        $ndiPath = $path
        break
    }
}

# Check registry as fallback
if (-not $ndiPath) {
    try {
        $regPath = Get-ItemProperty "HKLM:\SOFTWARE\NewTek\NDI" -ErrorAction SilentlyContinue
        if ($regPath.PathToApp) {
            $candidatePath = $regPath.PathToApp
            if (Test-Path "$candidatePath\Include\Processing.NDI.Lib.h") {
                Write-Success "NDI SDK found (via registry): $candidatePath"
                $ndiPath = $candidatePath
            }
        }
    } catch {
        # Continue to download if not in registry
    }
}

# ============================================================================
# Download and Install if not found
# ============================================================================

if (-not $ndiPath) {
    if ($DoNotDownload) {
        Write-Error-Custom "NDI SDK not found and -DoNotDownload was specified"
        exit 1
    }

    Write-Info "NDI SDK not found locally. Downloading..."
    
    $ndiUrl = "https://downloads.ndi.tv/SDK/NDI_SDK/NDI%206%20SDK.exe"
    $ndiInstaller = "$env:TEMP\NDI_SDK_installer.exe"
    
    # Download NDI SDK
    try {
        Write-Host "Downloading from: $ndiUrl"
        Invoke-WebRequest -Uri $ndiUrl -OutFile $ndiInstaller -TimeoutSec 300 -ErrorAction Stop
        Write-Success "Downloaded to: $ndiInstaller"
        $installerSize = (Get-Item $ndiInstaller).Length / 1MB
        Write-Host "  Size: $([math]::Round($installerSize, 2)) MB"
    } catch {
        Write-Error-Custom "Failed to download NDI SDK: $_"
        exit 1
    }
    
    # Detect installer type
    Write-Info "Detecting installer type..."
    try {
        $fileSignature = Get-Content $ndiInstaller -AsByteStream -TotalCount 2000
        $stringContent = [System.Text.Encoding]::ASCII.GetString($fileSignature)
        
        if ($stringContent -match "Inno Setup") {
            Write-Host "Detected: Inno Setup installer"
            $installerType = "InnoSetup"
        } elseif ($stringContent -match "Nullsoft") {
            Write-Host "Detected: NSIS installer"
            $installerType = "NSIS"
        } elseif ($ndiInstaller -match "\.msi$") {
            Write-Host "Detected: MSI installer"
            $installerType = "MSI"
        } else {
            Write-Host "Unknown type, will try Inno Setup (most common)"
            $installerType = "InnoSetup"
        }
    } catch {
        Write-Host "Could not detect - assuming Inno Setup"
        $installerType = "InnoSetup"
    }
    
    # Set install parameters based on type
    switch ($installerType) {
        "InnoSetup" {
            $installArgs = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /DIR=`"C:\NDI SDK 6`" /LOG=`"$env:TEMP\ndi_install.log`""
        }
        "NSIS" {
            $installArgs = "/S /D=C:\NDI SDK 6"
        }
        "MSI" {
            $installArgs = "/quiet /qn /norestart /l*v `"$env:TEMP\ndi_install.log`" INSTALLDIR=`"C:\NDI SDK 6`""
        }
        default {
            $installArgs = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /DIR=`"C:\NDI SDK 6`" /LOG=`"$env:TEMP\ndi_install.log`""
        }
    }
    
    # Run installer
    Write-Info "Starting NDI SDK installation (timeout: 5 minutes)..."
    $logFile = "$env:TEMP\ndi_install.log"
    $process = Start-Process -FilePath $ndiInstaller -ArgumentList $installArgs -PassThru -NoNewWindow
    Write-Host "Installer PID: $($process.Id)"
    
    # Wait with timeout
    $timeout = 300
    $elapsed = 0
    $interval = 10
    
    while (-not $process.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds $interval
        $elapsed += $interval
        Write-Host "  ... waiting ($elapsed/$timeout seconds)"
    }
    
    if (-not $process.HasExited) {
        Write-Error-Custom "Installation timed out after $timeout seconds"
        $process.Kill()
        if (Test-Path $logFile) {
            Write-Host "`nInstallation log:"
            Get-Content $logFile | Select-Object -Last 20
        }
        exit 1
    }
    
    if ($process.ExitCode -ne 0) {
        Write-Error-Custom "Installation failed with exit code $($process.ExitCode)"
        if (Test-Path $logFile) {
            Write-Host "`nInstallation log:"
            Get-Content $logFile | Select-Object -Last 50
        }
        exit 1
    }
    
    Write-Success "NDI SDK installed successfully"
    
    # Verify installation
    $expectedPath = "C:\NDI SDK 6"
    if (Test-Path "$expectedPath\Include\Processing.NDI.Lib.h") {
        Write-Success "Installation verified"
        $ndiPath = $expectedPath
    } else {
        Write-Error-Custom "Installation could not be verified - headers not found"
        exit 1
    }
}

# ============================================================================
# Copy DLL if OutputDir specified
# ============================================================================

if ($OutputDir) {
    Write-Info "Copying NDI DLL to output directory..."
    
    # Find DLL (check multiple locations)
    $dllPaths = @(
        "$ndiPath\Bin\x64\Processing.NDI.Lib.x64.dll",
        "C:\Program Files\NDI\NDI 6 Runtime\v6\Processing.NDI.Lib.x64.dll",
        "$ndiPath\Lib\x64\Processing.NDI.Lib.x64.dll"
    )
    
    $dllFound = $false
    foreach ($dllPath in $dllPaths) {
        if (Test-Path $dllPath) {
            # Create output directory if needed
            New-Item -ItemType Directory -Force $OutputDir | Out-Null
            
            Copy-Item $dllPath "$OutputDir\Processing.NDI.Lib.x64.dll" -Force
            Write-Success "DLL copied to: $OutputDir"
            $dllFound = $true
            break
        }
    }
    
    if (-not $dllFound) {
        Write-Error-Custom "NDI DLL not found. Searched:"
        $dllPaths | ForEach-Object { Write-Host "  $_" }
        exit 1
    }
}

# ============================================================================
# Output NDI_PATH for use in other scripts
# ============================================================================

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Success "NDI SDK ready at: $ndiPath"
Write-Host "========================================`n" -ForegroundColor Cyan

# Set environment variable for downstream steps
$env:NDI_PATH = $ndiPath
echo "NDI_PATH=$ndiPath" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append -ErrorAction SilentlyContinue

exit 0
