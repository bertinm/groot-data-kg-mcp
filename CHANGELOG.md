# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of WS Memory MCP Server
- Support for Amazon Neptune (Database and Analytics) backends
- Support for FalkorDB (Redis-based) backend
- Semantic vector search using sentence transformers
- Multiple operational modes (read, write, full)
- Docker and container deployment support
- Comprehensive MCP tool interface
- Knowledge graph CRUD operations
- Graph traversal with depth control

### Changed
- Renamed from `graph-memory-mcp-server` to `ws-memory-mcp-server`
- Improved file naming consistency for database backends

### Fixed
- Corrected command names in documentation
- Fixed import paths after file renaming
- Resolved linting and formatting issues

## [0.0.9] - 2024-XX-XX

### Added
- Initial project structure
- Basic MCP server implementation
- Neptune and FalkorDB backend support
- Vector search capabilities
- Docker deployment configuration

[Unreleased]: https://github.com/your-org/ws-memory-mcp-server/compare/v0.0.9...HEAD
[0.0.9]: https://github.com/your-org/ws-memory-mcp-server/releases/tag/v0.0.9