#!/usr/bin/env python3
"""
Example usage of the Graph Memory MCP Server with both Neptune and FalkorDB backends.

This script demonstrates how to initialize and use the memory system with different backends.
"""

import logging
from ws_memory_mcp.memory import KnowledgeGraphManager
from ws_memory_mcp.neptune import NeptuneServer
from ws_memory_mcp.falkordb_server import FalkorDBServer
from ws_memory_mcp.models import Entity, Relation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_with_falkordb():
    """Example using FalkorDB backend."""
    print("=== FalkorDB Example ===")
    
    try:
        # Initialize FalkorDB server
        # Note: Requires FalkorDB running on localhost:6379
        graph = FalkorDBServer(
            host="localhost",
            port=6379,
            graph_name="example_memory"
        )
        
        # Initialize memory manager
        memory = KnowledgeGraphManager(graph, logger)
        
        # Check status
        status = graph.status()
        print(f"FalkorDB Status: {status}")
        
        if status == "Available":
            # Create some example entities
            entities = [
                Entity(name="Alice", type="Person", observations=["Works at Tech Corp", "Lives in Seattle"]),
                Entity(name="Bob", type="Person", observations=["Software Engineer", "Likes coffee"]),
                Entity(name="Tech Corp", type="Company", observations=["Technology company", "Founded in 2010"])
            ]
            
            # Create entities
            memory.create_entities(entities)
            print("Created entities successfully")
            
            # Create relationships
            relations = [
                Relation(source="Alice", target="Tech Corp", relationType="works_at"),
                Relation(source="Bob", target="Tech Corp", relationType="works_at"),
                Relation(source="Alice", target="Bob", relationType="colleague_of")
            ]
            
            memory.create_relations(relations)
            print("Created relations successfully")
            
            # Read the graph
            knowledge_graph = memory.read_graph()
            print(f"Graph contains {len(knowledge_graph.entities)} entities and {len(knowledge_graph.relations)} relations")
            
            # Search for entities
            search_results = memory.search_nodes("Alice")
            print(f"Search results for 'Alice': {len(search_results.entities)} entities found")
            
        # Close connection
        graph.close()
        
    except Exception as e:
        print(f"FalkorDB example failed: {e}")
        print("Make sure FalkorDB is running: docker run --rm -p 6379:6379 falkordb/falkordb")


def example_with_neptune():
    """Example using Neptune backend."""
    print("\n=== Neptune Example ===")
    
    try:
        # Initialize Neptune server
        # Note: Requires valid Neptune endpoint
        endpoint = "neptune-db://your-cluster-endpoint"  # Replace with actual endpoint
        
        graph = NeptuneServer(endpoint, use_https=True)
        
        # Initialize memory manager
        memory = KnowledgeGraphManager(graph, logger)
        
        # Check status
        status = graph.status()
        print(f"Neptune Status: {status}")
        
        if status == "Available":
            # Same operations as FalkorDB example
            entities = [
                Entity(name="Charlie", type="Person", observations=["Data Scientist", "PhD in ML"]),
                Entity(name="DataCorp", type="Company", observations=["AI company", "Startup"])
            ]
            
            memory.create_entities(entities)
            print("Created entities successfully")
            
            relations = [
                Relation(source="Charlie", target="DataCorp", relationType="works_at")
            ]
            
            memory.create_relations(relations)
            print("Created relations successfully")
            
            knowledge_graph = memory.read_graph()
            print(f"Graph contains {len(knowledge_graph.entities)} entities and {len(knowledge_graph.relations)} relations")
        
        # Close connection
        graph.close()
        
    except Exception as e:
        print(f"Neptune example failed: {e}")
        print("Make sure you have valid Neptune credentials and endpoint configured")


if __name__ == "__main__":
    print("Graph Memory MCP Server - Usage Examples")
    print("=" * 50)
    
    # Run FalkorDB example
    example_with_falkordb()
    
    # Run Neptune example (commented out by default since it requires AWS setup)
    # example_with_neptune()
    
    print("\nExamples completed!")