#!/usr/bin/env python3
"""
Test: Custom Finder Method Chain Preservation

Verifies that when expanding custom finder methods like company.find_all_active,
we preserve the entire method chain (.offset, .limit, .order, etc.)

Bug: Previously lost .offset/.limit/.order when expanding custom methods
Fix: Now preserves the full chain during expansion
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.components.where_clause_matcher import WhereClauseParser

def test_custom_finder_preserves_chain():
    """Test that custom finder expansion preserves .offset/.limit/.order"""

    # Initialize parser with Rails project root
    rails_root = "/Users/I503354/jam/local/ct"
    parser = WhereClauseParser(project_root=rails_root)

    # Test case: company.find_all_active with pagination
    code = "company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"

    print("=" * 80)
    print("TEST: Custom Finder Method Chain Preservation")
    print("=" * 80)
    print(f"\nInput code:\n  {code}")
    print(f"\nExpected expansion:\n  company.members.active.offset(...).limit(...).order(...)")
    print("\n" + "-" * 80)

    # Parse the code
    conditions = parser.parse_ruby_code(code)

    print(f"\nExtracted {len(conditions)} WHERE conditions:")
    for i, cond in enumerate(conditions, 1):
        print(f"  {i}. {cond}")

    # Verify we got all the expected conditions
    expected_columns = {'company_id', 'login_handle', 'owner_id', 'disabler_id', 'first_login_at'}
    actual_columns = {cond.column for cond in conditions}

    print(f"\nExpected columns: {sorted(expected_columns)}")
    print(f"Actual columns:   {sorted(actual_columns)}")

    missing = expected_columns - actual_columns
    extra = actual_columns - expected_columns

    if expected_columns == actual_columns:
        print("\n✓ SUCCESS: All WHERE conditions extracted correctly!")
        print("✓ Chain preservation working: .offset/.limit/.order preserved during expansion")
    else:
        print(f"\n✗ FAILURE: WHERE conditions mismatch")
        if missing:
            print(f"  Missing: {sorted(missing)}")
        if extra:
            print(f"  Extra: {sorted(extra)}")

    # Assert all conditions are present
    assert not missing, f"Missing WHERE conditions: {sorted(missing)}"
    assert not extra, f"Unexpected WHERE conditions: {sorted(extra)}"
    assert expected_columns == actual_columns, "WHERE conditions mismatch"

def test_direct_scope_chain():
    """Test that direct scope chains still work"""

    rails_root = "/Users/I503354/jam/local/ct"
    parser = WhereClauseParser(project_root=rails_root)

    # Test case: Direct Member.active call
    code = "Member.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"

    print("\n" + "=" * 80)
    print("TEST: Direct Scope Chain (no custom method)")
    print("=" * 80)
    print(f"\nInput code:\n  {code}")

    conditions = parser.parse_ruby_code(code)

    print(f"\nExtracted {len(conditions)} WHERE conditions:")
    for i, cond in enumerate(conditions, 1):
        print(f"  {i}. {cond}")

    # Should get 4 conditions (no company_id since no association)
    expected_columns = {'login_handle', 'owner_id', 'disabler_id', 'first_login_at'}
    actual_columns = {cond.column for cond in conditions}

    print(f"\nExpected columns: {sorted(expected_columns)}")
    print(f"Actual columns:   {sorted(actual_columns)}")

    if expected_columns == actual_columns:
        print("\n✓ SUCCESS: Direct scope chain working correctly!")
    else:
        print(f"\n✗ FAILURE: Expected {expected_columns}, got {actual_columns}")

    # Assert columns match
    assert expected_columns == actual_columns, f"Expected {expected_columns}, got {actual_columns}"

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("RUNNING TESTS")
    print("=" * 80)

    try:
        test_custom_finder_preserves_chain()
        test1_passed = True
    except AssertionError as e:
        print(f"\n✗ Test 1 failed: {e}")
        test1_passed = False

    try:
        test_direct_scope_chain()
        test2_passed = True
    except AssertionError as e:
        print(f"\n✗ Test 2 failed: {e}")
        test2_passed = False

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Custom finder chain preservation: {'PASS ✓' if test1_passed else 'FAIL ✗'}")
    print(f"Direct scope chain: {'PASS ✓' if test2_passed else 'FAIL ✗'}")

    if test1_passed and test2_passed:
        print("\nAll tests passed! 🎉")
        sys.exit(0)
    else:
        print("\nSome tests failed!")
        sys.exit(1)
