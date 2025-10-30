#!/usr/bin/env python3
"""
Debug the SQL parser to understand why it's not extracting WHERE conditions.
"""
import sys
import re
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.components.where_clause_matcher import WhereClauseParser

# The SQL query
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


def test_regex_extraction():
    """Test the regex pattern used by WhereClauseParser."""
    print("=" * 80)
    print("Testing WHERE clause extraction regex")
    print("=" * 80)

    # This is the regex from WhereClauseParser._parse_sql_regex_fallback
    pattern = r'WHERE\s+(.+?)(?:ORDER BY|LIMIT|OFFSET|GROUP BY|$)'

    print("\nRegex pattern:")
    print(f"  {pattern}")

    print("\nSearching in SQL query...")
    match = re.search(pattern, SQL_QUERY, re.IGNORECASE | re.DOTALL)

    if match:
        where_content = match.group(1).strip()
        print(f"\n✓ WHERE clause extracted ({len(where_content)} characters):")
        print("-" * 80)
        print(where_content)
        print("-" * 80)

        # Try to split by AND
        parts = re.split(r'\s+AND\s+', where_content, flags=re.IGNORECASE)
        print(f"\n✓ Split into {len(parts)} conditions by AND:")
        for i, part in enumerate(parts, 1):
            print(f"  {i}. {part.strip()}")

        return where_content
    else:
        print("\n❌ No WHERE clause found!")
        return None


def test_condition_parsing(where_clause):
    """Test parsing individual conditions."""
    if not where_clause:
        print("\n❌ No WHERE clause to parse")
        return

    print("\n" + "=" * 80)
    print("Testing condition parsing")
    print("=" * 80)

    parts = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)

    for i, part in enumerate(parts, 1):
        part = part.strip()
        print(f"\n📍 Condition {i}: {part[:60]}...")

        # Test IS NOT NULL pattern
        match = re.search(r'(\w+)\s+IS\s+NOT\s+NULL', part, re.IGNORECASE)
        if match:
            print(f"  ✓ IS NOT NULL: column = {match.group(1)}")
            continue

        # Test IS NULL pattern
        match = re.search(r'(\w+)\s+IS\s+NULL', part, re.IGNORECASE)
        if match:
            print(f"  ✓ IS NULL: column = {match.group(1)}")
            continue

        # Test binary operators
        match = re.search(r'(\w+)\s*(=|!=|<>|<=|>=|<|>)\s*(.+)', part)
        if match:
            print(f"  ✓ Binary: column = {match.group(1)}, op = {match.group(2)}, value = {match.group(3)}")
            continue

        print(f"  ❌ No pattern matched!")


def test_parser_method():
    """Test the actual WhereClauseParser.parse_sql method."""
    print("\n" + "=" * 80)
    print("Testing WhereClauseParser.parse_sql()")
    print("=" * 80)

    parser = WhereClauseParser()
    conditions = parser.parse_sql(SQL_QUERY)

    print(f"\n✓ Parser returned {len(conditions)} conditions:")
    if conditions:
        for i, cond in enumerate(conditions, 1):
            print(f"  {i}. {cond}")
    else:
        print("  (none)")


if __name__ == "__main__":
    print("\n🔍 SQL Parser Diagnostic\n")

    # Test each component
    where_clause = test_regex_extraction()
    test_condition_parsing(where_clause)
    test_parser_method()

    print("\n" + "=" * 80)
    print("✓ Diagnostic complete")
    print("=" * 80)
