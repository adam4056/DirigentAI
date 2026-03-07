#!/usr/bin/env python3
"""End-to-end test of DirigentAI with multi-provider configuration."""
import os
import sys
import logging

# Set environment variables for testing
os.environ["HIDE_WORKER_CREATION"] = "true"

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_orchestrator_initialization():
    """Test that orchestrator can be initialized with configuration."""
    print("Testing orchestrator initialization...")
    try:
        from core.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        print(f"[OK] Orchestrator initialized successfully")
        print(f"  Model: {orchestrator.model_name}")
        print(f"  LLM Client: {type(orchestrator.llm_client).__name__}")
        print(f"  Max workers: {orchestrator.max_workers}")
        print(f"  Hide worker creation: {orchestrator.hide_worker_creation}")
        return orchestrator
    except Exception as e:
        print(f"[FAIL] Orchestrator initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_simple_conversation(orchestrator):
    """Test a simple conversation that doesn't require workers."""
    print("\nTesting simple conversation...")
    try:
        response = orchestrator.process("Hello, what is 2+2?", session_id="test1")
        print(f"[OK] Simple conversation completed")
        print(f"  Response length: {len(response)} characters")
        print(f"  Response preview: {response[:100]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Simple conversation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_worker_delegation(orchestrator):
    """Test that orchestrator can delegate to a worker for a simple task."""
    print("\nTesting worker delegation...")
    try:
        # Ask to list files - should trigger worker creation and delegation
        response = orchestrator.process("List the files in the current directory", session_id="test2")
        print(f"[OK] Worker delegation completed")
        print(f"  Response length: {len(response)} characters")
        print(f"  Response preview: {response[:200]}...")
        return True
    except Exception as e:
        print(f"[FAIL] Worker delegation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_configuration_system():
    """Test that configuration system works correctly."""
    print("\nTesting configuration system...")
    try:
        from core.config import DirigentConfig
        config = DirigentConfig()
        
        # Test various config sections
        orchestrator_config = config.get_orchestrator_config()
        workers_config = config.get_workers_config()
        ui_config = config.get_ui_config()
        security_config = config.get_security_config()
        
        print(f"[OK] Configuration loaded successfully")
        print(f"  Provider: {orchestrator_config.get('provider')}")
        print(f"  Model: {orchestrator_config.get('model')}")
        print(f"  Max workers: {workers_config.get('max_workers')}")
        print(f"  Hide worker creation: {ui_config.get('hide_worker_creation')}")
        return True
    except Exception as e:
        print(f"[FAIL] Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("DirigentAI Multi-Provider System End-to-End Test")
    print("=" * 60)
    
    # Configure logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    # Run tests
    config_ok = test_configuration_system()
    if not config_ok:
        print("\nConfiguration test failed, aborting.")
        return 1
    
    orchestrator = test_orchestrator_initialization()
    if not orchestrator:
        print("\nOrchestrator initialization failed, aborting.")
        return 1
    
    conv_ok = test_simple_conversation(orchestrator)
    if not conv_ok:
        print("\nSimple conversation test failed.")
        # Continue anyway
    
    # Note: Worker delegation test uses API calls and may cost tokens
    # Uncomment to test worker delegation
    # delegation_ok = test_worker_delegation(orchestrator)
    
    print("\n" + "=" * 60)
    print("Test summary:")
    print(f"  Configuration: {'[OK]' if config_ok else '[FAIL]'}")
    print(f"  Orchestrator init: {'[OK]' if orchestrator else '[FAIL]'}")
    print(f"  Simple conversation: {'[OK]' if conv_ok else '[FAIL]'}")
    # print(f"  Worker delegation: {'[OK]' if delegation_ok else '[FAIL]'}")
    print("=" * 60)
    
    if config_ok and orchestrator and conv_ok:
        print("\nAll critical tests passed! The multi-provider system is working.")
        return 0
    else:
        print("\nSome tests failed. Review output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())