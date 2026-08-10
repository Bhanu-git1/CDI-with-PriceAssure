import json
import logging
import os
import httpx
from typing import Dict, Any, Tuple, Optional
import ollama

from app.config import settings
from app.services.mysql_service import MySQLService
from app.services.salesforce_service import SalesforceService
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

# Singletons for direct DCE Salesforce access (UC3)
sf_service = SalesforceService(
    username=settings.SF_USERNAME,
    password=settings.SF_PASSWORD,
    security_token=settings.SF_SECURITY_TOKEN,
    domain=settings.SF_DOMAIN,
    session_id=settings.SF_SESSION_ID,
    instance_url=settings.SF_INSTANCE_URL
)
code_executor_sf = CodeExecutor(sf_service, global_name="sf")

# Keyword router between UC1/UC2 (MySQL) and UC3 (Salesforce).
# MySQL/pharma-domain keywords take priority so existing UC1/UC2 behavior never regresses.
MYSQL_PRIORITY_KEYWORDS = (
    "leakage", "fatigue", "compliance", "campaign", "claim", "claims",
    "rejection", "rejections", "pharmacy", "engagement", "mysql",
    "prescriber", "npi",
)
SALESFORCE_KEYWORDS = (
    "salesforce", "doctor", "doctors", "sales rep", "sales reps",
    "sales representative", "sales representatives", "sales manager",
    "sales managers", "rep manager", "rep managers", "hcp status",
    "state license", "crm",
)

SYSTEM_PROMPT = """
You generate Python code to fetch and analyze data from a MySQL database using the Semantic YAML governance rules.
The database powers a Pharma Commercial Command Centre with UC1 (Leakage Signals) and UC2 (Journey Orchestration & HCP Fatigue).

UI DASHBOARD displays data from PRIMARY TABLES:
  1. Leakage_Activity (60 rows) — Main leakage records table
  2. fatigue_score (49 rows) — Fatigue scores table (fatigue range: 10-60)
  3. leakage_history (13 rows) — Threshold update log
  4. Compliance_Table (111 rows) — Govt plans bypassed KPI

PRIMARY TABLE FOR CLAIMS & REJECTIONS ANALYSIS:
  1. Leakage_Activity (60 rows) — Use for ALL claims, rejection claims, pharmacy rejections, brand rejections, and leakage queries.
     Columns: HCP_Name, BrandName, Pharmacy_ID, zip_code, Prescriber_NPI, State, Pharmacy_Rejections, Total_Brand_Rejections, Leakage_Percentage.

WARNING: DO NOT use copay_Claims_Transactions or Reverse_Claims for claims/rejections analysis. Use Leakage_Activity instead.

RULES:
- ALWAYS refer to the SEMANTIC YAML LAYER GOVERNANCE block below for exact table names, column names, join conditions, and pre-defined SQL measures.
- NEVER invent table or column names. Use ONLY columns listed in the governance block.
- For ALL claims, claim rejections, rejected claims, or rejection keywords, ALWAYS use `Leakage_Activity` (Pharmacy_Rejections, Total_Brand_Rejections). DO NOT use `copay_Claims_Transactions`.
- Use standard MySQL SQL syntax.
- Use ONLY the VERIFIED JOIN PATHS defined in governance block. Use table aliases: la = Leakage_Activity, cct = copay_Claims_Transactions, pm = Product_Master, hm = hcp_master, zg = Zip_Geography_Master, ct = Compliance_Table, pay = Payer_Master, hel = hcp_engagement_logs, cm = campaign_master, fs = fatigue_score, lh = leakage_history, rcm = Reject_Code_Master.
- When user explicitly asks for 'today\'s' records or data for today, filter using `CURDATE()` on the date column: e.g. `WHERE DATE(Processed_TimeStamp) = CURDATE()`.
- When PRE-DEFINED SQL MEASURES match the user's question, use them as templates.
"""

