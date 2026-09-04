#!/bin/bash
set -euo pipefail
curl --fail --location --retry 3 \
  https://github.com/KiCad/kicad-source-mirror/releases/download/10.0.6/kicad-unified-universal-10.0.6.dmg \
  -o "$RUNNER_TEMP/kicad.dmg"
mkdir -p "$RUNNER_TEMP/kicad-mount" "$RUNNER_TEMP/kicad-install"
hdiutil attach "$RUNNER_TEMP/kicad.dmg" -nobrowse -mountpoint "$RUNNER_TEMP/kicad-mount"
rsync -a "$RUNNER_TEMP/kicad-mount/" "$RUNNER_TEMP/kicad-install/"
hdiutil detach "$RUNNER_TEMP/kicad-mount"
python3 tests/ci/find_kicad_python.py "$RUNNER_TEMP/kicad-install"
