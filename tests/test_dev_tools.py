import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from agents.worker import Worker

def test_dev_tools_capability():
    """Test that dev_tools capability adds development tools."""
    worker = Worker(
        worker_id="dev_test",
        capabilities=["dev_tools"],
        description="Development specialist",
        api_key=None,
    )
    
    # Check that tool definitions include dev tools
    tools = worker._build_tool_definitions()
    tool_names = [t["name"] for t in tools]
    
    expected_tools = ["execute_code", "git_status", "run_dependency_command", "run_tests"]
    for expected in expected_tools:
        assert expected in tool_names, f"Missing tool {expected} in {tool_names}"
    
    print("OK dev_tools capability adds development tools")

def test_execute_code_dispatch():
    """Test that execute_code dispatch works (without actual execution)."""
    worker = Worker(
        worker_id="dev_test",
        capabilities=["dev_tools"],
        description="Development specialist",
        api_key=None,
    )
    
    # Test dispatch with minimal args
    result = worker._dispatch_tool("execute_code", {"language": "python", "code": "print(1)"})
    # Should not raise exception
    assert isinstance(result, str)
    print(f"OK execute_code dispatch works: {result[:50]}")

def test_git_status_dispatch():
    """Test git_status dispatch."""
    worker = Worker(
        worker_id="dev_test",
        capabilities=["dev_tools"],
        description="Development specialist",
        api_key=None,
    )
    
    result = worker._dispatch_tool("git_status", {"operation": "status"})
    assert isinstance(result, str)
    print(f"OK git_status dispatch works: {result[:50]}")

def test_run_dependency_command_dispatch():
    """Test run_dependency_command dispatch."""
    worker = Worker(
        worker_id="dev_test",
        capabilities=["dev_tools"],
        description="Development specialist",
        api_key=None,
    )
    
    result = worker._dispatch_tool("run_dependency_command", {"tool": "pip", "command": "list"})
    assert isinstance(result, str)
    print(f"OK run_dependency_command dispatch works: {result[:50]}")

def test_run_tests_dispatch():
    """Test run_tests dispatch."""
    worker = Worker(
        worker_id="dev_test",
        capabilities=["dev_tools"],
        description="Development specialist",
        api_key=None,
    )
    
    result = worker._dispatch_tool("run_tests", {"framework": "pytest"})
    assert isinstance(result, str)
    print(f"OK run_tests dispatch works: {result[:50]}")

if __name__ == "__main__":
    test_dev_tools_capability()
    test_execute_code_dispatch()
    test_git_status_dispatch()
    test_run_dependency_command_dispatch()
    test_run_tests_dispatch()
    print("All dev_tools tests passed!")