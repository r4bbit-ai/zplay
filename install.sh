#!/usr/bin/env bash
# zplay installer (Arch Linux / any Linux with python3)
set -euo pipefail

RED=$'\e[38;2;226;106;156m'; DIM=$'\e[2m'; OFF=$'\e[0m'
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "${RED}◉ ゼットプレイ  zplay installer${OFF}"

if [[ "${1:-}" == "--system" ]]; then
  LIB=/usr/lib/zplay ; BIN=/usr/bin ; SUDO=sudo
else
  LIB="$HOME/.local/lib/zplay" ; BIN="$HOME/.local/bin" ; SUDO=""
fi

$SUDO mkdir -p "$LIB" "$BIN"
$SUDO rm -rf "$LIB/zplay"
$SUDO cp -r "$HERE/zplay" "$LIB/zplay"
$SUDO install -m755 "$HERE/bin/zplay" "$BIN/zplay"
echo "  installed: $BIN/zplay  (library: $LIB/zplay)"

# ---- dependencies -----------------------------------------------------------
missing=()
command -v mpv     >/dev/null || missing+=(mpv)
command -v ffmpeg  >/dev/null || missing+=(ffmpeg)
python3 -c 'import PIL'   2>/dev/null || missing+=(python-pillow)
python3 -c 'import numpy' 2>/dev/null || missing+=(python-numpy)

if ((${#missing[@]})); then
  echo "  ${DIM}missing packages: ${missing[*]}${OFF}"
  if command -v pacman >/dev/null; then
    read -rp "  install them with pacman now? [Y/n] " a
    [[ "${a:-y}" =~ ^[Yy]?$ ]] && sudo pacman -S --needed "${missing[@]}"
  fi
fi

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "  ${DIM}add to your shell rc:  export PATH=\"\$HOME/.local/bin:\$PATH\"${OFF}" ;;
esac

echo "  ${RED}done — run:  zplay${OFF}"
