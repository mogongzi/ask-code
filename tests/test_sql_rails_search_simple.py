#!/usr/bin/env python3
"""
Simple test for sql_rails_search tool.
Tests with the exact SQL query from the agent execution.

Usage:
    source .venv/bin/activate
    python tests/test_sql_rails_search_simple.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sql_rails_search import SQLRailsSearch

# Your Rails project path
PROJECT_ROOT = "/Users/I503354/jam/local/ct"

# Your exact SQL from the agent execution
SQL_QUERY = """SELECT `members`.`id`, `members`.`email`, `members`.`password_reset_key`, `members`.`is_admin`,
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
`members`.`first_login_at` IS NOT NULL ORDER BY `members`.`id` ASC LIMIT 500 OFFSET 1000;"""


def test_sql_rails_search():
    """Test sql_rails_search tool with exact agent input."""

    print("=" * 80)
    print("SQL RAILS SEARCH TEST")
    print("=" * 80)
    print(f"\nProject root: {PROJECT_ROOT}")
    print(f"\nSQL query:")
    print("  " + " ".join(SQL_QUERY.split()))
    print("\n" + "-" * 80)

    # Initialize tool (debug=True to see execution details)
    tool = SQLRailsSearch(project_root=PROJECT_ROOT, debug=True)

    # Execute with exact same input as the agent
    result = tool.execute({
        "sql": SQL_QUERY,
        "include_explanation": True
    })

    # Print results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    # Check for errors
    if "error" in result:
        print(f"\n❌ ERROR: {result['error']}")
        return result

    # Print summary
    print(f"\nSearch type: {result.get('search_type', 'unknown')}")
    print(f"Match count: {result.get('match_count', 0)}")

    # Print each match
    matches = result.get('matches', [])
    for i, match in enumerate(matches, 1):
        print(f"\n{i}. {match.get('file', 'N/A')}:{match.get('line', 'N/A')}")
        print(f"   Snippet: {match.get('snippet', 'N/A')}")
        print(f"   Confidence: {match.get('confidence', 'N/A')}")
        print(f"   Why:")
        for reason in match.get('why', []):
            print(f"     {reason}")

    # Print search strategy if included
    if 'search_strategy' in result:
        print("\n" + "=" * 80)
        print("SEARCH STRATEGY")
        print("=" * 80)
        strategy = result['search_strategy']
        if isinstance(strategy, dict):
            for key, value in strategy.items():
                print(f"\n{key}:")
                if isinstance(value, list):
                    for item in value:
                        print(f"  - {item}")
                elif isinstance(value, dict):
                    for k, v in value.items():
                        print(f"  {k}: {v}")
                else:
                    print(f"  {value}")
        else:
            print(f"\n{strategy}")

    # Highlight the expected match
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)

    alert_mailer_found = False
    alert_mailer_confidence = None

    for match in matches:
        if 'alert_mailer.rb' in match.get('file', '') and match.get('line') in [176, 180]:
            alert_mailer_found = True
            alert_mailer_confidence = float(match.get('confidence', 0))
            print(f"\n✓ Found alert_mailer.rb at line {match.get('line')}")
            print(f"  Confidence: {match.get('confidence')}")

            if alert_mailer_confidence >= 0.90:
                print(f"  ✓ HIGH CONFIDENCE (>= 90%) - Fix is working!")
            elif alert_mailer_confidence >= 0.70:
                print(f"  ⚠ MEDIUM CONFIDENCE (70-90%) - Partial match")
            else:
                print(f"  ✗ LOW CONFIDENCE (< 70%) - Fix not working")
            break

    if not alert_mailer_found:
        print("\n✗ alert_mailer.rb NOT found in top matches")
        print("  Expected: app/mailers/alert_mailer.rb:180")
        print("  This suggests the search is not finding the correct code")

    return result


if __name__ == "__main__":
    try:
        result = test_sql_rails_search()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
