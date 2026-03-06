#!/usr/bin/env bash
set -euo pipefail

# Build Linux release artifacts (AppImage + .deb) from PyInstaller output.
# Usage:
#   ./build_linux.sh --version 1.0.0
#   ./build_linux.sh --version 1.0.0 --skip-build

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

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: build_linux.sh must be run on Linux"
  exit 1
fi

if ! command -v appimagetool >/dev/null 2>&1; then
  echo "ERROR: appimagetool not found in PATH"
  echo "Install appimagetool or run the release workflow Linux job."
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "ERROR: dpkg-deb not found in PATH"
  echo "Install dpkg tooling (Debian/Ubuntu package: dpkg)."
  exit 1
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "[1/4] Building with PyInstaller"
  pyinstaller VideoCue.spec --clean --noconfirm
else
  echo "[1/4] Skipping PyInstaller build (--skip-build)"
fi

DIST_ROOT="dist/VideoCue"
DIST_EXE="${DIST_ROOT}/VideoCue"
ICON_SRC="resources/icon.png"
OUTPUT_DIR="installer_output"
APPIMAGE_PATH="${OUTPUT_DIR}/VideoCue-${VERSION}-x86_64.AppImage"
DEB_PATH="${OUTPUT_DIR}/VideoCue-${VERSION}-amd64.deb"
DEB_VERSION="${VERSION//-/.}"

if [[ ! -d "$DIST_ROOT" ]]; then
  echo "ERROR: Dist directory not found at ${DIST_ROOT}"
  exit 1
fi

if [[ ! -f "$DIST_EXE" ]]; then
  echo "ERROR: Expected executable not found at ${DIST_EXE}"
  exit 1
fi

if [[ ! -f "$ICON_SRC" ]]; then
  echo "ERROR: Expected icon not found at ${ICON_SRC}"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
TMP_DIR="$(mktemp -d)"
APPDIR="${TMP_DIR}/AppDir"
DEBROOT="${TMP_DIR}/debroot"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

create_launcher() {
  local target_file="$1"
  local app_root="$2"
  cat > "$target_file" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${app_root}/VideoCue" "\$@"
EOF
  chmod +x "$target_file"
}

create_desktop_entry() {
  local target_file="$1"
  cat > "$target_file" <<EOF
[Desktop Entry]
Type=Application
Name=VideoCue
Comment=VISCA-over-IP camera controller
Exec=videocue
Icon=videocue
Terminal=false
Categories=AudioVideo;Video;
EOF
}

echo "[2/4] Creating AppImage"
mkdir -p \
  "${APPDIR}/usr/lib/VideoCue" \
  "${APPDIR}/usr/bin" \
  "${APPDIR}/usr/share/applications" \
  "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

cp -a "${DIST_ROOT}/." "${APPDIR}/usr/lib/VideoCue/"
create_launcher "${APPDIR}/usr/bin/videocue" '${APPDIR}/usr/lib/VideoCue'
create_desktop_entry "${APPDIR}/usr/share/applications/videocue.desktop"
cp "$ICON_SRC" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/videocue.png"

cat > "${APPDIR}/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export APPDIR="$SCRIPT_DIR"
exec "$APPDIR/usr/bin/videocue" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

cp "${APPDIR}/usr/share/applications/videocue.desktop" "${APPDIR}/videocue.desktop"
cp "$ICON_SRC" "${APPDIR}/videocue.png"

ARCH=x86_64 appimagetool "${APPDIR}" "${APPIMAGE_PATH}"

echo "[3/4] Creating Debian package"
mkdir -p \
  "${DEBROOT}/DEBIAN" \
  "${DEBROOT}/opt/VideoCue" \
  "${DEBROOT}/usr/bin" \
  "${DEBROOT}/usr/share/applications" \
  "${DEBROOT}/usr/share/icons/hicolor/256x256/apps"

cp -a "${DIST_ROOT}/." "${DEBROOT}/opt/VideoCue/"
create_launcher "${DEBROOT}/usr/bin/videocue" "/opt/VideoCue"
create_desktop_entry "${DEBROOT}/usr/share/applications/videocue.desktop"
cp "$ICON_SRC" "${DEBROOT}/usr/share/icons/hicolor/256x256/apps/videocue.png"

cat > "${DEBROOT}/DEBIAN/control" <<EOF
Package: videocue
Version: ${DEB_VERSION}
Section: video
Priority: optional
Architecture: amd64
Maintainer: VideoCue Team <maintainers@videocue.local>
Depends: libc6 (>= 2.31), libstdc++6, libgl1, libx11-6, libxext6, libxrender1, libxkbcommon0
Description: VideoCue PTZ camera controller
 Multi-camera PTZ controller using VISCA-over-IP with optional NDI video streaming,
 USB game controller support, and Stream Deck integration.
EOF

chmod 0755 "${DEBROOT}/DEBIAN"
chmod 0644 "${DEBROOT}/DEBIAN/control"

dpkg-deb --build "${DEBROOT}" "${DEB_PATH}"

echo "[4/4] Build complete"
echo "AppImage: ${APPIMAGE_PATH}"
echo "Debian:   ${DEB_PATH}"
