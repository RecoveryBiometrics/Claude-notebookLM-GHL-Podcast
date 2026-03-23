#!/bin/bash
# Setup GHL Podcast Pipeline on macOS
# Run once after NotebookLM login is complete

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.ghl.podcast-scheduler"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== GHL Podcast Pipeline — Mac Setup ==="
echo ""

# 1. Ensure logs dir exists
mkdir -p "$SCRIPT_DIR/logs"

# 2. Prevent Mac from sleeping on AC power
echo "Step 1: Disabling sleep on AC power (requires sudo)..."
sudo pmset -c sleep 0
sudo pmset -c disablesleep 1
echo "  ✓ Mac will stay awake while plugged in"
echo ""

# 3. Install launchd plist
echo "Step 2: Installing launchd service..."
# Unload if already loaded
launchctl bootout gui/$(id -u) "$PLIST_DST" 2>/dev/null || true
cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootstrap gui/$(id -u) "$PLIST_DST"
echo "  ✓ Scheduler installed and started"
echo ""

# 4. Verify
echo "Step 3: Verifying..."
sleep 2
if launchctl print gui/$(id -u)/$PLIST_NAME 2>/dev/null | grep -q "state = running"; then
    echo "  ✓ Scheduler is running!"
else
    echo "  ⚠ Scheduler loaded but may not be running yet. Check:"
    echo "    launchctl print gui/$(id -u)/$PLIST_NAME"
fi
echo ""

echo "=== Setup Complete ==="
echo ""
echo "The scheduler will:"
echo "  - Run every 25 hours automatically"
echo "  - Restart if it crashes"
echo "  - Start on login"
echo "  - Keep running with Mac plugged in (even lid closed)"
echo ""
echo "Monitor: tail -f $SCRIPT_DIR/logs/scheduler.log"
echo "Stop:    launchctl bootout gui/$(id -u) $PLIST_DST"
echo "Start:   launchctl bootstrap gui/$(id -u) $PLIST_DST"
