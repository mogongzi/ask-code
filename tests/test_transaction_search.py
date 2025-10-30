#!/usr/bin/env python3
"""
Simple test for transaction log search.
Tests the transaction analyzer with page_views + audit_logs transaction.

Usage:
    source .venv/bin/activate
    python tests/test_transaction_search.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.sql_rails_search import SQLRailsSearch

# Your Rails project path
PROJECT_ROOT = "/Users/I503354/jam/local/ct"

# Transaction log from your execution
TRANSACTION_LOG = """2025-08-19T08:21:23.381609Z     1791542 Query   BEGIN
2025-08-19T08:21:23.382333Z     1791542 Query   INSERT INTO `page_views` (`member_id`, `company_id`, `referer`, `action`, `controller`, `created_at`, `updated_at`, `owner_id`, `more_info`, `group_id`, `first_view`, `user_agent`, `key_type`, `key_id`) VALUES (19220828, 1720, 'https://workzone.one.int.sap/', 'show_as_tab', 'work_pages', '2025-08-19 08:21:23', '2025-08-19 08:21:23', 19220828, NULL, 851949, FALSE, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0', 'LayoutPage', 415024)
2025-08-19T08:21:23.384672Z     1791542 Query   SELECT 1 AS one FROM `audit_logs` WHERE `audit_logs`.`uuid` = x'6452594435704865365a616d4c473279654f456f4b41' LIMIT 1
2025-08-19T08:21:23.389976Z     1791542 Query   INSERT INTO `audit_logs` (`created_at`, `member_id`, `operation`, `table_name`, `table_id`, `column_name`, `old_value`, `new_value`, `company_id`, `is_deleted`, `group_id`, `uuid`) VALUES ('2025-08-19 08:21:23', 19220828, 'INSERT', 'page_views', 5070127592, NULL, NULL, NULL, 1720, FALSE, 851949, x'6452594435704865365a616d4c473279654f456f4b41')
2025-08-19T08:21:23.392217Z     1791542 Query   INSERT INTO member_actions_feed_items (created_at, audit_log_id,company_id,logged_in_member_id) VALUES ((SELECT created_at FROM audit_logs WHERE id = 6908952432), 6908952432,1720,19220828)
2025-08-19T08:21:23.395155Z     1791542 Query   INSERT INTO content_usage_feed_items (created_at, audit_log_id,company_id,table_name,table_id) VALUES ((SELECT created_at FROM audit_logs WHERE id = 6908952432), 6908952432,1720,'layout_pages',415024)
2025-08-19T08:21:23.397100Z     1791542 Query   SELECT `aggregated_content_views`.* FROM `aggregated_content_views` WHERE `aggregated_content_views`.`content_type` = 'LayoutPage' AND `aggregated_content_views`.`content_id` = 415024 AND `aggregated_content_views`.`last_n` = 3650 LIMIT 1
2025-08-19T08:21:23.414070Z     1791542 Query   COMMIT"""


def test_transaction_search():
    """Test sql_rails_search with transaction log."""

    print("=" * 80)
    print("TRANSACTION LOG SEARCH TEST")
    print("=" * 80)
    print(f"\nProject root: {PROJECT_ROOT}")
    print(f"\nTransaction summary:")
    print("  - INSERT INTO page_views")
    print("  - SELECT FROM audit_logs (uuid check)")
    print("  - INSERT INTO audit_logs")
    print("  - INSERT INTO member_actions_feed_items")
    print("  - INSERT INTO content_usage_feed_items")
    print("  - SELECT FROM aggregated_content_views")
    print("\n" + "-" * 80)

    # Initialize tool (debug=True to see what's happening)
    tool = SQLRailsSearch(project_root=PROJECT_ROOT, debug=True)

    # Execute search
    result = tool.execute({
        "sql": TRANSACTION_LOG,
        "max_results": 10,
        "include_explanation": True
    })

    # Print results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    # Check for errors
    if "error" in result:
        print(f"\n❌ ERROR: {result['error']}")
        assert False, f"Tool returned error: {result['error']}"

    # Print summary
    search_type = result.get('search_type', 'unknown')
    match_count = result.get('match_count', 0)

    print(f"\nSearch type: {search_type}")
    print(f"Match count: {match_count}")

    if search_type == 'transaction_log':
        print("✓ Transaction log correctly identified")
    else:
        print(f"⚠ Expected 'transaction_log' but got '{search_type}'")

    # Print top matches
    matches = result.get('matches', [])
    if not matches:
        print("\n⚠️ No matches found!")
        print("This suggests the transaction analyzer may not be finding the code.")
        assert False, "No matches found"

    print(f"\nTop {min(10, len(matches))} matches:")

    for i, match in enumerate(matches[:10], 1):
        file_path = match.get('file', 'N/A')
        line = match.get('line', 'N/A')
        confidence = match.get('confidence', 'N/A')
        snippet = match.get('snippet', 'N/A')[:100]

        print(f"\n{i}. {file_path}:{line}")
        print(f"   Confidence: {confidence}")
        print(f"   Snippet: {snippet}...")

        # Show why for high-confidence matches
        if float(confidence) >= 0.7:
            why = match.get('why', [])
            if why:
                print(f"   Why:")
                for reason in why[:3]:  # Show first 3 reasons
                    print(f"     - {reason}")

    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Look for key patterns in the transaction
    patterns_found = {
        'page_views': False,
        'audit_logs': False,
        'feed_items': False,
        'callbacks': False
    }

    high_confidence_count = 0

    for match in matches:
        file_path = match.get('file', '').lower()
        snippet = match.get('snippet', '').lower()
        confidence = float(match.get('confidence', 0))

        if confidence >= 0.7:
            high_confidence_count += 1

        # Check for page_views related code
        if 'page_view' in file_path or 'page_view' in snippet:
            patterns_found['page_views'] = True

        # Check for audit_logs related code
        if 'audit' in file_path or 'audit' in snippet:
            patterns_found['audit_logs'] = True

        # Check for feed items
        if 'feed' in file_path or 'feed' in snippet:
            patterns_found['feed_items'] = True

        # Check for callbacks (after_create, after_save, etc.)
        if 'after_create' in snippet or 'after_save' in snippet or 'callback' in snippet:
            patterns_found['callbacks'] = True

    print(f"\nHigh confidence matches (≥0.7): {high_confidence_count}/{len(matches)}")
    print("\nPattern detection:")

    for pattern, found in patterns_found.items():
        status = "✓" if found else "✗"
        print(f"  {status} {pattern.replace('_', ' ').title()}")

    # Expected behavior for this transaction
    print("\n" + "=" * 80)
    print("EXPECTED BEHAVIOR")
    print("=" * 80)
    print("\nThis transaction should trigger:")
    print("  1. PageView model - after_create callback")
    print("  2. Creates audit_log entry (uuid check + insert)")
    print("  3. Creates member_actions_feed_item")
    print("  4. Creates content_usage_feed_item")
    print("  5. Queries/updates aggregated_content_views")

    print("\nLikely locations to find this code:")
    print("  - app/models/page_view.rb (after_create callback)")
    print("  - app/models/audit_log.rb (model definition)")
    print("  - lib/ (audit logging helpers)")
    print("  - app/models/concerns/ (audit logging concern)")

    # Final verdict
    print("\n" + "=" * 80)
    if high_confidence_count >= 3 and patterns_found['page_views']:
        print("✅ SUCCESS: Transaction analyzer found relevant code")
        print("Multiple high-confidence matches with page_view patterns detected.")
    elif high_confidence_count >= 1:
        print("⚠️ PARTIAL SUCCESS: Found some matches")
        print("Transaction analyzer is working but may need tuning.")
    else:
        print("❌ FAILURE: No high-confidence matches found")
        print("Transaction analyzer may not be working correctly.")
    print("=" * 80)

    # Assert we found at least one high-confidence match
    assert high_confidence_count >= 1, f"Expected at least 1 high-confidence match, found {high_confidence_count}"


if __name__ == "__main__":
    try:
        test_transaction_search()
        print("\n✓ Test passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
