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
"""

import json
import logging
import uuid
from dataclasses import asdict
from ws_memory_mcp.graph_server import GraphServer
from ws_memory_mcp.models import Entity, KnowledgeGraph, Observation, QueryLanguage, Relation
from typing import Any, Dict, List, Optional


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
            RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations
            """
        else:
            query = """
            MATCH (entity:Memory)
            RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations
            """
        resp = self.client.query(query, parameters={"filter": filter_query}, language=QueryLanguage.OPEN_CYPHER)
        result = json.loads(resp)["results"]

        entities = []
        for record in result:
            # Handle different result formats from different backends
            if isinstance(record, dict):
                # Check for direct field access (FalkorDB format)
                if "name" in record and "type" in record:
                    observations = record.get("observations", [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split("|") if observations else []
                    elif not isinstance(observations, list):
                        observations = []
                    
                    entities.append(
                        Entity(
                            id=record.get("id"),
                            name=record["name"],
                            type=record["type"],
                            observations=observations,
                        )
                    )
                # Check for column-based format (col_0, col_1, col_2, col_3)
                elif "col_0" in record and "col_1" in record:
                    # col_0 = id, col_1 = name, col_2 = type, col_3 = observations
                    entity_id = record.get("col_0")
                    name = record.get("col_1")
                    entity_type = record.get("col_2")
                    observations = record.get("col_3", [])
                    
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split("|") if observations else []
                    elif not isinstance(observations, list):
                        observations = []
                    
                    entities.append(
                        Entity(
                            id=entity_id,
                            name=name,
                            type=entity_type,
                            observations=observations,
                        )
                    )
                    continue
                # Check for Neptune format with nested node
                elif "node" in record:
                    record = record["node"]
                
                if "name" in record:
                    observations = record.get("observations", [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split("|") if observations else []
                    elif not isinstance(observations, list):
                        observations = []
                    
                    entities.append(
                        Entity(
                            id=record.get("id"),
                            name=record["name"],
                            type=record.get("type", "Unknown"),
                            observations=observations,
                        )
                    )

        if filter_query:
            query = """
            MATCH (source:Memory)-[r:related_to]->(target:Memory)
            WHERE toLower(source.name) CONTAINS toLower($filter) OR toLower(target.name) CONTAINS toLower($filter)
            RETURN r.id as id, source.name as source, target.name as target, r.type as relationType, source.id as source_id, target.id as target_id
            """
        else:
            query = """
            MATCH (source:Memory)-[r:related_to]->(target:Memory)
            RETURN r.id as id, source.name as source, target.name as target, r.type as relationType, source.id as source_id, target.id as target_id
            """
        resp = self.client.query(query, parameters={"filter": filter_query}, language=QueryLanguage.OPEN_CYPHER)

        result = json.loads(resp)["results"]
        rels = []
        for record in result:
            # Handle different result formats from different backends
            if isinstance(record, dict):
                # Check for direct field access
                if "source" in record and "target" in record and "relationType" in record:
                    rels.append(
                        Relation(
                            id=record.get("id"),
                            source=record["source"],
                            target=record["target"],
                            relationType=record["relationType"],
                            source_id=record.get("source_id"),
                            target_id=record.get("target_id")
                        )
                    )
                # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5)
                elif "col_0" in record and "col_1" in record and "col_2" in record:
                    # col_0 = r.id, col_1 = source.name, col_2 = target.name, col_3 = r.type, col_4 = source.id, col_5 = target.id
                    rels.append(
                        Relation(
                            id=record.get("col_0"),
                            source=record.get("col_1"),
                            target=record.get("col_2"),
                            relationType=record.get("col_3"),
                            source_id=record.get("col_4"),
                            target_id=record.get("col_5")
                        )
                    )
                # Check for Neptune format with nested rel
                elif "rel" in record:
                    rel_data = record["rel"]
                    if "relationType" in rel_data:
                        rels.append(
                            Relation(
                                id=rel_data.get("id"),
                                source=rel_data["source"],
                                target=rel_data["target"],
                                relationType=rel_data["relationType"],
                                source_id=rel_data.get("source_id"),
                                target_id=rel_data.get("target_id")
                            )
                        )

        self.logger.debug(f"Loaded entities: {entities}")
        self.logger.debug(f"Loaded relations: {rels}")
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
        """

        self.client.query(
            query, parameters={"relations": [asdict(relation) for relation in relations]}, language=QueryLanguage.OPEN_CYPHER
        )

        return relations



    def read_graph(self) -> KnowledgeGraph:
        """Read the entire knowledge graph.

        Returns:
            KnowledgeGraph: Complete graph with all entities and relations
        """
        return self.load_graph()

    def search_nodes(self, query: str) -> KnowledgeGraph:
        """Search for nodes in the knowledge graph by name only.

        Args:
            query (str): Search query string (searches entity names only, not observations)

        Returns:
            KnowledgeGraph: Graph containing matching nodes and their relations
        """
        self.logger.debug(f"Searching nodes with query: '{query}'")
        
        # If query is empty, return empty results instead of all data
        if not query or query.strip() == "":
            self.logger.debug("Empty query provided, returning empty results")
            return KnowledgeGraph(entities=[], relations=[])
        
        result = self.load_graph(query)
        self.logger.debug(f"Search found {len(result.entities)} entities and {len(result.relations)} relations")
        return result



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
        self.logger.debug(f"Searching entities with attributes: {attributes}")
        
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
                elif key in ['observations', 'observation_contains', 'name_contains', 'type_contains']:
                    # Observation search not allowed
                    self.logger.warning(f"Search on observations is not supported: {key}")
                    match = False
                    break
                else:
                    self.logger.warning(f"Unsupported search attribute: {key}")
                    match = False
                    break
            
            if match:
                ids.append(entity.id)
        
        self.logger.debug(f"Found {len(ids)} entities matching criteria: {ids}")
        return ids

    def find_relation_ids_by_attributes(self, **attributes) -> List[str]:
        """Find relationship IDs by various attributes (exact matches only).

        Args:
            **attributes: Keyword arguments for relationship attributes 
                         (source, target, relationType, source_name, target_name, source_id, target_id)

        Returns:
            List[str]: List of relationship IDs that exactly match the criteria
        """
        self.logger.debug(f"Searching relations with attributes: {attributes}")
        
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
                    self.logger.warning(f"Unsupported relation search attribute: {key}")
                    match = False
                    break
            
            if match:
                ids.append(relation.id)
        
        self.logger.debug(f"Found {len(ids)} relations matching criteria: {ids}")
        return ids



    # ID-based operations
    def create_entities_with_ids(self, entities: List[Entity]) -> List[Entity]:
        """Create new entities with auto-generated IDs if not provided.

        Args:
            entities (List[Entity]): List of entities to create

        Returns:
            List[Entity]: The created entities with their IDs
        """
        # Generate IDs for entities that don't have them
        for entity in entities:
            if not entity.id:
                entity.id = str(uuid.uuid4())
        
        query = """
        UNWIND $entities as entity
        CREATE (e:Memory)
        SET e.id = entity.id
        SET e.name = entity.name
        SET e.type = entity.type
        SET e.observations = entity.observations
        """
        entities_data = [asdict(entity) for entity in entities]
        self.client.query(query, parameters={"entities": entities_data}, language=QueryLanguage.OPEN_CYPHER)
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
        RETURN entity.id as id, entity.name as name, entity.type as type, entity.observations as observations
        """
        resp = self.client.query(query, language=QueryLanguage.OPEN_CYPHER)
        result = json.loads(resp)["results"]
        
        if not result:
            return None
        
        # Use the same parsing logic as load_graph
        for record in result:
            if isinstance(record, dict):
                # Check for direct field access (FalkorDB format)
                if "name" in record and "type" in record:
                    observations = record.get("observations", [])
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split("|") if observations else []
                    elif not isinstance(observations, list):
                        observations = []
                    
                    return Entity(
                        id=record.get("id"),
                        name=record["name"],
                        type=record["type"],
                        observations=observations,
                    )
                # Check for column-based format (col_0, col_1, col_2, col_3)
                elif "col_0" in record and "col_1" in record:
                    # col_0 = id, col_1 = name, col_2 = type, col_3 = observations
                    entity_id_result = record.get("col_0")
                    name = record.get("col_1")
                    entity_type = record.get("col_2")
                    observations = record.get("col_3", [])
                    
                    # Handle both list and string formats for observations
                    if isinstance(observations, str):
                        observations = observations.split("|") if observations else []
                    elif not isinstance(observations, list):
                        observations = []
                    
                    return Entity(
                        id=entity_id_result,
                        name=name,
                        type=entity_type,
                        observations=observations,
                    )
        
        return None

    def update_entity_by_id(self, entity_id: str, updates: Dict[str, Any]) -> bool:
        """Update any attributes of an entity by its ID.

        Args:
            entity_id (str): ID of the entity to update
            updates (Dict[str, Any]): Dictionary of attribute updates

        Returns:
            bool: True if the update was successful, False otherwise
        """
        # First check if the entity exists
        check_query = """
        MATCH (e:Memory { id: $entity_id })
        RETURN e.id as id
        """
        result = self.client.query(check_query, parameters={"entity_id": entity_id}, language=QueryLanguage.OPEN_CYPHER)
        result_data = json.loads(result)
        
        if not result_data.get("results"):
            self.logger.warning(f"Entity with ID '{entity_id}' not found")
            return False
        
        # Build the SET clause dynamically based on updates
        set_clauses = []
        parameters = {"entity_id": entity_id}
        
        for key, value in updates.items():
            if key in ['name', 'type', 'observations']:
                param_name = f"new_{key}"
                set_clauses.append(f"e.{key} = ${param_name}")
                parameters[param_name] = value
            else:
                self.logger.warning(f"Unsupported update attribute: {key}")
        
        if not set_clauses:
            self.logger.warning("No valid attributes to update")
            return False
        
        update_query = f"""
        MATCH (e:Memory {{ id: $entity_id }})
        SET {', '.join(set_clauses)}
        RETURN e.id as id, e.name as name, e.type as type, e.observations as observations
        """
        
        try:
            self.client.query(update_query, parameters=parameters, language=QueryLanguage.OPEN_CYPHER)
            self.logger.info(f"Successfully updated entity with ID '{entity_id}' with attributes: {list(updates.keys())}")
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
        result = self.client.query(check_query, parameters={"entity_id": entity_id}, language=QueryLanguage.OPEN_CYPHER)
        result_data = json.loads(result)
        
        if not result_data.get("results"):
            self.logger.warning(f"Entity with ID '{entity_id}' not found")
            return False
        
        # Delete the entity and all its relationships
        delete_query = """
        MATCH (e:Memory { id: $entity_id })
        DETACH DELETE e
        """
        
        try:
            self.client.query(delete_query, parameters={"entity_id": entity_id}, language=QueryLanguage.OPEN_CYPHER)
            self.logger.info(f"Successfully deleted entity with ID '{entity_id}' and all its relationships")
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
               source.id as source_id, target.id as target_id
        """
        result = self.client.query(query, parameters={"relation_id": relation_id}, language=QueryLanguage.OPEN_CYPHER)
        result_data = json.loads(result)
        
        if not result_data.get("results"):
            return None
        
        record = result_data["results"][0]
        # Handle different result formats
        if isinstance(record, dict):
            # Check for direct field access
            if "id" in record and "source" in record and "target" in record and "relationType" in record:
                return Relation(
                    id=record["id"],
                    source=record["source"],
                    target=record["target"],
                    relationType=record["relationType"],
                    source_id=record.get("source_id"),
                    target_id=record.get("target_id")
                )
            # Check for column-based format (col_0, col_1, col_2, col_3, col_4, col_5)
            elif "col_0" in record and "col_1" in record and "col_2" in record and "col_3" in record:
                # col_0 = r.id, col_1 = source.name, col_2 = target.name, col_3 = r.type, col_4 = source.id, col_5 = target.id
                return Relation(
                    id=record.get("col_0"),
                    source=record.get("col_1"),
                    target=record.get("col_2"),
                    relationType=record.get("col_3"),
                    source_id=record.get("col_4"),
                    target_id=record.get("col_5")
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
        result = self.client.query(check_query, parameters={"relation_id": relation_id}, language=QueryLanguage.OPEN_CYPHER)
        result_data = json.loads(result)
        
        if not result_data.get("results"):
            self.logger.warning(f"Relationship with ID '{relation_id}' not found")
            return False
        
        # Handle source and target updates by recreating the relationship
        if 'source' in updates or 'target' in updates:
            # Get current relationship data
            current_rel = result_data["results"][0]
            current_source = current_rel.get("source") or current_rel.get("col_1")
            current_target = current_rel.get("target") or current_rel.get("col_2")
            
            # Get current relationship type
            rel_query = """
            MATCH ()-[r:related_to { id: $relation_id }]->()
            RETURN r.type as relationType
            """
            rel_result = self.client.query(rel_query, parameters={"relation_id": relation_id}, language=QueryLanguage.OPEN_CYPHER)
            rel_data = json.loads(rel_result)
            current_rel_type = rel_data["results"][0].get("relationType") or rel_data["results"][0].get("col_0")
            
            # Determine new source and target
            new_source = updates.get('source', current_source)
            new_target = updates.get('target', current_target)
            new_rel_type = updates.get('relationType', current_rel_type)
            
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
            """
            
            try:
                # Delete old relationship
                self.client.query(delete_query, parameters={"relation_id": relation_id}, language=QueryLanguage.OPEN_CYPHER)
                
                # Create new relationship
                self.client.query(create_query, parameters={
                    "relation_id": relation_id,
                    "source": new_source,
                    "target": new_target,
                    "relationType": new_rel_type
                }, language=QueryLanguage.OPEN_CYPHER)
                
                self.logger.info(f"Successfully updated relationship with ID '{relation_id}' with attributes: {list(updates.keys())}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to update relationship with ID '{relation_id}': {e}")
                return False
        
        # Handle simple attribute updates (relationType only)
        else:
            set_clauses = []
            parameters = {"relation_id": relation_id}
            
            for key, value in updates.items():
                if key == 'relationType':
                    param_name = f"new_{key}"
                    set_clauses.append(f"r.type = ${param_name}")
                    parameters[param_name] = value
                else:
                    self.logger.warning(f"Unsupported relationship update attribute: {key}")
            
            if not set_clauses:
                self.logger.warning("No valid relationship attributes to update")
                return False
            
            update_query = f"""
            MATCH ()-[r:related_to {{ id: $relation_id }}]->()
            SET {', '.join(set_clauses)}
            RETURN r.id as id, r.type as relationType
            """
            
            try:
                self.client.query(update_query, parameters=parameters, language=QueryLanguage.OPEN_CYPHER)
                self.logger.info(f"Successfully updated relationship with ID '{relation_id}' with attributes: {list(updates.keys())}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to update relationship with ID '{relation_id}': {e}")
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
        result = self.client.query(check_query, parameters={"relation_id": relation_id}, language=QueryLanguage.OPEN_CYPHER)
        result_data = json.loads(result)
        
        if not result_data.get("results"):
            self.logger.warning(f"Relationship with ID '{relation_id}' not found")
            return False
        
        # Delete the specific relationship
        delete_query = """
        MATCH ()-[r:related_to { id: $relation_id }]->()
        DELETE r
        """
        
        try:
            self.client.query(delete_query, parameters={"relation_id": relation_id}, language=QueryLanguage.OPEN_CYPHER)
            self.logger.info(f"Successfully deleted relationship with ID '{relation_id}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete relationship with ID '{relation_id}': {e}")
            return False
