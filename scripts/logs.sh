#!/bin/bash

# Script to view logs from different sources

case "$1" in
  "mcp"|"server")
    echo "=== MCP Server Logs ==="
    podman logs -f groot-mcp-server
    ;;
  "falkor"|"db")
    echo "=== FalkorDB Logs ==="
    podman logs -f groot-graph-db
    ;;
  "file"|"files")
    echo "=== Log Files ==="
    echo "Available log files in ./logs/:"
    ls -la ./logs/
    if [ -n "$2" ]; then
      echo "=== Viewing $2 ==="
      tail -f "./logs/$2"
    fi
    ;;
  *)
    echo "Usage: $0 {mcp|server|falkor|db|file|files} [filename]"
    echo ""
    echo "Examples:"
    echo "  $0 mcp          # View MCP server container logs"
    echo "  $0 falkor       # View FalkorDB container logs"
    echo "  $0 file         # List available log files"
    echo "  $0 file app.log # View specific log file"
    exit 1
    ;;
esac