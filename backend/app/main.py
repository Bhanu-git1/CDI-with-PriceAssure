import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from app.config import settings
from app.mcp_client import sf_mcp_client
from app.llm_service import llm_service

# Configure standard console logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-fastapi-app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the local MCP Client (launches MCP subprocess)
    logger.info("Initializing Salesforce MCP workspace...")
    try:
        await sf_mcp_client.start()
        logger.info("Salesforce MCP client started successfully.")
    except Exception as e:
        logger.error(f"Failed to start Salesforce MCP client on startup: {e}")
    
    yield
    
    # Shutdown: Stop client and sub-processes
    logger.info("Shutting down Salesforce MCP workspace...")
    await sf_mcp_client.stop()
    logger.info("Salesforce MCP client shut down cleanly.")

# Create FastAPI instance with Lifespan lifecycle hooks
app = FastAPI(
    title="MCP Salesforce Chat Assistant",
    description="FastAPI Backend for Salesforce CRM retrieval via Model Context Protocol",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS so React (Vite / Salesforce embedded) can query backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open for development; restrict in production
    allow_credentials=False,  # Set to False to allow wildcard origins (*); credentials are not sent by the frontend
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,  # Enable Private Network Access (PNA) preflight approval for loopback
)

from typing import List, Optional

class ChatMessage(BaseModel):
    sender: str
    text: str
    sql: Optional[str] = None
    soql: Optional[str] = None

# Request schema for Chat endpoint
class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []
    sf_session_id: Optional[str] = None
    sf_instance_url: Optional[str] = None

# Endpoints

@app.get("/api/")
@app.get("/api")
@app.get("/")
def read_root():
    return {
        "status": "online",
        "provider": "Gemini API" if settings.GEMINI_API_KEY else f"Ollama ({settings.OLLAMA_MODEL})",
        "mcp_server": "salesforce-server (active)",
        "platform": "Salesforce CRM"
    }

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for taking natural language prompts, calling LLM + MCP tools,
    and returning formatted responses with Salesforce data.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
        
    logger.info(f"Received chat request: {request.message}")
    
    # If the frontend passes Salesforce session credentials, update the MCP client dynamically
    if request.sf_session_id and request.sf_instance_url:
        logger.info("Using Salesforce session credentials from frontend context.")
        # These would be used for per-request auth in a production implementation
        # For now, the MCP server uses env-based credentials
    
    # Run the prompt-tool calling loop
    response_data = await llm_service.process_chat(request.message, request.history)
    return response_data

@app.get("/api/schema")
async def schema_endpoint():
    """
    Exposes Salesforce object schema context to the frontend so it can render 
    a visual object explorer.
    """
    logger.info("Fetching Salesforce schema info for explorer...")
    schema_overview = await llm_service.get_schema_context()
    return {"schema": schema_overview}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
