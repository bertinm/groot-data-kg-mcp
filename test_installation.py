#!/usr/bin/env python3
"""
Test script to verify the Graph Memory MCP Server installation.

This script tests that all modules can be imported and basic functionality works.
"""

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    try:
        from ws_memory_mcp.server import main
        print("✓ Server module imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import server module: {e}")
        return False
    
    try:
        from ws_memory_mcp.memory import KnowledgeGraphManager
        print("✓ Memory module imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import memory module: {e}")
        return False
    
    try:
        from ws_memory_mcp.neptune import NeptuneServer
        print("✓ Neptune module imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import Neptune module: {e}")
        return False
    
    try:
        from ws_memory_mcp.falkordb_server import FalkorDBServer
        print("✓ FalkorDB module imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import FalkorDB module: {e}")
        return False
    
    try:
        from ws_memory_mcp.models import Entity, Relation, KnowledgeGraph
        print("✓ Models module imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import models module: {e}")
        return False
    
    return True


def test_model_creation():
    """Test that model objects can be created."""
    print("\nTesting model creation...")
    
    try:
        from ws_memory_mcp.models import Entity, Relation, KnowledgeGraph
        
        # Test Entity creation
        entity = Entity(name="Test", type="TestType", observations=["Test observation"])
        print("✓ Entity created successfully")
        
        # Test Relation creation
        relation = Relation(source="A", target="B", relationType="test_relation")
        print("✓ Relation created successfully")
        
        # Test KnowledgeGraph creation
        kg = KnowledgeGraph(entities=[entity], relations=[relation])
        print("✓ KnowledgeGraph created successfully")
        
        return True
    except Exception as e:
        print(f"✗ Failed to create models: {e}")
        return False


def test_server_help():
    """Test that the server can show help information."""
    print("\nTesting server help...")
    
    try:
        import sys
        from io import StringIO
        from ws_memory_mcp.server import main
        
        # Capture stdout
        old_stdout = sys.stdout
        old_argv = sys.argv
        
        try:
            sys.stdout = StringIO()
            sys.argv = ['test', '--help']
            main()
        except SystemExit as e:
            # Help command exits with code 0
            if e.code == 0:
                print("✓ Server help displayed successfully")
                return True
            else:
                print(f"✗ Server help failed with exit code: {e.code}")
                return False
        finally:
            sys.stdout = old_stdout
            sys.argv = old_argv
            
    except Exception as e:
        print(f"✗ Failed to test server help: {e}")
        return False


def main():
    """Run all tests."""
    print("Graph Memory MCP Server - Installation Test")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_model_creation,
        test_server_help
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Installation is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the installation.")
        return 1


if __name__ == "__main__":
    exit(main())