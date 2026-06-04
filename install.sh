#!/usr/bin/env bash
# Installer for the Claude Usage SwiftBar plugin.
# Idempotent: safe to re-run. Installs SwiftBar if missing, links the plugin
# into SwiftBar's plugin folder, points SwiftBar at it, and reloads.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="claude-usage.1m.py"
PLUGIN_DIR="$HOME/.swiftbar-plugins"

echo "▶ Claude Usage SwiftBar — install"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "✗ macOS only (SwiftBar is a macOS menu-bar app)." >&2; exit 1
fi

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "✗ Homebrew not found. Install it from https://brew.sh then re-run." >&2; exit 1
fi

# 2. SwiftBar
if [[ ! -d "/Applications/SwiftBar.app" ]]; then
  echo "• Installing SwiftBar…"
  brew install --cask swiftbar
else
  echo "• SwiftBar already installed."
fi

# 2b. Pillow — used to render the menu-bar ring icon (plugin runs on Homebrew's
#     python3; without Pillow it falls back to a plain "NN%" text title).
if /opt/homebrew/bin/python3 -c "import PIL" >/dev/null 2>&1; then
  echo "• Pillow already installed."
else
  echo "• Installing Pillow…"
  brew install pillow
fi

# 3. Link the plugin (symlink so `git pull` updates it instantly)
mkdir -p "$PLUGIN_DIR"
ln -sf "$REPO_DIR/$PLUGIN" "$PLUGIN_DIR/$PLUGIN"
chmod +x "$REPO_DIR/$PLUGIN"
echo "• Linked $PLUGIN → $PLUGIN_DIR/"

# 4. Point SwiftBar at the folder
defaults write com.ameba.SwiftBar PluginDirectory "$PLUGIN_DIR" >/dev/null 2>&1 || true

# 5. Launch / reload
open -a SwiftBar >/dev/null 2>&1 || true
sleep 1
open "swiftbar://refreshallplugins" >/dev/null 2>&1 || true

cat <<'EOF'

✓ Installed.

First run only: macOS will show a Keychain prompt asking to access
"Claude Code-credentials" — click **Always Allow**. The menu bar will then
show your live plan usage as a circular ring with the 5-hour % inside.

If it shows a "⚠" estimate, open Claude Code once to refresh your auth token,
then click the menu-bar item → Refresh.
EOF
