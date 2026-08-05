import json
import logging
import httpx
from typing import Dict, Any, Tuple, Optional
import ollama

from app.config import settings
from app.services.mysql_service import MySQLService
from app.services.code_executor import CodeExecutor
from app.semantic.loader import SemanticModelLoader

logger = logging.getLogger("llm-service")

# Singletons for direct DCE MySQL access & Semantic Layer
db_service = MySQLService(
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    user=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DATABASE
)
code_executor = CodeExecutor(db_service)
semantic_loader = SemanticModelLoader()

SYSTEM_PROMPT = """
You generate Python code to fetch and analyze data from a MySQL database using the Semantic YAML governance rules.
The database powers a Pharma Commercial Command Centre with UC1 (Leakage Signals), UC2 (Journey Orchestration), and UC3 (Voice Work Detail Manager & HCP Interaction Recording).

UI DASHBOARD displays data from PRIMARY TABLES:
  1. Leakage_Activity (60 rows) — Main leakage records table
  2. fatigue_score (49 rows) — Fatigue scores table (fatigue range: 10-60)
  3. leakage_history (13 rows) — Threshold update log
  4. Compliance_Table (111 rows) — Govt plans bypassed KPI
  5. hcp_master_details — Main UC3 table (Prescriber_NPI, hcp_firstName, hcp_lastName, rep_id, status, work_detail, sf_id)
  6. hcp_master_workdetails_history — UC3 audit trail history table (history_id, hcp_id, rep_id, rep_firstName, rep_lastName, work_detail, updated_datetime)
  7. rep_details — Sales representative directory (rep_id, rep_firstName, rep_lastName, email, phone, manager_id)
  8. rep_master — Manager directory (rep_id, rep_firstName, rep_lastName, email, phone)

PRIMARY TRANSACTION TABLE for claims analysis:
  9. copay_Claims_Transactions (713 rows) — Use for ALL copay/claims/reject queries
     Response_Status: V=Verified(249), R=Rejected(237), A=Approved(227)
     claim_status: PAID, REJECTED

WARNING: Reverse_Claims has only 1 test row. DO NOT use it for claims analysis.

RULES:
- ALWAYS refer to the SEMANTIC YAML LAYER GOVERNANCE block below for exact table names, column names, join conditions, and pre-defined SQL measures.
- NEVER invent table or column names. Use ONLY columns listed in the governance block.
- Use standard MySQL SQL syntax.
- Use ONLY the VERIFIED JOIN PATHS defined in the governance block.
- Use table aliases: la = Leakage_Activity, cct = copay_Claims_Transactions, pm = Product_Master, hm = hcp_master, zg = Zip_Geography_Master, ct = Compliance_Table, pay = Payer_Master, hel = hcp_engagement_logs, cm = campaign_master, fs = fatigue_score, lh = leakage_history, rcm = Reject_Code_Master, hmd = hcp_master_details, hmwh = hcp_master_workdetails_history, rd = rep_details, rm = rep_master.
- When user explicitly asks for 'today\'s' records or data for today, filter using `CURDATE()` on the date column: e.g. `WHERE DATE(Processed_TimeStamp) = CURDATE()`.
- When PRE-DEFINED SQL MEASURES match the user's question, use them as templates.
"""


