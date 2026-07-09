import json
import logging
import httpx
from typing import Dict, Any, Tuple, Optional
import ollama

from backend.app.config import settings
from backend.app.mcp_client import db_mcp_client

logger = logging.getLogger("llm-service")

SYSTEM_PROMPT = """
You are a expert database assistant. Your task is to help users query a MySQL database.
You have access to a database via the Model Context Protocol (MCP) server.

BUSINESS TO DATABASE MAPPING:
Copay & Claims
- Any queries related to copay, copay count, copay transactions, reversed claims, or claim reversals should use the `Reverse_Claims` table.
- Queries about raw transaction status, reject codes, or reject messages (like `Reject_Code` or `Reject_Message`) should use the `Reverse_Claims` table.

Leakage & Rejections
- For queries asking for the **"leakage limit"**, **"leakage threshold"**, "history of changes", "audit history", "who updated leakage values", or "value updates/modifications", use the `leakage_history` table (which contains columns like `previous_value`, `new_value`, `updated_by`, and `updated_at`). For example, the "latest leakage limit" query should select `new_value` from `leakage_history` ordered by `updated_at` DESC.
- For all other leakage metrics—including "top leakage", "leakage percentage", "leakage count", or "leakage by zip/HCP"—as well as queries about "rejections" or "rejected count", use the `Leakage_Activity` table.

Government Plans / Compliance
- Any queries related to government plans, bypassed records, compliance, or bypassed transactions should use the `Compliance_Table` table.

Fatigue & HCP Engagement
- For queries about "fatigue", "fatigue score", "fatigue percentage", "fatigue %", or queries linking fatigue to HCPs or products (e.g. "product name with fatigue %", or searching for HCPs/products by campaign names), you MUST query the `fatigue_score` table directly.
- The `fatigue_score` table already contains the HCP's name in the `HCP_Name` column, the product name in the `Product` column, the campaign name in the `Campaign_Name` column, and the fatigue percentage in the `Fatigue` column. 
- **DO NOT join other tables** (like `hcp_master` or `copay_Claims_Transactions`) for names, product names, or campaign names when querying fatigue, as `fatigue_score` has all these fields directly.
- Do not query the `hcp_master` or `hcp_engagement_logs` tables for campaign name lookups, as `hcp_engagement_logs` only contains IDs, not full text campaign names.
- For queries about "HCP engagement metrics", "physician engagement logs", or "provider engagement channels", use the `hcp_engagement_logs` table.

FEW-SHOT EXAMPLES (Follow these templates exactly for SQL generation):
Example 1:
User: hcp name with fatigue %
SQL: SELECT HCP_Name, Fatigue FROM fatigue_score WHERE Fatigue > 0;

Example 2:
User: product name with fatigue %
SQL: SELECT DISTINCT Product, Fatigue FROM fatigue_score WHERE Fatigue > 0;

Example 3:
User: who is the hcp for NeuroLife Campaign 5
SQL: SELECT DISTINCT HCP_Name FROM fatigue_score WHERE Campaign_Name LIKE '%NeuroLife Campaign 5%';

Example 4:
User: pharmacy NCPDP-5512 how many product rejected count
SQL: SELECT SUM(Pharmacy_Rejections) AS Rejected_Count FROM Leakage_Activity WHERE Pharmacy_ID = 'NCPDP-5512';

Example 5:
User: show the full list of product now (follow-up after searching a pharmacy)
SQL: SELECT DISTINCT BrandName, productid FROM Leakage_Activity WHERE Pharmacy_ID = '[Previous_Pharmacy_ID_From_History]';

You MUST follow these rules:
1. When asked about data, check the schema details provided below.
2. Formulate a correct SQL query that is safe and read-only (SELECT queries only).
3. For text or name searches (e.g., looking up people, brands, or text fields), use the `LIKE` operator with wildcards (e.g., `column_name LIKE '%search_term%'`) rather than an exact match `=` unless the user explicitly requests an exact match.
4. **Do not truncate, alter, or auto-correct identifier codes, phone numbers, ZIP codes, campaign names, brand names, or product names** provided by the user. Always search for the exact full terms they typed (e.g., if they ask for "cardioplus campaign 2", do not truncate it to "cardioplus"; search for the full "cardioplus campaign 2" using `=` or `LIKE '%cardioplus campaign 2%'`).
5. Use the tool `execute_query` to fetch the data.
6. After receiving the tool execution result, formulate your final answer.
7. In your final response:
   - Provide a clear, natural language explanation of the results.
   - If the results are structured data, include the exact raw SQL query used inside a markdown code block labeled with `sql`.
   - Also, summarize the data briefly.
"""

