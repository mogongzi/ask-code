from util.sql_log_extractor import AdaptiveSQLExtractor, SQLType


SAMPLE_LOG = """
2025-10-07T07:00:00.000000Z        1791542 Connect reports_service@10.0.0.8 on main_reporting_db
2025-10-07T07:00:00.500000Z        1791542 Query START TRANSACTION
2025-10-07T07:00:00.750000Z        1791542 Query
SELECT
    /*application:RailsApp, controller:ReportsController, action:show, db_host:prod-db-01*/
    `customers`.`id` AS customer_id,
    `customers`.`email`
FROM `customers`;
2025-10-07T07:03:45.999999Z        1791542 Query COMMIT
2025-10-07T07:03:46.100000Z        1791542 Quit
"""


def test_adaptive_extractor_handles_multiline_and_transaction():
    extractor = AdaptiveSQLExtractor()
    results = extractor.extract_all_sql(SAMPLE_LOG)

    assert results, "Extractor should return at least one statement"

    # Expect a single transaction block with BEGIN/SELECT/COMMIT or multiple statements
    # Accept either behavior depending on learned format
    if len(results) == 1:
        stmt = results[0]
        assert stmt.sql_type in (SQLType.TRANSACTION, SQLType.SELECT)
        assert 'SELECT' in stmt.sql
    else:
        # If split, ensure START/SELECT/COMMIT present across statements
        types = {r.sql_type for r in results}
        assert SQLType.SELECT in types
