import re
import json
import logging
from typing import List, Dict, Any
import mysql.connector
from mysql.connector import pooling, Error as MySQLError

logger = logging.getLogger("mysql-service")


class MySQLService:
    """
    Direct MySQL operations service.
    Replaces SalesforceService with equivalent methods for MySQL database access.
    """

    def __init__(self, host: str = "localhost", port: int = 3306, user: str = "",
                 password: str = "", database: str = "", pool_size: int = 5):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self._pool = None

    def get_connection(self):
        """Establish or return a connection from the pool."""
        if self._pool is None:
            if not self.user or not self.database:
                raise ValueError(
                    "MySQL credentials not configured. Please supply user and database name."
                )

            logger.info(f"Creating MySQL connection pool for '{self.database}' at {self.host}:{self.port}...")
            try:
                self._pool = pooling.MySQLConnectionPool(
                    pool_name="dce_pool",
                    pool_size=self.pool_size,
                    pool_reset_session=True,
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    autocommit=True
                )
                logger.info(f"Successfully created MySQL connection pool for database '{self.database}'.")
            except MySQLError as e:
                logger.error(f"MySQL connection pool creation failed: {e}")
                raise e

        return self._pool.get_connection()

    def is_sql_safe(self, query: str) -> bool:
        """Ensure the query is a read-only statement (SELECT, SHOW, EXPLAIN, DESCRIBE)."""
        cleaned = query.strip().upper()
        allowed_prefixes = ("SELECT", "SHOW", "EXPLAIN", "DESCRIBE", "DESC")
        if not any(cleaned.startswith(prefix) for prefix in allowed_prefixes):
            return False
        destructive_keywords = [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
            "CREATE", "REPLACE", "GRANT", "REVOKE", "CALL", "LOAD"
        ]
        for keyword in destructive_keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, cleaned):
                return False
        return True

    def list_tables(self) -> str:
        """
        List all tables in the connected MySQL database.
        Returns a JSON string containing 'tables' list and 'records' list.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()

            output = {
                "totalTables": len(tables),
                "tables": tables,
                "records": [{"table_name": t} for t in tables]
            }
            return json.dumps(output, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Error listing MySQL tables: {str(e)}"})

    def describe_table(self, table_name: str) -> str:
        """
        Get column details and schema of a specific MySQL table.
        Returns a JSON string containing column metadata.
        """
        if not re.match(r"^[a-zA-Z0-9_]+$", table_name):
            return json.dumps({"error": "Error: Invalid table name format."})

        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()

            # Also get row count
            cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`")
            row_count = cursor.fetchone()["cnt"]

            cursor.close()
            conn.close()

            output = {
                "tableName": table_name,
                "totalColumns": len(columns),
                "rowCount": row_count,
                "columns": columns,
                "records": columns
            }
            return json.dumps(output, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"Error describing table '{table_name}': {str(e)}"})

    def execute_sql(self, sql_query: str) -> str:
        """
        Execute read-only SQL query against MySQL. Limit defaults to 200 records.
        Equivalent to SalesforceService.execute_soql().
        """
        if not self.is_sql_safe(sql_query):
            return json.dumps({"error": "Error: Forbidden query. Only read-only SELECT statements are allowed."})

        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            executed_query = sql_query.strip().rstrip(";")

            # Add LIMIT if not present (skip for aggregate-only queries)
            limit_match = re.search(r"\bLIMIT\b\s+\d+", executed_query, re.IGNORECASE)
            if not limit_match:
                is_aggregate = re.search(
                    r"\b(COUNT\s*\(\s*\)|COUNT\s*\(|SUM\s*\(|AVG\s*\(|MIN\s*\(|MAX\s*\()",
                    executed_query, re.IGNORECASE
                )
                is_grouped = re.search(r"\bGROUP\s+BY\b", executed_query, re.IGNORECASE)
                if not (is_aggregate and not is_grouped):
                    executed_query += " LIMIT 200"

            logger.info(f"Executing SQL: {executed_query}")
            cursor.execute(executed_query)
            records = cursor.fetchall()
            cursor.close()
            conn.close()

            # Convert any non-serializable types (like datetime, Decimal)
            cleaned_records = []
            for record in records:
                cleaned = {}
                for k, v in record.items():
                    cleaned[k] = v
                cleaned_records.append(cleaned)

            output = {
                "totalSize": len(cleaned_records),
                "recordsReturned": len(cleaned_records),
                "records": cleaned_records
            }
            return json.dumps(output, indent=2, default=str)

        except Exception as e:
            return json.dumps({"error": f"MySQL query error: {str(e)}"})

    def search_records(self, search_term: str, tables: list = None) -> str:
        """
        Perform cross-table text search in MySQL.
        Equivalent to SalesforceService.search_records().
        Searches all VARCHAR/TEXT columns across specified tables (or all tables).
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Get list of tables to search
            if not tables:
                cursor.execute("SHOW TABLES")
                tables = [row[list(row.keys())[0]] for row in cursor.fetchall()]

            grouped = {}
            total_results = 0

            for table in tables:
                try:
                    # Get text columns for this table
                    cursor.execute(f"DESCRIBE `{table}`")
                    columns = cursor.fetchall()
                    text_columns = [
                        col["Field"] for col in columns
                        if any(t in col.get("Type", "").lower() for t in ["varchar", "text", "char"])
                    ]

                    if not text_columns:
                        continue

                    # Build LIKE search across all text columns
                    where_clauses = [f"`{col}` LIKE %s" for col in text_columns]
                    where_sql = " OR ".join(where_clauses)
                    search_pattern = f"%{search_term}%"
                    params = [search_pattern] * len(text_columns)

                    query = f"SELECT * FROM `{table}` WHERE {where_sql} LIMIT 50"
                    cursor.execute(query, params)
                    results = cursor.fetchall()

                    if results:
                        grouped[table] = results
                        total_results += len(results)
                except Exception as table_err:
                    logger.warning(f"Error searching table '{table}': {table_err}")
                    continue

            cursor.close()
            conn.close()

            output = {
                "totalResults": total_results,
                "resultsByTable": grouped
            }
            return json.dumps(output, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"MySQL search error: {str(e)}"})

    def get_schema_overview(self) -> str:
        """
        Get summary of all tables and their columns for LLM context.
        Equivalent to SalesforceService.get_schema_overview().
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)

            # Get all tables
            cursor.execute("SHOW TABLES")
            tables = [row[list(row.keys())[0]] for row in cursor.fetchall()]

            overview = [f"MySQL Database Schema Overview:"]
            overview.append(f"Database: {self.database}")
            overview.append(f"Host: {self.host}:{self.port}")
            overview.append("")

            for table_name in tables:
                try:
                    cursor.execute(f"DESCRIBE `{table_name}`")
                    columns = cursor.fetchall()

                    # Get row count
                    cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`")
                    row_count = cursor.fetchone()["cnt"]

                    field_summary_parts = []
                    for col in columns:
                        field_summary_parts.append(f"{col['Field']} ({col['Type']})")

                    field_summary = ", ".join(field_summary_parts[:25])
                    if len(field_summary_parts) > 25:
                        field_summary += f", ... +{len(field_summary_parts) - 25} more fields"

                    overview.append(
                        f"Table '{table_name}' ({row_count} rows): [{field_summary}]"
                    )
                except Exception as e:
                    overview.append(f"Table '{table_name}': [Error reading schema: {e}]")

            # Also get foreign key relationships
            overview.append("")
            overview.append("Foreign Key Relationships:")
            try:
                cursor.execute("""
                    SELECT 
                        TABLE_NAME, COLUMN_NAME,
                        REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = %s
                    AND REFERENCED_TABLE_NAME IS NOT NULL
                """, (self.database,))
                fk_rows = cursor.fetchall()
                for fk in fk_rows:
                    overview.append(
                        f"  {fk['TABLE_NAME']}.{fk['COLUMN_NAME']} -> "
                        f"{fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}"
                    )
                if not fk_rows:
                    overview.append("  (No foreign keys found)")
            except Exception as fk_err:
                overview.append(f"  (Could not read foreign keys: {fk_err})")

            cursor.close()
            conn.close()
            return "\n".join(overview)
        except Exception as e:
            return f"Error retrieving MySQL schema: {str(e)}"
