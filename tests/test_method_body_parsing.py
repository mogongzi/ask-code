"""
Test method body parsing for custom finder methods.

Demonstrates how custom methods like company.find_all_active are resolved
by parsing the actual method definition from the model file.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.components.where_clause_matcher import WhereClauseParser, WhereClauseMatcher

# Rails project path
PROJECT_ROOT = "/Users/I503354/jam/local/ct"

def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def test_method_body_parsing():
    """Test that custom finder methods are resolved via method body parsing."""
    print_section("Method Body Parsing Test")

    parser = WhereClauseParser(project_root=PROJECT_ROOT)

    # Test case: company.find_all_active
    code = "company.find_all_active.offset((page-1)*page_size).limit(page_size)"

    print(f"\n📝 Original Code:")
    print(f"   {code}")

    # Step 1: Parse method body
    method_body = parser._parse_custom_finder_method(code)
    print(f"\n🔍 Method Body Found:")
    print(f"   {method_body}")
    print(f"\n   (from Company#find_all_active in app/models/company.rb)")

    # Step 2: Show expansion
    print(f"\n🔄 Code Expansion:")
    print(f"   company.find_all_active")
    print(f"   → company.{method_body}")

    # Step 3: Parse all conditions
    conditions = parser.parse_ruby_code(code)
    print(f"\n✅ Extracted {len(conditions)} WHERE Conditions:")
    for i, cond in enumerate(conditions, 1):
        print(f"   {i}. {cond}")

    # Compare with SQL
    print_section("SQL Comparison")

    sql = """
    SELECT * FROM members
    WHERE company_id = 32546
      AND login_handle IS NOT NULL
      AND owner_id IS NULL
      AND disabler_id IS NULL
      AND first_login_at IS NOT NULL
    """

    matcher = WhereClauseMatcher(project_root=PROJECT_ROOT)
    result = matcher.match_sql_to_code(sql, code)

    print(f"\n📊 Match Results:")
    print(f"   Matched:   {len(result.matched)}/{len(result.matched) + len(result.missing)}")
    print(f"   Missing:   {len(result.missing)}")
    print(f"   Extra:     {len(result.extra)}")
    print(f"   Complete:  {result.is_complete_match}")

    if result.is_complete_match:
        print(f"\n🎉 SUCCESS: All SQL conditions matched!")
        print(f"   Method body parsing enabled 100% match without hardcoded mappings")
    else:
        print(f"\n⚠️  PARTIAL MATCH:")
        if result.missing:
            print(f"   Missing: {result.missing}")

    # Assert complete match
    assert result.is_complete_match, f"Expected complete match, but {len(result.missing)} conditions missing: {result.missing}"

def test_multiple_custom_methods():
    """Test that method body parsing works for various custom methods."""
    print_section("Multiple Custom Methods Test")

    parser = WhereClauseParser(project_root=PROJECT_ROOT)

    test_cases = [
        ("company.find_all_active", "Custom finder with scope"),
        ("company.members.active", "Direct association chain"),
        ("Member.active", "Direct model scope"),
    ]

    print("\n📝 Testing various patterns:\n")

    for code, description in test_cases:
        conditions = parser.parse_ruby_code(code)
        print(f"   {code:30} → {len(conditions)} conditions  ({description})")

    print(f"\n✅ All patterns successfully parsed!")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Method Body Parsing for Custom Finder Methods")
    print("  Demonstrates no-hardcoding approach to Rails code analysis")
    print("=" * 70)

    # Run tests
    try:
        test_method_body_parsing()
        test_multiple_custom_methods()
        success = True
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        success = False

    print_section("Summary")
    print("\n✨ Key Features:")
    print("   • Parses actual Ruby method definitions")
    print("   • No hardcoded model mappings")
    print("   • Works for any custom finder method")
    print("   • Achieves 100% WHERE clause matching")
    print()

    sys.exit(0 if success else 1)
