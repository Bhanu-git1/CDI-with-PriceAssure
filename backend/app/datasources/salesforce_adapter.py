"""
Salesforce data source adapter.

Thin wrapper over the existing SalesforceService, giving it the same surface as
the MySQL adapter so the registry, health checks and pipeline can treat all
sources alike. Query methods keep the names the code sandbox already uses
(execute_soql / describe_object / list_objects / search_records).
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("salesforce-adapter")


class SalesforceAdapter:
    def __init__(self, service, source_id: str, label: str):
        self._service = service
        self.source_id = source_id
        self.label = label
        # Salesforce has no table concept to exclude, and SOSL is bounded by
        # the API rather than by table scans, so search stays enabled.
        self.allow_cross_table_search = True

    @property
    def raw_service(self):
        """The underlying SalesforceService, for code that needs the client directly."""
        return self._service

    def health(self) -> Dict[str, Any]:
        try:
            self._service.get_connection()
            return {"status": "connected", "detail": None}
        except Exception as e:
            return {"status": "offline", "detail": str(e)}

    # --- sandbox-facing API (names must not change) --------------------

    def execute_soql(self, soql_query: str) -> str:
        return self._service.execute_soql(soql_query)

    def describe_object(self, object_name: str) -> str:
        return self._service.describe_object(object_name)

    def list_objects(self) -> str:
        return self._service.list_objects()

    def search_records(self, sosl_query: str) -> str:
        return self._service.search_records(sosl_query)

    def get_schema_overview(self) -> str:
        return self._service.get_schema_overview()

    def list_entities(self) -> str:
        return self._service.list_objects()
