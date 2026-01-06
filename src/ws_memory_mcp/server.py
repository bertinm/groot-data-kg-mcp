#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance
# with the License. A copy of the License is located at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions
# and limitations under the License.
#
"""Neptune Memory Server Module

This module implements a Model Context Protocol (MCP) server that provides access to a memory system
stored in Amazon Neptune graph database. It enables creation, reading, and searching of entities
and relations in the knowledge graph.

The server exposes various tools through FastMCP for managing the knowledge graph operations.
"""

import argparse
import logging
from mcp.server.fastmcp import FastMCP
from typing import List
from ws_memory_mcp.falkordb_server import FalkorDBServer
from ws_memory_mcp.memory import KnowledgeGraphManager
from ws_memory_mcp.models import Entity, Relation
from ws_memory_mcp.neptune import NeptuneServer


logger = logging.getLogger(__name__)

# Global variables for graph database connection (will be initialized in main)
graph = None
memory = None


mcp = FastMCP(
    'Memory',
    instructions="""
    This provides access to a memory for an agentic workflow stored in a graph database (Neptune or FalkorDB).
    """,
    dependencies=[
        'langchain-aws',
        'mcp[cli]',
        'falkordb',
    ],
)


@mcp.tool(name='get_memory_server_status')
def get_status() -> str:
    """Retrieve the current status of the graph database memory server.

    Returns:
        str: The status information of the graph database server instance.
    """
    return graph.status()


@mcp.tool(
    name='create_entities',
    description='Create multiple new entities in the knowledge graph',
)
def create_entities(entities: List[Entity]) -> str:
    """Create multiple new entities in the knowledge graph.

    Args:
        entities (List[Entity]): A list of Entity objects to be created in the graph.

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    result = memory.create_entities_with_ids(entities)
    return f'Successfully created {len(result)} entities.'


@mcp.tool(
    name='create_relations',
    description='Create multiple new relations between entities in the knowledge graph. Relations should be in active voice',
)
def create_relations(relations: List[Relation]) -> str:
    """Create multiple new relations between entities in the knowledge graph.

    Args:
        relations (List[Relation]): A list of Relation objects defining connections
                                  between entities. Relations should be in active voice.

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    result = memory.create_relations(relations)
    return f'Successfully created {len(result)} relations.'


@mcp.tool(name='read_memory', description='Read the memory knowledge graph')
def read_graph() -> dict:
    """Read the entire memory knowledge graph.

    Returns:
        dict: A dictionary containing all entities and relations in the memory graph.
    """
    graph = memory.read_graph()
    return {
        'entities': [
            {
                'name': e.name,
                'type': e.type,
                'observations': e.observations,
                'id': getattr(e, 'id', None),
                'created_at': getattr(e, 'created_at', None),
                'last_modified': getattr(e, 'last_modified', None),
                'metadata': getattr(e, 'metadata', {}),
            }
            for e in graph.entities
        ],
        'relations': [
            {
                'source': r.source,
                'target': r.target,
                'relationType': r.relationType,
                'id': getattr(r, 'id', None),
                'source_id': getattr(r, 'source_id', None),
                'target_id': getattr(r, 'target_id', None),
                'created_at': getattr(r, 'created_at', None),
                'properties': getattr(r, 'properties', {}),
            }
            for r in graph.relations
        ],
    }


@mcp.tool(
    name='search_memory',
    description='Search the memory knowledge graph for a specific entity name',
)
def search_graph(query: str) -> dict:
    """Search the memory knowledge graph for entities matching a specific name.

    Args:
        query (str): The search query string to match against entity names only (not observations).
                    Empty queries return no results.

    Returns:
        dict: A dictionary containing the matching entities and their relations.
    """
    graph = memory.search_nodes(query)
    return {
        'entities': [
            {
                'name': e.name,
                'type': e.type,
                'observations': e.observations,
                'id': getattr(e, 'id', None),
                'created_at': getattr(e, 'created_at', None),
                'last_modified': getattr(e, 'last_modified', None),
                'metadata': getattr(e, 'metadata', {}),
            }
            for e in graph.entities
        ],
        'relations': [
            {
                'source': r.source,
                'target': r.target,
                'relationType': r.relationType,
                'id': getattr(r, 'id', None),
                'source_id': getattr(r, 'source_id', None),
                'target_id': getattr(r, 'target_id', None),
                'created_at': getattr(r, 'created_at', None),
                'properties': getattr(r, 'properties', {}),
            }
            for r in graph.relations
        ],
    }


