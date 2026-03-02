#!/usr/bin/env python3
"""
Installation verification for DirigentAI.
"""

import sys
import os
from dotenv import load_dotenv

def check_installation():
    print("1. Checking library imports...")
    try:
        from google import genai
        print("   OK: google-genai")
    except ImportError:
        print("   FAIL: google-genai - install with: pip install google-genai")
        return False
    
    try:
        import dotenv
        print("   OK: python-dotenv")
    except ImportError:
        print("   FAIL: python-dotenv - install with: pip install python-dotenv")
        return False
    
    print("2. Checking internal modules...")
    try:
        from core.orchestrator import Orchestrator
        print("   OK: core.orchestrator")
    except ImportError as e:
        print(f"   FAIL: core.orchestrator - {e}")
        return False
    
    try:
        from agents.worker import Worker
        print("   OK: agents.worker")
    except ImportError as e:
        print(f"   FAIL: agents.worker - {e}")
        return False
    
    print("3. Checking configuration...")
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and api_key != "your_api_key_here":
        print(f"   OK: GEMINI_API_KEY set ({api_key[:10]}...)")
    else:
        print("   WARNING: GEMINI_API_KEY not set or default value")
        print("      Edit the .env file and insert a valid key from Google AI Studio")
    
    print("\nSUCCESS Verification complete!")
    print("\nIf everything passed, start the system with:")
    print("   python main.py cli")
    return True

if __name__ == "__main__":
    check_installation()
