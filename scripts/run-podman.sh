#!/bin/bash

# Create necessary directories
mkdir -p ./graph-memory ./logs

# Create isolated network if it doesn't exist
podman network exists groot-isolated-net || podman network create groot-isolated-net

# Run FalkorDB container
echo "Starting FalkorDB container..."
podman run -d \
  --name groot-graph-db \
  --network groot-isolated-net \
  -p 6379:6379 \
  -p 3000:3000 \
  -v ./graph-memory:/var/lib/falkordb/data:Z \
  -v ./logs:/var/log/falkordb:Z \
  --restart unless-stopped \
  falkordb/falkordb:latest

# Wait for FalkorDB to be ready
echo "Waiting for FalkorDB to be ready..."
sleep 10

# Build MCP server image
echo "Building MCP server image..."
podman build -t groot-mcp-server .

# Run MCP server container
echo "Starting MCP server container..."
podman run -d \
  --name groot-mcp-server \
  --network groot-isolated-net \
  -p 8888:8888 \
  -v ./logs:/app/logs:Z \
  -e FASTMCP_LOG_LEVEL=INFO \
  --restart unless-stopped \
  groot-mcp-server \
  uv run graph-memory-mcp-server \
  --backend falkordb \
  --falkor-host groot-graph-db \
  --falkor-port 6379 \
  --graph-name memory \
  --sse \
  --port 8888 \
  --log-level INFO

echo "Containers started successfully!"
echo "FalkorDB UI available at: http://localhost:3000"
echo "MCP Server SSE endpoint: http://localhost:8888"
echo "Logs directory: ./logs"