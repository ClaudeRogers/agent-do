#!/bin/bash
# screenshot-capture.sh — UserPromptSubmit hook
# Detects screenshot intent and injects the latest Shottr screenshot.
# Triggers: "ss" at start of prompt, "[ss]" anywhere, or "ss:" anywhere
# Primary: iCloud-synced Shottr folder (reliable across SSH/tmux)
# Fallback: clipboard via osascript (if GUI session active)
#
# Safety: only uses screenshots < 2 min old AND not previously served.

set -uo pipefail

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""')

# Match: "ss " at start, "[ss]" anywhere, "ss:" anywhere
if ! echo "$PROMPT" | grep -qiE '(^\s*ss\s|^\s*ss$|\[ss\]|^\s*ss:)'; then
  exit 0
fi

SCREENSHOT_PATH="/tmp/screenshot-$(date +%s).png"
ICLOUD_SS_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Screen Shots"
LAST_SERVED_FILE="/tmp/.ss-last-served"
GOT_IMAGE=false
SOURCE=""

# Read last-served screenshot path (to avoid re-serving stale images)
LAST_SERVED=""
if [ -f "$LAST_SERVED_FILE" ]; then
  LAST_SERVED=$(cat "$LAST_SERVED_FILE")
fi

# Path 1 (primary): newest image in iCloud folder, < 2 min old, not already served
if [ -d "$ICLOUD_SS_DIR" ]; then
  LATEST=$(find "$ICLOUD_SS_DIR" -maxdepth 1 -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \) -newermt '2 minutes ago' -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1)

  if [ -n "$LATEST" ] && [ "$LATEST" != "$LAST_SERVED" ]; then
    cp "$LATEST" "$SCREENSHOT_PATH"
    echo "$LATEST" > "$LAST_SERVED_FILE"
    GOT_IMAGE=true
    SOURCE="iCloud ($(basename "$LATEST"))"
  fi
fi

# Path 2 (fallback): clipboard via osascript
if [ "$GOT_IMAGE" = false ]; then
  if osascript -e "
try
  set imgData to the clipboard as «class PNGf»
  set filePath to POSIX file \"$SCREENSHOT_PATH\"
  set fileRef to open for access filePath with write permission
  set eof fileRef to 0
  write imgData to fileRef
  close access fileRef
on error errMsg
  try
    close access (POSIX file \"$SCREENSHOT_PATH\")
  end try
  error errMsg
end try
" 2>/dev/null; then
    # Check clipboard image isn't the same as last served (by size comparison)
    if [ -f "$SCREENSHOT_PATH" ]; then
      NEW_SIZE=$(wc -c < "$SCREENSHOT_PATH")
      LAST_SIZE=0
      if [ -f /tmp/latest-screenshot.png ]; then
        LAST_SIZE=$(wc -c < /tmp/latest-screenshot.png)
      fi
      if [ "$NEW_SIZE" != "$LAST_SIZE" ]; then
        GOT_IMAGE=true
        SOURCE="clipboard"
      fi
    fi
  fi
fi

if [ "$GOT_IMAGE" = true ]; then
  ln -sf "$SCREENSHOT_PATH" /tmp/latest-screenshot.png

  jq -n --arg path "$SCREENSHOT_PATH" --arg source "$SOURCE" '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: ("SCREENSHOT HOOK FIRED. The user prefixed their message with \"ss\" meaning they want you to look at a screenshot. A screenshot has been captured from " + $source + " and saved to " + $path + ". YOU MUST use the Read tool to view this image file BEFORE doing anything else. The image is critical context for understanding what the user is asking about. Read the file now.")
    }
  }'
else
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: "SCREENSHOT HOOK FIRED but no fresh screenshot was found. Either iCloud has not synced yet or no screenshot was taken recently (must be < 2 minutes old). Tell the user: take a screenshot with Shottr, wait a few seconds for iCloud to sync to the Mac Studio, then type ss again."
    }
  }'
fi

exit 0
