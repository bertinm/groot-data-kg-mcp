#!/bin/bash

# Test script to verify MCP server is working

echo "Testing MCP Server SSE endpoint..."

# Test if server is responding
curl -s -o /dev/null -w "%{http_code}" http://localhost:8888/health || echo "Server not responding"

echo ""
echo "Testing SSE connection..."

# Test SSE endpoint (this will show the SSE stream)
timeout 5s curl -N -H "Accept: text/event-stream" http://localhost:8888/sse 2>/dev/null || echo "SSE endpoint test completed"

echo ""
echo "Container status:"
podman ps --filter name=groot

echo ""
echo "Recent logs:"
echo "=== MCP Server ==="
podman logs --tail 10 groot-mcp-server 2>/dev/null || echo "MCP server container not running"

echo ""
echo "=== FalkorDB ==="
podman logs --tail 10 groot-graph-db 2>/dev/null || echo "FalkorDB container not running"