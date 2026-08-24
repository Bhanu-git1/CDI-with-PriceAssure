import asyncio
import logging
from typing import List, Optional, Union, Any, Dict
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from contextlib import asynccontextmanager

from app.config import settings
from app.llm_service import llm_service, db_service, sf_service
from app.services.history_service import HistoryService

# Configure standard console logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dce-fastapi-app")

history_service = HistoryService(db_service)


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
    # Startup: log initial reachability and initialize history tables
    logger.info("Initializing MySQL DCE workspace...")
    logger.info(f"MySQL connection check: {_check_mysql()['status']}")

    try:
        await run_in_threadpool(history_service.init_db)
    except Exception as e:
        logger.warning(f"History service db init deferred or failed: {e}")

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


# Schemas
class ChatMessage(BaseModel):
    sender: str
    text: str
    sql: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []


class ChatMessageItem(BaseModel):
    id: Optional[Union[int, str]] = None
    sender: str
    text: str
    sql: Optional[str] = None
    data: Optional[Any] = None
    error: Optional[str] = None
    source: Optional[str] = None
    timestamp: Optional[str] = None


class ChatSessionPayload(BaseModel):
    id: str
    title: str
    isPinned: Optional[bool] = False
    user_id: Optional[str] = "default_user"
    messages: Optional[List[ChatMessageItem]] = []


class ChatSessionUpdatePayload(BaseModel):
    title: Optional[str] = None
    isPinned: Optional[bool] = None


class SyncLocalPayload(BaseModel):
    user_id: Optional[str] = "default_user"
    sessions: List[ChatSessionPayload]


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


# -------------------------------------------------------------
# Chat History Management Endpoints (MySQL-backed)
# -------------------------------------------------------------

@app.get("/api/chats")
async def list_chats(
    user_id: str = Query("default_user"),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0)
):
    """
    Retrieve lightweight list of saved chat sessions for sidebar.
    """
    sessions = await run_in_threadpool(history_service.list_sessions, user_id, limit, offset)
    return {"sessions": sessions}


@app.get("/api/chats/{session_id}")
async def get_chat_session(session_id: str):
    """
    Retrieve full transcript and metadata for a single session.
    """
    session = await run_in_threadpool(history_service.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@app.post("/api/chats")
async def save_chat_session(payload: ChatSessionPayload):
    """
    Save or update a chat session and its messages.
    """
    messages_dicts = [m.model_dump() for m in payload.messages] if payload.messages else []
    success = await run_in_threadpool(
        history_service.save_session,
        payload.id,
        payload.title,
        messages_dicts,
        payload.user_id or "default_user",
        bool(payload.isPinned)
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save chat session to MySQL")
    return {"status": "success", "id": payload.id}


@app.patch("/api/chats/{session_id}")
async def update_chat_session(session_id: str, payload: ChatSessionUpdatePayload):
    """
    Update chat session metadata (title, pin state).
    """
    success = await run_in_threadpool(
        history_service.update_session,
        session_id,
        payload.title,
        payload.isPinned
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update chat session")
    return {"status": "success", "id": session_id}


@app.delete("/api/chats/{session_id}")
async def delete_chat_session(session_id: str):
    """
    Delete a chat session and all its messages.
    """
    success = await run_in_threadpool(history_service.delete_session, session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete chat session")
    return {"status": "success", "id": session_id}


@app.post("/api/chats/sync-local")
async def sync_local_chats(payload: SyncLocalPayload):
    """
    Batch-sync localStorage sessions into MySQL on migration/first load.
    """
    synced_count = 0
    for s in payload.sessions:
        msg_dicts = [m.model_dump() for m in s.messages] if s.messages else []
        saved = await run_in_threadpool(
            history_service.save_session,
            s.id,
            s.title,
            msg_dicts,
            payload.user_id or "default_user",
            bool(s.isPinned)
        )
        if saved:
            synced_count += 1
    return {"status": "success", "synced": synced_count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
