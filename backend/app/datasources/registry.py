"""
Data source registry.

Reads app/semantic/datasources.yaml, builds one SourceContext per enabled
source, and hands them out by id. This is the only place that knows how many
sources exist or what kind they are — everything else iterates.

Adding a source means editing the YAML manifest, not this file.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import yaml

from app.config import settings
from app.datasources.base import RouterConfig, RoutingRules, SourceContext
from app.datasources.mysql_adapter import MySQLAdapter
from app.datasources.salesforce_adapter import SalesforceAdapter
from app.semantic.loader import SemanticModelLoader
from app.services.code_executor import CodeExecutor
from app.services.mysql_service import MySQLService
from app.services.salesforce_service import SalesforceService

logger = logging.getLogger("datasource-registry")

SEMANTIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "semantic")
MANIFEST_PATH = os.path.join(SEMANTIC_DIR, "datasources.yaml")


class DataSourceRegistry:
    def __init__(self, manifest_path: str = MANIFEST_PATH):
        self.manifest_path = manifest_path
        self._manifest = self._load_manifest()
        self._sources: Dict[str, SourceContext] = {}
        self.router_config = self._build_router_config()
        self.cross_source_links = self._manifest.get("cross_source_links") or []
        self._build_sources()
        self._validate()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_manifest(self) -> dict:
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.error(f"Data source manifest not found at {self.manifest_path}")
            return {}
        except Exception as e:
            logger.error(f"Failed to load data source manifest: {e}")
            return {}

    def _build_router_config(self) -> RouterConfig:
        cfg = self._manifest.get("router") or {}
        defaults = RouterConfig()
        return RouterConfig(
            min_score=cfg.get("min_score", defaults.min_score),
            min_margin=cfg.get("min_margin", defaults.min_margin),
            min_llm_confidence=cfg.get("min_llm_confidence", defaults.min_llm_confidence),
            sticky_followup=cfg.get("sticky_followup", defaults.sticky_followup),
            sticky_max_tokens=cfg.get("sticky_max_tokens", defaults.sticky_max_tokens),
            decision_cache_size=cfg.get("decision_cache_size", defaults.decision_cache_size),
        )

    @staticmethod
    def _env(name: Optional[str], default=None):
        """Resolve a *_env manifest reference against the loaded settings."""
        if not name:
            return default
        value = getattr(settings, name, None)
        return default if value in (None, "") else value

    def _build_semantic(self, spec: dict):
        """Returns (SemanticModelLoader | None, raw_yaml_text)."""
        model_file = spec.get("model_file")
        if not model_file:
            return None, ""

        path = os.path.join(SEMANTIC_DIR, model_file)
        if not os.path.exists(path):
            logger.warning(f"Semantic model file missing: {path}")
            return None, ""

        if spec.get("style") == "raw":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return None, f.read()
            except Exception as e:
                logger.warning(f"Could not read raw semantic file {path}: {e}")
                return None, ""

        loader = SemanticModelLoader(
            yaml_path=path,
            max_chars=spec.get("max_chars", 3500),
            max_cols_per_table=spec.get("max_cols_per_table", 30),
            trim_strategy=spec.get("trim_strategy", "legacy"),
        )
        return loader, ""

    def _build_mysql_source(self, entry: dict) -> Optional[SourceContext]:
        conn = entry.get("connection") or {}
        database = self._env(conn.get("database_env"), "")
        user = self._env(conn.get("user_env"), "")

        if not database or not user:
            logger.warning(
                f"Source '{entry.get('id')}' skipped: missing credentials "
                f"({conn.get('user_env')} / {conn.get('database_env')} not set in .env)."
            )
            return None

        service = MySQLService(
            host=self._env(conn.get("host_env"), "localhost"),
            port=int(self._env(conn.get("port_env"), 3306)),
            user=user,
            password=self._env(conn.get("password_env"), ""),
            database=database,
            # Each source needs its own pool name so pool logs are attributable.
            pool_name=conn.get("pool_name") or f"dce_pool_{entry.get('id')}",
            read_only=bool(conn.get("read_only", False)),
        )

        capabilities = entry.get("capabilities") or {}
        adapter = MySQLAdapter(
            service=service,
            source_id=entry["id"],
            label=entry.get("label", entry["id"]),
            exclude_tables=entry.get("exclude_tables") or [],
            allow_cross_table_search=capabilities.get("cross_table_search", True),
        )
        return self._assemble(entry, adapter)

    def _build_salesforce_source(self, entry: dict) -> Optional[SourceContext]:
        conn = entry.get("connection") or {}
        service = SalesforceService(
            username=self._env(conn.get("username_env"), ""),
            password=self._env(conn.get("password_env"), ""),
            security_token=self._env(conn.get("security_token_env"), ""),
            domain=self._env(conn.get("domain_env"), "login"),
            session_id=self._env(conn.get("session_id_env")),
            instance_url=self._env(conn.get("instance_url_env")),
        )
        adapter = SalesforceAdapter(
            service=service,
            source_id=entry["id"],
            label=entry.get("label", entry["id"]),
        )
        return self._assemble(entry, adapter)

    def _assemble(self, entry: dict, adapter) -> SourceContext:
        semantic, semantic_raw = self._build_semantic(entry.get("semantic") or {})
        routing = entry.get("routing") or {}
        sandbox_global = entry.get("sandbox_global", "db")

        return SourceContext(
            id=entry["id"],
            label=entry.get("label", entry["id"]),
            short_label=entry.get("short_label", entry.get("label", entry["id"])),
            kind=entry.get("kind", "mysql"),
            dialect=entry.get("dialect", "mysql"),
            badge=entry.get("badge", entry["id"]),
            priority=int(entry.get("priority", 0)),
            aliases=list(entry.get("aliases") or []),
            adapter=adapter,
            executor=CodeExecutor(adapter, global_name=sandbox_global),
            sandbox_global=sandbox_global,
            semantic=semantic,
            semantic_raw=semantic_raw,
            routing=RoutingRules(
                domain=routing.get("domain", ""),
                entities=list(routing.get("entities") or []),
                strong_keywords=list(routing.get("strong_keywords") or []),
                weak_keywords=list(routing.get("weak_keywords") or []),
                exclude_keywords=list(routing.get("exclude_keywords") or []),
            ),
            exclude_tables=list(entry.get("exclude_tables") or []),
            capabilities=dict(entry.get("capabilities") or {}),
        )

    def _build_sources(self):
        for entry in self._manifest.get("sources") or []:
            if not entry.get("enabled", True):
                logger.info(f"Source '{entry.get('id')}' is disabled in the manifest; skipping.")
                continue
            if not entry.get("id"):
                logger.warning("Manifest entry without an 'id' skipped.")
                continue

            kind = entry.get("kind", "mysql")
            try:
                if kind == "mysql":
                    ctx = self._build_mysql_source(entry)
                elif kind == "salesforce":
                    ctx = self._build_salesforce_source(entry)
                else:
                    logger.warning(f"Unknown source kind '{kind}' for '{entry['id']}'; skipping.")
                    continue
            except Exception as e:
                logger.error(f"Failed to build source '{entry['id']}': {e}")
                continue

            if ctx is not None:
                self._sources[ctx.id] = ctx
                logger.info(
                    f"Registered data source '{ctx.id}' ({ctx.kind}, "
                    f"sandbox global '{ctx.sandbox_global}', badge '{ctx.badge}')"
                )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self):
        """
        Fail loudly on manifest mistakes that would cause silent misrouting.

        Overlapping strong keywords are the dangerous case: two sources both
        claiming a decisive term means the winner is decided by priority
        instead of by meaning, which is exactly the ambiguity this design is
        meant to prevent.
        """
        if not self._sources:
            raise RuntimeError(
                "No data sources could be registered. Check "
                "app/semantic/datasources.yaml and the credentials in backend/.env."
            )

        globals_seen = {}
        for ctx in self._sources.values():
            if ctx.sandbox_global in globals_seen:
                raise RuntimeError(
                    f"Sources '{globals_seen[ctx.sandbox_global]}' and '{ctx.id}' share the "
                    f"sandbox global '{ctx.sandbox_global}'. Each source needs a distinct "
                    f"global so generated code cannot hit the wrong source."
                )
            globals_seen[ctx.sandbox_global] = ctx.id

        ids = list(self._sources)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                ka = {k.lower() for k in self._sources[a].routing.strong_keywords}
                kb = {k.lower() for k in self._sources[b].routing.strong_keywords}
                overlap = ka & kb
                if overlap:
                    raise RuntimeError(
                        f"Sources '{a}' and '{b}' both claim strong keyword(s) "
                        f"{sorted(overlap)}. Strong keywords must be decisive for exactly "
                        f"one source — move shared vocabulary to weak_keywords."
                    )

        default = self._manifest.get("default_source")
        if default and default not in self._sources:
            logger.warning(
                f"default_source '{default}' is not a registered source; "
                f"falling back to '{ids[0]}'."
            )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def default_source_id(self) -> str:
        default = self._manifest.get("default_source")
        if default in self._sources:
            return default
        return next(iter(self._sources))

    def get(self, source_id: str) -> Optional[SourceContext]:
        return self._sources.get(source_id)

    def require(self, source_id: str) -> SourceContext:
        ctx = self._sources.get(source_id)
        if ctx is None:
            raise KeyError(f"Unknown data source '{source_id}'")
        return ctx

    def all(self) -> List[SourceContext]:
        return list(self._sources.values())

    def ids(self) -> List[str]:
        return list(self._sources)

    def default(self) -> SourceContext:
        return self._sources[self.default_source_id]

    def public_catalogue(self) -> List[Dict[str, Any]]:
        """Source list for the UI selector, via GET /api/sources."""
        return [ctx.public_info() for ctx in self._sources.values()]

    def health(self) -> List[Dict[str, Any]]:
        """
        Reachability of every source, in the shape the UI's
        "Connected System Status" panel already renders.
        """
        rows = []
        for ctx in self._sources.values():
            probe = ctx.adapter.health()
            rows.append({
                "id": ctx.id,
                # Display name for the sidebar — short, no engine name.
                "name": ctx.short_label,
                # Full descriptive name, surfaced on hover rather than inline.
                "label": ctx.label,
                "status": probe.get("status", "offline"),
                "detail": probe.get("detail"),
            })
        return rows


# Single global instance, built at import time like the services it wraps.
registry = DataSourceRegistry()
