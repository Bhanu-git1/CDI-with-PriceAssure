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
