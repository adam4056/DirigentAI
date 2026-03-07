#!/usr/bin/env python3
"""Quick test of orchestrator initialization."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.orchestrator import Orchestrator

def main():
    try:
        # This will load config from default location
        orchestrator = Orchestrator()
        print(f"Orchestrator initialized successfully")
        print(f"Model: {orchestrator.model_name}")
        print(f"LLM Client: {orchestrator.llm_client}")
        print(f"Config: {orchestrator.config._config}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())