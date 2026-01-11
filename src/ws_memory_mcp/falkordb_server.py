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
"""FalkorDB Database Interface Module

This module provides a high-level interface for interacting with FalkorDB instances.
It handles connection management, query execution, and schema operations for FalkorDB
graph databases, providing a unified interface similar to the Neptune implementation.

The module supports OpenCypher queries and provides a unified interface through the
FalkorDBServer class.
"""

import json
import logging
from dataclasses import asdict
from falkordb import FalkorDB
from ws_memory_mcp.graph_server import GraphServer
from ws_memory_mcp.models import (
    GraphSchema,
    Node,
    Property,
    QueryLanguage,
    Relationship,
    RelationshipPattern,
)


class FalkorDBServer(GraphServer):
    """A unified interface for interacting with FalkorDB instances.

    This class provides methods for connecting to and querying FalkorDB instances.
    It handles connection management, query execution, and schema operations.

    Attributes:
        _logger (logging.Logger): Logger instance for operation tracking
        client: Connection to the FalkorDB instance
        graph: The selected graph instance
        graph_name (str): Name of the graph being used
    """

    _logger: logging.Logger = logging.getLogger()
    client = None
    graph = None
    graph_name: str = 'memory'

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        password: str = None,
        graph_name: str = 'memory',
        ssl: bool = False,
        *args,
        **kwargs,
    ):
        """Initialize a connection to a FalkorDB instance.

        Args:
            host (str, optional): FalkorDB host. Defaults to "localhost".
            port (int, optional): Port number for connection. Defaults to 6379.
            password (str, optional): Password for authentication. Defaults to None.
            graph_name (str, optional): Name of the graph to use. Defaults to "memory".
            ssl (bool, optional): Whether to use SSL connection. Defaults to False.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Raises:
            Exception: If connection to FalkorDB fails
        """
        try:
            self.graph_name = graph_name
            self._logger.debug('FalkorDBServer connecting to %s:%s', host, port)

            # Initialize FalkorDB client
            self.client = FalkorDB(
                host=host, port=port, password=password, ssl=ssl, **kwargs
            )

            # Select the graph
            self.graph = self.client.select_graph(graph_name)
            self._logger.debug('Connected to FalkorDB graph: %s', graph_name)

        except Exception as e:
            self._logger.error('Failed to connect to FalkorDB: %s', e)
            raise e

    def close(self):
        """Close the connection to the FalkorDB instance."""
        if self.client:
            # FalkorDB client doesn't have explicit close method
            # The underlying Redis connection will be closed automatically
            self.client = None
            self.graph = None

    def status(self) -> str:
        """Check the current status of the FalkorDB instance.

        Returns:
            str: Current status of the FalkorDB instance ("Available" or "Unavailable")
        """
        try:
            # Simple query to test connectivity
            self.graph.query('RETURN 1')
            return 'Available'
        except Exception as e:
            self._logger.debug('FalkorDB status check failed: %s', e)
            return 'Unavailable'

    def schema(self) -> GraphSchema:
        """Retrieve the schema information from the FalkorDB instance.

        Returns:
            GraphSchema: Complete schema information for the graph
        """
        try:
            # Get node labels and their properties
            nodes_result = self.graph.query('CALL db.labels() YIELD label RETURN label')
            node_labels = [record[0] for record in nodes_result.result_set]

            # Get relationship types
            rels_result = self.graph.query(
                'CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType'
            )
            rel_types = [record[0] for record in rels_result.result_set]

            # Build schema
            nodes = []
            relationships = []
            relationship_patterns = []

            # For each node label, get its properties
            for label in node_labels:
                try:
                    # Get property keys for this label
                    props_query = f'MATCH (n:{label}) UNWIND keys(n) AS key RETURN DISTINCT key, apoc.meta.type(n[key]) AS type LIMIT 100'
                    try:
                        props_result = self.graph.query(props_query)
                        properties = [
                            Property(name=record[0], type=record[1])
                            for record in props_result.result_set
                        ]
                    except Exception:
                        # Fallback if APOC is not available
                        props_query = f'MATCH (n:{label}) UNWIND keys(n) AS key RETURN DISTINCT key LIMIT 100'
                        props_result = self.graph.query(props_query)
                        properties = [
                            Property(name=record[0], type='STRING')
                            for record in props_result.result_set
                        ]

                    nodes.append(Node(labels=label, properties=properties))
                except Exception as e:
                    self._logger.debug(
                        f'Could not get properties for label {label}: {e}'
                    )
                    nodes.append(Node(labels=label, properties=[]))

            # For each relationship type, get its properties and patterns
            for rel_type in rel_types:
                try:
                    # Get property keys for this relationship type
                    props_query = f'MATCH ()-[r:{rel_type}]-() UNWIND keys(r) AS key RETURN DISTINCT key LIMIT 100'
                    props_result = self.graph.query(props_query)
                    properties = [
                        Property(name=record[0], type='STRING')
                        for record in props_result.result_set
                    ]

                    relationships.append(
                        Relationship(type=rel_type, properties=properties)
                    )

                    # Get relationship patterns
                    pattern_query = f'MATCH (a)-[r:{rel_type}]->(b) RETURN DISTINCT labels(a)[0] AS from_label, labels(b)[0] AS to_label LIMIT 100'
                    pattern_result = self.graph.query(pattern_query)
                    for record in pattern_result.result_set:
                        if record[0] and record[1]:  # Ensure labels exist
                            relationship_patterns.append(
                                RelationshipPattern(
                                    left_node=record[0],
                                    relation=rel_type,
                                    right_node=record[1],
                                )
                            )
                except Exception as e:
                    self._logger.debug(
                        f'Could not get properties for relationship {rel_type}: {e}'
                    )
                    relationships.append(Relationship(type=rel_type, properties=[]))

            schema = GraphSchema(
                nodes=nodes,
                relationships=relationships,
                relationship_patterns=relationship_patterns,
            )

            return asdict(schema)

        except Exception as e:
            self._logger.error('Failed to retrieve schema: %s', e)
            # Return empty schema on error
            return asdict(
                GraphSchema(nodes=[], relationships=[], relationship_patterns=[])
            )

    def query(
        self, query: str, language: QueryLanguage, parameters: dict = None
    ) -> str:
        """Execute a query against the FalkorDB instance.

        Args:
            query (str): Query string to execute
            language (QueryLanguage): Query language to use (only OpenCypher supported)
            parameters (dict, optional): Query parameters. Defaults to None.

        Returns:
            str: Query results in JSON format

        Raises:
            ValueError: If using unsupported query language
            Exception: If query execution fails
        """
        if language != QueryLanguage.OPEN_CYPHER:
            raise ValueError('FalkorDB only supports OpenCypher queries')

        try:
            self._logger.debug('Executing FalkorDB query: %s', query)

            # Execute query with parameters if provided
            if parameters:
                result = self.graph.query(query, params=parameters)
            else:
                result = self.graph.query(query)

            # Convert result to JSON format similar to Neptune
            results = []
            if result.result_set:
                for record in result.result_set:
                    # Handle different record structures
                    if isinstance(record, (list, tuple)):
                        if len(record) == 1:
                            # Single value result
                            value = record[0]
                            if hasattr(value, 'properties'):
                                # Node or relationship object
                                results.append(value.properties)
                            elif hasattr(value, '__dict__'):
                                # Object with attributes
                                results.append(vars(value))
                            else:
                                # Simple value
                                results.append(value)
                        else:
                            # Multiple values in record - create a dictionary
                            record_dict = {}
                            for i, value in enumerate(record):
                                if hasattr(value, 'properties'):
                                    record_dict[f'col_{i}'] = value.properties
                                elif hasattr(value, '__dict__'):
                                    record_dict[f'col_{i}'] = vars(value)
                                else:
                                    record_dict[f'col_{i}'] = value
                            results.append(record_dict)
                    else:
                        # Single non-list record
                        if hasattr(record, 'properties'):
                            results.append(record.properties)
                        elif hasattr(record, '__dict__'):
                            results.append(vars(record))
                        else:
                            results.append(record)

            # Return in Neptune-compatible format
            return json.dumps({'results': results})

        except Exception as e:
            self._logger.error('FalkorDB query failed: %s', e)
            raise e
