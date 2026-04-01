#!/bin/bash
# Aify Container installer for Claude Code
#
# Usage:
#   bash install.sh                          # default (localhost:8800)
#   bash install.sh http://192.168.1.5:8800  # custom server URL
#
# Registers the MCP server with Claude Code and installs dependencies.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_URL="${1:-http://localhost:8800}"

echo "=== aify-container installer ==="
echo "Repo: $SCRIPT_DIR"
echo "Server: $SERVER_URL"
echo ""

# Step 1: npm install
echo "[1/2] Installing MCP dependencies..."
cd "$SCRIPT_DIR/mcp/stdio"
npm install --silent 2>/dev/null
cd "$SCRIPT_DIR"
echo "  Done."

# Step 2: Register MCP server
echo "[2/2] Registering MCP server with Claude Code..."
SERVICE_NAME=$(node -e "try{console.log(JSON.parse(require('fs').readFileSync('$SCRIPT_DIR/.claude-plugin/plugin.json','utf-8')).name)}catch{console.log('aify-service')}" 2>/dev/null)
claude mcp remove "$SERVICE_NAME" 2>/dev/null || true
claude mcp add --scope user "$SERVICE_NAME" \
  -e SERVICE_API_URL="$SERVER_URL" \
  -- node "$SCRIPT_DIR/mcp/stdio/server.js"
echo "  Done."

echo ""
echo "=== Installation complete ==="
echo "Restart Claude Code for changes to take effect."
