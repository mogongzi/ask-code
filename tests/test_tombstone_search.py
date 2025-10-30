#!/usr/bin/env python3
"""
Simple test for custom_domain_tombstone SQL search.
Tests the fix for scope-based queries with .take

Usage:
    source .venv/bin/activate
    python tests/test_tombstone_search.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sql_rails_search import SQLRailsSearch

# Your Rails project path
PROJECT_ROOT = "/Users/I503354/jam/local/ct"

# SQL query for custom_domain_tombstone lookup
SQL_QUERY = """SELECT * FROM custom_domain_tombstones WHERE custom_domain = ? LIMIT ?"""


def test_tombstone_search():
    """Test sql_rails_search with custom_domain_tombstone query."""

    print("=" * 80)
    print("CUSTOM DOMAIN TOMBSTONE SEARCH TEST")
    print("=" * 80)
    print(f"\nProject root: {PROJECT_ROOT}")
    print(f"\nSQL query: {SQL_QUERY}")
    print("\n" + "-" * 80)

    # Initialize tool (debug=False for clean output, set to True to see details)
    tool = SQLRailsSearch(project_root=PROJECT_ROOT, debug=False)

    # Execute search
    result = tool.execute({
        "sql": SQL_QUERY,
        "max_results": 20,
        "include_explanation": True
    })

    # Print results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    # Check for errors
    if "error" in result:
        print(f"\n❌ ERROR: {result['error']}")
        assert False, f"Tool returned error: {result['error']}"

    # Print summary
    print(f"\nSearch type: {result.get('search_type', 'unknown')}")
    print(f"Match count: {result.get('match_count', 0)}")

    # Print top matches
    matches = result.get('matches', [])
    print(f"\nTop {min(10, len(matches))} matches:")

    for i, match in enumerate(matches[:10], 1):
        file_path = match.get('file', 'N/A')
        line = match.get('line', 'N/A')
        confidence = match.get('confidence', 'N/A')
        snippet = match.get('snippet', 'N/A')[:80]

        print(f"\n{i}. {file_path}:{line}")
        print(f"   Confidence: {confidence}")
        print(f"   Snippet: {snippet}...")

        # Show why for high-confidence matches
        if float(confidence) >= 0.9:
            why = match.get('why', [])
            if why:
                print(f"   Why:")
                for reason in why[:3]:  # Show first 3 reasons
                    print(f"     - {reason}")

    # Verification
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)

    expected_files = {
        'lib/multi_domain.rb': {'found': False, 'confidence': 0.0, 'line': None},
        'app/models/company.rb': {'found': False, 'confidence': 0.0, 'line': None}
    }

    for match in matches:
        file_path = match.get('file', '')
        line = match.get('line', 0)
        confidence = float(match.get('confidence', 0))

        # Check lib/multi_domain.rb (line 43)
        if 'lib/multi_domain.rb' in file_path and line == 43:
            expected_files['lib/multi_domain.rb']['found'] = True
            expected_files['lib/multi_domain.rb']['confidence'] = confidence
            expected_files['lib/multi_domain.rb']['line'] = line

        # Check app/models/company.rb (line 2987)
        if 'app/models/company.rb' in file_path and line == 2987:
            expected_files['app/models/company.rb']['found'] = True
            expected_files['app/models/company.rb']['confidence'] = confidence
            expected_files['app/models/company.rb']['line'] = line

    # Print verification results
    all_found = True
    for file, info in expected_files.items():
        if info['found']:
            conf = info['confidence']
            status = "✅" if conf >= 0.9 else "⚠️" if conf >= 0.7 else "❌"
            conf_label = "HIGH" if conf >= 0.9 else "MEDIUM" if conf >= 0.7 else "LOW"
            print(f"\n{status} {file}:{info['line']}")
            print(f"   Confidence: {conf:.2f} ({conf_label})")

            if conf >= 0.9:
                print(f"   ✓ Fix is working! High confidence match.")
            elif conf >= 0.7:
                print(f"   ⚠ Partial match - may need improvement")
            else:
                print(f"   ✗ Low confidence - fix not working properly")
                all_found = False
        else:
            print(f"\n❌ {file} NOT FOUND")
            print(f"   Expected to find this file in results")
            all_found = False

    # Final verdict
    print("\n" + "=" * 80)
    if all_found:
        print("✅ SUCCESS: All expected files found with high confidence!")
        print("The scope-based .take detection is working correctly.")
    else:
        print("❌ FAILURE: Some expected files missing or low confidence")
        print("The fix may not be working as expected.")
    print("=" * 80)

    # Assert all expected files found
    assert all_found, "Some expected files missing or have low confidence"


if __name__ == "__main__":
    try:
        test_tombstone_search()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