# ID-based operations
@mcp.tool(name='get_entity_by_id', description='Get an entity by its unique ID')
def get_entity_by_id(entity_id: str) -> dict:
    """Get an entity by its unique ID.

    Args:
        entity_id (str): Unique ID of the entity to retrieve

    Returns:
        dict: Entity data if found, or error message if not found
    """
    entity = memory.get_entity_by_id(entity_id)
    if entity:
        return {
            'id': entity.id,
            'name': entity.name,
            'type': entity.type,
            'observations': entity.observations,
            'created_at': getattr(entity, 'created_at', None),
            'last_modified': getattr(entity, 'last_modified', None),
            'metadata': getattr(entity, 'metadata', {}),
        }
    else:
        return {'error': f"Entity with ID '{entity_id}' not found"}


@mcp.tool(
    name='update_entity_by_id',
    description='Update any attributes of an entity by its unique ID',
)
def update_entity_by_id(entity_id: str, updates: dict) -> str:
    """Update any attributes of an entity by its unique ID.

    Args:
        entity_id (str): Unique ID of the entity to update
        updates (dict): Dictionary of attribute updates.
                       Supported keys: 'name', 'type', 'observations', 'metadata'
                       Note: 'observations' should be timestamped entries in format
                       "YYYY-MM-DD HH:MM:SS | content" containing only recent,
                       time-sensitive information (max 15 entries, auto-pruned)

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    success = memory.update_entity_by_id(entity_id, updates)
    if success:
        updated_attrs = list(updates.keys())
        return f"Successfully updated entity with ID '{entity_id}' attributes: {updated_attrs}."
    else:
        return f"Failed to update entity with ID '{entity_id}'. Entity may not exist or invalid attributes provided."


@mcp.tool(
    name='delete_entity_by_id',
    description='Delete an entity by its unique ID and all its relationships',
)
def delete_entity_by_id(entity_id: str) -> str:
    """Delete an entity by its unique ID and all its relationships.

    Args:
        entity_id (str): Unique ID of the entity to delete

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    success = memory.delete_entity_by_id(entity_id)
    if success:
        return f"Successfully deleted entity with ID '{entity_id}' and all its relationships."
    else:
        return f"Failed to delete entity with ID '{entity_id}'. Entity may not exist."


@mcp.tool(name='get_relation_by_id', description='Get a relationship by its unique ID')
def get_relation_by_id(relation_id: str) -> dict:
    """Get a relationship by its unique ID.

    Args:
        relation_id (str): Unique ID of the relationship to retrieve

    Returns:
        dict: Relationship data if found, or error message if not found
    """
    relation = memory.get_relation_by_id(relation_id)
    if relation:
        return {
            'id': relation.id,
            'source': relation.source,
            'target': relation.target,
            'relationType': relation.relationType,
            'source_id': relation.source_id,
            'target_id': relation.target_id,
            'created_at': getattr(relation, 'created_at', None),
            'properties': getattr(relation, 'properties', {}),
        }
    else:
        return {'error': f"Relationship with ID '{relation_id}' not found"}


@mcp.tool(
    name='update_relation_by_id',
    description='Update attributes of a relationship by its unique ID',
)
def update_relation_by_id(relation_id: str, updates: dict) -> str:
    """Update attributes of a relationship by its unique ID.

    Args:
        relation_id (str): Unique ID of the relationship to update
        updates (dict): Dictionary of attribute updates.
                       Supported keys: 'relationType', 'source', 'target', 'properties'

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    logger.debug(f'Updating relation {relation_id} with updates: {updates}')
    success = memory.update_relation_by_id(relation_id, updates)
    if success:
        updated_attrs = list(updates.keys())
        return f"Successfully updated relationship with ID '{relation_id}' attributes: {updated_attrs}."
    else:
        return f"Failed to update relationship with ID '{relation_id}'. Relationship may not exist or invalid attributes provided."


@mcp.tool(
    name='delete_relation_by_id', description='Delete a relationship by its unique ID'
)
def delete_relation_by_id(relation_id: str) -> str:
    """Delete a relationship by its unique ID.

    Args:
        relation_id (str): Unique ID of the relationship to delete

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    success = memory.delete_relation_by_id(relation_id)
    if success:
        return f"Successfully deleted relationship with ID '{relation_id}'."
    else:
        return f"Failed to delete relationship with ID '{relation_id}'. Relationship may not exist."


