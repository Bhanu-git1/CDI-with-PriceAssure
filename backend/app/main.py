import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from contextlib import asynccontextmanager

from app.config import settings
from app.llm_service import llm_service, db_service, sf_service

# Configure standard console logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dce-fastapi-app")


def _check_mysql() -> dict:
    """
    Live MySQL connectivity check. Never raises — a failed/unreachable
    connection is reported as "offline", not "error"; "error" is reserved
    for genuine application bugs, not a disconnected service.
    """
    try:
        conn = db_service.get_connection()
        conn.close()
        return {"name": "MySQL Database", "status": "connected", "detail": None}
    except Exception as e:
        return {"name": "MySQL Database", "status": "offline", "detail": str(e)}


def _check_salesforce() -> dict:
    """Live Salesforce connectivity check — see _check_mysql for status semantics."""
    try:
        sf_service.get_connection()
        return {"name": "Salesforce CRM", "status": "connected", "detail": None}
    except Exception as e:
        return {"name": "Salesforce CRM", "status": "offline", "detail": str(e)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: log initial reachability. The authoritative status is recomputed
    # live on every "/api/" request (see read_root) so the UI never goes stale.
    logger.info("Initializing MySQL DCE workspace...")
    logger.info(f"MySQL connection check: {_check_mysql()['status']}")

    logger.info("Initializing Salesforce DCE workspace (UC3)...")
    logger.info(f"Salesforce connection check: {_check_salesforce()['status']}")

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
async def read_root():
    if llm_service.provider == "groq":
        provider = f"Groq ({settings.GROQ_MODEL})"
    elif llm_service.provider == "claude":
        backend_label = "Bedrock" if llm_service.is_bedrock else "Anthropic"
        provider = f"Claude via {backend_label} ({llm_service.claude_model})"
    else:
        provider = "Not configured"

    # Run all three health checks concurrently. MySQL/Salesforce use blocking
    # client libraries, so they're offloaded to a thread pool; the LLM check
    # is native async.
    mysql_health, sf_health, llm_health = await asyncio.gather(
        run_in_threadpool(_check_mysql),
        run_in_threadpool(_check_salesforce),
        llm_service.check_llm_health(),
    )

    return {
        "status": "online",
        "provider": provider,
        "connections": [mysql_health, sf_health],
        "llm": {"name": provider, "status": llm_health["status"], "detail": llm_health["detail"]},
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
