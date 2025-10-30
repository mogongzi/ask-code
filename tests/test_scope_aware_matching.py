"""
Test suite for scope-aware WHERE clause matching.

Tests the integration of ModelScopeAnalyzer with WhereClauseParser to ensure
Rails scopes are correctly resolved to their WHERE conditions.
"""
import pytest
from pathlib import Path
import tempfile
import os

from tools.components.where_clause_matcher import (
    WhereClauseParser,
    WhereClauseMatcher,
    NormalizedCondition,
    Operator
)


@pytest.fixture
def temp_rails_project():
    """Create a temporary Rails project structure with a Member model."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create Rails directory structure
        models_dir = Path(tmpdir) / "app" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create Member model with scopes
        member_model = models_dir / "member.rb"
        member_model.write_text("""
class Member < ApplicationRecord
  # Scope definitions that match the SQL from the bug report
  scope :all_canonical, -> { where.not(login_handle: nil).where(owner_id: nil) }
  scope :not_disabled, -> { all_canonical.where(disabler_id: nil) }
  scope :active, -> { not_disabled.where.not(first_login_at: nil) }

  # Additional test scopes
  scope :enabled, -> { where(status: 'enabled') }
  scope :visible, -> { where(hidden: false) }
end
""")

        yield tmpdir


def test_detect_scope_chains():
    """Test that scope chains are correctly detected in Ruby code."""
    parser = WhereClauseParser()

    # Test basic scope chain
    code = "Member.active.offset(100).limit(50)"
    scopes = parser._detect_scope_chains(code)
    assert scopes == [("Member", "active")]

    # Test multiple scopes
    code = "User.enabled.visible.limit(10)"
    scopes = parser._detect_scope_chains(code)
    assert ("User", "enabled") in scopes
    assert ("User", "visible") in scopes

    # Test should not detect ActiveRecord methods
    code = "Member.where(id: 1).first"
    scopes = parser._detect_scope_chains(code)
    assert scopes == []


def test_resolve_scope_without_project_root():
    """Test that scope resolution returns empty list when no project_root is provided."""
    parser = WhereClauseParser(project_root=None)
    conditions = parser._resolve_scope_conditions("Member", "active")
    assert conditions == []


def test_resolve_scope_with_project_root(temp_rails_project):
    """Test that scopes are correctly resolved to WHERE conditions."""
    parser = WhereClauseParser(project_root=temp_rails_project)

    # Resolve the 'active' scope which chains through not_disabled and all_canonical
    conditions = parser._resolve_scope_conditions("Member", "active")

    # The 'active' scope should resolve to all WHERE conditions from the chain:
    # - login_handle IS NOT NULL (from all_canonical)
    # - owner_id IS NULL (from all_canonical)
    # - disabler_id IS NULL (from not_disabled)
    # - first_login_at IS NOT NULL (from active)

    assert len(conditions) == 4

    # Check that all expected conditions are present
    condition_strs = [f"{c.column} {c.operator.value}" for c in conditions]
    assert "login_handle IS NOT NULL" in condition_strs
    assert "owner_id IS NULL" in condition_strs
    assert "disabler_id IS NULL" in condition_strs
    assert "first_login_at IS NOT NULL" in condition_strs


def test_parse_ruby_code_with_scope(temp_rails_project):
    """Test that parse_ruby_code correctly extracts conditions from scopes."""
    parser = WhereClauseParser(project_root=temp_rails_project)

    # The exact code from the bug report
    code = "Member.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"

    conditions = parser.parse_ruby_code(code)

    # Should find 4 WHERE conditions from the 'active' scope
    assert len(conditions) >= 4

    # Verify the conditions match what the SQL expects
    columns = {c.column for c in conditions}
    assert "login_handle" in columns
    assert "owner_id" in columns
    assert "disabler_id" in columns
    assert "first_login_at" in columns


def test_parse_ruby_code_scope_plus_where(temp_rails_project):
    """Test that scopes and explicit .where() calls are both extracted."""
    parser = WhereClauseParser(project_root=temp_rails_project)

    # Scope + explicit where
    code = "Member.active.where(company_id: 32546).limit(100)"

    conditions = parser.parse_ruby_code(code)

    # Should find 4 conditions from scope + 1 from where()
    assert len(conditions) >= 5

    columns = {c.column for c in conditions}
    assert "company_id" in columns
    assert "login_handle" in columns
    assert "disabler_id" in columns


def test_where_clause_matcher_with_scopes(temp_rails_project):
    """Test the full matching workflow with scope resolution."""
    matcher = WhereClauseMatcher(project_root=temp_rails_project)

    # SQL from the bug report
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

    # Rails code from the bug report (with company_id in the scope chain)
    code = "Member.active.where(company_id: 32546).offset((page-1)*page_size).limit(page_size).order(id: :asc)"

    result = matcher.match_sql_to_code(sql, code)

    # Should be a complete match (all SQL conditions found in code)
    assert result.is_complete_match, f"Missing conditions: {result.missing}"
    assert len(result.missing) == 0, f"Missing: {[str(c) for c in result.missing]}"

    # All 5 WHERE conditions should match
    assert len(result.matched) == 5


def test_scope_caching(temp_rails_project):
    """Test that resolved scopes are cached for performance."""
    parser = WhereClauseParser(project_root=temp_rails_project)

    # First resolution
    conditions1 = parser._resolve_scope_conditions("Member", "active")

    # Cache should have the entry
    assert "Member.active" in parser._scope_cache

    # Second resolution (should use cache)
    conditions2 = parser._resolve_scope_conditions("Member", "active")

    # Should return same results
    assert len(conditions1) == len(conditions2)
    assert parser._scope_cache["Member.active"] == conditions2


def test_nonexistent_scope(temp_rails_project):
    """Test that nonexistent scopes return empty list."""
    parser = WhereClauseParser(project_root=temp_rails_project)

    conditions = parser._resolve_scope_conditions("Member", "nonexistent")
    assert conditions == []

    # Should be cached as empty
    assert parser._scope_cache["Member.nonexistent"] == []


def test_nonexistent_model(temp_rails_project):
    """Test that nonexistent models return empty list."""
    parser = WhereClauseParser(project_root=temp_rails_project)

    conditions = parser._resolve_scope_conditions("FakeModel", "active")
    assert conditions == []


def test_bug_report_exact_match(temp_rails_project):
    """
    Test the exact scenario from the bug report.

    This is the critical test that validates the fix.
    """
    matcher = WhereClauseMatcher(project_root=temp_rails_project)

    # Exact SQL from bug report
    sql = """
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
    `members`.`last_app_launched`, `members`.`displayname`
    FROM `members`
    WHERE `members`.`company_id` = 32546
      AND `members`.`login_handle` IS NOT NULL
      AND `members`.`owner_id` IS NULL
      AND `members`.`disabler_id` IS NULL
      AND `members`.`first_login_at` IS NOT NULL
    ORDER BY `members`.`id` ASC
    LIMIT 500 OFFSET 1000
    """

    # Exact code from bug report (simplified - company_id comes from somewhere)
    # In reality, Member.active needs to include company_id or it's passed via .where()
    # Let's assume it's: Member.where(company_id: 32546).active...
    code = "Member.where(company_id: 32546).active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"

    result = matcher.match_sql_to_code(sql, code)

    # BEFORE FIX: This would show 0 matched, 5 missing (25% confidence)
    # AFTER FIX: This should show 5 matched, 0 missing (100% confidence)

    print(f"\nMatch result:")
    print(f"  Matched: {len(result.matched)}")
    print(f"  Missing: {len(result.missing)}")
    print(f"  Match percentage: {result.match_percentage * 100:.0f}%")

    if result.missing:
        print(f"  Missing conditions:")
        for cond in result.missing:
            print(f"    - {cond}")

    assert result.is_complete_match, (
        f"Expected complete match but found {len(result.missing)} missing conditions: "
        f"{[str(c) for c in result.missing]}"
    )
    assert result.match_percentage == 1.0, f"Expected 100% match, got {result.match_percentage * 100:.0f}%"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