class LLMService:
    def __init__(self):
        if settings.GROQ_API_KEY:
            self.provider = "groq"
            logger.info(f"Initializing Groq client with model {settings.GROQ_MODEL} for DCE...")
        elif settings.GEMINI_API_KEY:
            self.provider = "gemini"
            logger.info("Initializing Google Gemini client for DCE...")
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            model_name = 'gemini-1.5-flash'  # fallback default
            try:
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                logger.info(f"Found available Gemini models: {available_models}")
                
                for candidate in ['models/gemini-2.0-flash', 'models/gemini-2.5-flash', 'models/gemini-1.5-flash']:
                    if candidate in available_models:
                        model_name = candidate
                        break
                else:
                    flash_candidates = [m for m in available_models if 'flash' in m.lower()]
                    if flash_candidates:
                        model_name = flash_candidates[0]
                    elif available_models:
                        model_name = available_models[0]
                
                logger.info(f"Selected model: {model_name}")
            except Exception as e:
                logger.warning(f"Could not list available models, defaulting to {model_name}. Error: {e}")
                
            self.gemini_model = genai.GenerativeModel(model_name)
        else:
            self.provider = "ollama"
            logger.info(f"Using local Ollama client running at {settings.OLLAMA_HOST} with model {settings.OLLAMA_MODEL} for DCE")

    async def get_schema_context(self) -> str:
        """Fetch MySQL schema overview directly."""
        try:
            return db_service.get_schema_overview()
        except Exception as e:
            logger.error(f"Error fetching schema resource: {e}")
            try:
                return db_service.list_tables()
            except Exception as inner_e:
                return f"Could not establish MySQL connection details. Error: {inner_e}"

    async def process_chat(self, user_message: str, history: Optional[list] = None) -> Dict[str, Any]:
        """
        Orchestrate the chat session. Uses LLM to generate Python code,
        executes it in the CodeExecutor sandbox, and returns formatted responses.
        """
        history_context = ""
        if history:
            formatted_history = []
            for h in history[-3:]:
                sender_name = "User" if h.sender == "user" else "Assistant"
                formatted_history.append(f"{sender_name}: {h.text}")
                if h.sql:
                    formatted_history.append(f"  (SQL executed: {h.sql})")
            history_context = "CONVERSATION HISTORY:\n" + "\n".join(formatted_history) + "\n\n"
            
        context_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"{self._get_refinement_instructions()}\n\n"
            f"{history_context}"
            f"User Question: {user_message}"
        )

        if self.provider == "groq":
            return await self._process_groq(user_message, context_prompt)
        elif self.provider == "gemini":
            return await self._process_gemini(user_message, context_prompt)
        else:
            return await self._process_ollama(user_message, context_prompt)

    def _get_refinement_instructions(self) -> str:
        return (
            "STRICT TABLE & COLUMN SELECTION MANDATE:\n"
            "You MUST strictly follow the BUSINESS TO DATABASE MAPPING RULES listed above.\n\n"
            "TABLE SELECTION QUICK REFERENCE & EXACT COLUMN SCHEMAS:\n"
            "  1. `Leakage_Activity` (60 rows): HCP_Name, BrandName, Pharmacy_ID, zip_code, Prescriber_NPI, State, Pharmacy_Rejections, Total_Brand_Rejections, Leakage_Percentage, productid. (PRE-RESOLVED — no JOINs needed for basic leakage queries).\n"
            "  2. `leakage_history` (13 rows): id, previous_value, new_value, updated_by, updated_at.\n"
            "  3. `copay_Claims_Transactions` (713 rows): Transaction_ID, transaction_datetime, Patient_Token, Prescriber_NPI, Pharmacy_ID, Response_Status ('V','R','A'), zip_code, payer_id, product_id, claim_status ('PAID','REJECTED'), reject_code, Reject_Message, claim_amount, BrandName, HCP_First_Name, HCP_Last_Name, HCP_Specialty, HCP_Practice_State. (NEVER use Reverse_Claims!).\n"
            "  4. `fatigue_score` (49 rows): Fatigue_ID, HCP_Name, Fatigue (range 10-60), Product, Campaign_Name. (NO JOINs needed).\n"
            "  5. `Compliance_Table` (111 rows): id, Patient_Token, Payer_id, Payer_Type ('Medicaid','Medicare'), Created_At.\n"
            "  6. `hcp_engagement_logs` (42 rows): Log_ID, HCP_ID (FK: Prescriber_NPI), Engagement_Date, Channel ('Email','Webinar'), Email_Sent, Email_Opened, Email_Clicked, Webinar_Minutes, Campaign_ID.\n"
            "  7. `campaign_master` (100 rows): campaign_id, campaign_name, campaign_type, campaign_category, channel ('Email','Webinar',etc.), product_id, brand_name, target_audience, target_specialty, target_segment, budget_amount, expected_reach, status.\n"
            "  8. `hcp_master` (103 rows): id, Prescriber_NPI, hcp_firstName, hcp_lastName, specialty, practice_state, practice_zip, phone, secure_fax. (Full HCP Name = CONCAT(hcp_firstName, ' ', hcp_lastName)).\n"
            "  9. `hcp_master_details` (UC3 Primary): hcp_detail_id, hcp_id, Prescriber_NPI, hcp_firstName, hcp_lastName, rep_id, status ('Completed','In-Progress'), work_detail, sf_id, created_at, updated_at.\n"
            "  10. `hcp_master_workdetails_history` (UC3 Audit): history_id, hcp_id, rep_id, rep_firstName, rep_lastName, work_detail, updated_datetime.\n"
            "  11. `rep_details` (UC3 Reps): rep_id, rep_firstName, rep_lastName, email, phone, manager_id.\n"
            "  12. `rep_master` (UC3 Managers): rep_id, rep_firstName, rep_lastName, email, phone.\n"
            "  13. `Reject_Code_Master` (200 rows): reject_code, reject_description, severity.\n"
            "  14. `Payer_Master` (200 rows): payer_id, payer_name, payer_type ('Commercial','Medicare','Medicaid'), region.\n\n"
            "CRITICAL RULES:\n"
            "  - TABLE WHITELIST: Leakage_Activity, copay_Claims_Transactions, leakage_history, Compliance_Table, hcp_engagement_logs, fatigue_score, Product_Master, hcp_master, Zip_Geography_Master, Payer_Master, campaign_master, Reject_Code_Master, territory_master, Reverse_Claims, hcp_master_details, hcp_master_workdetails_history, rep_details, rep_master.\n"
            "  - NEVER USE Reverse_Claims for claims analysis. It has only 1 test row and its NPI/NDC formats do not match other tables.\n"
            "  - NEVER invent column names.\n"
            "  - For cross-table keyword search (e.g. 'Search for Endocrinology in the database', 'Look up Nancy everywhere', 'Find any record containing TX across all tables'), call Python code: `data = json.loads(db.search_records('search_term'))` and store `result = {'sql': 'CROSS_TABLE_SEARCH: search_term', 'records': data.get('records', [])}`.\n"
            "  - When user asks for 'today\'s' records or data for today, ALWAYS filter strictly using `CURDATE()` on the relevant date column: `WHERE DATE(Processed_TimeStamp) = CURDATE()`.\n\n"
            "VERIFIED JOIN PATHS:\n"
            "  - copay_Claims_Transactions.Prescriber_NPI = hcp_master.Prescriber_NPI\n"
            "  - hcp_master_details.Prescriber_NPI = hcp_master.Prescriber_NPI\n"
            "  - hcp_master_details.hcp_id = hcp_master_workdetails_history.hcp_id\n"
            "  - hcp_master_details.rep_id = rep_details.rep_id\n"
            "  - rep_details.manager_id = rep_master.rep_id\n"
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
        for fb in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            if fb not in models_to_try:
                models_to_try.append(fb)
                
        last_error = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            for model_name in models_to_try:
                for fmt in [response_format, None]:
                    payload = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature
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
                        return resp_json["choices"][0]["message"]["content"].strip()
                    elif resp.status_code in (400, 429):
                        logger.warning(f"Groq API {resp.status_code} on {model_name} (json_mode={bool(fmt)}). Retrying fallback...")
                        last_error = f"Groq API Error {resp.status_code}: {resp.text}"
                        continue
                    else:
                        raise RuntimeError(f"Groq API Error {resp.status_code}: {resp.text}")
                    
        raise RuntimeError(last_error or "Groq API request failed across all models.")

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

    async def _process_groq(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process requests using Groq API (with automatic 429 rate-limit fallback) and dynamic code execution."""
        try:
            logger.info("Calling Groq API for code generation...")
            response_text = await self._call_groq_api(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            logger.info(f"Groq raw output: {response_text}")
            parsed = self._extract_json(response_text)

            code = parsed.get("code")
            answer = parsed.get("answer")

            if code and code.strip():
                # Perform code safety validation and execution
                execution = code_executor.execute(code)
                if execution["error"]:
                    return {
                        "answer": f"Code execution failed.",
                        "sql": code,
                        "data": None,
                        "error": execution["error"]
                    }
                
                result_data = execution["result"]
                logger.info(f"Sandbox execution results: {result_data}")

                # Summarize results with LLM
                final_prompt = (
                    f"You are a MySQL data expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this Python code:\n{code}\n"
                    f"Execution result: {json.dumps(result_data, default=str)}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct."
                )
                
                try:
                    final_answer = await self._call_groq_api(
                        messages=[{"role": "user", "content": final_prompt}],
                        temperature=0.2
                    )
                except Exception as e:
                    logger.warning(f"Summarization call failed, defaulting: {e}")
                    final_answer = "Query executed successfully."

                sql_to_return = code
                data_to_return = None

                if isinstance(result_data, dict):
                    sql_to_return = result_data.get("sql") or result_data.get("query") or code
                    data_to_return = result_data.get("records") or result_data.get("data")
                    if data_to_return is None:
                        data_to_return = result_data
                else:
                    data_to_return = result_data

                return {
                    "answer": final_answer,
                    "sql": sql_to_return,
                    "data": data_to_return,
                    "error": None
                }
            else:
                return {
                    "answer": answer or "I couldn't process that query.",
                    "sql": None,
                    "data": None,
                    "error": None
                }
                
        except Exception as e:
            logger.exception("Error in Groq processing")
            return {
                "answer": f"Groq Error: {str(e)}",
                "sql": None,
                "data": None,
                "error": str(e)
            }


    async def _process_gemini(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process requests using Gemini API and dynamic code execution."""
        try:
            logger.info("Calling Gemini API for code generation...")
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            response_text = response.text.strip()
            
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            logger.info(f"Gemini raw output: {response_text}")
            parsed = json.loads(response_text)

            code = parsed.get("code")
            answer = parsed.get("answer")

            if code and code.strip():
                # Perform code safety validation and execution
                execution = code_executor.execute(code)
                if execution["error"]:
                    return {
                        "answer": f"Code execution failed.",
                        "sql": code,
                        "data": None,
                        "error": execution["error"]
                    }
                
                result_data = execution["result"]
                logger.info(f"Sandbox execution results: {result_data}")

                # Summarize results with LLM
                final_prompt = (
                    f"You are a MySQL data expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this Python code:\n{code}\n"
                    f"Execution result: {json.dumps(result_data, default=str)}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct."
                )
                final_response = self.gemini_model.generate_content(final_prompt)

                # Process result formatting for frontend
                sql_to_return = code
                data_to_return = None

                if isinstance(result_data, dict):
                    # Extract raw SQL query if stored in result, otherwise return the python script code
                    sql_to_return = result_data.get("sql") or result_data.get("query") or code
                    data_to_return = result_data.get("records") or result_data.get("data")
                    if data_to_return is None:
                        # Fallback to the whole result if records/data not explicitly defined
                        data_to_return = result_data
                else:
                    data_to_return = result_data

                return {
                    "answer": final_response.text,
                    "sql": sql_to_return,
                    "data": data_to_return,
                    "error": None
                }
            else:
                return {
                    "answer": answer or "I couldn't process that query.",
                    "sql": None,
                    "data": None,
                    "error": None
                }
                
        except Exception as e:
            logger.exception("Error in Gemini processing")
            return {
                "answer": "An error occurred while generating the MySQL response.",
                "sql": None,
                "data": None,
                "error": str(e)
            }

    async def _process_ollama(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process requests using Local Ollama and dynamic code execution."""
        try:
            async with httpx.AsyncClient() as client:
                try:
                    await client.get(settings.OLLAMA_HOST, timeout=2.0)
                except Exception:
                    raise RuntimeError(f"Ollama server is not running or unreachable at {settings.OLLAMA_HOST}. Make sure you ran 'ollama serve'.")

            logger.info("Calling local Ollama model for code generation...")
            response = ollama.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0.1}
            )
            
            response_text = response['message']['content'].strip()
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            logger.info(f"Ollama raw output: {response_text}")
            parsed = json.loads(response_text)

            code = parsed.get("code")
            answer = parsed.get("answer")

            if code and code.strip():
                execution = code_executor.execute(code)
                if execution["error"]:
                    return {
                        "answer": f"Code execution failed.",
                        "sql": code,
                        "data": None,
                        "error": execution["error"]
                    }
                
                result_data = execution["result"]
                logger.info(f"Sandbox execution results: {result_data}")

                final_prompt = (
                    f"You are a MySQL data expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this Python code:\n{code}\n"
                    f"Execution result: {json.dumps(result_data, default=str)}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct."
                )
                
                final_resp = ollama.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": final_prompt}]
                )
                
                sql_to_return = code
                data_to_return = None

                if isinstance(result_data, dict):
                    sql_to_return = result_data.get("sql") or result_data.get("query") or code
                    data_to_return = result_data.get("records") or result_data.get("data")
                    if data_to_return is None:
                        data_to_return = result_data
                else:
                    data_to_return = result_data

                return {
                    "answer": final_resp['message']['content'],
                    "sql": sql_to_return,
                    "data": data_to_return,
                    "error": None
                }
            else:
                return {
                    "answer": answer or "I couldn't process that query.",
                    "sql": None,
                    "data": None,
                    "error": None
                }
                
        except Exception as e:
            logger.exception("Error in Ollama processing")
            return {
                "answer": f"Ollama Error: {str(e)}",
                "sql": None,
                "data": None,
                "error": str(e)
            }

# Single global instance
llm_service = LLMService()
