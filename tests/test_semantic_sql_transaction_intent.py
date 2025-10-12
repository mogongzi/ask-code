from tools.semantic_sql_analyzer import SemanticSQLAnalyzer, QueryIntent


class TestTransactionControlIntent:
    def setup_method(self):
        self.analyzer = SemanticSQLAnalyzer()

    def test_begin_transaction_intent(self):
        for stmt in ["BEGIN", "BEGIN;", "START TRANSACTION", "START TRANSACTION;"]:
            analysis = self.analyzer.analyze(stmt)
            assert analysis.intent == QueryIntent.TRANSACTION_CONTROL, f"Expected TRANSACTION_CONTROL for: {stmt}"

    def test_commit_intent(self):
        for stmt in ["COMMIT", "COMMIT;"]:
            analysis = self.analyzer.analyze(stmt)
            assert analysis.intent == QueryIntent.TRANSACTION_CONTROL, f"Expected TRANSACTION_CONTROL for: {stmt}"

    def test_rollback_intent(self):
        for stmt in ["ROLLBACK", "ROLLBACK;"]:
            analysis = self.analyzer.analyze(stmt)
            assert analysis.intent == QueryIntent.TRANSACTION_CONTROL, f"Expected TRANSACTION_CONTROL for: {stmt}"

