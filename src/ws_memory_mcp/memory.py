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
"""Knowledge Graph Management Module for Neptune Memory System

This module provides a comprehensive interface for managing a knowledge graph in Amazon Neptune.
It handles all graph operations including creating, reading, updating, and deleting entities,
relations, and observations in the knowledge graph.

The KnowledgeGraphManager class serves as the main interface for all graph operations,
providing methods to manipulate and query the graph structure while maintaining data consistency.

Note: Entity observations should be timestamped entries in format "YYYY-MM-DD HH:MM:SS | content"
containing only recent, time-sensitive information (not relationships or static facts).
Maximum 15 entries per entity, with automatic pruning of oldest entries when limit is exceeded.
"""

import json
import logging
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from ws_memory_mcp.graph_server import GraphServer
from ws_memory_mcp.models import (
    Entity,
    KnowledgeGraph,
    QueryLanguage,
    Relation,
)
from ws_memory_mcp.neptune import NeptuneServer, EngineType

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class KnowledgeGraphManager:
    """Manages operations on a knowledge graph stored in a graph database.

    This class provides methods for creating, reading, updating, and deleting
    entities, relations, and observations in the knowledge graph. It handles
    all interactions with the graph database through a provided client.

    Attributes:
        client (GraphServer): Instance of GraphServer for database operations
        logger (logging.Logger): Logger instance for tracking operations
    """

    def __init__(self, client: GraphServer, logger: logging.Logger):
        """Initialize the KnowledgeGraphManager.

        Args:
            client (GraphServer): Graph database client instance
            logger (logging.Logger): Logger instance for operation tracking
        """
        self.client = client
        self.logger = logger
        
        # Initialize vector search components
        self.embedding_model = None
        self.is_neptune_analytics = False
        self.vector_search_enabled = False
        
        # Detect backend type and initialize vector search
        if isinstance(client, NeptuneServer) and client._engine_type == EngineType.ANALYTICS:
            self.is_neptune_analytics = True
        
        # Initialize sentence transformer if available
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                self.vector_search_enabled = True
                self.logger.info("Vector search enabled with all-MiniLM-L6-v2 model")
                
                # Ensure vector index exists
                self._ensure_vector_index()
            except Exception as e:
                self.logger.warning(f"Failed to initialize vector search: {e}")
                self.vector_search_enabled = False
        else:
            self.logger.warning("sentence-transformers not available, vector search disabled")

    def _compute_embedding(self, text: str) -> List[float]:
        """Compute embedding for a text string.

        Args:
            text (str): Text to encode

        Returns:
            List[float]: Vector embedding (384 dimensions)
        """
        if not self.embedding_model:
            return []
        
        try:
            embedding = self.embedding_model.encode(text)
            return embedding.tolist()
        except Exception as e:
            self.logger.warning(f"Failed to compute embedding: {e}")
            return []

    def _ensure_vector_index(self):
        """Ensure vector index exists for the backend."""
        if not self.vector_search_enabled:
            return
            
        try:
            if self.is_neptune_analytics:
                # Neptune Analytics: Vector indexes are defined at graph creation time
                self.logger.info("Neptune Analytics detected - vector indexes should be defined at graph creation")
            else:
                # FalkorDB: Create vector index dynamically
                index_query = """
                CREATE VECTOR INDEX FOR (m:Memory) ON (m.embedding)
                OPTIONS {dimension: 384, similarityFunction: 'cosine'}
                """
                try:
                    self.client.query(index_query, language=QueryLanguage.OPEN_CYPHER)
                    self.logger.info("Created vector index for Memory nodes")
                except Exception as e:
                    # Index might already exist, which is fine
                    if "already exists" in str(e).lower() or "equivalent index" in str(e).lower():
                        self.logger.debug("Vector index already exists")
                    else:
                        self.logger.warning(f"Failed to create vector index: {e}")
        except Exception as e:
            self.logger.warning(f"Error ensuring vector index: {e}")

    def load_graph(self, filter_query=None) -> KnowledgeGraph:
        """Load the knowledge graph with optional filtering.

        Retrieves entities and their relationships from the graph database.
        Can filter entities based on a provided query string.

        Args:
            filter_query (str, optional): Query string to filter entities by name

        Returns:
            KnowledgeGraph: Object containing filtered entities and their relations
        """
        if filter_query:
            query = """
            MATCH (entity:Memory)
            WHERE toLower(entity.name) CONTAINS toLower($filter)
            RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations,
                   entity.created_at as created_at, entity.last_modified as last_modified,
                   properties(entity) as all_properties
            """
        else:
            query = """
            MATCH (entity:Memory)
            RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations,
                   entity.created_at as created_at, entity.last_modified as last_modified,
                   properties(entity) as all_properties
            """
        resp = self.client.query(
            query,
            parameters={'filter': filter_query},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result = json.loads(resp)['results']

        entities = []
        for record in result:
            # Handle different result formats from different backends
            if isinstance(record, dict):
                # Check for direct field access (FalkorDB format)
                if 'name' in record and 'type' in record:
                    observations = record.get('observations', [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entities.append(
                        Entity(
                            id=record.get('id'),
                            name=record['name'],
                            type=record['type'],
                            observations=observations,
                            embedding=[],  # Don't expose embeddings to LLM
                            created_at=record.get('created_at', time.time()),
                            last_modified=record.get('last_modified', time.time()),
                            metadata=metadata,
                        )
                    )
                # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5, col_6, col_7)
                elif 'col_0' in record and 'col_1' in record:
                    # col_0 = id, col_1 = name, col_2 = type, col_3 = observations,
                    # col_4 = created_at, col_5 = last_modified, col_6 = embedding, col_7 = all_properties
                    entity_id = record.get('col_0')
                    name = record.get('col_1')
                    entity_type = record.get('col_2')
                    observations = record.get('col_3', [])

                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('col_7', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entities.append(
                        Entity(
                            id=entity_id,
                            name=name,
                            type=entity_type,
                            observations=observations,
                            embedding=[],  # Don't expose embeddings to LLM
                            created_at=record.get('col_4', time.time()),
                            last_modified=record.get('col_5', time.time()),
                            metadata=metadata,
                        )
                    )
                    continue
                # Check for Neptune format with nested node
                elif 'node' in record:
                    record = record['node']

                if 'name' in record:
                    observations = record.get('observations', [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entities.append(
                        Entity(
                            id=record.get('id'),
                            name=record['name'],
                            type=record.get('type', 'Unknown'),
                            observations=observations,
                            embedding=[],  # Don't expose embeddings to LLM
                            created_at=record.get('created_at', time.time()),
                            last_modified=record.get('last_modified', time.time()),
                            metadata=metadata,
                        )
                    )

        if filter_query:
            query = """
            MATCH (source:Memory)-[r:related_to]->(target:Memory)
            WHERE toLower(source.name) CONTAINS toLower($filter) OR toLower(target.name) CONTAINS toLower($filter)
            RETURN r.id as id, source.name as source, target.name as target, r.type as relationType,
                   source.id as source_id, target.id as target_id, r.created_at as created_at,
                   properties(r) as all_properties
            """
        else:
            query = """
            MATCH (source:Memory)-[r:related_to]->(target:Memory)
            RETURN r.id as id, source.name as source, target.name as target, r.type as relationType,
                   source.id as source_id, target.id as target_id, r.created_at as created_at,
                   properties(r) as all_properties
            """
        resp = self.client.query(
            query,
            parameters={'filter': filter_query},
            language=QueryLanguage.OPEN_CYPHER,
        )

        result = json.loads(resp)['results']
        rels = []
        for record in result:
            # Handle different result formats from different backends
            if isinstance(record, dict):
                # Check for direct field access
                if (
                    'source' in record
                    and 'target' in record
                    and 'relationType' in record
                ):
                    # Extract properties from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    properties = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'type',
                            'source_id',
                            'target_id',
                            'created_at',
                        }
                        properties = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    rels.append(
                        Relation(
                            id=record.get('id'),
                            source=record['source'],
                            target=record['target'],
                            relationType=record['relationType'],
                            source_id=record.get('source_id'),
                            target_id=record.get('target_id'),
                            created_at=record.get('created_at', time.time()),
                            properties=properties,
                        )
                    )
                # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5, col_6, col_7)
                elif 'col_0' in record and 'col_1' in record and 'col_2' in record:
                    # col_0 = r.id, col_1 = source.name, col_2 = target.name, col_3 = r.type,
                    # col_4 = source.id, col_5 = target.id, col_6 = r.created_at, col_7 = all_properties
                    all_props = record.get('col_7', {})
                    properties = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'type',
                            'source_id',
                            'target_id',
                            'created_at',
                        }
                        properties = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    rels.append(
                        Relation(
                            id=record.get('col_0'),
                            source=record.get('col_1'),
                            target=record.get('col_2'),
                            relationType=record.get('col_3'),
                            source_id=record.get('col_4'),
                            target_id=record.get('col_5'),
                            created_at=record.get('col_6', time.time()),
                            properties=properties,
                        )
                    )
                # Check for Neptune format with nested rel
                elif 'rel' in record:
                    rel_data = record['rel']
                    if 'relationType' in rel_data:
                        # Extract properties from all_properties, excluding core fields
                        all_props = rel_data.get('all_properties', {})
                        properties = {}
                        if isinstance(all_props, dict):
                            core_fields = {
                                'id',
                                'type',
                                'source_id',
                                'target_id',
                                'created_at',
                            }
                            properties = {
                                k: v
                                for k, v in all_props.items()
                                if k not in core_fields
                            }

                        rels.append(
                            Relation(
                                id=rel_data.get('id'),
                                source=rel_data['source'],
                                target=rel_data['target'],
                                relationType=rel_data['relationType'],
                                source_id=rel_data.get('source_id'),
                                target_id=rel_data.get('target_id'),
                                created_at=rel_data.get('created_at', time.time()),
                                properties=properties,
                            )
                        )

        self.logger.debug(f'Loaded entities: {entities}')
        self.logger.debug(f'Loaded relations: {rels}')
        return KnowledgeGraph(entities=entities, relations=rels)

    def create_relations(self, relations: List[Relation]) -> List[Relation]:
        """Create new relations between entities in the knowledge graph.

        Args:
            relations (List[Relation]): List of relations to create

        Returns:
            List[Relation]: The created relations
        """
        # Generate IDs for relations that don't have them
        for relation in relations:
            if not relation.id:
                relation.id = str(uuid.uuid4())
            # Ensure created_at is set
            if not hasattr(relation, 'created_at') or relation.created_at is None:
                relation.created_at = time.time()

        query = """
        UNWIND $relations as relation
        MATCH (from:Memory),(to:Memory)
        WHERE from.name = relation.source
        AND  to.name = relation.target
        MERGE (from)-[r:related_to]->(to)
        SET r.id = relation.id
        SET r.type = relation.relationType
        SET r.source_id = from.id
        SET r.target_id = to.id
        SET r.created_at = relation.created_at
        SET r += relation.properties
        """

        # Prepare relation data with properties
        relations_data = []
        for relation in relations:
            relation_dict = asdict(relation)
            # Ensure properties is included
            if 'properties' not in relation_dict:
                relation_dict['properties'] = {}
            relations_data.append(relation_dict)

        self.client.query(
            query,
            parameters={'relations': relations_data},
            language=QueryLanguage.OPEN_CYPHER,
        )

        return relations

    def read_graph(self) -> KnowledgeGraph:
        """Read the entire knowledge graph.

        Returns:
            KnowledgeGraph: Complete graph with all entities and relations
        """
        return self.load_graph()

    def read_graph_with_depth(
        self, depth: int = 1, filter_query: str = None
    ) -> KnowledgeGraph:
        """Read the knowledge graph with depth control.

        Retrieves entities and their relationships up to a specified depth.
        Depth control is implemented at the Cypher query level for efficiency.

        Args:
            depth (int): Maximum depth for relationship traversal (default: 1, max: 2)
            filter_query (str, optional): Query string to filter entities by name

        Returns:
            KnowledgeGraph: Graph containing entities and relations within the specified depth
        """
        # Validate depth parameter
        if depth < 1:
            depth = 1
        elif depth > 2:
            depth = 2

        self.logger.debug(
            f"Reading graph with depth {depth} and filter '{filter_query}'"
        )

        # Build the entity query with depth control
        if filter_query:
            # Start with filtered entities and expand to specified depth
            entity_query = f"""
            MATCH path = (start:Memory)-[*0..{depth}]-(connected:Memory)
            WHERE toLower(start.name) CONTAINS toLower($filter)
            WITH DISTINCT connected as entity
            RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations,
                   entity.created_at as created_at, entity.last_modified as last_modified,
                   properties(entity) as all_properties
            """
        else:
            # For no filter, we still need to limit the scope somehow
            # We'll get all entities but this will be the same as load_graph for depth > 1
            entity_query = """
            MATCH (entity:Memory)
            RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations,
                   entity.created_at as created_at, entity.last_modified as last_modified,
                   properties(entity) as all_properties
            """

        resp = self.client.query(
            entity_query,
            parameters={'filter': filter_query} if filter_query else {},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result = json.loads(resp)['results']

        entities = []
        entity_names = set()  # Track entity names for relation filtering

        for record in result:
            # Handle different result formats from different backends (same logic as load_graph)
            if isinstance(record, dict):
                # Check for direct field access (FalkorDB format)
                if 'name' in record and 'type' in record:
                    observations = record.get('observations', [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entity = Entity(
                        id=record.get('id'),
                        name=record['name'],
                        type=record['type'],
                        observations=observations,
                        created_at=record.get('created_at', time.time()),
                        last_modified=record.get('last_modified', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)

                # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5, col_6)
                elif 'col_0' in record and 'col_1' in record:
                    # col_0 = id, col_1 = name, col_2 = type, col_3 = observations,
                    # col_4 = created_at, col_5 = last_modified, col_6 = all_properties
                    entity_id = record.get('col_0')
                    name = record.get('col_1')
                    entity_type = record.get('col_2')
                    observations = record.get('col_3', [])

                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('col_6', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entity = Entity(
                        id=entity_id,
                        name=name,
                        type=entity_type,
                        observations=observations,
                        created_at=record.get('col_4', time.time()),
                        last_modified=record.get('col_5', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)
                    continue

                # Check for Neptune format with nested node
                elif 'node' in record:
                    record = record['node']

                if 'name' in record:
                    observations = record.get('observations', [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entity = Entity(
                        id=record.get('id'),
                        name=record['name'],
                        type=record.get('type', 'Unknown'),
                        observations=observations,
                        created_at=record.get('created_at', time.time()),
                        last_modified=record.get('last_modified', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)

        # Now get relations with depth control
        if filter_query:
            # For filtered queries, get relations within the depth from filtered starting points
            relation_query = f"""
            MATCH path = (start:Memory)-[r:related_to*1..{depth}]-(end:Memory)
            WHERE toLower(start.name) CONTAINS toLower($filter)
            UNWIND relationships(path) as rel
            MATCH (source:Memory)-[rel]->(target:Memory)
            RETURN DISTINCT rel.id as id, source.name as source, target.name as target, rel.type as relationType,
                   source.id as source_id, target.id as target_id, rel.created_at as created_at,
                   properties(rel) as all_properties
            """
        else:
            # For no filter, get relations between the entities we found
            # Since we got all entities above, we get all relations (same as original behavior)
            relation_query = """
            MATCH (source:Memory)-[r:related_to]->(target:Memory)
            RETURN r.id as id, source.name as source, target.name as target, r.type as relationType,
                   source.id as source_id, target.id as target_id, r.created_at as created_at,
                   properties(r) as all_properties
            """

        resp = self.client.query(
            relation_query,
            parameters={'filter': filter_query} if filter_query else {},
            language=QueryLanguage.OPEN_CYPHER,
        )

        result = json.loads(resp)['results']
        rels = []
        for record in result:
            # Handle different result formats from different backends (same logic as load_graph)
            if isinstance(record, dict):
                # Check for direct field access
                if (
                    'source' in record
                    and 'target' in record
                    and 'relationType' in record
                ):
                    # Only include relations where both source and target are in our entity set
                    if (
                        record['source'] in entity_names
                        and record['target'] in entity_names
                    ):
                        # Extract properties from all_properties, excluding core fields
                        all_props = record.get('all_properties', {})
                        properties = {}
                        if isinstance(all_props, dict):
                            core_fields = {
                                'id',
                                'type',
                                'source_id',
                                'target_id',
                                'created_at',
                            }
                            properties = {
                                k: v
                                for k, v in all_props.items()
                                if k not in core_fields
                            }

                        rels.append(
                            Relation(
                                id=record.get('id'),
                                source=record['source'],
                                target=record['target'],
                                relationType=record['relationType'],
                                source_id=record.get('source_id'),
                                target_id=record.get('target_id'),
                                created_at=record.get('created_at', time.time()),
                                properties=properties,
                            )
                        )

                # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5, col_6, col_7)
                elif 'col_0' in record and 'col_1' in record and 'col_2' in record:
                    # col_0 = r.id, col_1 = source.name, col_2 = target.name, col_3 = r.type,
                    # col_4 = source.id, col_5 = target.id, col_6 = r.created_at, col_7 = all_properties
                    source_name = record.get('col_1')
                    target_name = record.get('col_2')

                    # Only include relations where both source and target are in our entity set
                    if source_name in entity_names and target_name in entity_names:
                        all_props = record.get('col_7', {})
                        properties = {}
                        if isinstance(all_props, dict):
                            core_fields = {
                                'id',
                                'type',
                                'source_id',
                                'target_id',
                                'created_at',
                            }
                            properties = {
                                k: v
                                for k, v in all_props.items()
                                if k not in core_fields
                            }

                        rels.append(
                            Relation(
                                id=record.get('col_0'),
                                source=source_name,
                                target=target_name,
                                relationType=record.get('col_3'),
                                source_id=record.get('col_4'),
                                target_id=record.get('col_5'),
                                created_at=record.get('col_6', time.time()),
                                properties=properties,
                            )
                        )

                # Check for Neptune format with nested rel
                elif 'rel' in record:
                    rel_data = record['rel']
                    if 'relationType' in rel_data:
                        # Only include relations where both source and target are in our entity set
                        if (
                            rel_data['source'] in entity_names
                            and rel_data['target'] in entity_names
                        ):
                            # Extract properties from all_properties, excluding core fields
                            all_props = rel_data.get('all_properties', {})
                            properties = {}
                            if isinstance(all_props, dict):
                                core_fields = {
                                    'id',
                                    'type',
                                    'source_id',
                                    'target_id',
                                    'created_at',
                                }
                                properties = {
                                    k: v
                                    for k, v in all_props.items()
                                    if k not in core_fields
                                }

                            rels.append(
                                Relation(
                                    id=rel_data.get('id'),
                                    source=rel_data['source'],
                                    target=rel_data['target'],
                                    relationType=rel_data['relationType'],
                                    source_id=rel_data.get('source_id'),
                                    target_id=rel_data.get('target_id'),
                                    created_at=rel_data.get('created_at', time.time()),
                                    properties=properties,
                                )
                            )

        self.logger.debug(
            f'Loaded {len(entities)} entities and {len(rels)} relations with depth {depth}'
        )
        return KnowledgeGraph(entities=entities, relations=rels)

    def read_graph_from_entities(
        self, entity_ids: List[str], depth: int = 1
    ) -> KnowledgeGraph:
        """Read the knowledge graph starting from specific entity IDs with depth control.

        Retrieves entities and their relationships up to a specified depth, starting from
        the provided entity IDs as root nodes.

        Args:
            entity_ids (List[str]): List of entity IDs to start traversal from
            depth (int): Maximum depth for relationship traversal (default: 1, max: 2)

        Returns:
            KnowledgeGraph: Graph containing entities and relations within the specified depth from starting entities
        """
        # Validate depth parameter
        if depth < 1:
            depth = 1
        elif depth > 2:
            depth = 2

        if not entity_ids:
            self.logger.warning('No entity IDs provided, returning empty graph')
            return KnowledgeGraph(entities=[], relations=[])

        self.logger.debug(
            f'Reading graph from entity IDs {entity_ids} with depth {depth}'
        )

        # Build the entity query starting from specific IDs
        entity_query = f"""
        MATCH path = (start:Memory)-[*0..{depth}]-(connected:Memory)
        WHERE start.id IN $entity_ids
        WITH DISTINCT connected as entity
        RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations,
               entity.created_at as created_at, entity.last_modified as last_modified,
               properties(entity) as all_properties
        """

        resp = self.client.query(
            entity_query,
            parameters={'entity_ids': entity_ids},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result = json.loads(resp)['results']

        entities = []
        entity_names = set()  # Track entity names for relation filtering

        for record in result:
            # Handle different result formats from different backends (same logic as read_graph_with_depth)
            if isinstance(record, dict):
                # Check for direct field access (FalkorDB format)
                if 'name' in record and 'type' in record:
                    observations = record.get('observations', [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entity = Entity(
                        id=record.get('id'),
                        name=record['name'],
                        type=record['type'],
                        observations=observations,
                        created_at=record.get('created_at', time.time()),
                        last_modified=record.get('last_modified', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)

                # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5, col_6)
                elif 'col_0' in record and 'col_1' in record:
                    entity_id = record.get('col_0')
                    name = record.get('col_1')
                    entity_type = record.get('col_2')
                    observations = record.get('col_3', [])

                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('col_6', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entity = Entity(
                        id=entity_id,
                        name=name,
                        type=entity_type,
                        observations=observations,
                        created_at=record.get('col_4', time.time()),
                        last_modified=record.get('col_5', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)
                    continue

                # Check for Neptune format with nested node
                elif 'node' in record:
                    record = record['node']

                if 'name' in record:
                    observations = record.get('observations', [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    entity = Entity(
                        id=record.get('id'),
                        name=record['name'],
                        type=record.get('type', 'Unknown'),
                        observations=observations,
                        created_at=record.get('created_at', time.time()),
                        last_modified=record.get('last_modified', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)

        # Now get relations within the subgraph
        relation_query = f"""
        MATCH path = (start:Memory)-[r:related_to*1..{depth}]-(end:Memory)
        WHERE start.id IN $entity_ids
        UNWIND relationships(path) as rel
        MATCH (source:Memory)-[rel]->(target:Memory)
        RETURN DISTINCT rel.id as id, source.name as source, target.name as target, rel.type as relationType,
               source.id as source_id, target.id as target_id, rel.created_at as created_at,
               properties(rel) as all_properties
        """

        resp = self.client.query(
            relation_query,
            parameters={'entity_ids': entity_ids},
            language=QueryLanguage.OPEN_CYPHER,
        )

        result = json.loads(resp)['results']
        rels = []
        for record in result:
            # Handle different result formats from different backends (same logic as read_graph_with_depth)
            if isinstance(record, dict):
                # Check for direct field access
                if (
                    'source' in record
                    and 'target' in record
                    and 'relationType' in record
                ):
                    # Only include relations where both source and target are in our entity set
                    if (
                        record['source'] in entity_names
                        and record['target'] in entity_names
                    ):
                        # Extract properties from all_properties, excluding core fields
                        all_props = record.get('all_properties', {})
                        properties = {}
                        if isinstance(all_props, dict):
                            core_fields = {
                                'id',
                                'type',
                                'source_id',
                                'target_id',
                                'created_at',
                            }
                            properties = {
                                k: v
                                for k, v in all_props.items()
                                if k not in core_fields
                            }

                        rels.append(
                            Relation(
                                id=record.get('id'),
                                source=record['source'],
                                target=record['target'],
                                relationType=record['relationType'],
                                source_id=record.get('source_id'),
                                target_id=record.get('target_id'),
                                created_at=record.get('created_at', time.time()),
                                properties=properties,
                            )
                        )

                # Check for column-based format
                elif 'col_0' in record and 'col_1' in record and 'col_2' in record:
                    source_name = record.get('col_1')
                    target_name = record.get('col_2')

                    # Only include relations where both source and target are in our entity set
                    if source_name in entity_names and target_name in entity_names:
                        all_props = record.get('col_7', {})
                        properties = {}
                        if isinstance(all_props, dict):
                            core_fields = {
                                'id',
                                'type',
                                'source_id',
                                'target_id',
                                'created_at',
                            }
                            properties = {
                                k: v
                                for k, v in all_props.items()
                                if k not in core_fields
                            }

                        rels.append(
                            Relation(
                                id=record.get('col_0'),
                                source=source_name,
                                target=target_name,
                                relationType=record.get('col_3'),
                                source_id=record.get('col_4'),
                                target_id=record.get('col_5'),
                                created_at=record.get('col_6', time.time()),
                                properties=properties,
                            )
                        )

        self.logger.debug(
            f'Loaded {len(entities)} entities and {len(rels)} relations from entity IDs with depth {depth}'
        )
        return KnowledgeGraph(entities=entities, relations=rels)

    def search_nodes(self, query: str, depth: int = 0) -> KnowledgeGraph:
        """Search for nodes in the knowledge graph by name with depth control.

        Uses vector search when available, falls back to string matching.

        Args:
            query (str): Search query string (searches entity names and content semantically)
            depth (int): Maximum depth for relationship traversal (default: 1, max: 2)

        Returns:
            KnowledgeGraph: Graph containing matching nodes and their relations within specified depth
        """
        self.logger.debug(f"Searching nodes with query: '{query}' and depth: {depth}")

        # If query is empty, return empty results instead of all data
        if not query or query.strip() == '':
            self.logger.debug('Empty query provided, returning empty results')
            return KnowledgeGraph(entities=[], relations=[])

        # Validate depth parameter - allow 0 for entity-only search
        if depth < 0:
            depth = 0
        elif depth > 2:
            depth = 2

        # Try vector search first if available
        if self.vector_search_enabled:
            try:
                return self._vector_search_nodes(query, depth)
            except Exception as e:
                self.logger.warning(f"Vector search failed, falling back to string search: {e}")

        # Fallback to string-based search
        if depth == 0:
            # For depth 0, only return matching entities without relations
            result = self.load_graph(filter_query=query)
            # Return only entities, no relations
            return KnowledgeGraph(entities=result.entities, relations=[])
        else:
            result = self.read_graph_with_depth(depth=depth, filter_query=query)
        
        self.logger.debug(
            f'Search found {len(result.entities)} entities and {len(result.relations)} relations with depth {depth}'
        )
        return result

    def _vector_search_nodes(self, query: str, depth: int = 0) -> KnowledgeGraph:
        """Perform vector-based semantic search for nodes.

        Args:
            query (str): Search query string
            depth (int): Maximum depth for relationship traversal

        Returns:
            KnowledgeGraph: Graph containing semantically similar nodes and their relations
        """
        # Generate embedding for the query
        query_embedding = self._compute_embedding(query)
        if not query_embedding:
            raise Exception("Failed to generate query embedding")

        # Execute vector search based on backend
        if self.is_neptune_analytics:
            # Neptune Analytics vector search
            vector_query = """
            CALL neptune.algo.vectors.topKByEmbedding($embedding, 5) YIELD node, score
            RETURN node.id as id, node.name as name, node.type as type, node.observations as observations,
                   node.created_at as created_at, node.last_modified as last_modified,
                   properties(node) as all_properties, score
            """
        else:
            # FalkorDB vector search
            vector_query = """
            CALL db.idx.vector.queryNodes('Memory', 'embedding', 5, vecf32($embedding)) YIELD node, score
            RETURN node.id as id, node.name as name, node.type as type, node.observations as observations,
                   node.created_at as created_at, node.last_modified as last_modified,
                   properties(node) as all_properties, score
            """

        resp = self.client.query(
            vector_query,
            parameters={'embedding': query_embedding},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result = json.loads(resp)['results']

        entities = []
        entity_names = set()

        for record in result:
            if isinstance(record, dict):
                # Handle direct field access
                if 'name' in record and 'type' in record:
                    observations = record.get('observations', [])
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id', 'name', 'type', 'observations', 'created_at', 'last_modified'
                        }
                        metadata = {k: v for k, v in all_props.items() if k not in core_fields}

                    # Add score to metadata
                    score = record.get('score', 0.0)
                    metadata['vector_search_score'] = score

                    entity = Entity(
                        id=record.get('id'),
                        name=record['name'],
                        type=record['type'],
                        observations=observations,
                        embedding=[],  # Don't expose embeddings to LLM
                        created_at=record.get('created_at', time.time()),
                        last_modified=record.get('last_modified', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)

                # Handle column-based format
                elif 'col_0' in record and 'col_1' in record:
                    # Columns: id, name, type, observations, created_at, last_modified, embedding, all_properties, score
                    observations = record.get('col_3', [])
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    all_props = record.get('col_7', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id', 'name', 'type', 'observations', 'created_at', 'last_modified'
                        }
                        metadata = {k: v for k, v in all_props.items() if k not in core_fields}

                    # Add score to metadata
                    score = record.get('col_8', 0.0)
                    metadata['vector_search_score'] = score

                    entity = Entity(
                        id=record.get('col_0'),
                        name=record.get('col_1'),
                        type=record.get('col_2'),
                        observations=observations,
                        embedding=[],  # Don't expose embeddings to LLM
                        created_at=record.get('col_4', time.time()),
                        last_modified=record.get('col_5', time.time()),
                        metadata=metadata,
                    )
                    entities.append(entity)
                    entity_names.add(entity.name)

        # If depth is 0, return only entities
        if depth == 0:
            self.logger.debug(f'Vector search found {len(entities)} entities with depth 0')
            return KnowledgeGraph(entities=entities, relations=[])

        # For depth > 0, get relations between found entities
        if not entity_names:
            return KnowledgeGraph(entities=[], relations=[])

        # Get relations between the found entities
        relation_query = """
        MATCH (source:Memory)-[r:related_to]->(target:Memory)
        WHERE source.name IN $entity_names AND target.name IN $entity_names
        RETURN r.id as id, source.name as source, target.name as target, r.type as relationType,
               source.id as source_id, target.id as target_id, r.created_at as created_at,
               properties(r) as all_properties
        """

        resp = self.client.query(
            relation_query,
            parameters={'entity_names': list(entity_names)},
            language=QueryLanguage.OPEN_CYPHER,
        )

        result = json.loads(resp)['results']
        rels = []
        for record in result:
            if isinstance(record, dict):
                if 'source' in record and 'target' in record and 'relationType' in record:
                    all_props = record.get('all_properties', {})
                    properties = {}
                    if isinstance(all_props, dict):
                        core_fields = {'id', 'type', 'source_id', 'target_id', 'created_at'}
                        properties = {k: v for k, v in all_props.items() if k not in core_fields}

                    rels.append(
                        Relation(
                            id=record.get('id'),
                            source=record['source'],
                            target=record['target'],
                            relationType=record['relationType'],
                            source_id=record.get('source_id'),
                            target_id=record.get('target_id'),
                            created_at=record.get('created_at', time.time()),
                            properties=properties,
                        )
                    )

        self.logger.debug(f'Vector search found {len(entities)} entities and {len(rels)} relations with depth {depth}')
        return KnowledgeGraph(entities=entities, relations=rels)

    def find_entity_ids_by_name(self, name: str) -> List[str]:
        """Find entity IDs by name (exact match only).

        Args:
            name (str): Exact name of the entity to find

        Returns:
            List[str]: List of entity IDs that exactly match the name
        """
        # Use the same approach as load_graph but filter by name
        graph = self.load_graph()  # Load all entities

        ids = []
        for entity in graph.entities:
            # Exact match only
            if entity.name == name and entity.id is not None:
                ids.append(entity.id)

        return ids

    def find_entity_ids_by_attributes(self, **attributes) -> List[str]:
        """Find entity IDs by various attributes.

        Args:
            **attributes: Keyword arguments for entity attributes (name, type only - observations not supported)

        Returns:
            List[str]: List of entity IDs that match the criteria (exact matches only)
        """
        self.logger.debug(f'Searching entities with attributes: {attributes}')

        # Use the same approach as load_graph but filter by attributes
        graph = self.load_graph()  # Load all entities

        ids = []
        for entity in graph.entities:
            if entity.id is None:
                continue

            match = True
            for key, value in attributes.items():
                if key == 'name':
                    # Exact match only
                    if entity.name != value:
                        match = False
                        break
                elif key == 'type':
                    # Exact match only
                    if entity.type != value:
                        match = False
                        break
                elif key in [
                    'observations',
                    'observation_contains',
                    'name_contains',
                    'type_contains',
                ]:
                    # Observation search not allowed
                    self.logger.warning(
                        f'Search on observations is not supported: {key}'
                    )
                    match = False
                    break
                else:
                    self.logger.warning(f'Unsupported search attribute: {key}')
                    match = False
                    break

            if match:
                ids.append(entity.id)

        self.logger.debug(f'Found {len(ids)} entities matching criteria: {ids}')
        return ids

    def find_relation_ids_by_attributes(self, **attributes) -> List[str]:
        """Find relationship IDs by various attributes (exact matches only).

        Args:
            **attributes: Keyword arguments for relationship attributes
                         (source, target, relationType, source_name, target_name, source_id, target_id)

        Returns:
            List[str]: List of relationship IDs that exactly match the criteria
        """
        self.logger.debug(f'Searching relations with attributes: {attributes}')

        # Load all relations and filter in memory for precise matching
        graph = self.load_graph()

        ids = []
        for relation in graph.relations:
            if relation.id is None:
                continue

            match = True
            for key, value in attributes.items():
                if key == 'relationType':
                    # Exact match only
                    if relation.relationType != value:
                        match = False
                        break
                elif key in ['source', 'source_name']:
                    # Exact match only
                    if relation.source != value:
                        match = False
                        break
                elif key in ['target', 'target_name']:
                    # Exact match only
                    if relation.target != value:
                        match = False
                        break
                elif key == 'source_id':
                    # Exact match only
                    if relation.source_id != value:
                        match = False
                        break
                elif key == 'target_id':
                    # Exact match only
                    if relation.target_id != value:
                        match = False
                        break
                else:
                    self.logger.warning(f'Unsupported relation search attribute: {key}')
                    match = False
                    break

            if match:
                ids.append(relation.id)

        self.logger.debug(f'Found {len(ids)} relations matching criteria: {ids}')
        return ids

    # ID-based operations
    def create_entities_with_ids(self, entities: List[Entity]) -> List[Entity]:
        """Create new entities with auto-generated IDs if not provided.

        Uses MERGE logic: ON CREATE sets all fields, ON MATCH updates last_modified and merges metadata.

        Note: Entity observations should be timestamped entries in format "YYYY-MM-DD HH:MM:SS | content"
        containing only recent, time-sensitive information. Maximum 15 entries per entity, with
        automatic pruning of oldest entries when limit is exceeded.

        Args:
            entities (List[Entity]): List of entities to create

        Returns:
            List[Entity]: The created entities with their IDs
        """
        # Generate IDs, timestamps, and embeddings for entities that don't have them
        current_time = time.time()
        for entity in entities:
            if not entity.id:
                entity.id = str(uuid.uuid4())
            # Ensure timestamps are set
            if not hasattr(entity, 'created_at') or entity.created_at is None:
                entity.created_at = current_time
            if not hasattr(entity, 'last_modified') or entity.last_modified is None:
                entity.last_modified = current_time
            
            # Generate embedding if not present and vector search is enabled
            if self.vector_search_enabled and not entity.embedding:
                # Combine name, type, and observations for embedding
                text_for_embedding = f"{entity.name} {entity.type}"
                if entity.observations:
                    # Take first few observations to avoid too long text
                    obs_text = " ".join(entity.observations[:3])
                    text_for_embedding += f" {obs_text}"
                
                entity.embedding = self._compute_embedding(text_for_embedding)

        if self.is_neptune_analytics:
            # Neptune Analytics: Use vector upsert
            query = """
            UNWIND $entities as entity
            MERGE (e:Memory {name: entity.name})
            ON CREATE SET
                e.id = entity.id,
                e.type = entity.type,
                e.created_at = entity.created_at,
                e.last_modified = entity.last_modified,
                e.observations = entity.observations
            ON MATCH SET
                e.last_modified = $now,
                e.observations = CASE
                    WHEN entity.observations IS NOT NULL AND size(entity.observations) > 0
                    THEN [obs IN entity.observations WHERE NOT obs IN coalesce(e.observations, [])] + coalesce(e.observations, [])
                    ELSE coalesce(e.observations, [])
                END
            SET e += entity.metadata
            WITH e, entity
            CALL neptune.algo.vectors.upsert(e, entity.embedding)
            """
        else:
            # FalkorDB: Set embedding directly
            query = """
            UNWIND $entities as entity
            MERGE (e:Memory {name: entity.name})
            ON CREATE SET
                e.id = entity.id,
                e.type = entity.type,
                e.created_at = entity.created_at,
                e.last_modified = entity.last_modified,
                e.observations = entity.observations,
                e.embedding = CASE 
                    WHEN entity.embedding IS NOT NULL AND size(entity.embedding) > 0 
                    THEN vecf32(entity.embedding) 
                    ELSE null 
                END
            ON MATCH SET
                e.last_modified = $now,
                e.observations = CASE
                    WHEN entity.observations IS NOT NULL AND size(entity.observations) > 0
                    THEN [obs IN entity.observations WHERE NOT obs IN coalesce(e.observations, [])] + coalesce(e.observations, [])
                    ELSE coalesce(e.observations, [])
                END,
                e.embedding = CASE 
                    WHEN entity.embedding IS NOT NULL AND size(entity.embedding) > 0 
                    THEN vecf32(entity.embedding) 
                    ELSE e.embedding 
                END
            SET e += entity.metadata
            """

        # Prepare entity data with metadata
        entities_data = []
        for entity in entities:
            entity_dict = asdict(entity)
            # Ensure metadata is included
            if 'metadata' not in entity_dict:
                entity_dict['metadata'] = {}
            entities_data.append(entity_dict)

        self.client.query(
            query,
            parameters={'entities': entities_data, 'now': current_time},
            language=QueryLanguage.OPEN_CYPHER,
        )
        return entities

    def get_entity_by_id(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by its ID.

        Args:
            entity_id (str): ID of the entity to retrieve

        Returns:
            Optional[Entity]: The entity if found, None otherwise
        """
        query = f"""
        MATCH (entity:Memory)
        WHERE entity.id = '{entity_id}'
        RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations,
               entity.created_at as created_at, entity.last_modified as last_modified,
               properties(entity) as all_properties
        """
        resp = self.client.query(query, language=QueryLanguage.OPEN_CYPHER)
        result = json.loads(resp)['results']

        if not result:
            return None

        # Use the same parsing logic as load_graph
        for record in result:
            if isinstance(record, dict):
                # Check for direct field access (FalkorDB format)
                if 'name' in record and 'type' in record:
                    observations = record.get('observations', [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('all_properties', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    return Entity(
                        id=record.get('id'),
                        name=record['name'],
                        type=record['type'],
                        observations=observations,
                        created_at=record.get('created_at', time.time()),
                        last_modified=record.get('last_modified', time.time()),
                        metadata=metadata,
                    )
                # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5, col_6)
                elif 'col_0' in record and 'col_1' in record:
                    # col_0 = id, col_1 = name, col_2 = type, col_3 = observations,
                    # col_4 = created_at, col_5 = last_modified, col_6 = all_properties
                    entity_id_result = record.get('col_0')
                    name = record.get('col_1')
                    entity_type = record.get('col_2')
                    observations = record.get('col_3', [])

                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split('|') if observations else []
                    elif not isinstance(observations, list):
                        observations = []

                    # Extract metadata from all_properties, excluding core fields
                    all_props = record.get('col_6', {})
                    metadata = {}
                    if isinstance(all_props, dict):
                        core_fields = {
                            'id',
                            'name',
                            'type',
                            'observations',
                            'created_at',
                            'last_modified',
                        }
                        metadata = {
                            k: v for k, v in all_props.items() if k not in core_fields
                        }

                    return Entity(
                        id=entity_id_result,
                        name=name,
                        type=entity_type,
                        observations=observations,
                        created_at=record.get('col_4', time.time()),
                        last_modified=record.get('col_5', time.time()),
                        metadata=metadata,
                    )

        return None

    def update_entity_by_id(self, entity_id: str, updates: Dict[str, Any]) -> bool:
        """Update any attributes of an entity by its ID.

        Automatically updates the last_modified timestamp and regenerates embeddings
        if any embedding-relevant attributes (name, type, observations) are updated.

        Args:
            entity_id (str): ID of the entity to update
            updates (Dict[str, Any]): Dictionary of attribute updates

        Returns:
            bool: True if the update was successful, False otherwise
        """
        # First check if the entity exists and get current values
        check_query = """
        MATCH (e:Memory { id: $entity_id })
        RETURN e.id as id, e.name as name, e.type as type, e.observations as observations
        """
        result = self.client.query(
            check_query,
            parameters={'entity_id': entity_id},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result_data = json.loads(result)

        if not result_data.get('results'):
            self.logger.warning(f"Entity with ID '{entity_id}' not found")
            return False

        # Get current entity data
        current_entity = result_data['results'][0]
        current_name = current_entity.get('name', '')
        current_type = current_entity.get('type', '')
        current_observations = current_entity.get('observations', [])
        
        # Handle observations format
        if isinstance(current_observations, str):
            current_observations = current_observations.split('|') if current_observations else []
        elif not isinstance(current_observations, list):
            current_observations = []

        # Build the SET clause dynamically based on updates
        set_clauses = ['e.last_modified = $now']  # Always update last_modified
        parameters = {'entity_id': entity_id, 'now': time.time()}

        # Check if embedding-relevant attributes are being updated
        embedding_relevant_update = False
        updated_name = current_name
        updated_type = current_type
        updated_observations = current_observations

        for key, value in updates.items():
            if key in ['name', 'type', 'observations']:
                param_name = f'new_{key}'
                set_clauses.append(f'e.{key} = ${param_name}')
                parameters[param_name] = value
                embedding_relevant_update = True
                
                # Track updated values for embedding generation
                if key == 'name':
                    updated_name = value
                elif key == 'type':
                    updated_type = value
                elif key == 'observations':
                    updated_observations = value if isinstance(value, list) else [value] if value else []
                    
            elif key == 'metadata':
                # Merge metadata using += operator
                set_clauses.append('e += $new_metadata')
                parameters['new_metadata'] = value
            else:
                self.logger.warning(f'Unsupported update attribute: {key}')

        if len(set_clauses) == 1:  # Only last_modified update
            self.logger.warning('No valid attributes to update')
            return False

        # Generate new embedding if embedding-relevant attributes were updated and vector search is enabled
        if embedding_relevant_update and self.vector_search_enabled:
            # Combine updated name, type, and observations for embedding
            text_for_embedding = f"{updated_name} {updated_type}"
            if updated_observations:
                # Take first few observations to avoid too long text
                obs_text = " ".join(updated_observations[:3])
                text_for_embedding += f" {obs_text}"
            
            new_embedding = self._compute_embedding(text_for_embedding)
            
            if new_embedding:
                if self.is_neptune_analytics:
                    # Neptune Analytics: Use vector upsert after the main update
                    parameters['new_embedding'] = new_embedding
                else:
                    # FalkorDB: Set embedding directly in the same query
                    set_clauses.append('e.embedding = $new_embedding')
                    parameters['new_embedding'] = new_embedding
                
                self.logger.debug(f"Generated new embedding for entity '{entity_id}' due to attribute updates")

        update_query = f"""
        MATCH (e:Memory {{ id: $entity_id }})
        SET {', '.join(set_clauses)}
        RETURN e.id as id, e.name as name, e.type as type, e.observations as observations
        """

        try:
            # Execute the main update
            self.client.query(
                update_query, parameters=parameters, language=QueryLanguage.OPEN_CYPHER
            )
            
            # For Neptune Analytics, perform vector upsert separately
            if embedding_relevant_update and self.vector_search_enabled and self.is_neptune_analytics and 'new_embedding' in parameters:
                vector_upsert_query = """
                MATCH (e:Memory { id: $entity_id })
                CALL neptune.algo.vectors.upsert(e, $new_embedding)
                """
                self.client.query(
                    vector_upsert_query,
                    parameters={'entity_id': entity_id, 'new_embedding': parameters['new_embedding']},
                    language=QueryLanguage.OPEN_CYPHER
                )
                self.logger.debug(f"Updated vector embedding for entity '{entity_id}' in Neptune Analytics")
            
            self.logger.info(
                f"Successfully updated entity with ID '{entity_id}' with attributes: {list(updates.keys())}"
                + (" (embedding regenerated)" if embedding_relevant_update and self.vector_search_enabled else "")
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to update entity with ID '{entity_id}': {e}")
            return False

    def delete_entity_by_id(self, entity_id: str) -> bool:
        """Delete an entity by its ID and all its relationships.

        Args:
            entity_id (str): ID of the entity to delete

        Returns:
            bool: True if the deletion was successful, False otherwise
        """
        # First check if the entity exists
        check_query = """
        MATCH (e:Memory { id: $entity_id })
        RETURN e.id as id
        """
        result = self.client.query(
            check_query,
            parameters={'entity_id': entity_id},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result_data = json.loads(result)

        if not result_data.get('results'):
            self.logger.warning(f"Entity with ID '{entity_id}' not found")
            return False

        # Delete the entity and all its relationships
        delete_query = """
        MATCH (e:Memory { id: $entity_id })
        DETACH DELETE e
        """

        try:
            self.client.query(
                delete_query,
                parameters={'entity_id': entity_id},
                language=QueryLanguage.OPEN_CYPHER,
            )
            self.logger.info(
                f"Successfully deleted entity with ID '{entity_id}' and all its relationships"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete entity with ID '{entity_id}': {e}")
            return False

    def get_relation_by_id(self, relation_id: str) -> Optional[Relation]:
        """Get a relationship by its ID.

        Args:
            relation_id (str): ID of the relationship to retrieve

        Returns:
            Optional[Relation]: The relationship if found, None otherwise
        """
        query = """
        MATCH (source:Memory)-[r:related_to]->(target:Memory)
        WHERE r.id = $relation_id
        RETURN r.id as id, source.name as source, target.name as target, r.type as relationType,
               source.id as source_id, target.id as target_id, r.created_at as created_at,
               properties(r) as all_properties
        """
        result = self.client.query(
            query,
            parameters={'relation_id': relation_id},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result_data = json.loads(result)

        if not result_data.get('results'):
            return None

        record = result_data['results'][0]
        # Handle different result formats
        if isinstance(record, dict):
            # Check for direct field access
            if (
                'id' in record
                and 'source' in record
                and 'target' in record
                and 'relationType' in record
            ):
                # Extract properties from all_properties, excluding core fields
                all_props = record.get('all_properties', {})
                properties = {}
                if isinstance(all_props, dict):
                    core_fields = {'id', 'type', 'source_id', 'target_id', 'created_at'}
                    properties = {
                        k: v for k, v in all_props.items() if k not in core_fields
                    }

                return Relation(
                    id=record['id'],
                    source=record['source'],
                    target=record['target'],
                    relationType=record['relationType'],
                    source_id=record.get('source_id'),
                    target_id=record.get('target_id'),
                    created_at=record.get('created_at', time.time()),
                    properties=properties,
                )
            # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5, col_6, col_7)
            elif (
                'col_0' in record
                and 'col_1' in record
                and 'col_2' in record
                and 'col_3' in record
            ):
                # col_0 = r.id, col_1 = source.name, col_2 = target.name, col_3 = r.type,
                # col_4 = source.id, col_5 = target.id, col_6 = r.created_at, col_7 = all_properties
                all_props = record.get('col_7', {})
                properties = {}
                if isinstance(all_props, dict):
                    core_fields = {'id', 'type', 'source_id', 'target_id', 'created_at'}
                    properties = {
                        k: v for k, v in all_props.items() if k not in core_fields
                    }

                return Relation(
                    id=record.get('col_0'),
                    source=record.get('col_1'),
                    target=record.get('col_2'),
                    relationType=record.get('col_3'),
                    source_id=record.get('col_4'),
                    target_id=record.get('col_5'),
                    created_at=record.get('col_6', time.time()),
                    properties=properties,
                )
        return None

    def update_relation_by_id(self, relation_id: str, updates: Dict[str, Any]) -> bool:
        """Update attributes of a relationship by its ID.

        Args:
            relation_id (str): ID of the relationship to update
            updates (Dict[str, Any]): Dictionary of attribute updates

        Returns:
            bool: True if the update was successful, False otherwise
        """
        # First check if the relationship exists
        check_query = """
        MATCH (source:Memory)-[r:related_to { id: $relation_id }]->(target:Memory)
        RETURN r.id as id, source.name as source, target.name as target
        """
        result = self.client.query(
            check_query,
            parameters={'relation_id': relation_id},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result_data = json.loads(result)

        if not result_data.get('results'):
            self.logger.warning(f"Relationship with ID '{relation_id}' not found")
            return False

        # Handle source and target updates by recreating the relationship
        if 'source' in updates or 'target' in updates:
            # Get current relationship data
            current_rel = result_data['results'][0]
            current_source = current_rel.get('source') or current_rel.get('col_1')
            current_target = current_rel.get('target') or current_rel.get('col_2')

            # Get current relationship type and properties
            rel_query = """
            MATCH ()-[r:related_to { id: $relation_id }]->()
            RETURN r.type as relationType, r.created_at as created_at, properties(r) as all_properties
            """
            rel_result = self.client.query(
                rel_query,
                parameters={'relation_id': relation_id},
                language=QueryLanguage.OPEN_CYPHER,
            )
            rel_data = json.loads(rel_result)
            current_rel_type = rel_data['results'][0].get('relationType') or rel_data[
                'results'
            ][0].get('col_0')
            current_created_at = rel_data['results'][0].get('created_at') or rel_data[
                'results'
            ][0].get('col_1')

            # Extract current properties, excluding core fields
            all_props = rel_data['results'][0].get('all_properties', {}) or rel_data[
                'results'
            ][0].get('col_2', {})
            current_properties = {}
            if isinstance(all_props, dict):
                core_fields = {'id', 'type', 'source_id', 'target_id', 'created_at'}
                current_properties = {
                    k: v for k, v in all_props.items() if k not in core_fields
                }

            # Determine new values
            new_source = updates.get('source', current_source)
            new_target = updates.get('target', current_target)
            new_rel_type = updates.get('relationType', current_rel_type)
            new_properties = updates.get('properties', current_properties)

            # Delete old relationship and create new one
            delete_query = """
            MATCH ()-[r:related_to { id: $relation_id }]->()
            DELETE r
            """

            create_query = """
            MATCH (from:Memory { name: $source }), (to:Memory { name: $target })
            CREATE (from)-[r:related_to]->(to)
            SET r.id = $relation_id
            SET r.type = $relationType
            SET r.source_id = from.id
            SET r.target_id = to.id
            SET r.created_at = $created_at
            SET r += $properties
            """

            try:
                # Delete old relationship
                self.client.query(
                    delete_query,
                    parameters={'relation_id': relation_id},
                    language=QueryLanguage.OPEN_CYPHER,
                )

                # Create new relationship
                self.client.query(
                    create_query,
                    parameters={
                        'relation_id': relation_id,
                        'source': new_source,
                        'target': new_target,
                        'relationType': new_rel_type,
                        'created_at': current_created_at or time.time(),
                        'properties': new_properties,
                    },
                    language=QueryLanguage.OPEN_CYPHER,
                )

                self.logger.info(
                    f"Successfully updated relationship with ID '{relation_id}' with attributes: {list(updates.keys())}"
                )
                return True
            except Exception as e:
                self.logger.error(
                    f"Failed to update relationship with ID '{relation_id}': {e}"
                )
                return False

        # Handle simple attribute updates (relationType and properties)
        else:
            set_clauses = []
            parameters = {'relation_id': relation_id}

            for key, value in updates.items():
                if key == 'relationType':
                    param_name = f'new_{key}'
                    set_clauses.append(f'r.type = ${param_name}')
                    parameters[param_name] = value
                elif key == 'properties':
                    # Merge properties using += operator
                    set_clauses.append('r += $new_properties')
                    parameters['new_properties'] = value
                else:
                    self.logger.warning(
                        f'Unsupported relationship update attribute: {key}'
                    )

            if not set_clauses:
                self.logger.warning('No valid relationship attributes to update')
                return False

            update_query = f"""
            MATCH ()-[r:related_to {{ id: $relation_id }}]->()
            SET {', '.join(set_clauses)}
            RETURN r.id as id, r.type as relationType
            """

            try:
                self.client.query(
                    update_query,
                    parameters=parameters,
                    language=QueryLanguage.OPEN_CYPHER,
                )
                self.logger.info(
                    f"Successfully updated relationship with ID '{relation_id}' with attributes: {list(updates.keys())}"
                )
                return True
            except Exception as e:
                self.logger.error(
                    f"Failed to update relationship with ID '{relation_id}': {e}"
                )
                return False

    def delete_relation_by_id(self, relation_id: str) -> bool:
        """Delete a relationship by its ID.

        Args:
            relation_id (str): ID of the relationship to delete

        Returns:
            bool: True if the deletion was successful, False otherwise
        """
        # First check if the relationship exists
        check_query = """
        MATCH ()-[r:related_to { id: $relation_id }]->()
        RETURN r.id as id
        """
        result = self.client.query(
            check_query,
            parameters={'relation_id': relation_id},
            language=QueryLanguage.OPEN_CYPHER,
        )
        result_data = json.loads(result)

        if not result_data.get('results'):
            self.logger.warning(f"Relationship with ID '{relation_id}' not found")
            return False

        # Delete the specific relationship
        delete_query = """
        MATCH ()-[r:related_to { id: $relation_id }]->()
        DELETE r
        """

        try:
            self.client.query(
                delete_query,
                parameters={'relation_id': relation_id},
                language=QueryLanguage.OPEN_CYPHER,
            )
            self.logger.info(
                f"Successfully deleted relationship with ID '{relation_id}'"
            )
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to delete relationship with ID '{relation_id}': {e}"
            )
            return False
