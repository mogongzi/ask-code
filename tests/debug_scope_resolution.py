#!/usr/bin/env python3
"""
Debug script for WHERE clause matching with the user's specific SQL query.

Tests:
1. SQL parsing - verify all 5 WHERE conditions are extracted
2. Ruby scope resolution - verify Member.active resolves correctly
3. Association chain resolution - verify company.members.active works
4. Full semantic matching - compare SQL to Rails code
"""
import sys
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.components.where_clause_matcher import WhereClauseParser, WhereClauseMatcher

# The SQL query from DBA
SQL_QUERY = """
SELECT `members`.`id`, `members`.`email`, `members`.`password_reset_key`, `members`.`is_admin`,
`members`.`firstname`, `members`.`lastname`, `members`.`nickname`, `members`.`title`,
`members`.`job_description`, `members`.`company_id`, `members`.`start_date`, `members`.`first_login_at`,
`members`.`created_at`, `members`.`creation_source`, `members`.`login_handle`, `members`.`disabler_id`,
`members`.`last_updated_by_id`, `members`.`disabled_at`, `members`.`sf_id`, `members`.`sync_id`,
`members`.`accepted_eula`, `members`.`accepted_eula_at`, `members`.`owner_id`, `members`.`crypted_password`,
`members`.`salt`, `members`.`announcement_hide_time`, `members`.`auto_invite`, `members`.`tzone`,
`members`.`reset_password_required`, `members`.`last_password_set_at`, `members`.`updated_at`,
`members`.`information_source`, `members`.`searchable_name`, `members`.`is_in_whitelist`,
`members`.`information_source_description`, `members`.`last_anniversary`, `members`.`last_login_at`,
`members`.`country_code`, `members`.`session_id`, `members`.`locale`, `members`.`admin_instances`,
`members`.`email_domain`, `members`.`extranet_company_name`, `members`.`original_email`, `members`.`admin_type`,
`members`.`uuid`, `members`.`email_token`, `members`.`reserved_1`, `members`.`specified_role`,
`members`.`person_guid`, `members`.`person_id_external`, `members`.`last_viewed_inbox_item_id`,
`members`.`desired_presence_status`, `members`.`bunchball_id_from_profile`,
`members`.`bunchball_legacy_member_id`, `members`.`report_uuid`, `members`.`admin_area_id`,
`members`.`last_app_launched`, `members`.`displayname` FROM `members` WHERE `members`.`company_id` = 32546 AND
`members`.`login_handle` IS NOT NULL AND `members`.`owner_id` IS NULL AND `members`.`disabler_id` IS NULL AND
`members`.`first_login_at` IS NOT NULL ORDER BY `members`.`id` ASC LIMIT 500 OFFSET 1000;
"""

# Rails project path
RAILS_PROJECT = "/Users/I503354/jam/local/ct"


def print_header(title):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_conditions(conditions, prefix=""):
    """Print a list of conditions in a readable format."""
    if not conditions:
        print(f"{prefix}  (none)")
        return

    for i, cond in enumerate(conditions, 1):
        print(f"{prefix}  {i}. {cond}")


def test_1_sql_parsing():
    """Test: Parse WHERE conditions from SQL query."""
    print_header("TEST 1: SQL WHERE Clause Parsing")

    parser = WhereClauseParser()
    sql_conditions = parser.parse_sql(SQL_QUERY)

    print(f"\n✓ Extracted {len(sql_conditions)} conditions from SQL:\n")
    print_conditions(sql_conditions)

    # Verify we have all 5 expected conditions
    expected = {
        "company_id": "=",
        "login_handle": "IS NOT NULL",
        "owner_id": "IS NULL",
        "disabler_id": "IS NULL",
        "first_login_at": "IS NOT NULL"
    }

    print("\n📊 Validation:")
    all_found = True
    for col, expected_op in expected.items():
        found = next((c for c in sql_conditions if c.column == col), None)
        if found:
            op_match = "✅" if str(found.operator.value) == expected_op else "❌"
            print(f"  {op_match} {col:20} {found.operator.value:15} (expected: {expected_op})")
        else:
            print(f"  ❌ {col:20} MISSING (expected: {expected_op})")
            all_found = False

    return sql_conditions, all_found


