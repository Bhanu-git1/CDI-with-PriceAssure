"""
MySQL data source adapter.

A thin wrapper over the existing MySQLService. It adds three things the
multi-source setup needs and the bare service does not have:

  1. `health()` that reports offline instead of raising.
  2. Table exclusion, so infrastructure tables (chat transcripts) never appear
     in schema context or search results.
  3. A capability switch for cross-table search, which is unsafe on very large
     schemas.

All query methods keep the names the code sandbox already uses
(execute_sql / describe_table / list_tables / search_records), so generated
code is unchanged.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mysql-adapter")


class MySQLAdapter:
    def __init__(
        self,
        service,
        source_id: str,
        label: str,
        exclude_tables: Optional[List[str]] = None,
        allow_cross_table_search: bool = True,
    ):
        self._service = service
        self.source_id = source_id
        self.label = label
        # Compared case-insensitively: MySQL table-name case sensitivity varies
        # by platform, and this database mixes UPPER_CASE and lower_case names.
        self._excluded = {t.lower() for t in (exclude_tables or [])}
        self.allow_cross_table_search = allow_cross_table_search

    # --- introspection -------------------------------------------------

    @property
    def raw_service(self):
        """
        The underlying MySQLService.

        For infrastructure that needs a real connection rather than the
        read-only query surface — chat-history persistence, which writes and
        so deliberately bypasses the adapter's read-only guarantees.
        """
        return self._service

    @property
    def database(self) -> str:
        return self._service.database

    @property
    def host(self) -> str:
        return self._service.host

    def health(self) -> Dict[str, Any]:
        try:
            conn = self._service.get_connection()
            conn.close()
            return {"status": "connected", "detail": None}
        except Exception as e:
            return {"status": "offline", "detail": str(e)}

    def _is_excluded(self, table_name: str) -> bool:
        return (table_name or "").lower() in self._excluded

    # --- sandbox-facing API (names must not change) --------------------

    def execute_sql(self, sql_query: str) -> str:
        return self._service.execute_sql(sql_query)

    def describe_table(self, table_name: str) -> str:
        if self._is_excluded(table_name):
            return json.dumps(
                {"error": f"Table '{table_name}' is not available on this data source."}
            )
        return self._service.describe_table(table_name)

    def list_tables(self) -> str:
        raw = self._service.list_tables()
        try:
            payload = json.loads(raw)
        except Exception:
            return raw
        if "tables" not in payload:
            return raw

        kept = [t for t in payload["tables"] if not self._is_excluded(t)]
        payload["tables"] = kept
        payload["totalTables"] = len(kept)
        payload["records"] = [{"table_name": t} for t in kept]
        return json.dumps(payload, indent=2)

    def search_records(self, search_term: str, tables: Optional[list] = None) -> str:
        """
        Cross-table text search.

        Disabled per-source via capabilities.cross_table_search. The underlying
        implementation LIKE-scans every text column of every table; on a schema
        with hundreds of thousands of rows that is a full-table-scan storm
        against a shared database instance, so it is opt-in rather than default.
        """
        if not self.allow_cross_table_search:
            return json.dumps({
                "error": (
                    "Cross-table search is disabled for this data source because "
                    "it contains very large tables. Query a specific table with "
                    "execute_sql() and a WHERE clause instead."
                )
            })

        if tables:
            tables = [t for t in tables if not self._is_excluded(t)]
        else:
            try:
                listed = json.loads(self._service.list_tables())
                tables = [t for t in listed.get("tables", []) if not self._is_excluded(t)]
            except Exception:
                tables = None

        return self._service.search_records(search_term, tables=tables)

    def row_counts_block(self, tables: Optional[List[str]] = None, max_tables: int = 80) -> str:
        """
        Compact, authoritative row-count block for the prompt.

        Returns "" on any failure — a missing block is a small loss of context,
        whereas a failed prompt build would take the whole request down.
        """
        try:
            counts = self._service.get_row_counts(tables=tables)
        except Exception as e:
            logger.warning(f"Row counts unavailable for '{self.source_id}': {e}")
            return ""

        counts = {t: n for t, n in counts.items() if not self._is_excluded(t)}
        if not counts:
            return ""

        # Largest first: knowing which tables are big is what changes whether
        # the model filters and aggregates instead of listing.
        items = sorted(counts.items(), key=lambda kv: -kv[1])[:max_tables]
        rendered = ", ".join(f"{t}={n:,}" for t, n in items)
        return (
            "AUTHORITATIVE LIVE ROW COUNTS (read from the database just now — these "
            "SUPERSEDE any row counts mentioned elsewhere in this prompt):\n"
            f"{rendered}\n"
            "For any table above with more than a few thousand rows, do NOT return a bare "
            "list: filter with a WHERE clause, or aggregate with COUNT/GROUP BY. Results are "
            f"capped at {self._service.row_limit} rows, so an unfiltered list silently hides "
            "most of the data."
        )

    def get_schema_overview(self) -> str:
        overview = self._service.get_schema_overview()
        if not self._excluded:
            return overview
        # Drop excluded tables from the rendered overview. Lines are shaped
        # "Table 'name' (N rows): [...]" by MySQLService.get_schema_overview.
        kept_lines = []
        for line in overview.split("\n"):
            if line.startswith("Table '"):
                name = line.split("'", 2)[1] if line.count("'") >= 2 else ""
                if self._is_excluded(name):
                    continue
            kept_lines.append(line)
        return "\n".join(kept_lines)

    def list_entities(self) -> str:
        return self.list_tables()
