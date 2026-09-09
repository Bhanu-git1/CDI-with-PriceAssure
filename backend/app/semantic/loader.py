import os
import re
import yaml
import logging

logger = logging.getLogger("semantic-loader")

# Legacy keyword->table hints for the DB 1 commercial model.
#
# Kept in code deliberately: schema_model.yaml has no `domains:` block, and
# reproducing this map exactly is what guarantees DB 1 prompts are trimmed the
# same way they were before multi-source support. Newer models (see
# gpo_schema_model.yaml) declare their own `domains:` block in YAML instead,
# and never reach this table.
LEGACY_TABLE_KEYWORDS = {
    "Leakage_Activity":                   ["leakage", "reject", "claim", "pharmacy", "brand"],
    "leakage_history":                    ["leakage", "threshold", "history"],
    "fatigue_score":                      ["fatigue", "hcp fatigue", "digital fatigue"],
    "hcp_engagement_logs":                ["engagement", "email", "webinar", "campaign", "log"],
    "campaign_master":                    ["campaign", "channel", "budget"],
    "Compliance_Table":                   ["compliance", "medicaid", "medicare", "payer"],
    "hcp_master_details":                 ["hcp", "work detail", "rep", "prescriber", "npi", "sf_id", "sync"],
    "hcp_master_workdetails_history":     ["work detail", "history", "audit", "rep", "hcp"],
    "Tablet_Extract_History":             ["tablet", "medicine", "drug", "extract", "dosage", "frequency", "guidance"],
    "Transcript_Extraction_History":      ["transcript", "extract", "tablet", "medicine"],
    "medicine_extraction_log":            ["medicine", "drug", "extract", "brand", "generic", "confidence"],
    "salesforce_sync_log":                ["salesforce", "sync", "crm", "sf_id", "push"],
    "rep_details":                        ["rep", "sales rep", "representative", "email", "phone"],
    "rep_master":                         ["manager", "rep master"],
    "hcp_master":                         ["hcp", "prescriber", "npi", "specialty", "state"],
    "copay_Claims_Transactions":          ["copay", "transaction", "claim"],
}

# Default cap on the trimmed prompt block (~875 tokens).
DEFAULT_MAX_CHARS = 3500

# Cap on columns rendered per table. Some tables are extremely wide
# (GPO_STAGED_INPUT has 200 columns, the *_STAGED_INPUT variants 111); listing
# them in full would consume the whole budget for a single table. The live
# schema overview appended to the prompt still carries the complete column list.
DEFAULT_MAX_COLS_PER_TABLE = 30


