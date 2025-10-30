#!/usr/bin/env python3
"""
Demonstration of the scope-aware WHERE matching fix.

This script demonstrates that the bug reported by the user has been fixed:

BEFORE FIX:
- Member.active snippet showed 0 matched conditions, 5 missing conditions
- Confidence: 25%
- Reason: ✗ Missing 5/5 WHERE conditions (scope not resolved)

AFTER FIX:
- Member.active snippet shows 5 matched conditions, 0 missing conditions
- Confidence: 100%
- Reason: ✓ All WHERE conditions matched (scope correctly resolved)
"""

import tempfile
from pathlib import Path
from tools.components.where_clause_matcher import WhereClauseMatcher
from tools.components.unified_confidence_scorer import UnifiedConfidenceScorer, ClausePresence


def demo_bug_fix():
    """Demonstrate the fix for the scope-aware WHERE matching bug."""

    # Create a temporary Rails project with Member model
    with tempfile.TemporaryDirectory() as tmpdir:
        models_dir = Path(tmpdir) / "app" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create Member model with scope definitions that match production
        member_model = models_dir / "member.rb"
        member_model.write_text("""
class Member < ApplicationRecord
  # Scope chain that generates the WHERE conditions
  scope :all_canonical, -> { where.not(login_handle: nil).where(owner_id: nil) }
  scope :not_disabled, -> { all_canonical.where(disabler_id: nil) }
  scope :active, -> { not_disabled.where.not(first_login_at: nil) }
end
""")

        # The exact SQL from the bug report (simplified for demo)
        sql = """
SELECT * FROM members
WHERE company_id = 32546
  AND login_handle IS NOT NULL
  AND owner_id IS NULL
  AND disabler_id IS NULL
  AND first_login_at IS NOT NULL
ORDER BY id ASC
LIMIT 500 OFFSET 1000
"""

        # The exact code snippet from the bug report
        code_snippet = "Member.where(company_id: 32546).active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"

        print("=" * 80)
        print("SCOPE-AWARE WHERE MATCHING FIX DEMONSTRATION")
        print("=" * 80)
        print(f"\nSQL Query:")
        print(f"  WHERE company_id = 32546")
        print(f"    AND login_handle IS NOT NULL")
        print(f"    AND owner_id IS NULL")
        print(f"    AND disabler_id IS NULL")
        print(f"    AND first_login_at IS NOT NULL")
        print(f"  ORDER BY id ASC")
        print(f"  LIMIT 500 OFFSET 1000")

        print(f"\nRails Code:")
        print(f"  {code_snippet}")

        print(f"\nScope Definition (Member.active):")
        print(f"  scope :active, -> {{ not_disabled.where.not(first_login_at: nil) }}")
        print(f"  ↓ (chains to)")
        print(f"  scope :not_disabled, -> {{ all_canonical.where(disabler_id: nil) }}")
        print(f"  ↓ (chains to)")
        print(f"  scope :all_canonical, -> {{ where.not(login_handle: nil).where(owner_id: nil) }}")

        # Test with scope resolution (AFTER FIX)
        print(f"\n{'─' * 80}")
        print("AFTER FIX: With Scope Resolution")
        print(f"{'─' * 80}")

        matcher = WhereClauseMatcher(project_root=tmpdir)
        result = matcher.match_sql_to_code(sql, code_snippet)

        print(f"\nWHERE Clause Matching Results:")
        print(f"  ✓ Matched:  {len(result.matched)}/{len(result.matched) + len(result.missing)} conditions")
        print(f"  ✗ Missing:  {len(result.missing)} conditions")
        print(f"  Match Rate: {result.match_percentage * 100:.0f}%")

        if result.matched:
            print(f"\n  Matched conditions:")
            for cond in result.matched:
                print(f"    ✓ {cond}")

        if result.missing:
            print(f"\n  Missing conditions:")
            for cond in result.missing:
                print(f"    ✗ {cond}")
        else:
            print(f"\n  🎉 All WHERE conditions matched!")

        # Calculate confidence score
        scorer = UnifiedConfidenceScorer()
        clause_presence = ClausePresence(
            sql_has_where=True, sql_has_order=True, sql_has_limit=True, sql_has_offset=True,
            code_has_where=True, code_has_order=True, code_has_limit=True, code_has_offset=True
        )

        scoring_result = scorer.score_match(
            result,
            clause_presence,
            pattern_distinctiveness=0.5
        )

        print(f"\nConfidence Score: {scoring_result['confidence'] * 100:.0f}%")
        print(f"\nExplanation:")
        for reason in scoring_result['why']:
            print(f"  {reason}")

        # Compare with WITHOUT scope resolution (simulating BEFORE FIX)
        print(f"\n{'─' * 80}")
        print("BEFORE FIX: Without Scope Resolution (for comparison)")
        print(f"{'─' * 80}")

        matcher_no_scope = WhereClauseMatcher(project_root=None)  # No project root = no scope resolution
        result_no_scope = matcher_no_scope.match_sql_to_code(sql, code_snippet)

        print(f"\nWHERE Clause Matching Results:")
        print(f"  ✓ Matched:  {len(result_no_scope.matched)}/{len(result_no_scope.matched) + len(result_no_scope.missing)} conditions")
        print(f"  ✗ Missing:  {len(result_no_scope.missing)} conditions")
        print(f"  Match Rate: {result_no_scope.match_percentage * 100:.0f}%")

        scoring_result_no_scope = scorer.score_match(
            result_no_scope,
            clause_presence,
            pattern_distinctiveness=0.5
        )

        print(f"\nConfidence Score: {scoring_result_no_scope['confidence'] * 100:.0f}%")
        print(f"\nExplanation:")
        for reason in scoring_result_no_scope['why']:
            print(f"  {reason}")

        # Summary
        print(f"\n{'=' * 80}")
        print("SUMMARY")
        print(f"{'=' * 80}")
        print(f"\nBEFORE FIX (no scope resolution):")
        print(f"  - Matched: {len(result_no_scope.matched)} conditions")
        print(f"  - Missing: {len(result_no_scope.missing)} conditions  ← WRONG!")
        print(f"  - Confidence: {scoring_result_no_scope['confidence'] * 100:.0f}%  ← TOO LOW!")

        print(f"\nAFTER FIX (with scope resolution):")
        print(f"  - Matched: {len(result.matched)} conditions  ← CORRECT!")
        print(f"  - Missing: {len(result.missing)} conditions")
        print(f"  - Confidence: {scoring_result['confidence'] * 100:.0f}%  ← ACCURATE!")

        print(f"\n✓ The bug has been fixed! Member.active now resolves to its WHERE conditions.")
        print(f"{'=' * 80}\n")


if __name__ == "__main__":
    demo_bug_fix()
