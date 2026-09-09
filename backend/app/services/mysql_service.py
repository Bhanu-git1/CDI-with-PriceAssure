import re
import json
import logging
import time
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
                 password: str = "", database: str = "", pool_size: int = 5,
                 pool_name: str = "dce_pool", read_only: bool = False):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        # Distinct per source, so pool logs are attributable when more than one
        # database is connected.
        self.pool_name = pool_name
        # When set, every connection handed out is put into a read-only
        # transaction mode, so the SERVER rejects writes. is_sql_safe() is a
        # regex and therefore a best effort; this is enforcement. Must stay
        # False for the database that stores chat transcripts, which writes.
        self.read_only = read_only
        # Maximum rows any single generated query may return.
        self.row_limit = 200
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
                    pool_name=self.pool_name,
                    pool_size=self.pool_size,
                    pool_reset_session=True,
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    autocommit=True,
                    connection_timeout=5
                )
                logger.info(f"Successfully created MySQL connection pool for database '{self.database}'.")
            except MySQLError as e:
                logger.error(f"MySQL connection pool creation failed: {e}")
                raise e

        conn = self._pool.get_connection()

        if self.read_only:
            # The pool is created with pool_reset_session=True, so session state
            # is cleared when a connection is returned — this has to be re-applied
            # on every checkout rather than once at pool creation.
            try:
                cursor = conn.cursor()
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.close()
            except MySQLError as e:
                # A connection that cannot be made read-only must not be handed
                # out for a source declared read-only.
                conn.close()
                logger.error(f"Could not set read-only session on '{self.database}': {e}")
                raise

        return conn

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

    # A trailing LIMIT clause, optionally with an offset in either syntax.
    # Anchored to the end because that is the only place an outer LIMIT can
    # appear — a LIMIT inside a subquery does not bound the result set, so
    # matching one anywhere in the statement (as this used to) left the outer
    # query uncapped.
    _TRAILING_LIMIT = re.compile(
        r"\bLIMIT\s+\d+(?:\s*,\s*\d+)?(?:\s+OFFSET\s+\d+)?\s*$",
        re.IGNORECASE,
    )

    def apply_row_limit(self, query: str, max_rows: int = None) -> str:
        """
        Cap the number of rows a query can return.

        Only row-returning statements are capped. SHOW / DESCRIBE / EXPLAIN are
        left alone because they reject a LIMIT clause outright.

        There is deliberately no aggregate exemption. The previous version
        skipped the cap whenever an aggregate function appeared anywhere in the
        statement, which a scalar subquery such as
        `(SELECT MAX(Fatigue) FROM fatigue_score)` in the SELECT list was enough
        to trigger — leaving genuinely row-returning queries unbounded. Adding a
        LIMIT to a single-row aggregate costs nothing, whereas omitting one from
        a row query can return the whole table, so the bias is toward capping.
        """
        if max_rows is None:
            max_rows = self.row_limit
        head = query.lstrip("( \t\r\n").upper()
        if not (head.startswith("SELECT") or head.startswith("WITH")):
            return query
        if self._TRAILING_LIMIT.search(query):
            return query
        return f"{query} LIMIT {max_rows}"

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

            original_query = sql_query.strip().rstrip(";")
            executed_query = self.apply_row_limit(original_query)
            capped = executed_query != original_query

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

            # Hitting the injected cap exactly almost always means the result
            # set was cut short. Say so, rather than letting the caller report
            # the cap as if it were the total — several of these tables hold
            # tens of thousands of rows.
            if capped and len(cleaned_records) >= self.row_limit:
                output["truncated"] = True
                output["rowLimit"] = self.row_limit
                output["note"] = (
                    f"Result truncated to the first {self.row_limit} rows. More rows match; "
                    f"narrow the query with a WHERE clause or aggregate with COUNT/GROUP BY "
                    f"to describe the full set."
                )

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

    def get_row_counts(self, tables: List[str] = None, ttl_seconds: int = 600) -> Dict[str, int]:
        """
        Live row counts, cached briefly.

        Exists because hardcoded counts in a prompt go stale silently: the DB 1
        semantic layer described Leakage_Activity as "60 rows" when it held
        25,323, which encourages the model to list rather than aggregate. A
        cached live read cannot drift.

        COUNT(*) is used rather than INFORMATION_SCHEMA.TABLE_ROWS, which is an
        InnoDB estimate and can be off by large factors.
        """
        now = time.time()
        cached = getattr(self, "_row_count_cache", None)
        if cached and now - cached[0] < ttl_seconds:
            counts = cached[1]
            return {t: counts[t] for t in tables if t in counts} if tables else counts

        counts = {}
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            present = {row[0] for row in cursor.fetchall()}
            for table in sorted(present):
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                    counts[table] = cursor.fetchone()[0]
                except Exception as e:
                    logger.warning(f"Could not count rows in '{table}': {e}")
        except Exception as e:
            logger.warning(f"Row count refresh failed on '{self.database}': {e}")
            # Serve a stale cache rather than nothing.
            if cached:
                counts = cached[1]
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        self._row_count_cache = (now, counts)
        return {t: counts[t] for t in tables if t in counts} if tables else counts

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
