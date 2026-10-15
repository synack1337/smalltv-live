#!/bin/sh
# Installs the SmallTV Live host on macOS for the current user:
#   Python environment   ~/Library/Application Support/SmallTV Live/venv
#   app launcher         ~/Applications/SmallTV Live.app
#   login agent          ~/Library/LaunchAgents/io.github.synack1337.smalltv-live.plist
#   config (if missing)  ~/.config/smalltv-live/config.toml
#   log                  ~/Library/Logs/SmallTV Live.log
# Re-running it updates an existing install. Needs Python 3.11+ and the Xcode command line tools.
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
LABEL=io.github.synack1337.smalltv-live
SUPPORT="$HOME/Library/Application Support/SmallTV Live"
VENV="$SUPPORT/venv"
APP="$HOME/Applications/SmallTV Live.app"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/smalltv-live"
PYTHON=${PYTHON:-python3}

say() { printf '==> %s\n' "$*"; }

"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || { echo "Python 3.11 or newer is required (set PYTHON=/path/to/python3)." >&2; exit 1; }
command -v clang >/dev/null || { echo "clang not found: run xcode-select --install" >&2; exit 1; }

say "Python environment"
mkdir -p "$SUPPORT"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$REPO/host/requirements.txt"
"$VENV/bin/python" -m pip install --quiet --no-deps "$REPO/host"

if [ ! -f "$CONFIG_DIR/config.toml" ]; then
  say "Config: $CONFIG_DIR/config.toml (edit it: TV address, location, language)"
  mkdir -p "$CONFIG_DIR"
  cp "$REPO/config.example.toml" "$CONFIG_DIR/config.toml"
  chmod 600 "$CONFIG_DIR/config.toml"
fi

say "App: $APP"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
pkill -f "$APP/Contents/MacOS/smalltv-live" 2>/dev/null || true
mkdir -p "$APP/Contents/MacOS"
cp "$REPO/macos/Info.plist" "$APP/Contents/Info.plist"
clang -O2 -Wall -Wextra -DPYTHON_PATH="\"$VENV/bin/python\"" \
  -o "$APP/Contents/MacOS/smalltv-live" "$REPO/macos/launcher.c"
codesign --force --sign - "$APP" >/dev/null 2>&1

say "Login agent: $AGENT"
mkdir -p "$(dirname "$AGENT")"
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-W</string>
    <string>-g</string>
    <string>$APP</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
</dict>
</plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$AGENT"

say "Done. On first start macOS asks to let \"SmallTV Live\" find devices on your local network: allow it."
say "If you missed it: System Settings > Privacy & Security > Local Network > SmallTV Live."
say "Log: $HOME/Library/Logs/SmallTV Live.log"
