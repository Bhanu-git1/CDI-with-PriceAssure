import json
import logging
import httpx
from typing import Dict, Any, Tuple, Optional
import ollama

from app.config import settings
from app.mcp_client import sf_mcp_client

logger = logging.getLogger("llm-service")

SYSTEM_PROMPT = """
You are an expert Salesforce data assistant. Your task is to help users query a Salesforce CRM instance using SOQL (Salesforce Object Query Language).
You have access to Salesforce via the Model Context Protocol (MCP) server.

SALESFORCE OBJECT OVERVIEW:
Below are the key standard Salesforce objects you can query:

1. **Account** – Companies/organizations. Key fields: Id, Name, Industry, Type, BillingCity, BillingState, AnnualRevenue, NumberOfEmployees, OwnerId, CreatedDate.
2. **Contact** – People associated with Accounts. Key fields: Id, FirstName, LastName, Name, Email, Phone, AccountId, Title, Department, MailingCity, MailingState, OwnerId.
3. **Opportunity** – Sales deals. Key fields: Id, Name, StageName, Amount, CloseDate, Probability, AccountId, OwnerId, Type, LeadSource, IsClosed, IsWon, ForecastCategory.
4. **Lead** – Potential customers. Key fields: Id, FirstName, LastName, Name, Company, Email, Phone, Status, LeadSource, Industry, IsConverted, OwnerId.
5. **Case** – Support tickets. Key fields: Id, CaseNumber, Subject, Description, Status, Priority, Origin, AccountId, ContactId, OwnerId, CreatedDate, ClosedDate.
6. **Task** – Activities/to-dos. Key fields: Id, Subject, Status, Priority, ActivityDate, WhoId, WhatId, OwnerId, Description.
7. **Event** – Calendar events. Key fields: Id, Subject, StartDateTime, EndDateTime, WhoId, WhatId, Location, OwnerId.
8. **Campaign** – Marketing campaigns. Key fields: Id, Name, Type, Status, StartDate, EndDate, BudgetedCost, ActualCost, NumberOfLeads, NumberOfContacts.
9. **CampaignMember** – Links Leads/Contacts to Campaigns. Key fields: Id, CampaignId, LeadId, ContactId, Status.
10. **Product2** – Products in the catalog. Key fields: Id, Name, ProductCode, Description, Family, IsActive.
11. **User** – Salesforce users. Key fields: Id, Name, Username, Email, Profile.Name, UserRole.Name, IsActive, Department.
12. **Contract** – Agreements. Key fields: Id, ContractNumber, AccountId, Status, StartDate, EndDate, ContractTerm.
13. **Order** – Purchase orders. Key fields: Id, OrderNumber, AccountId, Status, EffectiveDate, TotalAmount.

SOQL SYNTAX RULES (IMPORTANT — follow these strictly):
1. SOQL uses `SELECT ... FROM ObjectName [WHERE ...] [ORDER BY ...] [LIMIT ...]`.
2. SOQL does NOT support `SELECT *`. You MUST explicitly list the fields you want.
3. Use `LIKE` with `%` for partial text matches: `WHERE Name LIKE '%Acme%'`.
4. Date literals: `TODAY`, `LAST_N_DAYS:30`, `THIS_MONTH`, `LAST_MONTH`, `THIS_YEAR`, `LAST_YEAR`.
5. Aggregate functions: `COUNT()`, `COUNT(Id)`, `SUM(Amount)`, `AVG(Amount)`, `MIN()`, `MAX()`.
6. `GROUP BY` works with aggregate queries. Use `HAVING` to the filter aggregated results.
7. To query related objects, use relationship names:
   - Child-to-Parent: `SELECT Name, Account.Name FROM Contact` (dot notation).
   - Parent-to-Child subqueries: `SELECT Name, (SELECT LastName FROM Contacts) FROM Account`.
8. Boolean fields: `IsWon = true`, `IsClosed = false`, `IsConverted = true`.
9. NULL checks: `WHERE Email != null`, `WHERE Phone = null`.
10. `IN` operator: `WHERE StageName IN ('Closed Won', 'Negotiation')`.
11. `ORDER BY` supports `ASC`/`DESC` and `NULLS FIRST`/`NULLS LAST`.
12. Maximum LIMIT is 2000 in standard SOQL. Default to `LIMIT 100` unless user asks for more.
13. SOQL does NOT have `JOIN` syntax — use relationship queries instead.
14. For cross-object text search, suggest using SOSL via the `search_records` tool.

FEW-SHOT EXAMPLES (Follow these SOQL templates):

Example 1 — List Accounts:
User: Show me the top 10 accounts by revenue
SOQL: SELECT Id, Name, Industry, AnnualRevenue FROM Account WHERE AnnualRevenue != null ORDER BY AnnualRevenue DESC LIMIT 10

Example 2 — Contact lookup:
User: Find all contacts at Acme Corp
SOQL: SELECT Id, FirstName, LastName, Email, Phone, Title FROM Contact WHERE Account.Name LIKE '%Acme%'

Example 3 — Pipeline analysis:
User: What is the total opportunity amount by stage?
SOQL: SELECT StageName, COUNT(Id) OpportunityCount, SUM(Amount) TotalAmount FROM Opportunity GROUP BY StageName ORDER BY SUM(Amount) DESC

Example 4 — Recent cases:
User: Show me open high-priority cases from the last 30 days
SOQL: SELECT CaseNumber, Subject, Status, Priority, CreatedDate, Account.Name FROM Case WHERE Priority = 'High' AND IsClosed = false AND CreatedDate = LAST_N_DAYS:30 ORDER BY CreatedDate DESC

Example 5 — Lead conversion:
User: How many leads were converted this year?
SOQL: SELECT COUNT(Id) ConvertedCount FROM Lead WHERE IsConverted = true AND ConvertedDate = THIS_YEAR

Example 6 — Relationship query:
User: Show accounts with their contacts
SOQL: SELECT Name, Industry, (SELECT FirstName, LastName, Email FROM Contacts) FROM Account LIMIT 10

You MUST follow these rules:
1. When asked about data, first check if you know the fields of the relevant Salesforce object. If unsure, use the `describe_object` tool to discover the exact field names.
2. Formulate a correct SOQL query that is read-only (SELECT only).
3. For text or name searches, use the `LIKE` operator with wildcards (e.g., `Name LIKE '%search_term%'`) unless the user requests exact match.
4. **Do not truncate, alter, or auto-correct names, IDs, or values** provided by the user. Search for the exact terms they typed.
5. Use the tool `execute_soql` to fetch the data from Salesforce.
6. If the user wants a cross-object keyword search (not a structured query), use `search_records` with a SOSL query.
7. After receiving the tool execution result, formulate your final answer.
8. In your final response: 
   - Provide a clear, natural language explanation of the results.
   - If the results are structured data, include the exact SOQL query used inside a markdown code block labeled with `soql`.
   - Summarize the data briefly. 
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
        """Fetch Salesforce schema overview from the MCP server."""
        try:
            schema_overview = await sf_mcp_client.read_resource("schema://overview")
            return schema_overview
        except Exception as e:
            logger.error(f"Error fetching schema resource: {e}")
            # Fallback to listing objects
            try:
                objects = await sf_mcp_client.execute_tool("list_objects", {})
                return f"Could not fetch complete schema overview, but available objects are:\n{objects}"
            except Exception as inner_e:
                return f"Could not establish Salesforce connection details. Error: {inner_e}"

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
                if h.soql:
                    formatted_history.append(f"  (SOQL executed: {h.soql})")
                elif h.sql:
                    formatted_history.append(f"  (SOQL executed: {h.sql})")
            history_context = "CONVERSATION HISTORY:\n" + "\n".join(formatted_history) + "\n\n"
            
        # 3. Setup prompts
        context_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"SALESFORCE SCHEMA DETAILS:\n{schema_context}\n\n"
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
            refinement_prompt = (
                f"{prompt}\n\n"
                "If the query requires Salesforce data, output a JSON object in this format:\n"
                '{"reasoning": "...", "soql": "SELECT ... FROM ..."}\n'
                "If you need to first discover the schema of an object, output:\n"
                '{"reasoning": "...", "describe_object": "ObjectName"}\n'
                "If the user wants a cross-object text search, output:\n"
                '{"reasoning": "...", "sosl": "FIND {term} IN ALL FIELDS RETURNING ..."}\n'
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

            # Handle describe_object request (schema discovery step)
            describe_obj = parsed.get("describe_object")
            if describe_obj:
                logger.info(f"Gemini wants to describe object: {describe_obj}")
                schema_result = await sf_mcp_client.execute_tool("describe_object", {"object_name": describe_obj})
                
                # Now re-prompt with the schema info to generate the actual SOQL
                followup_prompt = (
                    f"{prompt}\n\n"
                    f"ADDITIONAL SCHEMA INFO for '{describe_obj}':\n{schema_result}\n\n"
                    "Now generate the SOQL query. Output a JSON object:\n"
                    '{"reasoning": "...", "soql": "SELECT ... FROM ..."}\n'
                    "Output ONLY the JSON object."
                )
                
                response2 = self.gemini_model.generate_content(
                    followup_prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                response_text2 = response2.text.strip()
                if response_text2.startswith("```json"):
                    response_text2 = response_text2.replace("```json", "", 1)
                if response_text2.endswith("```"):
                    response_text2 = response_text2[:-3]
                response_text2 = response_text2.strip()
                parsed = json.loads(response_text2)

            # Handle SOSL search
            sosl = parsed.get("sosl")
            if sosl:
                logger.info(f"Gemini suggested SOSL: {sosl}")
                search_results = await sf_mcp_client.execute_tool("search_records", {"sosl_query": sosl})
                
                final_prompt = (
                    f"You are a Salesforce data expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this SOSL search: {sosl}\n"
                    f"And got these results: {search_results}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct."
                )
                final_response = self.gemini_model.generate_content(final_prompt)
                
                try:
                    data_obj = json.loads(search_results)
                    # Flatten search results for table display
                    flat_data = []
                    for obj_type, records in data_obj.get("resultsByObject", {}).items():
                        for r in records:
                            r["_ObjectType"] = obj_type
                            flat_data.append(r)
                    data_obj = flat_data if flat_data else None
                except Exception:
                    data_obj = None

                return {
                    "answer": final_response.text,
                    "sql": sosl,
                    "data": data_obj,
                    "error": None
                }
            
            # Handle SOQL query
            soql = parsed.get("soql")
            if soql:
                logger.info(f"Gemini suggested SOQL: {soql}")
                # Execute the SOQL via MCP tool
                sf_results = await sf_mcp_client.execute_tool("execute_soql", {"soql_query": soql})
                
                # Format final answer
                final_prompt = (
                    f"You are a Salesforce data expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this SOQL: {soql}\n"
                    f"And got these results: {sf_results}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct. Also state what Salesforce returned."
                )
                final_response = self.gemini_model.generate_content(final_prompt)
                
                # Attempt to parse results for visual charts/tables
                try:
                    result_obj = json.loads(sf_results)
                    data_obj = result_obj.get("records", None)
                except Exception:
                    data_obj = None

                return {
                    "answer": final_response.text,
                    "sql": soql,
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
                "answer": "An error occurred while generating the Salesforce response.",
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
                "If the query requires Salesforce data, output a JSON object in this format:\n"
                '{"reasoning": "...", "soql": "SELECT ... FROM ..."}\n'
                "If you need to first discover the schema of an object, output:\n"
                '{"reasoning": "...", "describe_object": "ObjectName"}\n'
                "If the user wants a cross-object text search, output:\n"
                '{"reasoning": "...", "sosl": "FIND {term} IN ALL FIELDS RETURNING ..."}\n'
                "Otherwise, output a JSON object in this format:\n"
                '{"reasoning": "...", "answer": "your natural language answer"}\n'
                "Output ONLY the JSON object. Do not include markdown code block formatting like ```json ... ```. Just the raw JSON string."
            )
            
            logger.info("Calling local Ollama model...")
            response = ollama.chat(
                model=settings.OLLAMA_MODEL,
                messages=[
                    {"role": "user", "content": refinement_prompt}
                ],
                format="json",
                options={"temperature": 0.1}  # low temperature for precise SOQL
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

            # Handle describe_object request (schema discovery step)
            describe_obj = parsed.get("describe_object")
            if describe_obj:
                logger.info(f"Ollama wants to describe object: {describe_obj}")
                schema_result = await sf_mcp_client.execute_tool("describe_object", {"object_name": describe_obj})
                
                followup_prompt = (
                    f"{prompt}\n\n"
                    f"ADDITIONAL SCHEMA INFO for '{describe_obj}':\n{schema_result}\n\n"
                    "Now generate the SOQL query. Output a JSON object:\n"
                    '{"reasoning": "...", "soql": "SELECT ... FROM ..."}\n'
                    "Output ONLY the JSON object."
                )
                
                response2 = ollama.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": followup_prompt}],
                    format="json",
                    options={"temperature": 0.1}
                )
                response_text2 = response2['message']['content'].strip()
                if response_text2.startswith("```json"):
                    response_text2 = response_text2.replace("```json", "", 1)
                if response_text2.endswith("```"):
                    response_text2 = response_text2[:-3]
                response_text2 = response_text2.strip()
                parsed = json.loads(response_text2)

            # Handle SOSL search
            sosl = parsed.get("sosl")
            if sosl:
                logger.info(f"Ollama suggested SOSL: {sosl}")
                search_results = await sf_mcp_client.execute_tool("search_records", {"sosl_query": sosl})
                
                final_prompt = (
                    f"You are a Salesforce data expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this SOSL search: {sosl}\n"
                    f"And got these results: {search_results}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct."
                )
                
                final_resp = ollama.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": final_prompt}]
                )
                
                try:
                    data_obj = json.loads(search_results)
                    flat_data = []
                    for obj_type, records in data_obj.get("resultsByObject", {}).items():
                        for r in records:
                            r["_ObjectType"] = obj_type
                            flat_data.append(r)
                    data_obj = flat_data if flat_data else None
                except Exception:
                    data_obj = None

                return {
                    "answer": final_resp['message']['content'],
                    "sql": sosl,
                    "data": data_obj,
                    "error": None
                }
            
            # Handle SOQL query
            soql = parsed.get("soql")
            if soql:
                logger.info(f"Ollama suggested SOQL: {soql}")
                sf_results = await sf_mcp_client.execute_tool("execute_soql", {"soql_query": soql})
                
                final_prompt = (
                    f"You are a Salesforce data expert.\n"
                    f"User asked: {user_message}\n"
                    f"You ran this SOQL: {soql}\n"
                    f"And got these results: {sf_results}\n\n"
                    f"Provide a natural language summary of the results. Be clear and direct. Also state what Salesforce returned."
                )
                
                final_resp = ollama.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[{"role": "user", "content": final_prompt}]
                )
                
                try:
                    result_obj = json.loads(sf_results)
                    data_obj = result_obj.get("records", None)
                except Exception:
                    data_obj = None
                    
                return {
                    "answer": final_resp['message']['content'],
                    "sql": soql,
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
