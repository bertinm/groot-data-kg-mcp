#!/bin/bash

echo "Stopping containers..."

# Stop and remove containers
podman stop groot-mcp-server groot-graph-db 2>/dev/null || true
podman rm groot-mcp-server groot-graph-db 2>/dev/null || true

# Remove network
podman network rm groot-isolated-net 2>/dev/null || true

echo "Containers stopped and cleaned up."