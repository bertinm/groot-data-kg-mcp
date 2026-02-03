# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions
# and limitations under the License.
#
"""Graph Memory MCP Package

This package provides a comprehensive Model Context Protocol (MCP) server implementation
for managing knowledge graphs across multiple graph database backends. It supports
Amazon Neptune (Database and Analytics), FalkorDB, and provides semantic search
capabilities using vector embeddings.

Key modules:
- server: Main MCP server implementation with configurable operational modes
- memory: Knowledge graph management with CRUD operations and semantic search
- models: Data structures and type definitions for graph entities and relationships
- neptune_server: Amazon Neptune database interface (Database and Analytics)
- falkordb_server: FalkorDB (Redis-based) database interface
- graph_server: Abstract base class for database backend implementations

The package enables building intelligent agentic workflows with persistent memory
stored in graph databases, supporting both traditional graph queries and modern
semantic vector search capabilities.
"""

__version__ = '0.0.9'
__author__ = 'Graph Memory MCP Team'
__license__ = 'Apache License 2.0'

# Package metadata
__all__ = [
    'server',
    'memory',
    'models',
    'neptune_server',
    'falkordb_server',
    'graph_server',
]
