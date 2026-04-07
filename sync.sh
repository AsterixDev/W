#!/usr/bin/env bash
# sync.sh — keeps this folder up to date with the remote repo automatically.
# Run once to install; after that it works silently in the background.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.user.w-autosync"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

# ── Install ────────────────────────────────────────────────────────────────────

install() {
    echo "Installing auto-sync for: $REPO_DIR"

    mkdir -p "$HOME/Library/LaunchAgents"

    cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$PLIST_NAME</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>git -C "$REPO_DIR" pull --ff-only --quiet 2>&1 | logger -t w-autosync</string>
  </array>

  <!-- Check for updates every 60 seconds -->
  <key>StartInterval</key>
  <integer>60</integer>

  <key>RunAtLoad</key>
  <true/>

  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/w-autosync.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/w-autosync.log</string>
</dict>
</plist>
PLIST

    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
    echo "Done. Files in $REPO_DIR will now sync automatically every 60 seconds."
    echo "Logs: $HOME/Library/Logs/w-autosync.log"
}

# ── Uninstall ──────────────────────────────────────────────────────────────────

uninstall() {
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "Auto-sync removed."
}

# ── Status ─────────────────────────────────────────────────────────────────────

status() {
    if launchctl list | grep -q "$PLIST_NAME"; then
        echo "Auto-sync is RUNNING"
        echo "Repo: $REPO_DIR"
        echo "Logs: tail -f $HOME/Library/Logs/w-autosync.log"
    else
        echo "Auto-sync is NOT running. Run: bash sync.sh install"
    fi
}

# ── Entry point ────────────────────────────────────────────────────────────────

case "${1:-install}" in
    install)   install   ;;
    uninstall) uninstall ;;
    status)    status    ;;
    *)
        echo "Usage: bash sync.sh [install|uninstall|status]"
        echo "  install   — start auto-syncing (default)"
        echo "  uninstall — stop auto-syncing"
        echo "  status    — check if it's running"
        ;;
esac
