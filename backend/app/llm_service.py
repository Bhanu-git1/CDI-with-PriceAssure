import json
import logging
import os
import re
import asyncio
import httpx
from typing import Dict, Any, Tuple, Optional
import anthropic

from app.config import settings
from app.datasources import registry
from app.router import SourceRouter

logger = logging.getLogger("llm-service")

# These module-level names are now views onto the data source registry rather
# than independently constructed singletons, so each backend has exactly one
# connection pool no matter how many places reference it. The names are kept
# so existing imports (main.py, history_service) keep working unchanged.
_primary_ctx = registry.require("mysql_primary")
_sf_ctx = registry.get("salesforce")

# Raw service: chat-history persistence needs a real connection (it writes),
# which the read-only adapter deliberately does not expose.
db_service = _primary_ctx.adapter.raw_service
semantic_loader = _primary_ctx.semantic

SYSTEM_PROMPT = """
You generate Python code to fetch and analyze data from a MySQL database using the Semantic YAML governance rules.
The database powers a Pharma Commercial Command Centre with 5 integrated Use Cases:
  - UC1: Leakage Signals (Leakage_Activity, leakage_history, Reverse_Claims, Compliance_Table)
  - UC2: Journey Orchestration & HCP Fatigue (fatigue_score, hcp_engagement_logs, campaign_master)
  - UC3: Voice Work Detail Manager & HCP Interaction Recording (hcp_master_details, hcp_master_workdetails_history, rep_details)
  - UC4: Clinical Medicine Extraction & Guideline Analysis (Tablet_Extract_History, Transcript_Extraction_History)
  - UC5: Salesforce Integration & Sync Audit (hcp_master_details, Tablet_Extract_History)

UI DASHBOARD displays data from PRIMARY TABLES:
  1. Leakage_Activity (60 rows) — Main leakage records table (UC1)
  2. fatigue_score (49 rows) — Fatigue scores table (fatigue range: 10-60) (UC2)
  3. leakage_history (13 rows) — Threshold update log (UC1)
  4. Compliance_Table (111 rows) — Govt plans bypassed KPI (UC1)
  5. hcp_master_details (29 rows) — Main UC3/UC5 table (Prescriber_NPI, hcp_firstName, hcp_lastName, rep_id, status, work_detail, sf_id, created_at, updated_at)
  6. hcp_master_workdetails_history — UC3 audit trail history table (history_id, hcp_id, rep_id, rep_firstName, rep_lastName, work_detail, updated_datetime)
  7. Tablet_Extract_History (170 rows) — UC4 medicine extraction table (id, Tablet_name, Dosage, Frequency, guidance, timestamp, Prescriber_NPI, sf_id, status, message)
  8. Transcript_Extraction_History (48 rows) — UC4 transcript extraction log (id, hcp_detail_id, Prescriber_NPI, sf_id, transcript_text, tablet_names, status, created_at)
  9. rep_details — Sales representative directory (rep_id, rep_firstName, rep_lastName, email, phone, manager_id)
  10. rep_master — Manager directory (rep_id, rep_firstName, rep_lastName, email, phone)

RULES:
- ALWAYS refer to the SEMANTIC YAML LAYER GOVERNANCE block below for exact table names, column names, join conditions, and pre-defined SQL measures.
- NEVER invent table or column names. Use ONLY columns listed in the governance block.
- For ALL claims and rejection queries, use `Leakage_Activity`.
- For ALL medicine, tablet, drug extraction queries (UC4), use `Tablet_Extract_History` or `Transcript_Extraction_History` (joined with `hcp_master_details` on `Prescriber_NPI` to get HCP name: `CONCAT(hmd.hcp_firstName, ' ', hmd.hcp_lastName) AS HCP_Name`).
- For Salesforce CRM sync/push audit queries (UC5), use `hcp_master_details` (sf_id, status, updated_at) or `Tablet_Extract_History` (sf_id, status, message).
- Use standard MySQL SQL syntax.
- When user explicitly asks for 'today\'s' records or data for today, filter using `CURDATE()` on the date column: e.g. `WHERE DATE(Processed_TimeStamp) = CURDATE()`.
- When PRE-DEFINED SQL MEASURES match the user's question, use them as templates.
"""

# UC3 (Salesforce) system prompt — reused verbatim from the standalone DCE Salesforce project.
SALESFORCE_SYSTEM_PROMPT = """
You generate Python code to fetch and analyze data from a MySQL database using the Semantic YAML governance rules.
The database powers a Pharma Commercial Command Centre with 5 integrated Use Cases:
  - UC1: Leakage Signals (Leakage_Activity, leakage_history, Reverse_Claims, Compliance_Table)
  - UC2: Journey Orchestration & HCP Fatigue (fatigue_score, hcp_engagement_logs, campaign_master)
  - UC3: Voice Work Detail Manager & HCP Interaction Recording (hcp_master_details, hcp_master_workdetails_history, rep_details)
  - UC4: Clinical Medicine Extraction & Guideline Analysis (Tablet_Extract_History, Transcript_Extraction_History, medicine_extraction_log)
  - UC5: Salesforce Integration & Sync Audit (salesforce_sync_log , Tablet_Extract_History, hcp_master_details)

UI DASHBOARD displays data from PRIMARY TABLES:
  1. Leakage_Activity (60 rows) — Main leakage records table (UC1)
  2. fatigue_score (49 rows) — Fatigue scores table (fatigue range: 10-60) (UC2)
  3. leakage_history (13 rows) — Threshold update log (UC1)
  4. Compliance_Table (111 rows) — Govt plans bypassed KPI (UC1)
  5. hcp_master_details — Main UC3/UC5 table (Prescriber_NPI, hcp_firstName, hcp_lastName, rep_id, status, work_detail, sf_id, created_at, updated_at)
  6. hcp_master_workdetails_history — UC3 audit trail history table (history_id, hcp_id, rep_id, rep_firstName, rep_lastName, work_detail, updated_datetime)
  7. Tablet_Extract_History — UC4 medicine extraction table (167 rows: id, Tablet_name, Dosage, Frequency, guidance, timestamp, Prescriber_NPI, sf_id, status, message)
  8. Transcript_Extraction_History — UC4 transcript extraction log (id, hcp_detail_id, Prescriber_NPI, sf_id, transcript_text, tablet_names, status, created_at)
  9. medicine_extraction_log — UC4 medicine extraction summary log (extraction_id, Prescriber_NPI, HCP_Name, extracted_drug, brand_name, generic_name, dosage, frequency, confidence_score)
  10. salesforce_sync_log — UC5 Salesforce CRM sync status log (sync_id, Prescriber_NPI, HCP_Name, sf_object_type, sf_record_id, sync_status, sync_message)
  11. rep_details — Sales representative directory (rep_id, rep_firstName, rep_lastName, email, phone, manager_id)
  12. rep_master — Manager directory (rep_id, rep_firstName, rep_lastName, email, phone)

RULES:
- ALWAYS refer to the SEMANTIC YAML LAYER GOVERNANCE block below for exact table names, column names, join conditions, and pre-defined SQL measures.
- NEVER invent table or column names. Use ONLY columns listed in the governance block.
- For ALL claims and rejection queries, use `Leakage_Activity`.
- For ALL medicine, tablet, drug extraction queries (UC4), use `Tablet_Extract_History` or `medicine_extraction_log` (joined with `hcp_master_details` on `Prescriber_NPI` to get HCP name: `CONCAT(hmd.hcp_firstName, ' ', hmd.hcp_lastName) AS HCP_Name`).
- For Salesforce CRM sync/push queries (UC5), use `salesforce_sync_log` or `hcp_master_details` (sf_id, status, updated_at).
- Use standard MySQL SQL syntax.
- When user explicitly asks for 'today\'s' records or data for today, filter using `CURDATE()` on the date column: e.g. `WHERE DATE(Processed_TimeStamp) = CURDATE()`.
- When PRE-DEFINED SQL MEASURES match the user's question, use them as templates.
"""


