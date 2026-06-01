#!/usr/bin/env bash
# Remove the plugin link + cache. Leaves SwiftBar installed (remove with
# `brew uninstall --cask swiftbar` if you want it gone too).
set -euo pipefail
PLUGIN_DIR="$HOME/.swiftbar-plugins"
rm -f "$PLUGIN_DIR/claude-usage.1m.py"
rm -f "$PLUGIN_DIR/.claude-usage-cache.json"
rm -rf "$PLUGIN_DIR/__pycache__"
open "swiftbar://refreshallplugins" >/dev/null 2>&1 || true
echo "✓ Plugin removed. (SwiftBar app left installed.)"
