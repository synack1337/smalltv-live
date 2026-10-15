#!/bin/sh
# Removes what install.sh created. The config in ~/.config/smalltv-live is kept.
set -u
LABEL=io.github.synack1337.smalltv-live
APP="$HOME/Applications/SmallTV Live.app"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
pkill -f "$APP/Contents/MacOS/smalltv-live" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
rm -rf "$APP" "$HOME/Library/Application Support/SmallTV Live"
echo "SmallTV Live removed. Config kept in ${XDG_CONFIG_HOME:-$HOME/.config}/smalltv-live."
