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
from ws_memory_mcp.memory import KnowledgeGraphManager
from ws_memory_mcp.models import Entity, KnowledgeGraph, Relation
from ws_memory_mcp.neptune import NeptuneServer
from typing import List


logger = logging.getLogger(__name__)

# Global variables for Neptune connection (will be initialized in main)
graph = None
memory = None


mcp = FastMCP(
    "Memory",
    instructions="""
    This provides access to a memory for an agentic workflow stored in Amazon Neptune graph.
    """,
    dependencies=[
        "langchain-aws",
        "mcp[cli]",
    ]
)

@mcp.tool(name="get_memory_server_status")
def get_status() -> str:
    """Retrieve the current status of the Amazon Neptune memory server.

    Returns:
        str: The status information of the Neptune server instance.
    """
    return graph.status()


@mcp.tool(name="create_entities",
        description="Create multiple new entities in the knowledge graph")
def create_entities(entities: List[Entity]) -> str:
    """Create multiple new entities in the knowledge graph.

    Args:
        entities (List[Entity]): A list of Entity objects to be created in the graph.

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    result = memory.create_entities(entities)
    return f"Successfully created {len(result)} entities."


@mcp.tool(name="create_relations",
        description="Create multiple new relations between entities in the knowledge graph. Relations should be in active voice")
def create_relations(relations: List[Relation]) -> str:
    """Create multiple new relations between entities in the knowledge graph.

    Args:
        relations (List[Relation]): A list of Relation objects defining connections
                                  between entities. Relations should be in active voice.

    Returns:
        str: Confirmation message indicating the result of the operation.
    """
    result = memory.create_relations(relations)
    return f"Successfully created {len(result)} relations."


@mcp.tool(name="read_memory",
        description="Read the memory knowledge graph")
def read_graph() -> KnowledgeGraph:
    """Read the entire memory knowledge graph.

    Returns:
        KnowledgeGraph: A KnowledgeGraph object containing all entities and relations
                       in the memory graph.
    """
    return memory.read_graph()


@mcp.tool(name="search_memory",
        description="Search the memory knowledge graph for a specific entity name")
def search_graph(query: str) -> KnowledgeGraph:
    """Search the memory knowledge graph for entities matching a specific name.

    Args:
        query (str): The search query string to match against entity names.

    Returns:
        KnowledgeGraph: A KnowledgeGraph object containing the matching entities
                       and their relations.
    """
    return memory.search_nodes(query)


def configure_logging(log_level: str) -> None:
    """Configure logging for the application and AWS SDK.
    
    Args:
        log_level (str): The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Convert string to logging level
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')
    
    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
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
        's3transfer'
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
    transport method, Neptune endpoint, HTTPS usage, and logging level.

    Command line arguments:
        --sse: Enable SSE transport
        --port: Specify the port number (default: 8888)
        --endpoint: Neptune endpoint (required)
        --use-https: Use HTTPS for Neptune connection (default: True)
        --no-https: Disable HTTPS for Neptune connection
        --log-level: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    global graph, memory
    
    parser = argparse.ArgumentParser(description='A Model Context Protocol (MCP) server')
    parser.add_argument('--sse', action='store_true', help='Use SSE transport')
    parser.add_argument('--port', type=int, default=8888, help='Port to run the server on')
    parser.add_argument('--endpoint', type=str, required=True, help='Neptune endpoint (required)')
    parser.add_argument('--use-https', action='store_true', default=True, help='Use HTTPS for Neptune connection (default: True)')
    parser.add_argument('--no-https', action='store_true', help='Disable HTTPS for Neptune connection')
    parser.add_argument('--log-level', type=str, default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Set logging level (default: INFO)')

    args = parser.parse_args()
    
    # Configure logging first
    configure_logging(args.log_level)

    # Configure Neptune connection
    endpoint = args.endpoint
    
    # Handle HTTPS configuration
    if args.use_https and args.no_https:
        raise ValueError("Cannot specify both --use-https and --no-https")
    
    if args.no_https:
        use_https = False
    else:
        # Default to HTTPS (secure by default)
        use_https = True
    
    logger.info(f"Neptune endpoint: {endpoint}")
    logger.info(f"Using HTTPS: {use_https}")
    
    # Initialize Neptune connection and memory manager
    graph = NeptuneServer(endpoint, use_https=use_https)
    memory = KnowledgeGraphManager(graph, logger)

    # Run server with appropriate transport
    if args.sse:
        mcp.settings.port = args.port
        mcp.run(transport='streamable-http')
    else:
        mcp.run()


if __name__ == '__main__':
    main()
