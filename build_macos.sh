#!/usr/bin/env bash
set -euo pipefail

# Build an unsigned macOS DMG from the PyInstaller app bundle.
# Usage:
#   ./build_macos.sh --version 1.0.0
#   ./build_macos.sh --version 1.0.0 --skip-build

VERSION=""
SKIP_BUILD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    -h|--help)
      echo "Usage: $0 --version <version> [--skip-build]"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1"
      echo "Usage: $0 --version <version> [--skip-build]"
      exit 1
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "ERROR: --version is required"
  echo "Usage: $0 --version <version> [--skip-build]"
  exit 1
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "[1/3] Building app bundle with PyInstaller"
  pyinstaller VideoCue.spec --clean --noconfirm
else
  echo "[1/3] Skipping PyInstaller build (--skip-build)"
fi

echo "[2/3] Resolving app bundle path"
APP_PATH="dist/VideoCue/VideoCue.app"
if [[ ! -d "$APP_PATH" ]]; then
  APP_PATH="dist/VideoCue.app"
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "ERROR: VideoCue.app not found in expected locations"
  echo "Checked: dist/VideoCue/VideoCue.app and dist/VideoCue.app"
  exit 1
fi

mkdir -p installer_output
DMG_PATH="installer_output/VideoCue-${VERSION}-macOS.dmg"

echo "[3/3] Creating DMG: ${DMG_PATH}"
hdiutil create -volname "VideoCue" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"

echo "Build complete: ${DMG_PATH}"
