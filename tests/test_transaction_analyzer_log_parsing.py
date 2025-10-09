from tools.transaction_analyzer import TransactionAnalyzer


SAMPLE_LOG = """
2025-10-07T07:00:00.000000Z        1791542 Connect reports_service@10.0.0.8 on main_reporting_db
2025-10-07T07:00:00.500000Z        1791542 Query START TRANSACTION
2025-10-07T07:00:00.750000Z        1791542 Query
SELECT
    /*application:RailsApp, controller:ReportsController, action:show, db_host:prod-db-01*/
    `customers`.`id` AS customer_id,
    `customers`.`email`,
    COUNT(DISTINCT `support_tickets`.`id`) AS total_tickets
FROM
    `customers`
LEFT OUTER JOIN
    `support_tickets` ON `support_tickets`.`customer_id` = `customers`.`id`
WHERE
    `customers`.`is_premium` = TRUE
GROUP BY
    `customers`.`id`
HAVING
    total_tickets < 10
ORDER BY
    total_tickets DESC
LIMIT 10 OFFSET 0
;
2025-10-07T07:03:45.999999Z        1791542 Query COMMIT
2025-10-07T07:03:46.100000Z        1791542 Quit
"""


def test_transaction_analyzer_parses_select_and_begin_commit():
    analyzer = TransactionAnalyzer(project_root=None, debug=False)
    result = analyzer.execute({"transaction_log": SAMPLE_LOG, "find_source_code": False})

    assert result.get("query_count", 0) >= 2
    ops = set(result.get("operation_types") or [])
    # Expect SELECT and COMMIT; BEGIN may be recognized as BEGIN
    assert "SELECT" in ops
    assert "COMMIT" in ops
    # Validate table detection includes customers
    tables = set(result.get("tables_affected") or [])
    assert "customers" in tables
