#!/usr/bin/env bash
# Codex UserPromptSubmit hook: screenshot shorthand (`ss`, `[ss]`, `ss:`).

set -uo pipefail

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("prompt") or ""))' 2>/dev/null || true)

if ! echo "$PROMPT" | grep -qiE '(^\s*ss\s|^\s*ss$|\[ss\]|^\s*ss:)'; then
  exit 0
fi

SCREENSHOT_PATH="/tmp/screenshot-$(date +%s).png"
ICLOUD_SS_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/Screen Shots"
LAST_SERVED_FILE="/tmp/.codex-ss-last-served"
GOT_IMAGE=false
SOURCE=""

LAST_SERVED=""
if [ -f "$LAST_SERVED_FILE" ]; then
  LAST_SERVED=$(cat "$LAST_SERVED_FILE")
fi

if [ -d "$ICLOUD_SS_DIR" ]; then
  LATEST=$(find "$ICLOUD_SS_DIR" -maxdepth 1 -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" \) -newermt '2 minutes ago' -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1)
  if [ -n "$LATEST" ] && [ "$LATEST" != "$LAST_SERVED" ]; then
    cp "$LATEST" "$SCREENSHOT_PATH"
    echo "$LATEST" > "$LAST_SERVED_FILE"
    GOT_IMAGE=true
    SOURCE="iCloud ($(basename "$LATEST"))"
  fi
fi

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
    if [ -f "$SCREENSHOT_PATH" ]; then
      GOT_IMAGE=true
      SOURCE="clipboard"
    fi
  fi
fi

if [ "$GOT_IMAGE" = true ]; then
  ln -sf "$SCREENSHOT_PATH" /tmp/latest-screenshot.png
  jq -n --arg path "$SCREENSHOT_PATH" --arg source "$SOURCE" '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: ("SCREENSHOT HOOK FIRED. The user used screenshot shorthand. A screenshot was captured from " + $source + " at " + $path + ". Use the available image-viewing tool on that file before answering.")
    }
  }'
else
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "UserPromptSubmit",
      additionalContext: "SCREENSHOT HOOK FIRED but no fresh screenshot was found. Ask the user to take a screenshot, wait a few seconds for sync, then type ss again."
    }
  }'
fi