# DB 2 (GPO) system prompt. Mirrors the structure of the two above, but the
# authoritative table/column detail comes from the generated semantic layer
# (gpo_schema_model.yaml) rather than being restated here — that file is built
# from the live schema, so it cannot drift.
GPO_SYSTEM_PROMPT = """
You generate Python code to fetch and analyze data from the GPO customer-roster
validation MySQL database, using the Semantic YAML governance rules.

The database supports a batch validation pipeline:
  1. UPLOAD      — a customer roster file creates a batch header (GPO_CUST_HDR) and raw rows (GPO_STAGED_INPUT)
  2. MAPPING     — raw rows are mapped to standardized rows (GPO_CUST_INPUT) via a GPO_INPUT_FORMAT template
  3. VALIDATION  — each row is checked against master data:
                     HIN  -> GPO_HIN  / GPO_HIN_VALIDATE
                     DEA  -> GPO_DEA  / GPO_DEA_VALIDATE
                     HRSA -> GPO_HRSA / GPO_HRSA_VALIDATE
                     USPS -> GPO_USPS / GPO_USPS_VALIDATE
                     COT  -> GPO_COT_VALIDATE (derived from HIN/DEA/RODB opinions)
                     MEMBER -> GPO_MEMBER_VALIDATE
  4. MERGE       — all validation results are merged into GPO_CUST_STG_OUTPUT
  5. OUTPUT      — the final deliverable is written to GPO_CUST_OUTPUT via a GPO_OUTPUT_FORMAT template
  6. TRACKING    — per-stage status in GPO_VALIDATION_JOBS; every action audited in GPO_LOGS

It also holds:
  - Membership and contract reference data (MN_MEMBER, MN_ORGANIZATION_ID, MN_CF_ELIGIBLE_CUSTOMER,
    MN_STRUCTURED_DOC, MN_STRUCTURED_CONTRACT)
  - Role-based access control (GPO_ROLE_MASTER, GPO_ROLE_PERMISSION, GPO_ROLE_MAPPING, GPO_USER_LOGIN)
  - Three client-specific parallel pipelines with the same shape: REG_*, ABBOTT_*, EISAI_*

RULES:
- ALWAYS refer to the SEMANTIC YAML LAYER GOVERNANCE block below for exact table names, column
  names, join conditions and pre-defined SQL measures.
- NEVER invent table or column names. Business columns here are UPPER_CASE. When unsure,
  call gpo.describe_table('<TABLE_NAME>') first.
- BATCH_NUM is the correlation key. The large tables (GPO_CUST_INPUT, GPO_STAGED_INPUT,
  GPO_HIN_VALIDATE, GPO_CUST_STG_OUTPUT) MUST always be filtered by BATCH_NUM or another
  selective predicate — never scan them whole, and never SELECT * from GPO_STAGED_INPUT
  (it has 200 columns).
- Distinguish JOB status from MATCH status. Processing outcomes ('failed', 'pending',
  'completed') live on GPO_VALIDATION_JOBS. The STATUS column on the *_VALIDATE tables is a
  match-outcome code ('DUP', 'SAME', 'NO', 'ONE'), not a job state. Stage status values have
  inconsistent casing, so compare with LOWER().
- Use GPO_* tables unless the user explicitly names the REG, Abbott or Eisai program.
- Prefer aggregates (COUNT, GROUP BY) over returning raw rows from the large tables.
- Use standard MySQL SQL syntax.
- When PRE-DEFINED SQL MEASURES match the user's question, use them as templates.
"""