# UC3 (Salesforce) system prompt — reused verbatim from the standalone DCE Salesforce project.
SALESFORCE_SYSTEM_PROMPT = """
You generate Python code to fetch and analyze data from a Salesforce org for Healthcare Professionals (HCPs / Doctors), Sales Representatives, and Sales Managers.

########## OBJECT & FIELD MAPPING (SEMANTIC LAYER) ##########

1. Doctor__c (Healthcare Professionals / HCPs / Doctors):
   - Primary custom object representing Doctors and Healthcare Professionals.
   - Fields:
     * HCP_First_Name__c : First name of the HCP
     * HCP_Last_Name__c : Last name of the HCP
     * Speciality__c : Medical speciality (e.g. Cardiology, Oncology, Pediatrics, Neurology)
     * State_License__c : Medical license number
     * Practice_State__c : State code or name of practice (e.g., CA, NY, TX)
     * Phone__c : Phone number
     * Secure_Fax__c : Fax number
     * Status__c : Record status picklist (Valid values: 'In-Progress' and 'Completed'). Always query `Status__c = 'In-Progress'` for in-progress doctors, or `Status__c = 'Completed'` for completed doctors.
     * Work_Details__c : Clinic / hospital affiliation and work details
     * SF_Id__c : Internal/External Salesforce ID
     * Rep_ID__c : Representative ID assigned to this HCP
     * Rep_Ids__c : Lookup / Master-Detail reference to Rep_Details__c
     * Relationship: Rep_Ids__r (Use Rep_Ids__r.First_Name__c, Rep_Ids__r.Last_Name__c to query assigned rep details)

2. Rep_Details__c (Sales Representatives / Field Reps):
   - Primary custom object representing Sales Representatives. (Also referenced in legacy code/metadata as Rep_Detials__c or HCP_Rep_Detail__c).
   - Fields:
     * Rep_Id__c : Unique Representative ID
     * First_Name__c / Rep_firstName__c : Representative First Name
     * Last_Name__c / Rep_lastName__c : Representative Last Name
     * Email__c / Rep_Email__c : Representative Email
     * Phone_Number__c / Rep_Mobile__c : Mobile / Phone number
     * Rep_Manager__c : Lookup / Master-Detail reference to Rep_Manager__c (Relationship: Rep_Manager__r)
     * HCP_Master__c : Lookup / Master-Detail reference to Doctor__c (Relationship: HCP_Master__r)
     * Rep_Date_and_Time__c : Activity datetime timestamp
     * Manager_Name__c : Manager name
     * Status__c : Representative status (Active, Inactive)

3. Rep_Manager__c (Sales Representative Managers):
   - Primary custom object representing Sales Managers. (Also referenced in legacy code as Rep_Master__c).
   - Fields:
     * Rep_Manager_Id__c : Unique Manager ID
     * First_Name__c / Rep_Mgr_firstName__c : Manager First Name
     * Last_Name__c / Rep_Mgr_lastName__c : Manager Last Name
     * Email__c / Rep_Mgr_Email__c : Manager Email
     * Rep_Mgr_Mobile__c : Manager Mobile Phone

CRITICAL QUERYING RULES:
- Query ONLY custom objects 'Doctor__c', 'Rep_Details__c', or 'Rep_Manager__c'.
- NEVER query standard objects like 'Task', 'Account', or 'Contact' unless specifically asked.
- Always use correct relationship fields (e.g. Rep_Ids__r for Doctor__c -> Rep_Details__c, and Rep_Manager__r for Rep_Details__c -> Rep_Manager__c).
"""