# ID lookup and smart operations
@mcp.tool(
    name='find_entity_ids_by_name',
    description='Find entity IDs by name - useful for identifying entities before updates/deletes',
)
def find_entity_ids_by_name(name: str) -> dict:
    """Find entity IDs by exact name match.

    Args:
        name (str): Exact name of the entity to find

    Returns:
        dict: Dictionary containing the list of matching entity IDs
    """
    ids = memory.find_entity_ids_by_name(name)
    return {
        'entity_ids': ids,
        'count': len(ids),
        'message': f"Found {len(ids)} entity(ies) with exact name '{name}'",
    }


@mcp.tool(
    name='find_entity_ids_by_attributes',
    description='Find entity IDs by various attributes - useful for complex entity identification',
)
def find_entity_ids_by_attributes(attributes: str) -> dict:
    """Find entity IDs by various attributes (exact matches only).

    Args:
        attributes (str): JSON string of search criteria. Supported keys:
                         - 'name': Exact name match
                         - 'type': Exact type match
                         Note: Observation search is not supported
                         Example: '{"type": "Developer", "name": "Alice Johnson-Smith"}'

    Returns:
        dict: Dictionary containing the list of matching entity IDs
    """
    import json

    try:
        search_attrs = json.loads(attributes)
        logger.debug(f'Searching entities with attributes: {search_attrs}')
        ids = memory.find_entity_ids_by_attributes(**search_attrs)
        return {
            'entity_ids': ids,
            'count': len(ids),
            'search_criteria': search_attrs,
            'message': f'Found {len(ids)} entity(ies) matching the criteria',
        }
    except json.JSONDecodeError as e:
        logger.error(f'JSON decode error in entity search: {e}')
        return {'error': 'Invalid JSON format for attributes'}
    except Exception as e:
        logger.error(f'Error in entity search: {e}')
        return {'error': f'Search failed: {str(e)}'}


@mcp.tool(
    name='find_relation_ids_by_attributes',
    description='Find relationship IDs by attributes - useful for identifying relationships before updates/deletes',
)
def find_relation_ids_by_attributes(attributes: str) -> dict:
    """Find relationship IDs by various attributes (exact matches only).

    Args:
        attributes (str): JSON string of search criteria. Supported keys:
                         - 'source' or 'source_name': Source entity name (exact match)
                         - 'target' or 'target_name': Target entity name (exact match)
                         - 'relationType': Relationship type (exact match)
                         - 'source_id': Source entity ID (exact match)
                         - 'target_id': Target entity ID (exact match)
                         Example: '{"source": "Alice Johnson-Smith", "target": "TechCorp", "relationType": "works_at"}'

    Returns:
        dict: Dictionary containing the list of matching relationship IDs
    """
    import json

    try:
        search_attrs = json.loads(attributes)
        logger.debug(f'Searching relations with attributes: {search_attrs}')
        ids = memory.find_relation_ids_by_attributes(**search_attrs)
        return {
            'relation_ids': ids,
            'count': len(ids),
            'search_criteria': search_attrs,
            'message': f'Found {len(ids)} relationship(s) matching the criteria',
        }
    except json.JSONDecodeError as e:
        logger.error(f'JSON decode error in relation search: {e}')
        return {'error': 'Invalid JSON format for attributes'}
    except Exception as e:
        logger.error(f'Error in relation search: {e}')
        return {'error': f'Search failed: {str(e)}'}


def configure_logging(log_level: str, log_file: str = None) -> None:
    """Configure logging for the application and AWS SDK.

    Args:
        log_level (str): The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file (str): Optional path to log file for persistent logging
    """
    # Convert string to logging level
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if log_file is specified
    if log_file:
        import os

        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Configure application logger
    logger.setLevel(numeric_level)

    # Configure AWS SDK loggers (boto3, botocore, urllib3)
    aws_loggers = [
        'boto3',
        'botocore',
        'urllib3',
        'urllib3.connectionpool',
        'botocore.credentials',
        'botocore.utils',
        'botocore.hooks',
        'botocore.loaders',
        'botocore.parsers',
        'botocore.endpoint',
        'botocore.auth',
        'botocore.retryhandler',
        'botocore.httpsession',
        's3transfer',
    ]

    for aws_logger_name in aws_loggers:
        aws_logger = logging.getLogger(aws_logger_name)
        aws_logger.setLevel(numeric_level)

    # Configure langchain-aws logger
    langchain_logger = logging.getLogger('langchain_aws')
    langchain_logger.setLevel(numeric_level)

    # Configure MCP logger
    mcp_logger = logging.getLogger('mcp')
    mcp_logger.setLevel(numeric_level)