class SemanticModelLoader:
    def __init__(
        self,
        yaml_path: str = None,
        max_chars: int = DEFAULT_MAX_CHARS,
        max_cols_per_table: int = DEFAULT_MAX_COLS_PER_TABLE,
        trim_strategy: str = "legacy",
    ):
        """
        trim_strategy:
          "legacy"   — the original algorithm: all mapping rules first, then
                       tables, hard-truncated at max_chars. Retained bit-for-bit
                       for the DB 1 commercial model so its prompts do not change.
          "budgeted" — allocates the character budget across sections so relevant
                       tables always survive. Required for large schemas, where a
                       long rules block would otherwise consume the entire budget
                       before a single table is emitted.
        """
        if yaml_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            yaml_path = os.path.join(base_dir, "schema_model.yaml")
        elif not os.path.isabs(yaml_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            yaml_path = os.path.join(base_dir, yaml_path)

        self.yaml_path = yaml_path
        self.max_chars = max_chars
        self.max_cols_per_table = max_cols_per_table
        self.trim_strategy = trim_strategy
        self.model_data = self._load_yaml()
        self._table_keywords = self._build_table_keywords()

    def _load_yaml(self) -> dict:
        try:
            if not os.path.exists(self.yaml_path):
                logger.warning(f"Semantic YAML file not found at {self.yaml_path}")
                return {}
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading Semantic YAML {self.yaml_path}: {e}")
            return {}

    # ------------------------------------------------------------------
    # Relevance index
    # ------------------------------------------------------------------

    def _build_table_keywords(self) -> dict:
        """
        Map table name -> keywords used to decide whether it belongs in a
        trimmed prompt.

        Preference order:
          1. A `domains:` block in the YAML (self-describing; the right way).
          2. LEGACY_TABLE_KEYWORDS, for the DB 1 model that predates it.
        """
        model = self.model_data.get("semantic_model", {}) or {}
        domains = model.get("domains") or self.model_data.get("domains") or []

        if not domains:
            return dict(LEGACY_TABLE_KEYWORDS)

        mapping = {}
        for domain in domains:
            name = (domain.get("name") or "").replace("_", " ")
            kws = list(domain.get("keywords") or [])
            # The domain's own name is a usable keyword too.
            if name:
                kws.append(name)
            for table in domain.get("tables") or []:
                mapping.setdefault(table, [])
                mapping[table].extend(kws)
        return mapping

    @property
    def domains(self) -> list:
        model = self.model_data.get("semantic_model", {}) or {}
        return model.get("domains") or self.model_data.get("domains") or []

    def _iter_tables(self):
        model = self.model_data.get("semantic_model", {}) or {}
        for source in model.get("sources", []) or []:
            for table in source.get("tables", []) or []:
                yield table

    def table_names(self) -> list:
        return [t.get("name") for t in self._iter_tables() if t.get("name")]

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def get_semantic_context_prompt(self) -> str:
        """
        Formats the full semantic model (tables, joins, mapping rules, measures)
        into a structured system prompt for LLM query generation.
        """
        if not self.model_data:
            return ""

        model = self.model_data.get("semantic_model", {})
        sources = model.get("sources", [])
        joins = model.get("joins", [])
        mapping_rules = model.get("mapping_rules", [])
        measures = model.get("measures", [])
        metrics = model.get("metrics", [])

        prompt_lines = [
            "=== SEMANTIC YAML LAYER GOVERNANCE ===",
            f"Model Name: {model.get('name', 'default')}",
            f"Description: {model.get('description', '')}",
        ]

        # --- MAPPING RULES (First, so LLM sees them before tables) ---
        if mapping_rules:
            prompt_lines.append("\n--- BUSINESS TO DATABASE MAPPING RULES (STRICT COMPLIANCE REQUIRED) ---")
            for rule in mapping_rules:
                prompt_lines.append(f"- [{rule.get('category')}]: {rule.get('rule')}")

        # --- TABLES & COLUMNS ---
        prompt_lines.append("\n--- GOVERNED TABLES & FIELDS ---")
        for source in sources:
            for table in source.get("tables", []):
                desc = table.get("description", "")
                prompt_lines.append(f"\nTable: {table.get('name')} -- {desc}")
                cols = table.get("columns", [])
                for col in cols:
                    parts = [f"  - {col.get('name')} [{col.get('type')}]"]
                    if col.get("references"):
                        parts.append(f" -> FK: {col.get('references')}")
                    if col.get("description"):
                        parts.append(f" ({col.get('description')})")
                    prompt_lines.append("".join(parts))

        # --- EXPLICIT JOIN PATHS ---
        if joins:
            prompt_lines.append("\n--- EXPLICIT JOIN PATHS (Use these exact conditions for multi-table queries) ---")
            for j in joins:
                prompt_lines.append(
                    f"- {j.get('left_table')} <-> {j.get('right_table')}: "
                    f"ON {j.get('join_condition')} -- {j.get('description', '')}"
                )

        # --- MEASURES ---
        if measures:
            prompt_lines.append("\n--- PRE-DEFINED SQL MEASURES (Use as templates when applicable) ---")
            for m in measures:
                prompt_lines.append(f"- {m.get('name')}: {m.get('description', '')}")
                prompt_lines.append(f"  SQL: {m.get('sql')}")

        # --- METRICS ---
        if metrics:
            prompt_lines.append("\n--- PRE-DEFINED BUSINESS METRICS ---")
            for met in metrics:
                prompt_lines.append(f"- {met.get('name')}: {met.get('description', '')} | SQL: {met.get('sql')}")

        prompt_lines.append("\n======================================")
        return "\n".join(prompt_lines)

    def get_semantic_context_prompt_trimmed(self, user_message: str = "") -> str:
        """
        Returns a token-efficient version of the semantic context prompt,
        including only what is relevant to the user's question.
        """
        if not self.model_data:
            return ""
        if self.trim_strategy == "budgeted":
            return self._trimmed_budgeted(user_message)
        return self._trimmed_legacy(user_message)

    # ------------------------------------------------------------------
    # Budgeted trimmer (large schemas)
    # ------------------------------------------------------------------

    def matched_domains(self, user_message: str = "") -> list:
        """Domains whose keywords appear in the question, most specific first."""
        msg = (user_message or "").lower()
        scored = []
        for d in self.domains:
            kws = list(d.get("keywords") or [])
            name_kw = (d.get("name") or "").replace("_", " ")
            if name_kw:
                kws.append(name_kw)
            # Longer keywords are more specific, so weight them higher.
            score = sum(len(kw) for kw in kws if kw and re.search(
                r"(?<!\w)" + re.escape(kw) + r"(?!\w)", msg))
            # Naming a program ("Abbott", "Eisai", "REG") scopes the whole
            # question to that pipeline, so it must outrank an incidental
            # keyword hit on a general domain.
            if score and (d.get("name") or "").startswith("program_"):
                score *= 3
            if score:
                scored.append((score, d))
        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored]

    def _rule_is_critical(self, category: str) -> bool:
        c = (category or "").lower()
        return any(k in c for k in ("critical", "column naming", "read-only", "program-specific"))

    def _trimmed_budgeted(self, user_message: str = "") -> str:
        model = self.model_data.get("semantic_model", {}) or {}
        sources = model.get("sources", []) or []
        joins = model.get("joins", []) or []
        mapping_rules = model.get("mapping_rules", []) or []
        measures = model.get("measures", []) or []
        msg_lower = (user_message or "").lower()

        domains = self.matched_domains(user_message)
        wanted = []
        for d in domains:
            for t in d.get("tables") or []:
                if t not in wanted:
                    wanted.append(t)

        # Explicitly named tables always win, whatever the domain match said.
        for name in self.table_names():
            if name and re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", msg_lower):
                if name in wanted:
                    wanted.remove(name)
                wanted.insert(0, name)

        # Nothing matched — return a compact catalogue instead of a truncated
        # dump, so the model can still orient itself (and ask for a table).
        if not wanted:
            return self._domain_catalogue(model)

        table_defs = {}
        for source in sources:
            for table in source.get("tables", []) or []:
                table_defs[table.get("name")] = table

        # --- budget allocation ---------------------------------------
        rules_budget = int(self.max_chars * 0.40)
        tables_budget = int(self.max_chars * 0.45)
        # remainder goes to joins + measures

        head = ["=== SEMANTIC YAML LAYER (TRIMMED) ==="]
        if domains:
            head.append("Matched domain(s): " + ", ".join(
                d.get("name", "") for d in domains[:4]))

        # --- rules: critical first, then domain-relevant --------------
        domain_terms = set()
        for d in domains:
            domain_terms.add((d.get("name") or "").replace("_", " "))
            domain_terms.update(d.get("keywords") or [])

        critical, relevant, other = [], [], []
        for rule in mapping_rules:
            cat = rule.get("category", "")
            body = (cat + " " + str(rule.get("rule", ""))).lower()
            if self._rule_is_critical(cat):
                critical.append(rule)
            elif any(t and t in body for t in domain_terms):
                relevant.append(rule)
            else:
                other.append(rule)

        rules_lines, used = ["\n--- MAPPING RULES ---"], 0
        for rule in critical + relevant + other:
            entry = f"- [{rule.get('category')}]: {' '.join(str(rule.get('rule', '')).split())}"
            if used + len(entry) > rules_budget and used > 0:
                continue
            rules_lines.append(entry)
            used += len(entry)

        # --- tables ----------------------------------------------------
        table_lines, used, included = ["\n--- RELEVANT TABLES & FIELDS ---"], 0, set()
        for name in wanted:
            table = table_defs.get(name)
            if table is None:
                continue
            block = [f"\nTable: {name}"]
            if table.get("row_count") is not None:
                block[0] += f" ({table['row_count']} rows)"
            desc = " ".join(str(table.get("description", "")).split())
            if desc:
                block.append(f"  -- {desc}")
            cols = table.get("columns", []) or []
            for col in cols[: self.max_cols_per_table]:
                line = f"  - {col.get('name')} [{col.get('type')}]"
                if col.get("references"):
                    line += f" -> FK: {col.get('references')}"
                block.append(line)
            if len(cols) > self.max_cols_per_table:
                block.append(
                    f"  ... +{len(cols) - self.max_cols_per_table} more columns "
                    f"(describe_table('{name}') for all)"
                )
            text = "\n".join(block)
            # Truncate at table granularity — never mid-table, which would
            # leave the model with a half-listed set of columns.
            if used + len(text) > tables_budget and included:
                table_lines.append(
                    f"\n(+{len(wanted) - len(included)} more relevant tables omitted; "
                    f"call describe_table() for their columns)"
                )
                break
            table_lines.append(text)
            included.add(name)
            used += len(text)

        # --- joins touching included tables ---------------------------
        join_lines = []
        rel_joins = [
            j for j in joins
            if j.get("left_table") in included or j.get("right_table") in included
        ]
        if rel_joins:
            join_lines.append("\n--- JOIN PATHS ---")
            for j in rel_joins[:14]:
                join_lines.append(
                    f"- {j.get('left_table')} <-> {j.get('right_table')}: "
                    f"ON {j.get('join_condition')}"
                )

        # --- measures relevant to the question ------------------------
        measure_lines = []
        terms = [w for w in re.split(r"\W+", msg_lower) if len(w) > 3]
        rel_measures = [
            m for m in measures
            if any(t in (m.get("name", "") + " " + m.get("description", "")).lower() for t in terms)
        ][:4]
        if rel_measures:
            measure_lines.append("\n--- RELEVANT SQL MEASURES ---")
            for m in rel_measures:
                measure_lines.append(f"- {m.get('name')}: {m.get('sql')}")

        result = "\n".join(head + rules_lines + table_lines + join_lines + measure_lines)
        result += "\n\n=============================="

        if len(result) > self.max_chars:
            result = result[: self.max_chars] + "\n... (semantic layer truncated)"
        return result

    def _domain_catalogue(self, model: dict) -> str:
        """
        Compact orientation block used when no domain matched the question.
        Names the domains and their tables without any column detail.
        """
        lines = ["=== SEMANTIC YAML LAYER (CATALOGUE) ==="]
        lines.append(f"Model: {model.get('name', '')}")
        programs = model.get("programs") or []
        if programs:
            lines.append(
                "Parallel program pipelines (choose the prefix the user means; "
                "default to GPO_): "
                + ", ".join(f"{p.get('id')}={p.get('table_prefix')}" for p in programs)
            )
        lines.append("\n--- DOMAINS & TABLES ---")
        for d in self.domains:
            tables = ", ".join(d.get("tables") or [])
            purpose = " ".join(str(d.get("purpose", "")).split())
            lines.append(f"- {d.get('name')}: {purpose}")
            lines.append(f"    tables: {tables}")
        lines.append(
            "\nNo specific domain matched the question. Identify the relevant table(s) above, "
            "then call describe_table('<name>') before writing SQL."
        )
        lines.append("\n==============================")
        result = "\n".join(lines)
        if len(result) > self.max_chars:
            result = result[: self.max_chars] + "\n... (catalogue truncated)"
        return result

    # ------------------------------------------------------------------
    # Legacy trimmer (DB 1 — behaviour preserved exactly)
    # ------------------------------------------------------------------

    def _trimmed_legacy(self, user_message: str = "") -> str:
        """
        Original trimming algorithm, unchanged.

        Kept so the DB 1 commercial model produces exactly the prompts it did
        before multi-source support. Do not "improve" this without a regression
        run over the curated prompt set.
        """
        msg_lower = (user_message or "").lower()
        model = self.model_data.get("semantic_model", {})
        sources = model.get("sources", [])
        joins = model.get("joins", [])
        mapping_rules = model.get("mapping_rules", [])
        measures = model.get("measures", [])

        def table_is_relevant(table_name: str) -> bool:
            kws = self._table_keywords.get(table_name, [])
            if not kws:
                return True  # include unknown tables by default
            return any(kw in msg_lower for kw in kws)

        prompt_lines = ["=== SEMANTIC YAML LAYER (TRIMMED) ==="]

        # Mapping rules — always include (they're short)
        if mapping_rules:
            prompt_lines.append("\n--- MAPPING RULES ---")
            for rule in mapping_rules[:8]:  # cap at 8 rules
                prompt_lines.append(f"- [{rule.get('category')}]: {rule.get('rule')}")

        # Relevant tables only
        prompt_lines.append("\n--- RELEVANT TABLES & FIELDS ---")
        included_tables = set()
        for source in sources:
            for table in source.get("tables", []):
                name = table.get("name", "")
                if not table_is_relevant(name):
                    continue
                included_tables.add(name)
                desc = table.get("description", "")
                prompt_lines.append(f"\nTable: {name} -- {desc}")
                # No column cap here — the original emitted every column, and
                # this path exists to reproduce that output exactly.
                for col in table.get("columns", []):
                    col_line = f"  - {col.get('name')} [{col.get('type')}]"
                    if col.get("references"):
                        col_line += f" -> FK: {col.get('references')}"
                    prompt_lines.append(col_line)

        # Only include joins that touch included tables
        relevant_joins = [
            j for j in joins
            if j.get("left_table") in included_tables or j.get("right_table") in included_tables
        ]
        if relevant_joins:
            prompt_lines.append("\n--- JOIN PATHS ---")
            for j in relevant_joins:
                prompt_lines.append(
                    f"- {j.get('left_table')} <-> {j.get('right_table')}: ON {j.get('join_condition')}"
                )

        # Relevant measures only
        relevant_measures = [
            m for m in measures
            if any(kw in (m.get("name", "") + m.get("description", "")).lower() for kw in msg_lower.split())
        ][:5]
        if relevant_measures:
            prompt_lines.append("\n--- RELEVANT SQL MEASURES ---")
            for m in relevant_measures:
                prompt_lines.append(f"- {m.get('name')}: SQL: {m.get('sql')}")

        prompt_lines.append("\n==============================")
        result = "\n".join(prompt_lines)

        if len(result) > self.max_chars:
            result = result[: self.max_chars] + "\n... (semantic layer truncated)"
        return result
