import os
import sys
import json
from pathlib import Path

# Add project root to path so we can run this directly
sys.path.append(str(Path(__file__).resolve().parent.parent))

def test_imports():
    print("Testing imports...")
    try:
        from backend.config import BASE_DIR, CHROMA_DB_DIR
        from backend.schemas import ExtractedClause, RiskAnalysis, ComparisonItem, AgentState
        from backend.database import get_chroma_client, get_collection, list_documents
        from backend.agents import get_analysis_workflow
        print("[OK] Imports successful!")
        return True
    except Exception as e:
        print(f"[FAIL] Imports failed: {e}")
        return False

def test_playbook():
    print("Testing playbook loading...")
    from backend.config import PLAYBOOK_PATH
    try:
        assert PLAYBOOK_PATH.exists(), f"Playbook file not found at {PLAYBOOK_PATH}"
        with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "contract_types" in data, "Playbook missing 'contract_types'"
        print("[OK] Playbook validation successful!")
        return True
    except Exception as e:
        print(f"[FAIL] Playbook validation failed: {e}")
        return False

def test_graph_compilation():
    print("Testing LangGraph compilation...")
    try:
        from backend.agents import get_analysis_workflow
        workflow = get_analysis_workflow()
        assert workflow is not None, "Workflow is None"
        print("[OK] LangGraph compiled successfully!")
        return True
    except Exception as e:
        print(f"[FAIL] LangGraph compilation failed: {e}")
        return False

if __name__ == "__main__":
    print("=== RUNNING LEGAL AGENT BACKEND TESTS ===")
    success = True
    success &= test_imports()
    success &= test_playbook()
    success &= test_graph_compilation()
    
    if success:
        print("\n[SUCCESS] All tests passed successfully!")
        sys.exit(0)
    else:
        print("\n[ERROR] Some tests failed.")
        sys.exit(1)
