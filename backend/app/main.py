import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

from app.config import settings
from app.llm_service import llm_service, db_service, sf_service

# Configure standard console logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dce-fastapi-app")

# Tracks live/last-known health of each backend data connection, refreshed at
# startup, so the UI can list each one's status individually.
connection_status = {
    "mysql": {"name": "MySQL Database", "status": "unknown", "detail": None},
    "salesforce": {"name": "Salesforce CRM", "status": "unknown", "detail": None},
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Verify credentials & connection to MySQL (UC1/UC2)
    logger.info("Initializing MySQL DCE workspace...")
    try:
        conn = db_service.get_connection()
        conn.close()
        connection_status["mysql"]["status"] = "connected"
        logger.info("MySQL connection verified successfully (DCE).")
    except Exception as e:
        connection_status["mysql"]["status"] = "error"
        connection_status["mysql"]["detail"] = str(e)
        logger.error(f"Failed to establish MySQL connection on startup: {e}")

    # Startup: Verify credentials & connection to Salesforce (UC3). Non-fatal —
    # UC1/UC2 must keep working even if Salesforce is unreachable/misconfigured.
    logger.info("Initializing Salesforce DCE workspace (UC3)...")
    try:
        sf_service.get_connection()
        connection_status["salesforce"]["status"] = "connected"
        logger.info("Salesforce connection verified successfully (DCE).")
    except Exception as e:
        connection_status["salesforce"]["status"] = "error"
        connection_status["salesforce"]["detail"] = str(e)
        logger.error(f"Failed to establish Salesforce connection on startup: {e}")

    yield

    logger.info("Shutting down MySQL DCE workspace...")

# Create FastAPI instance with Lifespan lifecycle hooks
app = FastAPI(
    title="DCE MySQL Chat Assistant",
    description="FastAPI Backend for MySQL database retrieval via Dynamic Code Execution",
    version="3.0.0",
    lifespan=lifespan
)

# Configure CORS so React can query backend
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

# Request schema for Chat endpoint
class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []

# Endpoints

@app.get("/api/")
@app.get("/api")
@app.get("/")
def read_root():
    if settings.GROQ_API_KEY:
        provider = f"Groq ({settings.GROQ_MODEL})"
    elif settings.CLAUDE_API_KEY:
        provider = f"Claude ({settings.CLAUDE_MODEL})"
    else:
        provider = "Not configured"

    return {
        "status": "online",
        "provider": provider,
        "connections": list(connection_status.values()),
        "dce_service": "mysql-service + salesforce-service (active)",
        "platform": "MySQL Database (UC1/UC2) + Salesforce CRM (UC3)"
    }

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for taking natural language prompts, calling LLM + DCE,
    and returning formatted responses with MySQL data.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
        
    logger.info(f"Received chat request (DCE): {request.message}")
    
    # Run the prompt-execution loop
    response_data = await llm_service.process_chat(request.message, request.history)
    return response_data

@app.get("/api/schema")
async def schema_endpoint():
    """
    Exposes MySQL table schema context to the frontend.
    """
    logger.info("Fetching MySQL schema info for explorer...")
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
