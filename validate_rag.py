#!/usr/bin/env python3
"""
Static validation of the CueCard RAG enhancements.
This script performs basic validation without requiring external dependencies.
"""

import ast
import sys
from pathlib import Path

def validate_file_syntax(filepath):
    """Validate Python file syntax"""
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read())
        return True, None
    except SyntaxError as e:
        return False, str(e)

def check_file_has_content(filepath, expected_strings):
    """Check if file contains expected strings"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    missing = []
    for expected in expected_strings:
        if expected not in content:
            missing.append(expected)
    
    return len(missing) == 0, missing

def main():
    print("🔍 Validating CueCard RAG Enhancements\n")
    print("="*60)
    
    api_dir = Path(__file__).parent / "api"
    root_dir = Path(__file__).parent
    
    all_passed = True
    
    # 1. Validate Python syntax
    print("\n1. Checking Python Syntax...")
    python_files = [
        api_dir / "app" / "server.py",
        api_dir / "app" / "db" / "repo.py",
        api_dir / "test_rag_api.py",
        root_dir / "examples" / "rag_chatbot_example.py",
        root_dir / "examples" / "openapi_ingestion_example.py",
    ]
    
    for filepath in python_files:
        valid, error = validate_file_syntax(filepath)
        if valid:
            print(f"  ✓ {filepath.name} - syntax OK")
        else:
            print(f"  ✗ {filepath.name} - syntax error: {error}")
            all_passed = False
    
    # 2. Check server.py has all endpoints
    print("\n2. Checking API Endpoints...")
    endpoints = [
        '@app.get("/health")',
        '@app.post("/retrieve")',
        '@app.post("/record"',
        '@app.post("/log")',
        '@app.post("/vote")',
        '@app.get("/documents")',
        '@app.get("/documents/{doc_id}")',
        '@app.delete("/documents/{doc_id}")',
        '@app.get("/stats")',
        '@app.get("/config")',
    ]
    
    valid, missing = check_file_has_content(api_dir / "app" / "server.py", endpoints)
    if valid:
        print(f"  ✓ All {len(endpoints)} endpoints defined")
    else:
        print(f"  ✗ Missing endpoints: {missing}")
        all_passed = False
    
    # 3. Check repo.py has all functions
    print("\n3. Checking Repository Functions...")
    functions = [
        'async def list_documents(',
        'async def get_document(',
        'async def delete_document(',
        'async def get_statistics(',
    ]
    
    valid, missing = check_file_has_content(api_dir / "app" / "db" / "repo.py", functions)
    if valid:
        print(f"  ✓ All new repository functions defined")
    else:
        print(f"  ✗ Missing functions: {missing}")
        all_passed = False
    
    # 4. Check test coverage
    print("\n4. Checking Test Coverage...")
    test_classes = [
        'class TestHealthEndpoint:',
        'class TestConfigEndpoint:',
        'class TestStatsEndpoint:',
        'class TestRecordAndIngestion:',
        'class TestRetrieveEndpoint:',
        'class TestDocumentManagement:',
        'class TestVotingAndRanking:',
        'class TestLogging:',
        'class TestEndToEndRAGWorkflow:',
    ]
    
    valid, missing = check_file_has_content(api_dir / "test_rag_api.py", test_classes)
    if valid:
        print(f"  ✓ All {len(test_classes)} test classes defined")
    else:
        print(f"  ✗ Missing test classes: {missing}")
        all_passed = False
    
    # 5. Check documentation files exist
    print("\n5. Checking Documentation...")
    doc_files = [
        (root_dir / ".env.example", ".env.example"),
        (root_dir / "RAG-GUIDE.md", "RAG-GUIDE.md"),
        (root_dir / "examples" / "README.md", "examples/README.md"),
    ]
    
    for filepath, name in doc_files:
        if filepath.exists():
            print(f"  ✓ {name} exists")
        else:
            print(f"  ✗ {name} missing")
            all_passed = False
    
    # 6. Check .env.example has all configs
    print("\n6. Checking Configuration...")
    configs = [
        'POSTGRES_HOST',
        'DATABASE_URL',
        'EMBEDDING_PROVIDER',
        'EMBEDDING_MODEL',
        'RERANK_WEIGHT',
        'RETRIEVAL_OVERFETCH',
        'VOTE_BOOST_WEIGHT',
        'USAGE_BOOST_WEIGHT',
        'USAGE_BOOST_TTL_DAYS',
        'WORKER_POLL_SEC',
        'WORKER_BATCH',
        'WORKER_LEASE_SEC',
        'CLEANUP_INTERVAL_SEC',
    ]
    
    valid, missing = check_file_has_content(root_dir / ".env.example", configs)
    if valid:
        print(f"  ✓ All {len(configs)} configuration options documented")
    else:
        print(f"  ✗ Missing configs: {missing}")
        all_passed = False
    
    # 7. Check test dependencies file
    print("\n7. Checking Dependencies...")
    deps = ['pytest', 'pytest-asyncio']
    
    valid, missing = check_file_has_content(api_dir / "requirements-dev.txt", deps)
    if valid:
        print(f"  ✓ Test dependencies added")
    else:
        print(f"  ✗ Missing dependencies: {missing}")
        all_passed = False
    
    # Summary
    print("\n" + "="*60)
    if all_passed:
        print("✅ All validations passed!")
        print("\nThe RAG enhancements are ready for testing.")
        print("\nNext steps:")
        print("  1. Start the service: docker compose up -d --build")
        print("  2. Run migrations: docker compose run --rm migrations")
        print("  3. Run the tests: docker compose run --rm --no-deps api pytest -v")
        print("  4. Try the examples: python examples/rag_chatbot_example.py")
        return 0
    else:
        print("❌ Some validations failed")
        print("\nPlease review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