class LLMService:
    def __init__(self):
        self.use_gemini = bool(settings.GEMINI_API_KEY)
        if self.use_gemini:
            logger.info("Initializing Google Gemini client...")
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            # Dynamically select the best available flash model
            model_name = 'gemini-1.5-flash'  # fallback default
            try:
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                logger.info(f"Found available Gemini models: {available_models}")
                
                # Check list in order of preference
                for candidate in ['models/gemini-2.0-flash', 'models/gemini-2.5-flash', 'models/gemini-1.5-flash']:
                    if candidate in available_models:
                        model_name = candidate
                        break
                else:
                    # Pick the first one that has "flash" in it
                    flash_candidates = [m for m in available_models if 'flash' in m.lower()]
                    if flash_candidates:
                        model_name = flash_candidates[0]
                    elif available_models:
                        model_name = available_models[0]
                
                logger.info(f"Selected model: {model_name}")
            except Exception as e:
                logger.warning(f"Could not list available models, defaulting to {model_name}. Error: {e}")
                
            # If the name starts with "models/", strip it or keep it as required by GenerativeModel
            self.gemini_model = genai.GenerativeModel(model_name)
        else:
            logger.info(f"Using local Ollama client running at {settings.OLLAMA_HOST} with model {settings.OLLAMA_MODEL}")

    async def get_schema_context(self) -> str:
        """Fetch database schema overview from the MCP server."""
        try:
            schema_overview = await db_mcp_client.read_resource("schema://overview")
            return schema_overview
        except Exception as e:
            logger.error(f"Error fetching schema resource: {e}")
            # Fallback to listing tables
            try:
                tables = await db_mcp_client.execute_tool("list_tables", {})
                return f"Could not fetch complete schema overview, but available tables are:\n{tables}"
            except Exception as inner_e:
                return f"Could not establish database connection details. Error: {inner_e}"

    async def process_chat(self, user_message: str, history: Optional[list] = None) -> Dict[str, Any]:
        """
        Orchestrate the chat session. It uses LLM to generate tool calls,
        executes them via MCP, feeds the results back, and returns the response.
        """
        # 1. Fetch live schema info from MCP
        schema_context = await self.get_schema_context()
        
        # 2. Format history context
        history_context = ""
        if history:
            formatted_history = []
            for h in history:
                sender_name = "User" if h.sender == "user" else "Assistant"
                formatted_history.append(f"{sender_name}: {h.text}")
                if h.sql:
                    formatted_history.append(f"  (SQL executed: {h.sql})")
            history_context = "CONVERSATION HISTORY:\n" + "\n".join(formatted_history) + "\n\n"
            
        # 3. Setup prompts
        context_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"DATABASE NAME: {settings.DB_NAME}\n\n"
            f"DATABASE SCHEMA DETAILS:\n{schema_context}\n\n"
            f"{history_context}"
            f"User Question: {user_message}"
        )

        if self.use_gemini:
            return await self._process_gemini(user_message, context_prompt)
        else:
            return await self._process_ollama(user_message, context_prompt)

    async def _process_gemini(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process requests using Gemini API."""
        try:
            # We configure tool calling for Gemini
            # In Gemini API, tools are defined by python functions or JSON schema.
            # To keep this PoC simple and robust across local and cloud, we can do structured prompt engineering
            # to let Gemini output a SQL query, execute it, and feed the data back, OR use Gemini's function declaration.
            # Let's use prompt engineering to get the SQL query reliably, execute it, and format.
            # This is 100% reliable and works identically for Ollama and Gemini without complex API translations.
            
            refinement_prompt = (
                f"{prompt}\n\n"
                "If the query requires database data, output a JSON object in this format:\n"
                '{"reasoning": "...", "sql": "SELECT ... FROM ..."}\n'
                "Otherwise, output a JSON object in this format:\n"
                '{"reasoning": "...", "answer": "your natural language answer"}\n'
                "Output ONLY the JSON object. Do not include markdown code block formatting like ```json ... ```. Just the raw JSON string."
            )
            
            logger.info("Calling Gemini API...")
            response = self.gemini_model.generate_content(
                refinement_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            response_text = response.text.strip()
            
            # Clean up response if model wraps it in markdown blocks
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            logger.info(f"Gemini raw output: {response_text}")
            parsed = json.loads(response_text)
            
            sql = parsed.get("sql")
            if sql:
                logger.info(f"Gemini suggested SQL: {sql}")
                # Execute the SQL via MCP tool
                db_results = await db_mcp_client.execute_tool("execute_query", {"sql_query": sql})
                
                # Format final answer
                final_prompt = (
                    f"You are a database query expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this SQL: {sql}\n"
                    f"And got these results: {db_results}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct. Also state what the database found."
                )
                final_response = self.gemini_model.generate_content(final_prompt)
                
                # Attempt to parse database results back to object for visual charts/tables
                try:
                    data_obj = json.loads(db_results)
                except Exception:
                    data_obj = None

                return {
                    "answer": final_response.text,
                    "sql": sql,
                    "data": data_obj,
                    "error": None
                }
            else:
                return {
                    "answer": parsed.get("answer", "I couldn't process that query."),
                    "sql": None,
                    "data": None,
                    "error": None
                }
                
        except Exception as e:
            logger.exception("Error in Gemini processing")
            return {
                "answer": "An error occurred while generating the database response.",
                "sql": None,
                "data": None,
                "error": str(e)
            }

    async def _process_ollama(self, user_message: str, prompt: str) -> Dict[str, Any]:
        """Process requests using Local Ollama."""
        try:
            # Check Ollama health
            async with httpx.AsyncClient() as client:
                try:
                    await client.get(settings.OLLAMA_HOST, timeout=2.0)
                except Exception:
                    raise RuntimeError(f"Ollama server is not running or unreachable at {settings.OLLAMA_HOST}. Make sure you ran 'ollama serve'.")

            refinement_prompt = (
                f"{prompt}\n\n"
                "If the query requires database data, output a JSON object in this format:\n"
                '{"reasoning": "...", "sql": "SELECT ... FROM ..."}\n'
                "Otherwise, output a JSON object in this format:\n"
                '{"reasoning": "...", "answer": "your natural language answer"}\n'
                "Output ONLY the JSON object. Do not include markdown code block formatting like ```json ... ```. Just the raw JSON string."
            )
            
            logger.info("Calling local Ollama model...")
            # Run query
            response = ollama.chat(
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "user", "content": refinement_prompt}
                ],
                format="json",
                options={"temperature": 0.1}  # low temperature for precise SQL
            )
            
            response_text = response['message']['content'].strip()
            # Clean up JSON if model wraps in markdown
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            logger.info(f"Ollama raw output: {response_text}")
            parsed = json.loads(response_text)
            
            sql = parsed.get("sql")
            if sql:
                logger.info(f"Ollama suggested SQL: {sql}")
                # Execute query via MCP tool
                db_results = await db_mcp_client.execute_tool("execute_query", {"sql_query": sql})
                
                final_prompt = (
                    f"You are a database query expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this SQL: {sql}\n"
                    f"And got these results: {db_results}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct. Also state what the database found."
                )
                
                final_resp = ollama.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": final_prompt}]
                )
                
                try:
                    data_obj = json.loads(db_results)
                except Exception:
                    data_obj = None
                    
                return {
                    "answer": final_resp['message']['content'],
                    "sql": sql,
                    "data": data_obj,
                    "error": None
                }
            else:
                return {
                    "answer": parsed.get("answer", "I couldn't process that query."),
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
