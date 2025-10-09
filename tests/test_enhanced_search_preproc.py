from tools.enhanced_sql_rails_search import EnhancedSQLRailsSearch


MULTI_QUERY_LOG = """
2025-10-07T07:00:00.500000Z        1791542 Query START TRANSACTION
2025-10-07T07:00:00.750000Z        1791542 Query
SELECT 1;
2025-10-07T07:03:45.999999Z        1791542 Query COMMIT
"""


def test_enhanced_search_redirects_transaction_logs():
    tool = EnhancedSQLRailsSearch(project_root="/tmp/does-not-matter", debug=False)
    res = tool.execute({"sql": MULTI_QUERY_LOG, "include_usage_sites": False})
    assert res.get("error"), "Should return a transaction log error"
    assert "transaction_analyzer" in (res.get("suggestion") or "")
