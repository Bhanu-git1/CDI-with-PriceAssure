import os
import re
import sys
import logging
from typing import List, Dict, Any
from fastmcp import FastMCP
import mysql.connector
from mysql.connector import Error

# Configure logging to write to stderr so we don't corrupt the stdio stream
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("mcp-mysql-server")

# Initialize FastMCP Server
mcp = FastMCP("mysql-server")

# Retrieve Database connection details from environment variables
def get_db_config() -> Dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "mcp_readonly"),
        "password": os.getenv("DB_PASSWORD", "mcp_secure_pass123"),
        "database": os.getenv("DB_NAME", "mcp_poc_db")
    }

def get_db_connection():
    config = get_db_config()
    try:
        return mysql.connector.connect(**config)
    except Error as e:
        logger.error(f"Failed to connect to MySQL database: {e}")
        raise e

# Helper to validate that a query is strictly read-only
def is_query_safe(query: str) -> bool:
    cleaned = query.strip().upper()
    # Reject queries with destructive statements
    destructive_keywords = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", 
        "REPLACE", "CREATE", "GRANT", "REVOKE", "RENAME"
    ]
    for keyword in destructive_keywords:
        # Use regex to check for word boundaries, e.g. "DROP TABLE" vs "DROP" in names
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, cleaned):
            return False
    return True

# --- MCP Tools ---

@mcp.tool()
def list_tables() -> str:
    """
    List all tables available in the current database schema.
    Returns:
        A list of table names.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return f"Tables in database: {', '.join(tables)}"
    except Error as e:
        return f"Error listing tables: {str(e)}"

@mcp.tool()
def describe_table(table_name: str) -> str:
    """
    Get the columns, types, and schema of a specific table.
    Args:
        table_name: The name of the table to inspect.
    """
    # Sanitize input to prevent SQL injection in table name
    if not re.match(r"^[a-zA-Z0-9_]+$", table_name):
        return "Error: Invalid table name format."

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"DESCRIBE {table_name}")
        columns = cursor.fetchall()
        cursor.close()
        conn.close()
        
        output = [f"Columns in '{table_name}':"]
        for col in columns:
            output.append(f"  - {col['Field']} ({col['Type']}) | Null: {col['Null']} | Key: {col['Key']}")
        return "\n".join(output)
    except Error as e:
        return f"Error describing table '{table_name}': {str(e)}"

@mcp.tool()
def execute_query(sql_query: str) -> str:
    """
    Execute a read-only SQL query against the MySQL database.
    Only SELECT statements are allowed.
    Args:
        sql_query: The SQL query statement to run.
    """
    # 1. Enforce safety checks
    if not is_query_safe(sql_query):
        return "Error: Forbidden query. Only read-only operations (SELECT, etc.) are allowed."

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Limit rows to avoid overloading memory and context window
        # Check if the query already has a LIMIT clause; if not, we can safely append one
        limit_match = re.search(r"\bLIMIT\b\s+\d+", sql_query, re.IGNORECASE)
        executed_query = sql_query
        if not limit_match:
            # Strip trailing semicolon if present
            executed_query = executed_query.strip().rstrip(";")
            executed_query += " LIMIT 100;"
            
        logger.info(f"Executing query: {executed_query}")
        cursor.execute(executed_query)
        results = cursor.fetchall()
        
        # Retrieve column names
        row_count = len(results)
        cursor.close()
        conn.close()
        
        if row_count == 0:
            return "Query executed successfully. 0 rows returned."
            
        # Format the output as a simple visual text table
        import json
        return json.dumps(results, indent=2, default=str)
        
    except Error as e:
        return f"Database error while executing query: {str(e)}"

# --- MCP Resources ---

@mcp.resource("schema://overview")
def get_schema_overview() -> str:
    """Get a summary of the entire database schema structure."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        
        # Filter schema to include only target business tables for LLM optimization
        allowed_tables = {t.lower() for t in [
            "Reverse_Claims", "leakage_history", "Leakage_Activity", "leakage_rules",
            "Compliance_Table", "hcp_engagement_logs", "fatigue_score",
            "hcp_master", "Zip_Geography_Master", "copay_Claims_Transactions",
            "alerts", "Product_Master", "Reject_Code_Master", "tablet_master", 
            "territory_master", "sales_reps"
        ]}
        
        tables = [row[0] for row in cursor.fetchall() if row[0].lower() in allowed_tables]
        
        overview = ["Database Schema Overview:"]
        for table in tables:
            cursor.execute(f"DESCRIBE {table}")
            cols = cursor.fetchall()
            col_summary = ", ".join([f"{col[0]} ({col[1]})" for col in cols])
            overview.append(f"Table '{table}': [{col_summary}]")
            
        cursor.close()
        conn.close()
        return "\n".join(overview)
    except Error as e:
        return f"Error retrieving schema: {str(e)}"

if __name__ == "__main__":
    # Start FastMCP server in Stdio mode
    mcp.run()
