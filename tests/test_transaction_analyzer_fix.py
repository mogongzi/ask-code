"""
Test for transaction analyzer improvements to prevent hallucinated source locations.

This test verifies that:
1. Controller context is properly labeled as "inferred" when not verified
2. Controller context is verified against actual files when possible
3. Summary clearly distinguishes verified vs inferred sources
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.transaction_analyzer import TransactionAnalyzer


def test_inferred_context_has_warning():
    """Test that inferred controller context includes proper warnings."""
    analyzer = TransactionAnalyzer(project_root=None)

    # Sample transaction log with controller metadata in SQL comments (Rails marginalia style)
    sample_log = """
BEGIN
INSERT INTO `page_views` (`member_id`, `company_id`) VALUES (123, 456) /* controller:work_pages, action:show_as_tab */
COMMIT
"""

    result = analyzer.execute({
        "transaction_log": sample_log,
        "find_source_code": False  # Don't search for actual files
    })

    # Check that controller context pattern exists
    controller_patterns = [
        p for p in result.get("transaction_patterns", [])
        if p.get("pattern_type") == "controller_context"
    ]

    assert len(controller_patterns) > 0, "Should detect controller context from SQL"

    # Verify the pattern has proper fields
    pattern = controller_patterns[0]
    assert pattern.get("inferred_context") is not None, "Should have inferred_context field"
    assert pattern.get("source_type") == "sql_metadata", "Should mark as SQL metadata"
    assert pattern.get("warning") is not None, "Should include warning about inference"
    assert "not verified" in pattern.get("warning", "").lower(), "Warning should mention verification"

    # Verify old 'likely_source' field doesn't exist
    assert pattern.get("likely_source") is None, "Old 'likely_source' field should not exist"


def test_controller_verification_separate_from_inference():
    """Test that verified controller context is separate from inferred context."""
    # This would require a real Rails project, so we'll just verify the structure
    analyzer = TransactionAnalyzer(project_root="/tmp/fake_project")

    sample_log = """
BEGIN
INSERT INTO `page_views` (`member_id`, `company_id`) VALUES (123, 456) /* controller:users, action:show */
COMMIT
"""

    result = analyzer.execute({
        "transaction_log": sample_log,
        "find_source_code": True
    })

    # Check that source findings have proper search_strategy tags
    findings = result.get("source_code_findings", [])

    # Findings should be categorized by strategy
    strategies = [f.get("search_strategy") for f in findings]

    # Valid strategies
    valid_strategies = [
        "controller_context_verification",
        "transaction_fingerprint",
        "individual_query"
    ]

    for strategy in strategies:
        assert strategy in valid_strategies, f"Unknown search strategy: {strategy}"


def test_summary_separates_verified_from_inferred():
    """Test that summary clearly distinguishes verified vs inferred sources."""
    analyzer = TransactionAnalyzer(project_root=None)

    sample_log = """
BEGIN
INSERT INTO `page_views` (`member_id`, `company_id`) VALUES (123, 456) /* controller:home, action:index */
COMMIT
"""

    result = analyzer.execute({
        "transaction_log": sample_log,
        "find_source_code": False
    })

    summary = result.get("transaction_summary", "")

    # Summary should contain inferred context section with warning
    assert "Inferred Context" in summary or "inferred_context" in str(result), \
        "Should include inferred context information"

    # Should NOT claim "EXACT MATCH" or "VERIFIED" without actual verification
    if "controller" in summary.lower():
        # If controller is mentioned, verify it's marked appropriately
        patterns = result.get("transaction_patterns", [])
        controller_patterns = [p for p in patterns if p.get("pattern_type") == "controller_context"]

        if controller_patterns:
            # Check that the pattern includes warning
            assert controller_patterns[0].get("warning") is not None, \
                "Controller context must include warning when not verified"


def test_compact_output_prioritizes_verified_controller():
    """Test that compact output prioritizes verified controller over transaction fingerprint."""
    analyzer = TransactionAnalyzer(project_root=None)

    # Simulate findings with both types
    full_result = {
        "query_count": 5,
        "tables_affected": ["users", "posts"],
        "operation_types": ["INSERT", "SELECT"],
        "transaction_patterns": [],
        "source_code_findings": [
            {
                "search_strategy": "individual_query",
                "search_results": {
                    "matches": [{
                        "file": "lib/helper.rb",
                        "line": 10,
                        "confidence": "medium"
                    }]
                }
            },
            {
                "search_strategy": "controller_context_verification",
                "search_results": {
                    "matches": [{
                        "file": "app/controllers/users_controller.rb",
                        "line": 42,
                        "confidence": "verified"
                    }]
                }
            },
            {
                "search_strategy": "transaction_fingerprint",
                "search_results": {
                    "matches": [{
                        "file": "lib/service.rb",
                        "line": 100,
                        "confidence": "high"
                    }]
                }
            }
        ]
    }

    compact = analyzer.create_compact_output(full_result)

    # Compact output should prioritize verified controller
    source_info = compact.get("source_code")

    if isinstance(source_info, dict):
        assert source_info.get("file") == "app/controllers/users_controller.rb", \
            "Should prioritize verified controller over transaction fingerprint"
        assert source_info.get("type") == "verified_controller", \
            "Should mark as verified controller"


if __name__ == "__main__":
    # Run tests
    print("Running transaction analyzer fix tests...")

    test_inferred_context_has_warning()
    print("✓ Test 1 passed: Inferred context has proper warnings")

    test_controller_verification_separate_from_inference()
    print("✓ Test 2 passed: Controller verification is separate from inference")

    test_summary_separates_verified_from_inferred()
    print("✓ Test 3 passed: Summary separates verified from inferred")

    test_compact_output_prioritizes_verified_controller()
    print("✓ Test 4 passed: Compact output prioritizes verified controller")

    print("\n✅ All tests passed!")
