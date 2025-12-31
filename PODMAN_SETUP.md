# MCP Server with FalkorDB - Podman Setup

This setup allows you to run the MCP Server in SSE mode with FalkorDB using Podman containers with persistent logging.

## Quick Start

1. **Start the services:**
   ```bash
   ./scripts/run-podman.sh
   ```

2. **Test the setup:**
   ```bash
   # Test FalkorDB UI
   curl -s http://localhost:3000 | head -5
   
   # Test MCP server endpoint
   curl -H "Accept: text/event-stream" http://localhost:8888/mcp
   ```

3. **View logs:**
   ```bash
   # View MCP server logs
   podman logs groot-mcp-server
   
   # View FalkorDB logs
   podman logs groot-graph-db
   
   # View persistent log files in ./logs directory
   ls -la ./logs/
   ```

4. **Stop the services:**
   ```bash
   ./scripts/stop-podman.sh
   ```

## Services

### FalkorDB Container
- **Name:** `groot-graph-db`
- **Ports:** 
  - `6379` - FalkorDB Redis protocol
  - `3000` - FalkorDB Browser UI
- **Data persistence:** `./graph-memory` directory
- **Logs:** `./logs` directory

### MCP Server Container
- **Name:** `groot-mcp-server`
- **Port:** `8888` - SSE endpoint
- **Logs:** `./logs` directory
- **Backend:** FalkorDB

## Endpoints

- **FalkorDB Browser UI:** http://localhost:3000
- **MCP Server Endpoint:** http://localhost:8888/mcp (requires SSE headers and session ID)
- **Container Status Check:** `podman ps --filter name=groot`

## Directory Structure

```
./
├── graph-memory/          # FalkorDB data persistence
├── logs/                  # Application logs
├── scripts/
│   ├── run-podman.sh     # Start services
│   ├── stop-podman.sh    # Stop services
│   ├── logs.sh           # View logs
│   └── test-mcp.sh       # Test setup
├── Dockerfile            # MCP server image
└── docker-compose.yml    # Alternative docker-compose setup
```

## Configuration

### Environment Variables
- `FASTMCP_LOG_LEVEL`: Set logging level (INFO, DEBUG, ERROR)

### MCP Server Arguments
- `--backend falkordb`: Use FalkorDB backend
- `--falkor-host groot-graph-db`: FalkorDB container hostname
- `--falkor-port 6379`: FalkorDB port
- `--graph-name memory`: Graph database name
- `--sse`: Enable SSE transport
- `--port 8888`: Server port
- `--log-level INFO`: Logging level

### Host Binding
- The server is configured to bind to `0.0.0.0:8888` inside the container for external access
- Environment variable `UVICORN_HOST=0.0.0.0` ensures proper host binding
- Port 8888 is exposed and mapped to localhost:8888

## Troubleshooting

### Check container status
```bash
podman ps --filter name=groot
```

### View container logs
```bash
podman logs groot-mcp-server
podman logs groot-graph-db
```

### Test connectivity
```bash
# Test FalkorDB
curl -s http://localhost:3000 | head -5

# Test MCP server (should return JSON error about missing session ID)
curl -H "Accept: text/event-stream" http://localhost:8888/mcp
```

### Restart services
```bash
./scripts/stop-podman.sh
./scripts/run-podman.sh
```

### Network issues
```bash
# Check network
podman network ls
podman network inspect groot-isolated-net

# Recreate network if needed
podman network rm groot-isolated-net
podman network create groot-isolated-net
```

### Common Issues

1. **Server binding to 127.0.0.1**: Fixed by setting `UVICORN_HOST=0.0.0.0` environment variable
2. **Missing README.md during build**: Fixed by including README.md in Dockerfile COPY command
3. **Container registry errors**: Use full registry paths like `docker.io/falkordb/falkordb:latest`

## Using with Kiro

Add to your MCP configuration (`.kiro/settings/mcp.json` or `~/.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "falkor-memory": {
      "command": "curl",
      "args": ["-N", "-H", "Accept: text/event-stream", "http://localhost:8888/mcp"],
      "env": {
        "FASTMCP_LOG_LEVEL": "INFO"
      },
      "disabled": false,
      "autoApprove": ["get_memory_server_status", "read_memory", "search_memory"]
    }
  }
}
```

**Note**: The MCP server uses the `/mcp` endpoint, not `/sse`. The server expects SSE headers and will handle session management automatically.

## Manual Podman Commands

If you prefer to run commands manually:

```bash
# Create network
podman network create groot-isolated-net

# Run FalkorDB
podman run -d \
  --name groot-graph-db \
  --network groot-isolated-net \
  -p 6379:6379 -p 3000:3000 \
  -v ./graph-memory:/var/lib/falkordb/data:Z \
  -v ./logs:/var/log/falkordb:Z \
  falkordb/falkordb

# Build and run MCP server
podman build -t groot-mcp-server .
podman run -d \
  --name groot-mcp-server \
  --network groot-isolated-net \
  -p 8888:8888 \
  -v ./logs:/app/logs:Z \
  -e UVICORN_HOST=0.0.0.0 \
  groot-mcp-server \
  uv run graph-memory-mcp-server \
  --backend falkordb \
  --falkor-host groot-graph-db \
  --sse --port 8888 \
  --log-level INFO
```