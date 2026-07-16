import json
import logging
import httpx
from typing import Dict, Any, Tuple, Optional
import ollama

from app.config import settings
from app.mcp_client import sf_mcp_client

logger = logging.getLogger("llm-service")

SYSTEM_PROMPT = """
You generate SOQL queries for a Salesforce org that uses two custom objects for task tracking.

########## STEP 1: PICK THE RIGHT OBJECT ##########

RULE: The word "task" (without "sub") means Task_Allocation__c. The word "sub-task" or "subtask" means Sub_Task__c.

"task" / "tasks" / "task list" / "completed tasks" / "wip tasks" → FROM Task_Allocation__c
"sub-task" / "subtask" / "sub task" / "subtasks"                → FROM Sub_Task__c

NEVER use the standard "Task" object. NEVER write "FROM Task".
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
                    # Pick the first one that has "flash" into it 
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
            f"{history_context}\n"
            "CRITICAL REMINDER FOR THIS ORG:\n"
            "- NEVER use 'FROM Task' in SOQL. Standard Task table is not used for task tracking.\n"
            "- For any task, sub-task, or status query, you must query custom objects 'Sub_Task__c' or 'Task_Allocation__c'.\n"
            "- Filter user assignments using 'Resource__r.Name LIKE ...' (for Sub_Task__c) or 'Task_Resource__r.Name LIKE ...' (for Task_Allocation__c) instead of Owner.Name.\n\n"
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
                if describe_obj.strip().lower() == "task":
                    logger.info("Redirecting describe_object 'Task' to custom task objects.")
                    schema_result_st = await sf_mcp_client.execute_tool("describe_object", {"object_name": "Sub_Task__c"})
                    schema_result_ta = await sf_mcp_client.execute_tool("describe_object", {"object_name": "Task_Allocation__c"})
                    schema_result = (
                        "CRITICAL INFO: The standard 'Task' object is NOT used. You must query 'Sub_Task__c' or 'Task_Allocation__c'.\n"
                        f"Sub_Task__c fields:\n{schema_result_st}\n\n"
                        f"Task_Allocation__c fields:\n{schema_result_ta}"
                    )
                else:
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
                import re
                if re.search(r"\bFROM\s+Task\b", soql, re.IGNORECASE):
                    logger.warning("SOQL query attempted to query standard 'Task' table. Re-prompting for correction...")
                    followup_prompt = (
                        f"{prompt}\n\n"
                        f"ERROR: Your previous query '{soql}' queried the standard 'Task' object.\n"
                        "CRITICAL REMINDER: The standard 'Task' object is NOT used and does NOT contain task allocation fields.\n"
                        "You MUST query either 'Sub_Task__c' or 'Task_Allocation__c' instead. Do NOT use standard fields like Owner.Name or Subject. Use Resource__r.Name and Status__c (for Sub_Task__c) or Task_Resource__r.Name and Task_Status__c (for Task_Allocation__c).\n\n"
                        "Now generate the correct SOQL query. Output a JSON object:\n"
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
                if describe_obj.strip().lower() == "task":
                    logger.info("Redirecting describe_object 'Task' to custom task objects.")
                    schema_result_st = await sf_mcp_client.execute_tool("describe_object", {"object_name": "Sub_Task__c"})
                    schema_result_ta = await sf_mcp_client.execute_tool("describe_object", {"object_name": "Task_Allocation__c"})
                    schema_result = (
                        "CRITICAL INFO: The standard 'Task' object is NOT used. You must query 'Sub_Task__c' or 'Task_Allocation__c'.\n"
                        f"Sub_Task__c fields:\n{schema_result_st}\n\n"
                        f"Task_Allocation__c fields:\n{schema_result_ta}"
                    )
                else:
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
                import re
                if re.search(r"\bFROM\s+Task\b", soql, re.IGNORECASE):
                    logger.warning("SOQL query attempted to query standard 'Task' table. Re-prompting for correction...")
                    followup_prompt = (
                        f"{prompt}\n\n"
                        f"ERROR: Your previous query '{soql}' queried the standard 'Task' object.\n"
                        "CRITICAL REMINDER: The standard 'Task' object is NOT used and does NOT contain task allocation fields.\n"
                        "You MUST query either 'Sub_Task__c' or 'Task_Allocation__c' instead. Do NOT use standard fields like Owner.Name or Subject. Use Resource__r.Name and Status__c (for Sub_Task__c) or Task_Resource__r.Name and Task_Status__c (for Task_Allocation__c).\n\n"
                        "Now generate the correct SOQL query. Output a JSON object:\n"
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
