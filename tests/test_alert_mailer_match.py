#!/usr/bin/env python3
"""
Test: Alert Mailer SQL Match

Tests the exact scenario from the user's query:
SQL: SELECT ... FROM members WHERE company_id = 32546 AND login_handle IS NOT NULL
     AND owner_id IS NULL AND disabler_id IS NULL AND first_login_at IS NOT NULL
     ORDER BY id ASC LIMIT 500 OFFSET 1000

Code: company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)

This should now get a high confidence match (close to 100%).
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.components.where_clause_matcher import WhereClauseParser, WhereClauseMatcher
from tools.components.unified_confidence_scorer import UnifiedConfidenceScorer, ClausePresence

def test_alert_mailer_sql_match():
    """Test the exact SQL and code from alert_mailer.rb"""

    rails_root = "/Users/I503354/jam/local/ct"
    parser = WhereClauseParser(project_root=rails_root)
    matcher = WhereClauseMatcher(project_root=rails_root)
    scorer = UnifiedConfidenceScorer()

    # The actual SQL from the user's query
    sql = """
    SELECT `members`.`id`, `members`.`email` FROM `members`
    WHERE `members`.`company_id` = 32546
      AND `members`.`login_handle` IS NOT NULL
      AND `members`.`owner_id` IS NULL
      AND `members`.`disabler_id` IS NULL
      AND `members`.`first_login_at` IS NOT NULL
    ORDER BY `members`.`id` ASC
    LIMIT 500 OFFSET 1000
    """

    # The actual code from app/mailers/alert_mailer.rb:180
    code = "company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"

    print("=" * 80)
    print("TEST: Alert Mailer SQL-to-Code Match")
    print("=" * 80)
    print("\nSQL Query:")
    print("  " + " ".join(sql.split()))
    print("\nRails Code:")
    print(f"  {code}")
    print("\n" + "-" * 80)

    # Parse SQL and code
    sql_conditions = parser.parse_sql(sql)
    code_conditions = parser.parse_ruby_code(code)

    print(f"\nSQL WHERE conditions ({len(sql_conditions)}):")
    for i, cond in enumerate(sql_conditions, 1):
        print(f"  {i}. {cond}")

    print(f"\nCode WHERE conditions ({len(code_conditions)}):")
    for i, cond in enumerate(code_conditions, 1):
        print(f"  {i}. {cond}")

    # Match conditions
    match_result = matcher.match(sql_conditions, code_conditions)

    print(f"\n{'=' * 80}")
    print("MATCH RESULT")
    print("=" * 80)
    print(f"Match percentage: {match_result.match_percentage:.1%}")
    print(f"Matched:  {len(match_result.matched)}/{len(sql_conditions)}")
    print(f"Missing:  {len(match_result.missing)}")
    print(f"Extra:    {len(match_result.extra)}")

    if match_result.missing:
        print("\nMissing conditions:")
        for cond in match_result.missing:
            print(f"  ✗ {cond}")

    # Check clause presence
    clause_presence = ClausePresence(
        sql_has_where=True,
        sql_has_order=True,
        sql_has_limit=True,
        sql_has_offset=True,
        code_has_where=True,
        code_has_order=".order(" in code.lower(),
        code_has_limit=".limit(" in code.lower(),
        code_has_offset=".offset(" in code.lower()
    )

    # Calculate confidence score
    score_result = scorer.score_match(
        where_match_result=match_result,
        clause_presence=clause_presence,
        pattern_distinctiveness=0.7,  # High distinctiveness (OFFSET is rare)
        sql=sql,
        code=code
    )

    print("\n" + "=" * 80)
    print("CONFIDENCE SCORE")
    print("=" * 80)
    print(f"Overall confidence: {score_result['confidence']:.1%}")
    print("\nExplanation:")
    for reason in score_result['why']:
        print(f"  {reason}")

    print("\nScore breakdown:")
    for component, value in score_result['details'].items():
        if component != 'pagination_compatibility' and value is not None:
            print(f"  {component}: {value:.2f}")

    # Verdict
    print("\n" + "=" * 80)
    if match_result.is_complete_match and score_result['confidence'] >= 0.90:
        print("✓ PERFECT MATCH! This is the exact source code for the SQL query.")
        print("✓ All WHERE conditions matched")
        print("✓ ORDER BY, LIMIT, OFFSET all present")
        print(f"✓ High confidence: {score_result['confidence']:.1%}")
        return True
    elif match_result.is_complete_match:
        print("✓ COMPLETE MATCH: All WHERE conditions present")
        print(f"  Confidence: {score_result['confidence']:.1%}")
        return True
    else:
        print("✗ INCOMPLETE MATCH")
        print(f"  Missing {len(match_result.missing)} conditions")
        print(f"  Confidence: {score_result['confidence']:.1%}")
        return False

if __name__ == "__main__":
    success = test_alert_mailer_sql_match()
    sys.exit(0 if success else 1)
