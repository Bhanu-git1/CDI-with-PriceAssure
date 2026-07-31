import unittest
import json
from app.services.code_executor import CodeExecutor, SecurityError

class MockMySQLService:
    """Mock MySQLService for local sandbox testing."""
    def execute_sql(self, query):
        if "users" in query:
            return json.dumps({
                "totalSize": 1,
                "recordsReturned": 1,
                "records": [{"id": 1, "name": "John Doe", "status": "active"}]
            })
        return json.dumps({"totalSize": 0, "records": []})

    def describe_table(self, name):
        return f"Mock Table {name}"

class TestCodeExecutor(unittest.TestCase):
    def setUp(self):
        self.mock_db = MockMySQLService()
        self.executor = CodeExecutor(self.mock_db)

    def test_safe_execution(self):
        # A safe script querying users table
        safe_code = """
data = json.loads(db.execute_sql("SELECT name, status FROM users WHERE status = 'active'"))
records = data.get("records", [])
result = {
    "sql": "SELECT name, status FROM users WHERE status = 'active'",
    "records": records,
    "count": len(records)
}
"""
        exec_res = self.executor.execute(safe_code)
        self.assertIsNone(exec_res["error"])
        self.assertEqual(exec_res["result"]["count"], 1)
        self.assertEqual(exec_res["result"]["records"][0]["name"], "John Doe")

    def test_escaped_newlines_sanitization(self):
        escaped_code = 'sql_query = "SELECT * FROM users"\\ndata = json.loads(db.execute_sql(sql_query))\\nresult = {"sql": sql_query, "count": len(data.get("records", []))}'
        exec_res = self.executor.execute(escaped_code)
        self.assertIsNone(exec_res["error"])
        self.assertEqual(exec_res["result"]["count"], 1)

    def test_concatenated_statements_sanitization(self):
        concatenated_code = 'sql_query = "SELECT * FROM users" result = {"sql": sql_query, "count": len(json.loads(db.execute_sql(sql_query)).get("records", []))}'
        exec_res = self.executor.execute(concatenated_code)
        self.assertIsNone(exec_res["error"])
        self.assertEqual(exec_res["result"]["count"], 1)

    def test_whitelisted_imports_and_datetime(self):
        code_with_allowed_imports = """
import json
import datetime
from datetime import date
today = datetime.datetime.now().strftime('%Y-%m-%d')
result = {"today": today, "parsed": json.loads('{"ok": true}')}
"""
        exec_res = self.executor.execute(code_with_allowed_imports)
        self.assertIsNone(exec_res["error"])
        self.assertTrue(exec_res["result"]["parsed"]["ok"])

    def test_banned_import(self):
        code_with_import = """
import os
result = os.getcwd()
"""
        with self.assertRaises(SecurityError):
            self.executor.validate_code(code_with_import)

    def test_banned_from_import(self):
        code_with_from_import = """
from sys import argv
result = argv
"""
        with self.assertRaises(SecurityError):
            self.executor.validate_code(code_with_from_import)

    def test_banned_eval(self):
        code_with_eval = """
result = eval("1 + 1")
"""
        with self.assertRaises(SecurityError):
            self.executor.validate_code(code_with_eval)

    def test_banned_dunder(self):
        code_with_dunder = """
result = db.__class__.__subclasses__()
"""
        with self.assertRaises(SecurityError):
            self.executor.validate_code(code_with_dunder)

    def test_banned_dunder_attribute(self):
        code_with_private_attr = """
result = db._pool
"""
        with self.assertRaises(SecurityError):
            self.executor.validate_code(code_with_private_attr)

    def test_safe_math(self):
        code_with_math = """
result = math.sqrt(16) + math.pow(2, 3)
"""
        exec_res = self.executor.execute(code_with_math)
        self.assertIsNone(exec_res["error"])
        self.assertEqual(exec_res["result"], 12.0)

    def test_print_capture(self):
        code_with_print = """
print("Hello Sandbox")
print("Math: ", 10 + 5)
result = 100
"""
        exec_res = self.executor.execute(code_with_print)
        self.assertIsNone(exec_res["error"])
        self.assertEqual(exec_res["result"], 100)
        self.assertIn("Hello Sandbox", exec_res["logs"])
        self.assertIn("Math:  15", exec_res["logs"])

if __name__ == "__main__":
    unittest.main()
