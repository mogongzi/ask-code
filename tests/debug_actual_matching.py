#!/usr/bin/env python3
"""
Debug the actual WHERE clause matching in the progressive search flow.
"""
import sys
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.components.where_clause_matcher import WhereClauseParser, WhereClauseMatcher

# Rails project path
RAILS_PROJECT = "/Users/I503354/jam/local/ct"

# The SQL query
SQL_QUERY = """
SELECT * FROM `members`
WHERE `members`.`company_id` = 32546 AND
      `members`.`login_handle` IS NOT NULL AND
      `members`.`owner_id` IS NULL AND
      `members`.`disabler_id` IS NULL AND
      `members`.`first_login_at` IS NOT NULL
ORDER BY `members`.`id` ASC
LIMIT 500 OFFSET 1000;
"""

# The code snippet from alert_mailer.rb:176
CODE_SNIPPET = "Member.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"


def main():
    print("=" * 80)
    print("  🔍 Debug Actual WHERE Clause Matching")
    print("=" * 80)

    # Initialize parser and matcher with Rails project context
    parser = WhereClauseParser(project_root=RAILS_PROJECT)
    matcher = WhereClauseMatcher(project_root=RAILS_PROJECT)

    # Step 1: Parse SQL conditions
    print("\n📊 Step 1: Parse SQL WHERE conditions")
    print("-" * 80)
    sql_conditions = parser.parse_sql(SQL_QUERY)
    print(f"\nExtracted {len(sql_conditions)} conditions from SQL:")
    for i, cond in enumerate(sql_conditions, 1):
        print(f"  {i}. {cond}")

    # Step 2: Parse Ruby code conditions
    print("\n📊 Step 2: Parse Ruby code WHERE conditions")
    print("-" * 80)
    print(f"Code: {CODE_SNIPPET}\n")
    code_conditions = parser.parse_ruby_code(CODE_SNIPPET)
    print(f"Extracted {len(code_conditions)} conditions from code:")
    for i, cond in enumerate(code_conditions, 1):
        print(f"  {i}. {cond}")

    # Step 3: Perform semantic matching
    print("\n📊 Step 3: Semantic Matching")
    print("-" * 80)
    match_result = matcher.match(sql_conditions, code_conditions)

    print(f"\nMatch Results:")
    print(f"  • Match Percentage: {match_result.match_percentage:.0%}")
    print(f"  • Matched: {len(match_result.matched)}")
    print(f"  • Missing: {len(match_result.missing)}")
    print(f"  • Extra: {len(match_result.extra)}")

    if match_result.matched:
        print(f"\n✅ Matched Conditions ({len(match_result.matched)}):")
        for i, cond in enumerate(match_result.matched, 1):
            print(f"    {i}. {cond}")

    if match_result.missing:
        print(f"\n❌ Missing Conditions ({len(match_result.missing)}):")
        print(f"   (These are in SQL but NOT found in code)")
        for i, cond in enumerate(match_result.missing, 1):
            print(f"    {i}. {cond}")

    if match_result.extra:
        print(f"\nℹ️  Extra Conditions ({len(match_result.extra)}):")
        print(f"   (These are in code but NOT in SQL)")
        for i, cond in enumerate(match_result.extra, 1):
            print(f"    {i}. {cond}")

    # Step 4: Detailed condition comparison
    print("\n📊 Step 4: Detailed Condition-by-Condition Comparison")
    print("-" * 80)

    for i, sql_cond in enumerate(sql_conditions, 1):
        print(f"\n  SQL Condition {i}: {sql_cond}")

        # Check if this condition matches any code condition
        matched = False
        for j, code_cond in enumerate(code_conditions, 1):
            if sql_cond.matches(code_cond):
                print(f"    ✅ MATCHES Code Condition {j}: {code_cond}")
                matched = True
                break

        if not matched:
            print(f"    ❌ NO MATCH in code")
            # Show why it doesn't match
            for j, code_cond in enumerate(code_conditions, 1):
                if sql_cond.column == code_cond.column:
                    if sql_cond.operator != code_cond.operator:
                        print(f"       → Code has {code_cond.column} with different operator: {code_cond.operator.value}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