def main():
    """Run the MCP server with CLI argument support.

    This function initializes and runs the Model Context Protocol server,
    supporting both SSE (Server-Sent Events) and default transport options.
    Command line arguments can be used to configure the server port,
    transport method, database backend, and logging level.

    Command line arguments:
        --sse: Enable SSE transport
        --port: Specify the port number (default: 8888)
        --backend: Database backend (neptune or falkordb, default: neptune)

        Neptune-specific arguments:
        --endpoint: Neptune endpoint (required for Neptune)
        --use-https: Use HTTPS for Neptune connection (default: True)
        --no-https: Disable HTTPS for Neptune connection

        FalkorDB-specific arguments:
        --falkor-host: FalkorDB host (default: localhost)
        --falkor-port: FalkorDB port (default: 6379)
        --falkor-password: FalkorDB password
        --falkor-ssl: Use SSL for FalkorDB connection
        --graph-name: Graph name for FalkorDB (default: memory)

        --log-level: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    global graph, memory

    parser = argparse.ArgumentParser(
        description='A Model Context Protocol (MCP) server'
    )
    parser.add_argument('--sse', action='store_true', help='Use SSE transport')
    parser.add_argument(
        '--port', type=int, default=8888, help='Port to run the server on'
    )
    parser.add_argument(
        '--backend',
        type=str,
        choices=['neptune', 'falkordb'],
        default='neptune',
        help='Database backend to use (default: neptune)',
    )

    # Neptune-specific arguments
    parser.add_argument(
        '--endpoint', type=str, help='Neptune endpoint (required for Neptune backend)'
    )
    parser.add_argument(
        '--use-https',
        action='store_true',
        default=True,
        help='Use HTTPS for Neptune connection (default: True)',
    )
    parser.add_argument(
        '--no-https', action='store_true', help='Disable HTTPS for Neptune connection'
    )

    # FalkorDB-specific arguments
    parser.add_argument(
        '--falkor-host',
        type=str,
        default='localhost',
        help='FalkorDB host (default: localhost)',
    )
    parser.add_argument(
        '--falkor-port', type=int, default=6379, help='FalkorDB port (default: 6379)'
    )
    parser.add_argument('--falkor-password', type=str, help='FalkorDB password')
    parser.add_argument(
        '--falkor-ssl', action='store_true', help='Use SSL for FalkorDB connection'
    )
    parser.add_argument(
        '--graph-name',
        type=str,
        default='memory',
        help='Graph name for FalkorDB (default: memory)',
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set logging level (default: INFO)',
    )
    parser.add_argument(
        '--log-file', type=str, help='Path to log file for persistent logging'
    )

    args = parser.parse_args()

    # Configure logging first
    configure_logging(args.log_level, args.log_file)

    # Initialize graph database connection based on backend
    if args.backend == 'neptune':
        # Validate Neptune-specific arguments
        if not args.endpoint:
            raise ValueError(
                'Neptune endpoint is required when using Neptune backend (--endpoint)'
            )

        # Handle HTTPS configuration
        if args.use_https and args.no_https:
            raise ValueError('Cannot specify both --use-https and --no-https')

        if args.no_https:
            use_https = False
        else:
            # Default to HTTPS (secure by default)
            use_https = True

        logger.info('Using Neptune backend')
        logger.info(f'Neptune endpoint: {args.endpoint}')
        logger.info(f'Using HTTPS: {use_https}')

        # Initialize Neptune connection
        graph = NeptuneServer(args.endpoint, use_https=use_https)

    elif args.backend == 'falkordb':
        logger.info('Using FalkorDB backend')
        logger.info(f'FalkorDB host: {args.falkor_host}:{args.falkor_port}')
        logger.info(f'Graph name: {args.graph_name}')
        logger.info(f'Using SSL: {args.falkor_ssl}')

        # Initialize FalkorDB connection
        graph = FalkorDBServer(
            host=args.falkor_host,
            port=args.falkor_port,
            password=args.falkor_password,
            graph_name=args.graph_name,
            ssl=args.falkor_ssl,
        )

    # Initialize memory manager
    memory = KnowledgeGraphManager(graph, logger)

    # Run server with appropriate transport
    if args.sse:
        mcp.settings.port = args.port
        # Try to set host to bind to all interfaces
        if hasattr(mcp.settings, 'host'):
            mcp.settings.host = '0.0.0.0'
        mcp.run(transport='streamable-http')
    else:
        mcp.run()


if __name__ == '__main__':
    main()