class LLMService:
    def __init__(self):
        self.semantic_loader = semantic_loader
        self.sf_semantic_layer_raw = self._load_sf_semantic_layer()
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

    def _load_sf_semantic_layer(self) -> str:
        """Load the Salesforce (UC3) semantic layer YAML file if available."""
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            yaml_path = os.path.join(base_dir, "semantic", "salesforce_semantic_layer.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            logger.warning(f"Could not load salesforce_semantic_layer.yaml: {e}")
        return ""

    def _is_salesforce_query(self, message: str) -> bool:
        """
        Lightweight keyword-based router between UC1/UC2 (MySQL) and UC3 (Salesforce).
        MySQL/pharma-domain keywords are checked first so existing UC1/UC2 behavior
        never regresses; Salesforce CRM vocabulary (doctor, sales rep/manager, etc.)
        routes the request to the UC3 Salesforce pipeline instead.
        """
        text = (message or "").lower()
        if any(kw in text for kw in MYSQL_PRIORITY_KEYWORDS):
            return False
        return any(kw in text for kw in SALESFORCE_KEYWORDS)

    async def _get_salesforce_schema_context(self) -> str:
        """Fetch Salesforce schema overview directly."""
        try:
            return sf_service.get_schema_overview()
        except Exception as e:
            logger.error(f"Error fetching Salesforce schema resource: {e}")
            try:
                return sf_service.list_objects()
            except Exception as inner_e:
                return f"Could not establish Salesforce connection details. Error: {inner_e}"

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
            "  8. Preferred objects are Doctor__c, Rep_Details__c, and Rep_Manager__c.\n"
            "  9. ALWAYS include 'Status__c' in the SELECT clause when querying Doctor__c records (e.g. SELECT HCP_First_Name__c, HCP_Last_Name__c, Speciality__c, Practice_State__c, Status__c FROM Doctor__c ...).\n"
            "  10. FLEXIBLE SEARCHING: Use LIKE operators (e.g. Speciality__c LIKE '%cardiology%', HCP_First_Name__c LIKE '%John%', Practice_State__c LIKE '%TX%') for string searches to match partial or case-insensitive user inputs.\n"
            "  11. PICKLIST & STATE MAP:\n"
            "      - For Doctor__c.Status__c: Map 'in progress', 'progress', 'wip', 'ongoing' -> Status__c = 'In-Progress'. Map 'completed', 'complete', 'done', 'finished' -> Status__c = 'Completed'.\n"
            "      - For Practice_State__c: Support full state names and postal codes (e.g., 'California' -> Practice_State__c LIKE '%CA%' OR Practice_State__c LIKE '%California%').\n"
            "  12. GREETINGS & SCHEMA QUESTIONS:\n"
            "      - If the user prompt is a greeting (e.g. 'hello', 'hi', 'hey', 'help'), set code = null and provide a helpful, welcoming natural language answer in the 'answer' field explaining available data (Doctors, Sales Reps, Managers) with example prompts.\n"
            "      - If the user asks about available tables or schema ('what objects are in Salesforce?', 'describe Doctor__c object'), provide the schema info in 'answer' or run sf.describe_object('Doctor__c') / sf.list_objects().\n\n"
            "Example of querying Doctors:\n"
            "data = json.loads(sf.execute_soql(\"SELECT HCP_First_Name__c, HCP_Last_Name__c, Speciality__c, Practice_State__c, Status__c FROM Doctor__c WHERE Status__c = 'In-Progress'\"))\n"
            "result = {\"soql\": \"SELECT HCP_First_Name__c, HCP_Last_Name__c, Speciality__c, Practice_State__c, Status__c FROM Doctor__c WHERE Status__c = 'In-Progress'\", \"records\": data.get(\"records\", [])}\n\n"
            "Format your output ONLY as a valid JSON object with these keys:\n"
            "{\n"
            "  \"reasoning\": \"your reasoning/steps\",\n"
            "  \"code\": \"python code string to run or null\",\n"
            "  \"answer\": \"natural language answer if no salesforce query is required\"\n"
            "}\n"
            "Output ONLY the JSON object. Do not wrap in markdown tags like ```json."
        )

    async def _process_salesforce_chat(self, user_message: str, history_context: str) -> Dict[str, Any]:
        """UC3 pipeline: builds the Salesforce-specific prompt and dispatches to the active LLM provider."""
        schema_context = await self._get_salesforce_schema_context()
        semantic_layer_prompt = (
            f"SEMANTIC LAYER CONFIGURATION (YAML):\n{self.sf_semantic_layer_raw}\n\n"
            if self.sf_semantic_layer_raw else ""
        )

        context_prompt = (
            f"{SALESFORCE_SYSTEM_PROMPT}\n\n"
            f"{self._get_salesforce_refinement_instructions()}\n\n"
            f"{semantic_layer_prompt}"
            f"SALESFORCE SCHEMA DETAILS:\n{schema_context}\n\n"
            f"{history_context}"
            "CRITICAL REMINDER FOR THIS ORG:\n"
            "- Query custom objects 'Doctor__c', 'Rep_Details__c', or 'Rep_Manager__c'.\n"
            "- Filter HCPs / Doctors using fields like HCP_First_Name__c, HCP_Last_Name__c, Speciality__c, Practice_State__c, Status__c.\n"
            "- Use relationship 'Rep_Ids__r' on Doctor__c to get Sales Representative fields.\n"
            "- Use relationship 'Rep_Manager__r' on Rep_Details__c to get Manager fields.\n\n"
            f"User Question: {user_message}"
        )

        logger.info(f"Processing Salesforce (UC3) chat request using provider: {self.provider}")
        if self.provider == "groq":
            return await self._process_salesforce_groq(user_message, context_prompt)
        elif self.provider == "gemini":
            return await self._process_salesforce_gemini(user_message, context_prompt)
        else:
            return await self._process_salesforce_ollama(user_message, context_prompt)

    async def _process_salesforce_groq(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process Salesforce (UC3) requests using Groq API and dynamic code execution."""
        try:
            logger.info("Calling Groq API for Salesforce code generation...")
            response_text = await self._call_groq_api(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            logger.info(f"Groq raw output (Salesforce): {response_text}")
            parsed = self._extract_json(response_text)

            code = parsed.get("code")
            answer = parsed.get("answer")

            if code and code.strip():
                execution = code_executor_sf.execute(code)

                # Self-correction retry: LLM-generated code sometimes has quoting/syntax
                # issues (e.g. unescaped quotes inside SOQL string literals). Retry once
                # with the error fed back, same as the original standalone UC3 pipeline.
                if execution["error"]:
                    logger.warning(f"Salesforce code execution error on attempt 1: {execution['error']}. Retrying with error feedback...")
                    retry_prompt = (
                        f"{prompt}\n\n"
                        f"Your previous Python code failed with error:\n{execution['error']}\n"
                        f"Previous code was:\n```python\n{code}\n```\n"
                        f"Please correct the Python code or SOQL query to fix this error and return valid JSON."
                    )
                    try:
                        retry_response_text = await self._call_groq_api(
                            messages=[{"role": "user", "content": retry_prompt}],
                            response_format={"type": "json_object"},
                            temperature=0.1
                        )
                        parsed_retry = self._extract_json(retry_response_text)
                        if parsed_retry.get("code"):
                            code = parsed_retry.get("code")
                            execution = code_executor_sf.execute(code)
                    except Exception as e:
                        logger.warning(f"Salesforce retry call failed: {e}")

                if execution["error"]:
                    return {
                        "answer": f"I attempted to query Salesforce for your request, but encountered an execution issue.\n\n"
                                  f"**Detail:** `{execution['error']}`\n\n"
                                  f"Please try rephrasing your request or asking for specific fields (e.g. 'Show all doctors in CA' or 'List sales reps').",
                        "sql": code,
                        "data": None,
                        "error": execution["error"]
                    }

                result_data = execution["result"]
                logger.info(f"Sandbox execution results (Salesforce): {result_data}")

                final_prompt = (
                    f"You are a helpful Salesforce data assistant.\n"
                    f"User asked: {user_message}\n"
                    f"You executed this Python/SOQL code:\n{code}\n"
                    f"Execution result: {json.dumps(result_data, default=str)}\n\n"
                    f"Provide a clear, direct, and professional natural language response summarizing the findings. "
                    f"If 0 records were returned, state politely that no records matched the criteria in the Salesforce org and suggest alternative terms."
                )

                try:
                    final_answer = await self._call_groq_api(
                        messages=[{"role": "user", "content": final_prompt}],
                        temperature=0.3
                    )
                except Exception as e:
                    logger.warning(f"Salesforce summarization call failed, defaulting: {e}")
                    final_answer = "Query executed successfully."

                sql_to_return = code
                data_to_return = None

                if isinstance(result_data, dict):
                    sql_to_return = result_data.get("soql") or result_data.get("sosl") or result_data.get("query") or code
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
            logger.exception("Error in Salesforce Groq processing")
            return {
                "answer": f"I ran into an error processing your Salesforce request: {str(e)}. Please check your query or try rephrasing.",
                "sql": None,
                "data": None,
                "error": str(e)
            }

    async def _process_salesforce_gemini(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process Salesforce (UC3) requests using Gemini API and dynamic code execution."""
        try:
            logger.info("Calling Gemini API for Salesforce code generation...")
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

            logger.info(f"Gemini raw output (Salesforce): {response_text}")
            parsed = self._extract_json(response_text)

            code = parsed.get("code")
            answer = parsed.get("answer")

            if code and code.strip():
                execution = code_executor_sf.execute(code)

                # Self-correction retry: mirrors the original standalone UC3 pipeline.
                if execution["error"]:
                    logger.warning(f"Salesforce Gemini code execution error on attempt 1: {execution['error']}. Retrying...")
                    retry_prompt = (
                        f"{prompt}\n\n"
                        f"Your previous Python code failed with error:\n{execution['error']}\n"
                        f"Previous code was:\n```python\n{code}\n```\n"
                        f"Please correct the Python code or SOQL query to fix this error and return valid JSON."
                    )
                    try:
                        retry_response = self.gemini_model.generate_content(
                            retry_prompt,
                            generation_config={"response_mime_type": "application/json"}
                        )
                        parsed_retry = self._extract_json(retry_response.text)
                        if parsed_retry.get("code"):
                            code = parsed_retry.get("code")
                            execution = code_executor_sf.execute(code)
                    except Exception as e:
                        logger.warning(f"Salesforce Gemini retry call failed: {e}")

                if execution["error"]:
                    return {
                        "answer": f"I attempted to query Salesforce for your request, but encountered an execution issue.\n\n"
                                  f"**Detail:** `{execution['error']}`\n\n"
                                  f"Please try rephrasing your request or asking for specific fields (e.g. 'Show all doctors in CA').",
                        "sql": code,
                        "data": None,
                        "error": execution["error"]
                    }

                result_data = execution["result"]
                logger.info(f"Sandbox execution results (Salesforce): {result_data}")

                final_prompt = (
                    f"You are a helpful Salesforce data assistant.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this Python code:\n{code}\n"
                    f"Execution result: {json.dumps(result_data, default=str)}\n\n"
                    f"Provide a clear, direct, and professional natural language response summarizing the findings. "
                    f"If 0 records were returned, state politely that no records matched the criteria in Salesforce."
                )
                final_response = self.gemini_model.generate_content(final_prompt)

                sql_to_return = code
                data_to_return = None

                if isinstance(result_data, dict):
                    sql_to_return = result_data.get("soql") or result_data.get("sosl") or result_data.get("query") or code
                    data_to_return = result_data.get("records") or result_data.get("data")
                    if data_to_return is None:
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
            logger.exception("Error in Salesforce Gemini processing")
            return {
                "answer": "An error occurred while generating the Salesforce response.",
                "sql": None,
                "data": None,
                "error": str(e)
            }

    async def _process_salesforce_ollama(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process Salesforce (UC3) requests using local Ollama and dynamic code execution."""
        try:
            async with httpx.AsyncClient() as client:
                try:
                    await client.get(settings.OLLAMA_HOST, timeout=2.0)
                except Exception:
                    raise RuntimeError(f"Ollama server is not running or unreachable at {settings.OLLAMA_HOST}. Make sure you ran 'ollama serve'.")

            logger.info("Calling local Ollama model for Salesforce code generation...")
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

            logger.info(f"Ollama raw output (Salesforce): {response_text}")
            parsed = self._extract_json(response_text)

            code = parsed.get("code")
            answer = parsed.get("answer")

            if code and code.strip():
                execution = code_executor_sf.execute(code)
                if execution["error"]:
                    return {
                        "answer": f"Code execution failed.",
                        "sql": code,
                        "data": None,
                        "error": execution["error"]
                    }

                result_data = execution["result"]
                logger.info(f"Sandbox execution results (Salesforce): {result_data}")

                final_prompt = (
                    f"You are a helpful Salesforce data assistant.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this Python code:\n{code}\n"
                    f"Execution result: {json.dumps(result_data, default=str)}\n\n"
                    f"Provide a clear, direct, and professional natural language response summarizing the findings."
                )

                final_resp = ollama.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": final_prompt}]
                )

                sql_to_return = code
                data_to_return = None

                if isinstance(result_data, dict):
                    sql_to_return = result_data.get("soql") or result_data.get("sosl") or result_data.get("query") or code
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
            logger.exception("Error in Salesforce Ollama processing")
            return {
                "answer": f"Ollama Error: {str(e)}",
                "sql": None,
                "data": None,
                "error": str(e)
            }

    async def process_chat(self, user_message: str, history: Optional[list] = None) -> Dict[str, Any]:
        """
        Orchestrate the chat session. Uses LLM to generate Python code,
        executes it in the CodeExecutor sandbox, and returns formatted responses.
        """
        history_context = ""
        if history:
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
            history_context = "CONVERSATION HISTORY:\n" + "\n".join(formatted_history) + "\n\n"

        if self._is_salesforce_query(user_message):
            logger.info("Routing chat request to Salesforce (UC3) pipeline")
            return await self._process_salesforce_chat(user_message, history_context)

        context_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"{self._get_refinement_instructions()}\n\n"
            f"{self.semantic_loader.get_semantic_context_prompt()}\n\n"
            f"{history_context}"
            f"User Question: {user_message}"
        )

        logger.info(f"Processing chat request using provider: {self.provider}")
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
            "  - TABLE WHITELIST: Leakage_Activity, copay_Claims_Transactions, leakage_history, Compliance_Table, hcp_engagement_logs, fatigue_score, Product_Master, hcp_master, Zip_Geography_Master, Payer_Master, campaign_master, Reject_Code_Master, territory_master, Reverse_Claims.\n"
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
