import os
import yaml
import logging

logger = logging.getLogger("semantic-loader")

class SemanticModelLoader:
    def __init__(self, yaml_path: str = None):
        if yaml_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            yaml_path = os.path.join(base_dir, "schema_model.yaml")
        self.yaml_path = yaml_path
        self.model_data = self._load_yaml()

    def _load_yaml(self) -> dict:
        try:
            if not os.path.exists(self.yaml_path):
                logger.warning(f"Semantic YAML file not found at {self.yaml_path}")
                return {}
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading Semantic YAML: {e}")
            return {}

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
        Returns a token-efficient version of the semantic context prompt.
        Only includes tables/measures relevant to the user's query keywords.
        Caps total output to ~3500 chars to stay within model token limits.
        """
        if not self.model_data:
            return ""

        msg_lower = (user_message or "").lower()
        model = self.model_data.get("semantic_model", {})
        sources = model.get("sources", [])
        joins = model.get("joins", [])
        mapping_rules = model.get("mapping_rules", [])
        measures = model.get("measures", [])

        # Keyword -> table name hints for smart filtering
        TABLE_KEYWORDS = {
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

        def table_is_relevant(table_name: str) -> bool:
            kws = TABLE_KEYWORDS.get(table_name, [])
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

        # Hard cap at 3500 chars (~875 tokens) to stay safe
        if len(result) > 3500:
            result = result[:3500] + "\n... (semantic layer truncated)"
        return result

