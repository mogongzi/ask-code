#!/usr/bin/env python3
"""
Test script for transaction fingerprint search.
"""
from tools.transaction_analyzer import TransactionAnalyzer

# Your actual SQL log from production
SQL_LOG = """2025-08-19T08:21:23.381609Z     1791542 Query   BEGIN
2025-08-19T08:21:23.382333Z     1791542 Query   INSERT INTO `page_views` (`member_id`, `company_id`, `referer`, `action`, `controller`, `created_at`, `updated_at`, `owner_id`, `more_info`, `group_id`, `first_view`, `user_agent`, `key_type`, `key_id`) VALUES (19220828, 1720, 'https://workzone.one.int.sap/', 'show_as_tab', 'work_pages', '2025-08-19 08:21:23', '2025-08-19 08:21:23', 19220828, NULL, 851949, FALSE, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0', 'LayoutPage', 415024)
2025-08-19T08:21:23.384672Z     1791542 Query   SELECT 1 AS one FROM `audit_logs` WHERE `audit_logs`.`uuid` = x'6452594435704865365a616d4c473279654f456f4b41' LIMIT 1
2025-08-19T08:21:23.389976Z     1791542 Query   INSERT INTO `audit_logs` (`created_at`, `member_id`, `operation`, `table_name`, `table_id`, `column_name`, `old_value`, `new_value`, `company_id`, `is_deleted`, `group_id`, `uuid`) VALUES ('2025-08-19 08:21:23', 19220828, 'INSERT', 'page_views', 5070127592, NULL, NULL, NULL, 1720, FALSE, 851949, x'6452594435704865365a616d4c473279654f456f4b41')
2025-08-19T08:21:23.392217Z     1791542 Query   INSERT INTO member_actions_feed_items
  (created_at, audit_log_id,company_id,logged_in_member_id)
VALUES
  ((SELECT created_at
    FROM audit_logs
    WHERE id = 6908952432),
               6908952432,1720,19220828)
2025-08-19T08:21:23.395155Z     1791542 Query   INSERT INTO content_usage_feed_items
  (created_at, audit_log_id,company_id,table_name,table_id)
VALUES
  ((SELECT created_at
    FROM audit_logs
    WHERE id = 6908952432),
               6908952432,1720,'layout_pages',415024)
2025-08-19T08:21:23.397100Z     1791542 Query   SELECT `aggregated_content_views`.* FROM `aggregated_content_views` WHERE `aggregated_content_views`.`content_type` = 'LayoutPage' AND `aggregated_content_views`.`content_id` = 415024 AND `aggregated_content_views`.`last_n` = 3650 LIMIT 1
2025-08-19T08:21:23.414070Z     1791542 Query   COMMIT"""

def test_transaction_search():
    """Test transaction fingerprint matching."""
    print("=" * 80)
    print("Testing Transaction Fingerprint Search")
    print("=" * 80)

    # Initialize analyzer with your Rails project
    analyzer = TransactionAnalyzer(
        project_root="/Users/I503354/jam/local/ct",
        debug=True
    )

    print("\n📊 Analyzing transaction log...\n")

    # Execute the analysis
    result = analyzer.execute({
        "transaction_log": SQL_LOG,
        "find_source_code": True,
        "max_patterns": 5
    })

    # Print summary
    if result.get("transaction_summary"):
        print(result["transaction_summary"])

    print("\n" + "=" * 80)
    print("📋 Full Result Details")
    print("=" * 80)

    # Show source code findings in detail
    if result.get("source_code_findings"):
        print(f"\n✅ Found {len(result['source_code_findings'])} source code matches\n")

        for i, finding in enumerate(result["source_code_findings"], 1):
            print(f"\n🔍 Finding #{i}:")
            print(f"   Strategy: {finding.get('search_strategy', 'unknown')}")
            print(f"   Query: {finding.get('query', 'unknown')}")

            if finding.get('column_matches'):
                print(f"   Column Matches: {finding['column_matches']}")
                print(f"   Matched Columns: {', '.join(finding.get('matched_columns', []))}")

            if finding.get('search_results', {}).get('matches'):
                for match in finding['search_results']['matches'][:3]:
                    print(f"\n   📍 Location: {match.get('file', 'unknown')}:{match.get('line', '?')}")
                    print(f"   Confidence: {match.get('confidence', 'unknown')}")
                    if match.get('why'):
                        print(f"   Why: {', '.join(match['why'][:3])}")
    else:
        print("\n❌ No source code findings")

    print("\n" + "=" * 80)

    # Expected result check
    print("\n🎯 Expected Result: lib/page_view_helper.rb:4")
    print("   (The transaction block wrapping the page_view INSERT)")

    return result

if __name__ == "__main__":
    test_transaction_search()