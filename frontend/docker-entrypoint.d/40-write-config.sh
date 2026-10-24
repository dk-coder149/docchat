#!/bin/sh
# Container start hone par js/config.js likhta hai, API_BASE_URL environment variable se.
# Isse same image alag-alag jagah (local, cloud) bina rebuild ke chal jati hai.
set -eu

API="${API_BASE_URL:-http://localhost:8000}"
OUT="${CONFIG_OUT:-/usr/share/nginx/html/js/config.js}"

# JS string ke liye \ aur " ko escape karo
ESCAPED=$(printf '%s' "$API" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'window.APP_CONFIG = { API_BASE_URL: "%s" };\n' "$ESCAPED" > "$OUT"
echo "config.js written: API_BASE_URL=$API"
