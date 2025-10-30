"""
Test script to verify that scope-based queries with .take are correctly matched.

Tests the fix for:
- .take/.first/.last detection as LIMIT equivalents
- Heuristic scope matching (for_custom_domain → custom_domain = ?)
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.sql_rails_search import SQLRailsSearch

def test_custom_domain_tombstone_query():
    """
    Test the query that was failing before the fix:
    SELECT * FROM custom_domain_tombstones WHERE custom_domain = ? LIMIT ?

    Should find:
    1. lib/multi_domain.rb:43 - CustomDomainTombstone.for_custom_domain(request_host).take
    2. app/models/company.rb:2987 - CustomDomainTombstone.for_custom_domain(domain).take&.company
    """
    print("=" * 80)
    print("Testing: SELECT * FROM custom_domain_tombstones WHERE custom_domain = ? LIMIT ?")
    print("=" * 80)

    sql = "SELECT * FROM custom_domain_tombstones WHERE custom_domain = ? LIMIT ?"
    project_root = "/Users/I503354/jam/local/ct"

    tool = SQLRailsSearch(project_root=project_root, debug=False)
    result = tool.execute({"sql": sql, "max_results": 100})

    print("\n🔍 Search Results:")
    print(f"Total matches: {result.get('match_count', 0)}")
    print(f"Search type: {result.get('search_type', 'unknown')}")

    matches = result.get('matches', [])

    if not matches:
        print("\n❌ No matches found!")
        return False

    print(f"\n✅ Found {len(matches)} matches:\n")

    expected_files = {
        'lib/multi_domain.rb': False,
        'app/models/company.rb': False
    }

    for i, match in enumerate(matches[:10], 1):  # Show top 10 matches
        file_path = match.get('file', '')
        line = match.get('line', '')
        snippet = match.get('snippet', '').strip()
        confidence = match.get('confidence', '0.0')

        print(f"{i}. File: {file_path}:{line}")
        print(f"   Confidence: {confidence}")
        print(f"   Snippet: {snippet[:100]}...")

        # Check if this is one of the expected matches
        for expected_file in expected_files:
            if expected_file in file_path:
                expected_files[expected_file] = True

        # Show why explanation
        why = match.get('why', [])
        if why:
            print(f"   Why:")
            for reason in why[:3]:  # Show first 3 reasons
                print(f"     - {reason}")
        print()

    print("\n📊 Expected matches found:")
    for file, found in expected_files.items():
        status = "✅" if found else "❌"
        print(f"{status} {file}")

    all_found = all(expected_files.values())

    if all_found:
        print("\n✅ SUCCESS: All expected matches found!")

        # Check confidence scores
        print("\n🎯 Confidence Analysis:")
        for match in matches[:5]:
            file_path = match.get('file', '')
            confidence = float(match.get('confidence', '0.0'))

            if any(exp in file_path for exp in expected_files.keys()):
                if confidence >= 0.7:
                    print(f"  ✅ {file_path}: {confidence:.2f} (HIGH)")
                elif confidence >= 0.5:
                    print(f"  ⚠️  {file_path}: {confidence:.2f} (MEDIUM)")
                else:
                    print(f"  ❌ {file_path}: {confidence:.2f} (LOW)")
    else:
        print("\n❌ FAILURE: Some expected matches not found!")
        return False

    return all_found


if __name__ == "__main__":
    print("\n🧪 Running scope + .take matching test...\n")
    success = test_custom_domain_tombstone_query()

    if success:
        print("\n" + "=" * 80)
        print("✅ All tests passed!")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print("❌ Tests failed!")
        print("=" * 80)
        sys.exit(1)
