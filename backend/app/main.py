import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from backend.app.config import settings
from backend.app.mcp_client import db_mcp_client
from backend.app.llm_service import llm_service

# Configure standard console logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-fastapi-app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the local MCP Client (launches MCP subprocess)
    logger.info("Initializing application workspace...")
    try:
        await db_mcp_client.start()
        logger.info("Local MCP client started successfully.")
    except Exception as e:
        logger.error(f"Failed to start local MCP client on startup: {e}")
    
    yield
    
    # Shutdown: Stop client and sub-processes
    logger.info("Shutting down application workspace...")
    await db_mcp_client.stop()
    logger.info("Local MCP client shut down cleanly.")

# Create FastAPI instance with Lifespan lifecycle hooks
app = FastAPI(
    title="MCP MySQL Chat PoC",
    description="FastAPI Backend for MySQL retrieval via Model Context Protocol",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS so React (Vite) can query backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Open for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from typing import List, Optional

class ChatMessage(BaseModel):
    sender: str
    text: str
    sql: Optional[str] = None

# Request schema for Chat endpoint
class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []

# Endpoints

@app.get("/api/")
@app.get("/api")
@app.get("/")
def read_root():
    return {
        "status": "online",
        "provider": "Gemini API" if settings.GEMINI_API_KEY else f"Ollama ({settings.OLLAMA_MODEL})",
        "mcp_server": "mysql-server (active)"
    }

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for taking natural language prompts, calling LLM + MCP tools,
    and returning formatted responses.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
        
    logger.info(f"Received chat request: {request.message}")
    
    # Run the prompt-tool calling loop
    response_data = await llm_service.process_chat(request.message, request.history)
    return response_data

@app.get("/api/schema")
async def schema_endpoint():
    """
    Exposes raw database schema context to the frontend so it can render 
    a visual table schema list.
    """
    logger.info("Fetching schema info for schema explorer...")
    schema_overview = await llm_service.get_schema_context()
    return {"schema": schema_overview}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
