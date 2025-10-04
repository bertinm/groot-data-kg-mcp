#!/usr/bin/env python3
"""
Demo script showing FalkorDB integration working with the Graph Memory MCP Server.
"""

import logging
from ws_memory_mcp.memory import KnowledgeGraphManager
from ws_memory_mcp.falkordb_server import FalkorDBServer
from ws_memory_mcp.models import Entity, Relation, Observation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Demonstrate FalkorDB integration."""
    print("Graph Memory MCP Server - FalkorDB Demo")
    print("=" * 50)
    
    try:
        # Initialize FalkorDB server
        print("1. Connecting to FalkorDB...")
        graph = FalkorDBServer(
            host="localhost",
            port=6379,
            graph_name="demo_memory"
        )
        
        # Check status
        status = graph.status()
        print(f"   Status: {status}")
        
        if status != "Available":
            print("❌ FalkorDB is not available. Please start it with:")
            print("   docker run --rm -p 6379:6379 falkordb/falkordb")
            return 1
        
        # Initialize memory manager
        memory = KnowledgeGraphManager(graph, logger)
        
        # Clear any existing data for clean demo
        print("\n2. Clearing existing data...")
        try:
            from ws_memory_mcp.models import QueryLanguage
            graph.query("MATCH (n) DETACH DELETE n", QueryLanguage.OPEN_CYPHER)
        except:
            pass  # Ignore if no data exists
        
        # Create entities
        print("\n3. Creating entities...")
        entities = [
            Entity(
                name="Alice Johnson", 
                type="Person", 
                observations=["Software Engineer at TechCorp", "Lives in Seattle", "Loves Python programming"]
            ),
            Entity(
                name="Bob Smith", 
                type="Person", 
                observations=["Data Scientist", "PhD in Machine Learning", "Coffee enthusiast"]
            ),
            Entity(
                name="TechCorp", 
                type="Company", 
                observations=["Technology startup", "Founded in 2020", "Focuses on AI solutions"]
            ),
            Entity(
                name="Python", 
                type="Technology", 
                observations=["Programming language", "Popular for AI/ML", "Open source"]
            )
        ]
        
        result = memory.create_entities(entities)
        print(f"   Created {len(entities)} entities")
        
        # Create relationships
        print("\n4. Creating relationships...")
        relations = [
            Relation(source="Alice Johnson", target="TechCorp", relationType="works_at"),
            Relation(source="Bob Smith", target="TechCorp", relationType="works_at"),
            Relation(source="Alice Johnson", target="Bob Smith", relationType="colleague_of"),
            Relation(source="Alice Johnson", target="Python", relationType="programs_in"),
            Relation(source="Bob Smith", target="Python", relationType="uses_for_ml")
        ]
        
        memory.create_relations(relations)
        print(f"   Created {len(relations)} relationships")
        
        # Read the entire graph
        print("\n5. Reading knowledge graph...")
        knowledge_graph = memory.read_graph()
        print(f"   Graph contains:")
        print(f"   - {len(knowledge_graph.entities)} entities")
        print(f"   - {len(knowledge_graph.relations)} relations")
        
        # Display entities
        print("\n   Entities:")
        for entity in knowledge_graph.entities:
            print(f"   - {entity.name} ({entity.type})")
            for obs in entity.observations[:2]:  # Show first 2 observations
                print(f"     • {obs}")
        
        # Display relations
        print("\n   Relations:")
        for relation in knowledge_graph.relations:
            print(f"   - {relation.source} --[{relation.relationType}]--> {relation.target}")
        
        # Search functionality
        print("\n6. Testing search functionality...")
        search_results = memory.search_nodes("Alice")
        print(f"   Search for 'Alice' found {len(search_results.entities)} entities")
        
        search_results = memory.search_nodes("Tech")
        print(f"   Search for 'Tech' found {len(search_results.entities)} entities")
        
        # Add observations
        print("\n7. Adding new observations...")
        observations = [
            Observation(
                entityName="Alice Johnson",
                contents=["Recently promoted to Senior Engineer", "Working on new AI project"]
            ),
            Observation(
                entityName="TechCorp",
                contents=["Received Series A funding", "Expanding team"]
            )
        ]
        
        memory.add_observations(observations)
        print(f"   Added observations for {len(observations)} entities")
        
        # Read updated graph
        print("\n8. Reading updated graph...")
        updated_graph = memory.read_graph()
        
        # Show updated Alice entity
        alice = next((e for e in updated_graph.entities if e.name == "Alice Johnson"), None)
        if alice:
            print(f"   Alice Johnson now has {len(alice.observations)} observations:")
            for obs in alice.observations:
                print(f"     • {obs}")
        
        # Test schema retrieval
        print("\n9. Testing schema retrieval...")
        try:
            schema = graph.schema()
            print(f"   Schema retrieved successfully")
            print(f"   - Node types: {len(schema.get('nodes', []))}")
            print(f"   - Relationship types: {len(schema.get('relationships', []))}")
        except Exception as e:
            print(f"   Schema retrieval failed: {e}")
        
        # Close connection
        graph.close()
        
        print("\n🎉 FalkorDB demo completed successfully!")
        print("\nThis demonstrates that FalkorDB can be used as a drop-in replacement")
        print("for Neptune in the Graph Memory MCP Server, providing:")
        print("- Persistent memory storage")
        print("- Entity and relationship management") 
        print("- Search capabilities")
        print("- Observation tracking")
        print("- Schema introspection")
        
        return 0
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        print("\nMake sure FalkorDB is running:")
        print("docker run --rm -p 6379:6379 falkordb/falkordb")
        return 1


if __name__ == "__main__":
    exit(main())