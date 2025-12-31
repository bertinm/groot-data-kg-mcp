FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8888

# Set environment variables for host binding
ENV UVICORN_HOST=0.0.0.0

# Set default command
CMD ["uv", "run", "graph-memory-mcp-server", "--backend", "falkordb", "--falkor-host", "groot-graph-db", "--sse", "--port", "8888"]