class LLMService:
    def __init__(self):
        self.semantic_loader = semantic_loader
        self.sf_semantic_layer_raw = self._load_sf_semantic_layer()
        if settings.GROQ_API_KEY:
            self.provider = "groq"
            logger.info(f"Initializing Groq client with model {settings.GROQ_MODEL} for DCE...")
        elif settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            self.provider = "claude"
            self.is_bedrock = True
            self.claude_model = settings.BEDROCK_CLAUDE_MODEL
            logger.info(
                f"Initializing Claude client via AWS Bedrock (model={self.claude_model}, "
                f"region={settings.AWS_REGION}) for DCE..."
            )
            self.claude_client = anthropic.AsyncAnthropicBedrock(
                aws_access_key=settings.AWS_ACCESS_KEY_ID,
                aws_secret_key=settings.AWS_SECRET_ACCESS_KEY,
                aws_region=settings.AWS_REGION,
            )
        elif settings.CLAUDE_API_KEY:
            self.provider = "claude"
            self.is_bedrock = False
            self.claude_model = settings.CLAUDE_MODEL
            logger.info(f"Initializing Claude client with model {self.claude_model} for DCE...")
            self.claude_client = anthropic.AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)
        else:
            raise RuntimeError(
                "No LLM provider configured. Set GROQ_API_KEY, AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY "
                "(Bedrock), or CLAUDE_API_KEY in backend/.env."
            )

        # The router is given this service's own classifier for its Stage-2
        # tie-break, so it stays independent of the provider in use.
        self.router = SourceRouter(registry, classifier=self.classify_source)

    def _generate_data_summary(self, user_message: str, result_data, row_cap: Optional[int] = None) -> str:
        """Generate a natural language summary with an embedded markdown table directly from query results."""
        rows = []
        if isinstance(result_data, list):
            rows = result_data
        elif isinstance(result_data, dict):
            if "records" in result_data and isinstance(result_data["records"], list):
                rows = result_data["records"]
            elif "data" in result_data and isinstance(result_data["data"], list):
                rows = result_data["data"]
            else:
                rows = [result_data]

        count = len(rows)

        if count == 0:
            return (
                "🔍 No records found matching your criteria.\n\n"
                "Try broadening your search or rephrasing the query."
            )

        # Landing exactly on the row cap means the result set was almost
        # certainly cut short. Reporting the cap as the total would overstate
        # certainty about tables that hold tens of thousands of rows.
        was_truncated = bool(row_cap) and count >= row_cap
        if was_truncated:
            summary_lines = [
                f"✅ Showing the **first {count} record(s)** — more rows match this request "
                f"than can be returned at once.\n\n"
                f"_To see the full picture, narrow the question (add a filter) or ask for a "
                f"count/summary instead of a list._\n"
            ]
        else:
            summary_lines = [f"✅ Found **{count} record(s)** matching your request.\n"]

        if rows and isinstance(rows[0], dict):
            fields = list(rows[0].keys())

            # Prioritize key business fields (Email, Phone, Name, License, State, Specialty, Status) over technical IDs
            def field_priority(f: str) -> int:
                f_lower = f.lower()
                if f_lower in ("id", "id__c") or f_lower.endswith(".id") or "createdby" in f_lower or "modstamp" in f_lower or "system" in f_lower:
                    return 100
                if "email" in f_lower:
                    return 1
                if "phone" in f_lower or "mobile" in f_lower:
                    return 2
                if "name" in f_lower:
                    return 3
                if "license" in f_lower:
                    return 4
                if "state" in f_lower:
                    return 5
                if "special" in f_lower:
                    return 6
                if "status" in f_lower:
                    return 7
                return 10

            sorted_fields = sorted(fields, key=field_priority)
            displayed_fields = sorted_fields[:10]

            # Markdown table header & separator
            header_row = "| " + " | ".join(displayed_fields) + " |"
            sep_row = "| " + " | ".join(["---"] * len(displayed_fields)) + " |"

            summary_lines.append(header_row)
            summary_lines.append(sep_row)

            # Show top 8 rows directly inside Answer tab
            max_rows = min(count, 8)
            for i in range(max_rows):
                r = rows[i]
                vals = []
                for f in displayed_fields:
                    val = r.get(f)
                    if val is None or str(val).strip() == "":
                        val_str = "-"
                    else:
                        val_str = str(val).replace("\n", " ").replace("|", "\\|")
                        if len(val_str) > 40:
                            val_str = val_str[:37] + "..."
                    vals.append(val_str)
                summary_lines.append("| " + " | ".join(vals) + " |")

            if count > max_rows:
                summary_lines.append(f"\n_Showing top {max_rows} of {count} rows. Click the **Table View** tab above to explore the complete dataset._")

        return "\n".join(summary_lines)

    async def check_llm_health(self) -> Dict[str, Any]:
        """
        Lightweight liveness check for the configured LLM provider, used for
        UI status monitoring. Hits a metadata endpoint only — no completion
        tokens are consumed and no chat rate-limit budget is spent.
        """
        try:
            if self.provider == "groq":
                headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get("https://api.groq.com/openai/v1/models", headers=headers)
                if resp.status_code == 200:
                    return {"status": "connected", "detail": None}
                return {"status": "offline", "detail": f"Groq API returned HTTP {resp.status_code}"}
            elif self.provider == "claude":
                if self.is_bedrock:
                    # Bedrock has no metadata/models endpoint; a minimal 1-token
                    # completion is the cheapest available liveness probe.
                    await self.claude_client.messages.create(
                        model=self.claude_model,
                        max_tokens=1,
                        messages=[{"role": "user", "content": "ping"}],
                    )
                else:
                    await self.claude_client.models.retrieve(self.claude_model)
                return {"status": "connected", "detail": None}
            else:
                return {"status": "offline", "detail": "No LLM provider configured"}
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")
            return {"status": "offline", "detail": str(e)}

    def _load_sf_semantic_layer(self) -> str:
        """Load the Salesforce (UC3) semantic layer YAML file if available."""
        # Prefer the copy the registry already read from the manifest-declared
        # path; fall back to the direct file read for safety.
        if _sf_ctx is not None and _sf_ctx.semantic_raw:
            return _sf_ctx.semantic_raw
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            yaml_path = os.path.join(base_dir, "semantic", "salesforce_semantic_layer.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            logger.warning(f"Could not load salesforce_semantic_layer.yaml: {e}")
        return ""

    def _get_salesforce_refinement_instructions(self) -> str:
        return (
            "You write Python code to fetch or analyze data from Salesforce via the whitelisted 'sf' global object.\n"
            "The available 'sf' methods are:\n"
            "  - sf.execute_soql(soql_query: str) -> str: Runs read-only SOQL. Returns a JSON string containing 'records' and 'totalSize'. Must parse with json.loads().\n"
            "  - sf.describe_object(object_name: str) -> str: Returns schema details for a specific object name.\n"
            "  - sf.list_objects() -> str: Returns list of queryable objects.\n"
            "  - sf.search_records(sosl_query: str) -> str: Runs SOSL cross-object search. Returns a JSON string. Must parse with json.loads().\n\n"
            "Rules for writing code:\n"
            "  1. If the user query requires retrieving data, you MUST write code that executes a query using sf.execute_soql() or sf.search_records(). DO NOT hardcode empty lists or mock data.\n"
            "  2. Parse the returned JSON string using json.loads() to access the actual records.\n"
            "  3. Store your final output structure in the variable 'result' (e.g. result = {...}).\n"
            "  4. For queries, you MUST set: result = {'soql': '<query_string>', 'records': <records_list_retrieved>}\n"
            "  5. For search, you MUST set: result = {'sosl': '<search_query>', 'records': <flat_records_list_retrieved>}\n"
            "  6. Global scope already has 'sf', 'json', 'math', 'datetime', 'date', 'timedelta', 're', 'collections' pre-loaded.\n"
            "  7. Standard imports for allowed modules are permitted.\n"
            "  8. Preferred objects are Doctor__c and Rep_Details__c. DO NOT query or include Manager fields (`Rep_Manager__r`, `Rep_Manager__c`) in any Salesforce queries because manager data is unpopulated.\n"
            "  9. ALWAYS include Doctor Phone (`Phone__c`), State License (`State_License__c`), and Representative details (`Rep_Ids__r.First_Name__c`, `Rep_Ids__r.Last_Name__c`, `Rep_Ids__r.Email__c`, `Rep_Ids__r.Phone_Number__c`) in the SELECT clause when querying Doctor__c records so contact details and email addresses are always returned.\n"
            "  10. FLEXIBLE SEARCHING: Use LIKE operators (e.g. Speciality__c LIKE '%cardiology%', HCP_First_Name__c LIKE '%John%', Practice_State__c LIKE '%TX%') for string searches to match partial or case-insensitive user inputs.\n"
            "  11. PICKLIST & STATE MAP:\n"
            "      - For Doctor__c.Status__c: Map 'in progress', 'progress', 'wip', 'ongoing' -> Status__c = 'In-Progress'. Map 'completed', 'complete', 'done', 'finished' -> Status__c = 'Completed'.\n"
            "      - For Practice_State__c & State_License__c: Support full state names and postal codes (e.g. State_License__c LIKE '%California%' OR State_License__c LIKE '%CA%' OR Practice_State__c LIKE '%CA%').\n"
            "  12. GREETINGS & SCHEMA QUESTIONS:\n"
            "      - If the user prompt is a greeting (e.g. 'hello', 'hi', 'hey', 'help'), set code = null and provide a helpful, welcoming natural language answer in the 'answer' field explaining available data (Doctors, Sales Reps) with example prompts.\n"
            "      - If the user asks about available tables or schema ('what objects are in Salesforce?', 'describe Doctor__c object'), provide the schema info in 'answer' or run sf.describe_object('Doctor__c') / sf.list_objects().\n\n"
            "Example of querying Doctors with Rep Email & Contact Info:\n"
            "data = json.loads(sf.execute_soql(\"SELECT HCP_First_Name__c, HCP_Last_Name__c, Phone__c, State_License__c, Speciality__c, Practice_State__c, Status__c, Rep_Ids__r.First_Name__c, Rep_Ids__r.Last_Name__c, Rep_Ids__r.Email__c, Rep_Ids__r.Phone_Number__c FROM Doctor__c WHERE Status__c = 'In-Progress'\"))\n"
            "result = {\"soql\": \"SELECT HCP_First_Name__c, HCP_Last_Name__c, Phone__c, State_License__c, Speciality__c, Practice_State__c, Status__c, Rep_Ids__r.First_Name__c, Rep_Ids__r.Last_Name__c, Rep_Ids__r.Email__c, Rep_Ids__r.Phone_Number__c FROM Doctor__c WHERE Status__c = 'In-Progress'\", \"records\": data.get(\"records\", [])}\n\n"
            "Format your output ONLY as a valid JSON object with these keys:\n"
            "{\n"
            "  \"reasoning\": \"your reasoning/steps\",\n"
            "  \"code\": \"python code string to run or null\",\n"
            "  \"answer\": \"natural language answer if no salesforce query is required\"\n"
            "}\n"
            "Output ONLY the JSON object. Do not wrap in markdown tags like ```json."
        )

    # ==================================================================
    # Generic, source-parameterised pipeline
    # ==================================================================

    def _get_gpo_refinement_instructions(self) -> str:
        return (
            "You write Python code to fetch or analyze data from the GPO MySQL database via the "
            "whitelisted 'gpo' global object.\n"
            "The available 'gpo' methods are:\n"
            "  - gpo.execute_sql(sql_query: str) -> str: Runs read-only SQL SELECT. Returns a JSON string "
            "with 'records' and 'totalSize'. Must parse with json.loads().\n"
            "  - gpo.describe_table(table_name: str) -> str: Returns column details for one table.\n"
            "  - gpo.list_tables() -> str: Returns the list of tables in the database.\n\n"
            "IMPORTANT: the global is named 'gpo', NOT 'db'. There is no 'db' object in this scope.\n"
            "Cross-table keyword search is NOT available on this source (the tables are too large); "
            "write a targeted SELECT with a WHERE clause instead.\n\n"
            "Rules for writing code:\n"
            "  1. You MUST execute queries using gpo.execute_sql(). DO NOT hardcode empty lists or mock data.\n"
            "  2. Parse the returned JSON string using json.loads() to access records.\n"
            "  3. Store final output in variable 'result' = {'sql': '<query_string>', 'records': <records_list>}.\n"
            "  4. Global scope has 'gpo', 'json', 'math', 'datetime', 'date', 'timedelta', 're', "
            "'collections' pre-loaded.\n"
            "  5. Write valid multi-line Python code with proper line breaks.\n"
            "  6. When a PRE-DEFINED SQL MEASURE matches the user's question, adapt it as your template — "
            "replacing any <batch_num> placeholder with the batch the user named.\n"
            "  7. If the user asks about a batch without naming one, either aggregate across batches or "
            "return the most recent batches (ORDER BY CREATED_DATE DESC) — do not invent a batch number.\n"
            "  8. If the question could refer to the REG, Abbott or Eisai program as well as the base GPO "
            "program and the user did not say which, set code = null and ask which program they mean "
            "in the 'answer' field.\n"
            "  9. GREETINGS & SCHEMA QUESTIONS: if the prompt is a greeting or asks what data is "
            "available, set code = null and describe the pipeline domains in 'answer' with example prompts.\n\n"
            "Example 1 - per-stage status for a batch:\n"
            "sql = \"SELECT h.BATCH_NUM, h.FILE_NAME, h.CURRENT_ACTION, j.STATUS, j.HIN_STATUS, j.DEA_STATUS, "
            "j.USPS_STATUS, j.COT_STATUS, j.HRSA_STATUS, j.OUTPUT_STATUS FROM GPO_CUST_HDR h "
            "JOIN GPO_VALIDATION_JOBS j ON h.BATCH_NUM = j.BATCH_NUM WHERE h.BATCH_NUM = 1024\"\n"
            "data = json.loads(gpo.execute_sql(sql))\n"
            "result = {\"sql\": sql, \"records\": data.get(\"records\", [])}\n\n"
            "Example 2 - batches with a failed stage (case-insensitive):\n"
            "sql = \"SELECT BATCH_NUM, STATUS, HIN_STATUS, DEA_STATUS, USPS_STATUS FROM GPO_VALIDATION_JOBS "
            "WHERE LOWER(HIN_STATUS) = 'failed' OR LOWER(STATUS) = 'failed' ORDER BY BATCH_NUM DESC\"\n"
            "data = json.loads(gpo.execute_sql(sql))\n"
            "result = {\"sql\": sql, \"records\": data.get(\"records\", [])}\n\n"
            "Format your output ONLY as a JSON object with these keys:\n"
            "{\n"
            "  \"reasoning\": \"your reasoning/steps\",\n"
            "  \"code\": \"python code string to run or null\",\n"
            "  \"answer\": \"natural language answer if no database query is required\"\n"
            "}\n"
            "Output ONLY the JSON object. Do not wrap in markdown tags like ```json."
        )

    @staticmethod
    def _row_counts_block(ctx) -> str:
        """
        Live row counts for the tables this source's semantic model describes.

        Both MySQL semantic layers state row counts in prose, and DB 1's had
        drifted by more than two orders of magnitude (Leakage_Activity was
        described as 60 rows while holding 25,323), which pushes the model
        toward listing rows instead of aggregating them. Injecting the real
        numbers as authoritative removes the whole class of problem.
        """
        builder = getattr(ctx.adapter, "row_counts_block", None)
        if builder is None:
            return ""
        tables = ctx.semantic.table_names() if ctx.semantic else None
        block = builder(tables)
        return f"{block}\n\n" if block else ""

    def _build_source_prompt(self, ctx, user_message: str, history_context: str) -> str:
        """
        Assemble the prompt for one source.

        For mysql_primary and salesforce this reproduces the previously
        hardcoded assembly exactly — same constants, same order, same wording —
        so their generated code does not change. Verified by
        tests/test_prompt_equivalence.py.
        """
        if ctx.id == "salesforce":
            schema_context = ctx.adapter.get_schema_overview()
            semantic_layer_prompt = (
                f"SEMANTIC LAYER CONFIGURATION (YAML):\n{self.sf_semantic_layer_raw}\n\n"
                if self.sf_semantic_layer_raw else ""
            )
            return (
                f"{SALESFORCE_SYSTEM_PROMPT}\n\n"
                f"{self._get_salesforce_refinement_instructions()}\n\n"
                f"{semantic_layer_prompt}"
                f"SALESFORCE SCHEMA DETAILS:\n{schema_context}\n\n"
                f"{history_context}"
                "CRITICAL REMINDER FOR THIS ORG:\n"
                "- Query custom objects 'Doctor__c' and 'Rep_Details__c'.\n"
                "- Filter HCPs / Doctors using fields like HCP_First_Name__c, HCP_Last_Name__c, "
                "Speciality__c, Practice_State__c, Status__c.\n"
                "- Use relationship 'Rep_Ids__r' on Doctor__c to get Sales Representative fields.\n"
                "- DO NOT query or include Manager objects or relationship fields ('Rep_Manager__c', "
                "'Rep_Manager__r') as manager data is unpopulated.\n\n"
                f"User Question: {user_message}"
            )

        if ctx.id == "mysql_gpo":
            return (
                f"{GPO_SYSTEM_PROMPT}\n\n"
                f"{self._get_gpo_refinement_instructions()}\n\n"
                f"{ctx.semantic_context(user_message)}\n\n"
                f"{self._row_counts_block(ctx)}"
                f"{history_context}"
                f"CRITICAL REMINDER: You are operating on the GPO validation database "
                f"('{ctx.adapter.database}'). Use the 'gpo' global object. Do NOT reference 'db' or "
                f"'sf', and do NOT mention Salesforce, SOQL, or any commercial/pharma tables such as "
                f"Leakage_Activity or fatigue_score — they do not exist here.\n\n"
                f"User Question: {user_message}"
            )

        # mysql_primary (and any future MySQL source using the DB 1 convention)
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"{self._get_refinement_instructions()}\n\n"
            f"{ctx.semantic_context(user_message)}\n\n"
            f"{self._row_counts_block(ctx)}"
            f"{history_context}"
            f"CRITICAL REMINDER: You are currently operating in the MySQL database environment. "
            f"You MUST generate Python code using `db.execute_sql()` to retrieve data from MySQL "
            f"tables like `Tablet_Extract_History` or `medicine_extraction_log`. Do NOT mention "
            f"Salesforce or SOQL.\n\n"
            f"User Question: {user_message}"
        )

    async def _ask_model(self, prompt: str, max_tokens: int = 4096) -> str:
        """Single entry point to the configured provider, returning raw text."""
        if self.provider == "groq":
            return await self._call_groq_api(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        return await self._call_claude_api(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )

    @staticmethod
    def _unpack_result(result_data: Any, code: str) -> Tuple[Any, Any]:
        """
        Split an executed result into (query_to_display, rows).

        Handles both the MySQL convention ('sql') and the Salesforce one
        ('soql' / 'sosl'), which is why the two pipelines could be merged.
        """
        if isinstance(result_data, dict):
            query = (
                result_data.get("sql")
                or result_data.get("soql")
                or result_data.get("sosl")
                or result_data.get("query")
                or code
            )
            if "records" in result_data:
                return query, result_data["records"]
            if "data" in result_data:
                return query, result_data["data"]
            return query, result_data
        return code, result_data

    async def _run_source_pipeline(self, ctx, user_message: str, prompt: str) -> Dict[str, Any]:
        """
        Generate code for one source, execute it in that source's sandbox, and
        format the response.

        Replaces the four near-identical per-source/per-provider methods this
        file used to carry. The retry-on-execution-error loop previously existed
        only on the Salesforce path; every source now benefits from it.
        """
        label = ctx.short_label
        try:
            logger.info(f"Calling {self.provider} for code generation (source={ctx.id})...")
            response_text = await self._ask_model(prompt)
            logger.info(f"Raw model output (source={ctx.id}): {response_text}")
            parsed = self._extract_json(response_text)

            code = parsed.get("code")
            answer = parsed.get("answer")

            if not (code and str(code).strip()):
                return {
                    "answer": answer or "I couldn't process that query.",
                    "sql": None, "data": None, "error": None,
                }

            execution = ctx.executor.execute(code)

            # Self-correction retry: generated code sometimes has quoting or
            # syntax problems (e.g. unescaped quotes inside a query literal).
            if execution["error"]:
                logger.warning(
                    f"Code execution error on attempt 1 (source={ctx.id}): "
                    f"{execution['error']}. Retrying with error feedback..."
                )
                retry_prompt = (
                    f"{prompt}\n\n"
                    f"Your previous Python code failed with error:\n{execution['error']}\n"
                    f"Previous code was:\n```python\n{code}\n```\n"
                    f"Please correct the Python code or query to fix this error and return valid JSON."
                )
                try:
                    parsed_retry = self._extract_json(await self._ask_model(retry_prompt))
                    if parsed_retry.get("code"):
                        code = parsed_retry["code"]
                        execution = ctx.executor.execute(code)
                except Exception as e:
                    logger.warning(f"Retry call failed (source={ctx.id}): {e}")

            if execution["error"]:
                return {
                    "answer": (
                        f"I attempted to query {label} for your request, but encountered an "
                        f"execution issue.\n\n**Detail:** `{execution['error']}`\n\n"
                        f"Please try rephrasing your request or asking for specific fields."
                    ),
                    "sql": code, "data": None, "error": execution["error"],
                }

            result_data = execution["result"]
            logger.info(f"Sandbox execution results (source={ctx.id}): {result_data}")

            sql_to_return, data_to_return = self._unpack_result(result_data, code)
            # The adapter's row cap, so the summary can distinguish "this is the
            # whole answer" from "this is the first page of a larger set".
            row_cap = getattr(getattr(ctx.adapter, "raw_service", None), "row_limit", None)
            return {
                "answer": self._generate_data_summary(user_message, result_data, row_cap=row_cap),
                "sql": sql_to_return,
                "data": data_to_return,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Error in pipeline for source '{ctx.id}'")
            return {
                "answer": (
                    f"I ran into an error processing your {label} request: {str(e)}. "
                    f"Please check your query or try rephrasing."
                ),
                "sql": None, "data": None, "error": str(e),
            }

    async def classify_source(self, prompt: str, purpose: str = "") -> str:
        """
        Small structured call used only by the router's Stage-2 tie-break.

        Deliberately capped low: it returns a one-line JSON verdict, never SQL.
        """
        return await self._ask_model(prompt, max_tokens=300)

    @staticmethod
    def _build_history_context(history: Optional[list]) -> str:
        if not history:
            return ""
        formatted_history = []
        for h in history[-4:]:
            if isinstance(h, dict):
                sender_val = h.get("sender") or h.get("role") or "user"
                text_val = h.get("text") or h.get("content") or ""
                sql_val = h.get("sql")
            else:
                sender_val = getattr(h, "sender", None) or getattr(h, "role", "user")
                text_val = getattr(h, "text", None) or getattr(h, "content", "")
                sql_val = getattr(h, "sql", None)

            sender_name = "User" if sender_val == "user" else "Assistant"
            formatted_history.append(f"{sender_name}: {text_val}")
            if sql_val:
                formatted_history.append(f"  (SQL executed: {sql_val})")
        return "CONVERSATION HISTORY:\n" + "\n".join(formatted_history) + "\n\n"

    @staticmethod
    def _resolve_source_ref(value: Any) -> Optional[str]:
        """
        Map whatever a stored message calls its source onto a source id.

        Transcripts carry a display label rather than an id — historically
        "MySQL" or "Salesforce", now the short label — and older rows predate
        the id entirely. Accepting id, badge and either label keeps sticky
        follow-ups working across all of them without a schema migration.
        """
        if not value:
            return None
        needle = str(value).strip().lower()
        if needle in registry.ids():
            return needle

        for ctx in registry.all():
            if needle in {
                ctx.id.lower(),
                ctx.badge.lower(),
                ctx.short_label.lower(),
                ctx.label.lower(),
            }:
                return ctx.id

        # Display names used by earlier builds. Transcripts store the label that
        # was current when they were written, so every retired name has to keep
        # resolving or sticky follow-ups break on reopened sessions:
        #   "GPO DB"       -> renamed to "Memcot"
        #   "Commercial DB" -> shortened to "Commercial"
        legacy = {
            "mysql": "mysql_primary",
            "mysql database": "mysql_primary",
            "commercial db": "mysql_primary",
            "salesforce crm": "salesforce",
            "gpo": "mysql_gpo",
            "gpo db": "mysql_gpo",
            "mysql database (gpo validation)": "mysql_gpo",
        }
        mapped = legacy.get(needle)
        return mapped if mapped and registry.get(mapped) else None

    @classmethod
    def _last_assistant_source(cls, history: Optional[list]) -> Optional[str]:
        """The source of the most recent assistant turn, for sticky follow-ups."""
        if not history:
            return None
        for h in reversed(history):
            get = h.get if isinstance(h, dict) else (lambda k, d=None: getattr(h, k, d))
            if (get("sender") or get("role")) == "user":
                continue
            for key in ("source_id", "source"):
                resolved = cls._resolve_source_ref(get(key))
                if resolved:
                    return resolved
        return None

    def _clarification_response(self, decision) -> Dict[str, Any]:
        """
        Response used when the router abstains.

        No data source is queried. The candidate list drives clickable chips in
        the UI, each of which re-sends the same question with an explicit source.
        """
        lines = [
            "I can answer this from more than one connected data source, and I don't want to "
            "give you numbers from the wrong one.",
            "",
            "**Which source did you mean?**",
            "",
        ]
        for c in decision.candidates:
            lines.append(f"- **{c['label']}** — {c['why']}")
        lines.append("")
        lines.append(
            "Pick one above, or rephrase with the source in the question "
            "(for example \"in GPO, ...\" or \"from Salesforce, ...\")."
        )
        return {
            "answer": "\n".join(lines),
            "sql": None,
            "data": None,
            "error": None,
            "source": None,
            "source_id": None,
            "needs_clarification": True,
            "candidates": decision.candidates,
            "routing": decision.to_public(),
        }

    async def process_chat(
        self,
        user_message: str,
        history: Optional[list] = None,
        requested_source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Route the question to a data source, then run that source's pipeline.

        `requested_source` is the UI's explicit selection ("auto" or None means
        let the router decide).
        """
        history_context = self._build_history_context(history)
        previous_source = self._last_assistant_source(history)

        decision = await self.router.route(
            user_message,
            requested_source=requested_source,
            previous_source_id=previous_source,
        )

        if decision.needs_clarification:
            logger.info(
                f"Router abstained for {user_message!r} "
                f"(candidates={[c['id'] for c in decision.candidates]})"
            )
            return self._clarification_response(decision)

        ctx = registry.require(decision.source_id)
        logger.info(
            f"Routed to '{ctx.id}' via {decision.stage} "
            f"(confidence={decision.confidence:.2f}): {decision.reason}"
        )

        prompt = self._build_source_prompt(ctx, user_message, history_context)
        result = await self._run_source_pipeline(ctx, user_message, prompt)

        # `source` stays the human-readable label the UI already renders; the
        # machine-readable id travels alongside it.
        result["source"] = ctx.short_label
        result["source_id"] = ctx.id
        result["source_badge"] = ctx.badge
        result["routing"] = decision.to_public()
        result["needs_clarification"] = False
        return result

    def _get_refinement_instructions(self) -> str:
        return (
            "STRICT TABLE & COLUMN SELECTION MANDATE:\n"
            "You MUST strictly follow the BUSINESS TO DATABASE MAPPING RULES listed above.\n\n"
            "TABLE SELECTION QUICK REFERENCE & EXACT COLUMN SCHEMAS:\n"
            "  1. `Leakage_Activity` (60 rows): HCP_Name, BrandName, Pharmacy_ID, zip_code, Prescriber_NPI, State, Pharmacy_Rejections, Total_Brand_Rejections, Leakage_Percentage, productid. (Use for ALL claims, rejection claims, pharmacy rejections, brand rejections, and leakage queries).\n"
            "  2. `leakage_history` (13 rows): id, previous_value, new_value, updated_by, updated_at.\n"
            "  3. `copay_Claims_Transactions` (713 rows): DO NOT use for claims or rejection queries. Use Leakage_Activity instead.\n"
            "  4. `fatigue_score` (49 rows): Fatigue_ID, HCP_Name, Fatigue, Product, Campaign_Name. DO NOT hardcode numbers like 60 or 54. Calculate percentage dynamically: `CONCAT(ROUND((Fatigue / (SELECT MAX(Fatigue) FROM fatigue_score)) * 100, 1), '%') as fatigue_percentage` and filter `WHERE (Fatigue / (SELECT MAX(Fatigue) FROM fatigue_score)) * 100 > 90`. (NO JOINs needed).\n"
            "  5. `Compliance_Table` (111 rows): id, Patient_Token, Payer_id, Payer_Type ('Medicaid','Medicare'), Created_At.\n"
            "  6. `hcp_engagement_logs` (42 rows): Log_ID, HCP_ID (FK: Prescriber_NPI), Engagement_Date, Channel ('Email','Webinar'), Email_Sent, Email_Opened, Email_Clicked, Webinar_Minutes, Campaign_ID.\n"
            "  7. `campaign_master` (100 rows): campaign_id, campaign_name, campaign_type, campaign_category, channel ('Email','Webinar',etc.), product_id, brand_name, target_audience, target_specialty, target_segment, budget_amount, expected_reach, status.\n"
            "  8. `hcp_master` (103 rows): id, Prescriber_NPI, hcp_firstName, hcp_lastName, specialty, practice_state, practice_zip, phone, secure_fax. (Full HCP Name = CONCAT(hcp_firstName, ' ', hcp_lastName))\n"
            "  9. `Reject_Code_Master` (200 rows): reject_code, reject_description, severity.\n"
            "  10. `Payer_Master` (200 rows): payer_id, payer_name, payer_type ('Commercial','Medicare','Medicaid'), region.\n\n"
            "CRITICAL RULES:\n"
            "  - TABLE WHITELIST: Leakage_Activity, copay_Claims_Transactions, leakage_history, Compliance_Table, hcp_engagement_logs, fatigue_score, Product_Master, hcp_master, Zip_Geography_Master, Payer_Master, campaign_master, Reject_Code_Master, territory_master, Reverse_Claims, Tablet_Extract_History, Transcript_Extraction_History, hcp_master_details, hcp_master_workdetails_history, rep_details, rep_master.\n"
            "  - For ALL medicine, drug, and tablet extraction prompts (UC4), query `Tablet_Extract_History` or `Transcript_Extraction_History` (JOIN `hcp_master_details` ON `Prescriber_NPI` if physician name is requested).\n"
            "  - For ALL Salesforce sync audit, status, and CRM push prompts (UC5), query `hcp_master_details` (sf_id, status, updated_at) or `Tablet_Extract_History` (sf_id, status, message).\n"
            "  - DO NOT USE copay_Claims_Transactions or Reverse_Claims for any claim or rejection queries. ALWAYS use Leakage_Activity (Pharmacy_Rejections, Total_Brand_Rejections) for all claims and rejection prompts.\n"
            "  - NEVER invent column names.\n"
            "  - For cross-table keyword search (e.g. 'Search for Endocrinology in the database', 'Look up Nancy everywhere', 'Find any record containing TX across all tables'), call Python code: `data = json.loads(db.search_records('search_term'))` and store `result = {'sql': 'CROSS_TABLE_SEARCH: search_term', 'records': data.get('records', [])}`.\n"
            "  - When user asks for 'today\'s' records or data for today, ALWAYS filter strictly using `CURDATE()` on the relevant date column: `WHERE DATE(Processed_TimeStamp) = CURDATE()`.\n\n"
            "VERIFIED JOIN PATHS:\n"
            "  - copay_Claims_Transactions.Prescriber_NPI = hcp_master.Prescriber_NPI\n"
            "  - copay_Claims_Transactions.payer_id = Payer_Master.payer_id\n"
            "  - copay_Claims_Transactions.reject_code = Reject_Code_Master.reject_code\n"
            "  - hcp_engagement_logs.Campaign_ID = campaign_master.campaign_id\n"
            "  - hcp_engagement_logs.HCP_ID = hcp_master.Prescriber_NPI\n"
            "  - Compliance_Table.Payer_id = Payer_Master.payer_id\n"
            "  - Leakage_Activity.productid = Product_Master.product_id\n\n"
            "You write Python code to fetch or analyze data from a MySQL database via the whitelisted 'db' global object.\n"
            "The available 'db' methods are:\n"
            "  - db.execute_sql(sql_query: str) -> str: Runs read-only SQL SELECT. Returns a JSON string with 'records' and 'totalSize'. Must parse with json.loads().\n"
            "  - db.describe_table(table_name: str) -> str: Returns schema details for a specific table.\n"
            "  - db.list_tables() -> str: Returns list of tables in the database.\n"
            "  - db.search_records(search_term: str) -> str: Runs cross-table text search. Returns JSON. Must parse with json.loads().\n\n"
            "Rules for writing code:\n"
            "  1. You MUST execute queries using db.execute_sql() or db.search_records(). DO NOT hardcode empty lists or mock data.\n"
            "  2. Parse the returned JSON string using json.loads() to access records.\n"
            "  3. Store final output in variable 'result' = {'sql': '<query_string>', 'records': <records_list>}.\n"
            "  4. Global scope has 'db', 'json', 'math', 'datetime', 'date', 'timedelta', 're', 'collections' pre-loaded.\n"
            "  5. Write valid multi-line Python code with proper line breaks.\n"
            "  6. When a PRE-DEFINED SQL MEASURE matches the user's question, adapt it as your template.\n\n"
            "Example 1 - UC3 Work details (uses hcp_master_details):\n"
            "sql = \"SELECT hcp_firstName, hcp_lastName, Prescriber_NPI, rep_id, status, work_detail, updated_at FROM hcp_master_details ORDER BY updated_at DESC\"\n"
            "data = json.loads(db.execute_sql(sql))\n"
            "result = {\"sql\": sql, \"records\": data.get(\"records\", [])}\n\n"
            "Example 2 - UC3 Audit History (uses hcp_master_workdetails_history):\n"
            "sql = \"SELECT history_id, hcp_id, rep_id, rep_firstName, rep_lastName, work_detail, updated_datetime FROM hcp_master_workdetails_history ORDER BY updated_datetime DESC\"\n"
            "data = json.loads(db.execute_sql(sql))\n"
            "result = {\"sql\": sql, \"records\": data.get(\"records\", [])}\n\n"
            "Example 3 - Cross-table text search:\n"
            "data = json.loads(db.search_records('Nancy'))\n"
            "result = {\"sql\": \"CROSS_TABLE_SEARCH: Nancy\", \"records\": data.get(\"records\", [])}\n\n"
            "Format your output ONLY as a JSON object with these keys:\n"
            "{\n"
            "  \"reasoning\": \"your reasoning/steps\",\n"
            "  \"code\": \"python code string to run\",\n"
            "  \"answer\": \"natural language answer if no database query is required\"\n"
            "}\n"
            "Output ONLY the JSON object. Do not wrap in markdown tags like ```json."
        )

    async def _call_groq_api(self, messages: list, response_format: Optional[dict] = None, temperature: float = 0.1) -> str:
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        models_to_try = [settings.GROQ_MODEL]
        for fb in ["openai/gpt-oss-120b", "qwen/qwen3.6-27b", "openai/gpt-oss-20b"]:
            if fb not in models_to_try:
                models_to_try.append(fb)
                
        last_error = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            for model_name in models_to_try:
                for fmt in [response_format, None]:
                    payload = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "reasoning_format": "hidden"
                    }
                    if fmt:
                        payload["response_format"] = fmt

                    logger.info(f"Calling Groq API ({model_name}, json_mode={bool(fmt)})...")
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    if resp.status_code == 200:
                        resp_json = resp.json()
                        content = resp_json["choices"][0]["message"]["content"].strip()
                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                        return content
                    elif resp.status_code == 429:
                        logger.warning(f"Groq API 429 Rate Limit on {model_name} (json_mode={bool(fmt)}). Waiting 2s before retry/fallback...")
                        last_error = f"Groq API Error {resp.status_code}: {resp.text}"
                        await asyncio.sleep(2.0)
                        continue
                    elif resp.status_code == 400:
                        logger.warning(f"Groq API 400 on {model_name} (json_mode={bool(fmt)}). Retrying fallback...")
                        last_error = f"Groq API Error {resp.status_code}: {resp.text}"
                        continue
                    else:
                        raise RuntimeError(f"Groq API Error {resp.status_code}: {resp.text}")
                    
        raise RuntimeError(last_error or "Groq API request failed across all models.")

    async def _call_claude_api(self, messages: list, max_tokens: int = 4096) -> str:
        """Call the Claude Messages API (direct Anthropic or AWS Bedrock) and return the response text."""
        logger.info(f"Calling Claude API ({self.claude_model}, bedrock={self.is_bedrock})...")
        response = await self.claude_client.messages.create(
            model=self.claude_model,
            max_tokens=max_tokens,
            messages=messages,
        )
        for block in response.content:
            if block.type == "text":
                return block.text.strip()
        return ""

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Robust JSON payload extractor that handles markdown code blocks and multiline strings."""
        if not text:
            return {}
        raw = text.strip()
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0].strip()
            
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end+1]
            
        try:
            return json.loads(raw, strict=False)
        except Exception:
            import re
            def fix_newlines(match):
                return match.group(0).replace("\n", "\\n").replace("\r", "")
            cleaned = re.sub(r'"([^"\\]*(\\.[^"\\]*)*)"', fix_newlines, raw, flags=re.DOTALL)
            try:
                return json.loads(cleaned, strict=False)
            except Exception as e:
                logger.error(f"JSON parsing failed: {e}. Raw text snippet: {text[:200]}")
                return {}


# Single global instance
llm_service = LLMService()