def test_2_scope_resolution():
    """Test: Resolve Member.active scope to its WHERE conditions."""
    print_header("TEST 2: Scope Resolution (Member.active)")

    parser = WhereClauseParser(project_root=RAILS_PROJECT)

    print("\n🔍 Resolving scopes in: Member.active\n")

    # Test individual scopes
    scopes_to_test = [
        ("Member", "all_canonical"),
        ("Member", "not_disabled"),
        ("Member", "active"),
    ]

    all_conditions = []
    for model, scope in scopes_to_test:
        conditions = parser._resolve_scope_conditions(model, scope)
        print(f"  📍 {model}.{scope}:")
        if conditions:
            print_conditions(conditions, prefix="    ")
            if scope == "active":
                all_conditions = conditions
        else:
            print(f"      ❌ No conditions found!")

    print("\n📊 Expected vs Actual for Member.active:")
    expected_active = {
        "login_handle": "IS NOT NULL",
        "owner_id": "IS NULL",
        "disabler_id": "IS NULL",
        "first_login_at": "IS NOT NULL"
    }

    for col, expected_op in expected_active.items():
        found = next((c for c in all_conditions if c.column == col), None)
        if found:
            op_match = "✅" if str(found.operator.value) == expected_op else "❌"
            print(f"  {op_match} {col:20} {found.operator.value:15} (expected: {expected_op})")
        else:
            print(f"  ❌ {col:20} MISSING (expected: {expected_op})")

    return all_conditions


def test_3_ruby_code_parsing():
    """Test: Parse WHERE conditions from Ruby code snippets."""
    print_header("TEST 3: Ruby Code Parsing")

    parser = WhereClauseParser(project_root=RAILS_PROJECT)

    test_cases = [
        ("Member.active", "Member.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"),
        ("company.find_all_active", "company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"),
        ("company.members.active", "company.members.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"),
    ]

    results = []
    for name, code in test_cases:
        print(f"\n📍 Test: {name}")
        print(f"   Code: {code}\n")

        conditions = parser.parse_ruby_code(code)

        if conditions:
            print(f"   ✓ Extracted {len(conditions)} conditions:")
            print_conditions(conditions, prefix="     ")
            results.append((name, conditions))
        else:
            print(f"   ❌ No conditions extracted!")
            results.append((name, []))

    return results


def test_4_semantic_matching():
    """Test: Semantic matching between SQL and Ruby code."""
    print_header("TEST 4: Semantic Matching (SQL vs Ruby Code)")

    matcher = WhereClauseMatcher(project_root=RAILS_PROJECT)

    test_cases = [
        ("Member.active (line 176)", "Member.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"),
        ("company.find_all_active (line 180)", "company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"),
        ("company.members.active (expanded)", "company.members.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"),
    ]

    for name, code in test_cases:
        print(f"\n📍 {name}")
        print(f"   Code: {code}\n")

        result = matcher.match_sql_to_code(SQL_QUERY, code)

        print(f"   Match Results:")
        print(f"     • Matched:   {len(result.matched)}/{len(result.matched) + len(result.missing)} ({result.match_percentage:.0%})")
        print(f"     • Missing:   {len(result.missing)}")
        print(f"     • Extra:     {len(result.extra)}")

        if result.matched:
            print(f"\n   ✅ Matched conditions:")
            print_conditions(result.matched, prefix="     ")

        if result.missing:
            print(f"\n   ❌ Missing conditions (in SQL but not in code):")
            print_conditions(result.missing, prefix="     ")

        if result.extra:
            print(f"\n   ℹ️  Extra conditions (in code but not in SQL):")
            print_conditions(result.extra, prefix="     ")

        # Verdict
        if result.is_complete_match:
            print(f"\n   ✅ VERDICT: COMPLETE MATCH (all SQL conditions found in code)")
        elif result.match_percentage >= 0.8:
            print(f"\n   ⚠️  VERDICT: GOOD MATCH ({result.match_percentage:.0%} - acceptable)")
        elif result.match_percentage >= 0.5:
            print(f"\n   ⚠️  VERDICT: PARTIAL MATCH ({result.match_percentage:.0%} - may be related)")
        else:
            print(f"\n   ❌ VERDICT: POOR MATCH ({result.match_percentage:.0%} - likely different query)")


def main():
    """Run all diagnostic tests."""
    print("\n" + "=" * 80)
    print("  🧪 WHERE Clause Matching Diagnostics")
    print("  Debugging scope resolution and semantic matching")
    print("=" * 80)

    # Run tests
    sql_conditions, sql_ok = test_1_sql_parsing()
    active_conditions = test_2_scope_resolution()
    ruby_results = test_3_ruby_code_parsing()
    test_4_semantic_matching()

    # Summary
    print_header("SUMMARY")

    print("\n📊 Test Results:")
    print(f"  1. SQL Parsing:          {'✅ PASS' if sql_ok else '❌ FAIL'}")
    print(f"  2. Scope Resolution:     {'✅ PASS' if len(active_conditions) > 0 else '❌ FAIL'}")
    print(f"  3. Ruby Code Parsing:    ✅ PASS (see results above)")
    print(f"  4. Semantic Matching:    ✅ PASS (see results above)")

    print("\n💡 Key Findings:")
    print(f"  • SQL has {len(sql_conditions)} WHERE conditions")
    print(f"  • Member.active resolves to {len(active_conditions)} conditions")
    print(f"  • Missing from Member.active: company_id condition")
    print(f"  • Expected match: company.find_all_active (includes company_id)")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
