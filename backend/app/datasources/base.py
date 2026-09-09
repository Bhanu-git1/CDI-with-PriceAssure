"""
Data source abstraction.

Every queryable backend (MySQL database, Salesforce org, ...) is wrapped in an
adapter exposing the same small surface, so the rest of the application can
iterate over sources instead of naming them.

`SourceContext` is what the router hands to the pipeline: everything needed to
build a prompt and execute generated code against exactly one source.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class DataSourceAdapter(Protocol):
    """
    Uniform read-only surface over a data source.

    Method names are deliberately identical to those already exposed to the
    code sandbox by MySQLService / SalesforceService, so generated code keeps
    working unchanged.
    """

    def health(self) -> Dict[str, Any]:
        """
        Live reachability probe. Must never raise — an unreachable source is
        reported as "offline", not "error"; "error" is reserved for genuine
        application bugs.

        Returns: {"status": "connected" | "offline", "detail": str | None}
        """
        ...

    def get_schema_overview(self) -> str:
        """Human/LLM-readable summary of tables (or objects) and their fields."""
        ...

    def list_entities(self) -> str:
        """JSON string listing the tables (or objects) in this source."""
        ...


@dataclass
class RoutingRules:
    """Per-source routing vocabulary, loaded from datasources.yaml."""

    domain: str = ""
    entities: List[str] = field(default_factory=list)
    strong_keywords: List[str] = field(default_factory=list)
    weak_keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)


@dataclass
class RouterConfig:
    """Router thresholds, loaded from the `router:` block of datasources.yaml."""

    min_score: int = 6
    min_margin: int = 4
    min_llm_confidence: float = 0.6
    sticky_followup: bool = True
    sticky_max_tokens: int = 12
    decision_cache_size: int = 256


@dataclass
class SourceContext:
    """
    Everything the pipeline needs to answer a question from one source.

    Held by the registry; built once at startup.
    """

    id: str
    label: str
    short_label: str
    kind: str                      # "mysql" | "salesforce"
    dialect: str                   # "mysql" | "soql"
    badge: str                     # CSS suffix used by the UI source badge
    priority: int
    aliases: List[str]
    adapter: Any                   # DataSourceAdapter
    executor: Any                  # CodeExecutor bound to this source
    sandbox_global: str            # "db" | "gpo" | "sf"
    semantic: Any                  # SemanticModelLoader, or None for raw style
    semantic_raw: str              # raw YAML text, for style: raw sources
    routing: RoutingRules
    exclude_tables: List[str] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)

    def public_info(self) -> Dict[str, Any]:
        """Shape returned by GET /api/sources for the UI source selector."""
        return {
            "id": self.id,
            "label": self.label,
            "short_label": self.short_label,
            "kind": self.kind,
            "badge": self.badge,
            "domain": (self.routing.domain or "").strip(),
        }

    def semantic_context(self, user_message: str = "") -> str:
        """
        Build this source's semantic-layer prompt block.

        Structured models are trimmed to the tables relevant to the question;
        raw models are injected whole (they are small).
        """
        if self.semantic is not None:
            return self.semantic.get_semantic_context_prompt_trimmed(user_message)
        if self.semantic_raw:
            return f"SEMANTIC LAYER CONFIGURATION (YAML):\n{self.semantic_raw}"
        return ""
