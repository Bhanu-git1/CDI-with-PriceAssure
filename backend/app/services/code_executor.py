import ast
import collections
import datetime
import json
import logging
import math
import re
import sys
import time
from typing import Dict, Any, Tuple

logger = logging.getLogger("code-executor")

WHITELISTED_MODULES = {
    "json", "datetime", "time", "math", "re", "collections",
    "typing", "functools", "itertools", "string", "random", "enum"
}

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    module_base = name.split('.')[0]
    if module_base not in WHITELISTED_MODULES:
        raise SecurityError(f"Importing module '{name}' is forbidden in the sandbox.")
    return __import__(name, globals, locals, fromlist, level)

class SecurityError(Exception):
    """Raised when generated code violates sandbox constraints."""
    pass

class CodeSandboxValidator(ast.NodeVisitor):
    """
    AST Visitor that checks for forbidden operations in Python code.
    Ensures safe dynamic execution.
    """
    def __init__(self):
        # Banned builtin names
        self.banned_names = {
            "eval", "exec", "open", "compile", "globals", "locals",
            "__import__", "getattr", "setattr", "delattr", "hasattr",
            "breakpoint", "input"
        }
        
    def visit_Import(self, node):
        for alias in node.names:
            module_base = alias.name.split('.')[0]
            if module_base not in WHITELISTED_MODULES:
                raise SecurityError(f"Importing module '{alias.name}' is forbidden in the sandbox.")

    def visit_ImportFrom(self, node):
        if node.module:
            module_base = node.module.split('.')[0]
            if module_base not in WHITELISTED_MODULES:
                raise SecurityError(f"Importing from module '{node.module}' is forbidden in the sandbox.")

    def visit_Name(self, node):
        if node.id in self.banned_names:
            raise SecurityError(f"Use of banned function/name '{node.id}' is forbidden.")
        if (node.id.startswith("_") and len(node.id) > 1) or node.id.endswith("__"):
            raise SecurityError("Access to private/dunder names is forbidden.")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr.startswith("_") or node.attr.endswith("__"):
            raise SecurityError("Access to private/dunder attributes is forbidden.")
        self.generic_visit(node)

    def visit_Call(self, node):
        # Prevent calling getattr/setattr dynamically via names
        if isinstance(node.func, ast.Name) and node.func.id in self.banned_names:
            raise SecurityError(f"Call to forbidden function '{node.func.id}' is blocked.")
        self.generic_visit(node)


class CodeExecutor:
    """
    Executes LLM-generated Python code in a safe, restricted namespace.
    """
    def __init__(self, db_service, global_name: str = "db"):
        self.db = db_service
        self.global_name = global_name

    def sanitize_code(self, code: str) -> str:
        """Cleans LLM output, strips markdown fences, fixes escaped newlines and concatenated statements."""
        if not code:
            return ""
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        # Handle escaped \n strings from JSON LLM responses
        if "\\n" in code:
            try:
                ast.parse(code)
            except SyntaxError:
                cleaned = code.replace("\\n", "\n").replace("\\t", "\t")
                try:
                    ast.parse(cleaned)
                    code = cleaned
                except SyntaxError:
                    code = code.replace("\\n", "\n")

        # Auto-repair statements concatenated without newline or semicolon (e.g., 'sql_query = "..." result = ...')
        try:
            ast.parse(code)
        except SyntaxError:
            pattern = r'(["\'\]\)\}0-9a-zA-Z_])\s+(result\s*=|data\s*=|records\s*=|sql_query\s*=|df\s*=)'
            rebuilt_code = re.sub(pattern, r'\1\n\2', code)
            try:
                ast.parse(rebuilt_code)
                code = rebuilt_code
            except SyntaxError:
                pass

        return code

    def validate_code(self, code: str) -> str:
        """Parses the code, runs AST safety checks, and returns sanitized code."""
        code = self.sanitize_code(code)
        try:
            tree = ast.parse(code)
            validator = CodeSandboxValidator()
            validator.visit(tree)
            return code
        except SecurityError as se:
            logger.warning(f"Security validation failed: {se}")
            raise se
        except SyntaxError as sy:
            logger.warning(f"Syntax error in generated code: {sy}")
            raise sy
        except Exception as e:
            logger.warning(f"Failed to validate code: {e}")
            raise SecurityError(f"Validation error: {str(e)}")

    def execute(self, code: str) -> Dict[str, Any]:
        """
        Executes Python code in a restricted namespace.
        The code is expected to store its final result in the `result` variable.
        """
        # Validate safety & sanitize code first
        try:
            code = self.validate_code(code)
        except (SecurityError, SyntaxError) as e:
            return {
                "result": None,
                "logs": "",
                "error": f"Validation error: {str(e)}"
            }

        # Capturing stdout for print calls in the code
        class StringIO:
            def __init__(self):
                self.buf = []
            def write(self, s):
                self.buf.append(s)
            def flush(self):
                pass
            def getvalue(self):
                return "".join(self.buf)

        stdout_capture = StringIO()
        
        # Build restricted globals
        allowed_globals = {
            "__builtins__": {
                "abs": abs,
                "all": all,
                "any": any,
                "bool": bool,
                "dict": dict,
                "enumerate": enumerate,
                "filter": filter,
                "float": float,
                "int": int,
                "len": len,
                "list": list,
                "map": map,
                "max": max,
                "min": min,
                "print": lambda *args, **kwargs: stdout_capture.write(" ".join(map(str, args)) + "\n"),
                "range": range,
                "round": round,
                "set": set,
                "sorted": sorted,
                "str": str,
                "sum": sum,
                "zip": zip,
                "isinstance": isinstance,
                "issubclass": issubclass,
                "type": type,
                "__import__": safe_import,
                "Exception": Exception,
                "ValueError": ValueError,
                "TypeError": TypeError,
                "KeyError": KeyError,
                "IndexError": IndexError,
            },
            self.global_name: self.db,
            "json": json,
            "math": math,
            "datetime": datetime,
            "date": datetime.date,
            "timedelta": datetime.timedelta,
            "time": time,
            "re": re,
            "collections": collections,
        }

        local_vars = {"result": None}

        try:
            logger.info("Executing generated code inside sandbox...")
            exec(code, allowed_globals, local_vars)
            
            result = local_vars.get("result")
            printed_logs = stdout_capture.getvalue()
            
            return {
                "result": result,
                "logs": printed_logs,
                "error": None
            }
        except Exception as e:
            logger.exception("Runtime error inside code execution sandbox")
            return {
                "result": None,
                "logs": stdout_capture.getvalue(),
                "error": f"Runtime error: {str(e)}"
            }
