import asyncio
import logging
from typing import List, Optional, Union, Any, Dict
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from contextlib import asynccontextmanager

from app.config import settings
from app.datasources import registry
from app.llm_service import llm_service, db_service
from app.services.history_service import HistoryService
from app.services.auth_service import AuthService

# Configure standard console logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dce-fastapi-app")

# Chat transcripts and users always live in DB 1
history_service = HistoryService(db_service)
auth_service = AuthService(db_service)


def _check_connections() -> list:
    """
    Live reachability of every registered data source, in the shape the UI's
    "Connected System Status" panel renders.

    Never raises — an unreachable source is reported as "offline", not
    "error"; "error" is reserved for genuine application bugs.
    """
    return registry.health()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: log initial reachability and initialize history and users tables
    logger.info(
        f"Initializing DCE workspace with {len(registry.ids())} data source(s): "
        f"{', '.join(registry.ids())}"
    )

    for row in await run_in_threadpool(_check_connections):
        logger.info(f"  {row['name']}: {row['status']}" + (f" ({row['detail']})" if row["detail"] else ""))

    try:
        await run_in_threadpool(history_service.init_db)
    except Exception as e:
        logger.warning(f"History service db init deferred or failed: {e}")

    try:
        await run_in_threadpool(auth_service.init_db)
    except Exception as e:
        logger.warning(f"Auth service db init deferred or failed: {e}")

    yield

    logger.info("Shutting down DCE workspace...")


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
    # Carried back by the frontend so the router can keep short follow-up
    # turns on the source that answered the previous one.
    source: Optional[str] = None
    source_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []
    # Explicit data source selection from the UI. "auto" (or omitted) lets the
    # router decide; a concrete source id overrides routing entirely.
    source: Optional[str] = None


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


class RegisterRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    confirm_password: Optional[str] = None
    role: Optional[str] = None

    # Support camelCase names sent from React
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    userName: Optional[str] = None
    confirmPassword: Optional[str] = None


class LoginRequest(BaseModel):
    username: Optional[str] = None
    userName: Optional[str] = None
    userId: Optional[str] = None
    password: Optional[str] = None


# Endpoints

# -------------------------------------------------------------
# User Authentication & Registration Endpoints
# -------------------------------------------------------------

@app.get("/api/auth/check-username")
async def check_username(username: str = Query(..., description="Username to verify")):
    """
    Check if a username is already taken.
    """
    exists = await run_in_threadpool(auth_service.check_username_exists, username)
    return {"exists": exists, "username": username}


@app.post("/api/auth/register")
async def register_user_endpoint(payload: RegisterRequest):
    """
    Register a new user in the MySQL users table.
    """
    first_name = payload.first_name or payload.firstName
    last_name = payload.last_name or payload.lastName
    username = payload.username or payload.userName
    password = payload.password
    confirm_password = payload.confirm_password or payload.confirmPassword
    role = payload.role

    result = await run_in_threadpool(
        auth_service.register_user,
        first_name=first_name,
        last_name=last_name,
        username=username,
        password=password,
        confirm_password=confirm_password,
        role=role
    )

    if not result.get("success"):
        # If conflict / duplicate username
        if "already taken" in result.get("error", "").lower() or "already exists" in result.get("error", "").lower():
            raise HTTPException(status_code=409, detail=result.get("error"))
        raise HTTPException(status_code=400, detail=result.get("error"))

    return {"status": "success", "message": "User registered successfully", "user": result.get("user")}


@app.post("/api/auth/login")
async def login_user_endpoint(payload: LoginRequest):
    """
    Authenticate a user with username and password.
    """
    username = payload.username or payload.userName or payload.userId
    password = payload.password

    result = await run_in_threadpool(
        auth_service.authenticate_user,
        username=username,
        password=password
    )

    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid username or password"))

    return {"status": "success", "message": "Login successful", "user": result.get("user")}

@app.get("/api/")
@app.get("/api")
@app.get("/")
async def read_root():
    # Two forms: `provider_short` is what the sidebar shows, `provider` carries
    # the full model id for the tooltip and for logs. The UI needs a name it can
    # render in a narrow column, not a fully-qualified model identifier.
    if llm_service.provider == "groq":
        provider_short = "Groq"
        provider = f"Groq ({settings.GROQ_MODEL})"
    elif llm_service.provider == "claude":
        provider_short = "Bedrock" if llm_service.is_bedrock else "Anthropic"
        provider = f"Claude via {provider_short} ({llm_service.claude_model})"
    else:
        provider_short = "Not configured"
        provider = "Not configured"

    # Data source probes use blocking client libraries, so they're offloaded to
    # a thread pool; the LLM check is native async.
    connections, llm_health = await asyncio.gather(
        run_in_threadpool(_check_connections),
        llm_service.check_llm_health(),
    )

    return {
        "status": "online",
        "provider": provider,
        "connections": connections,
        "sources": registry.public_catalogue(),
        "provider_short": provider_short,
        "llm": {
            "name": provider_short,
            "full_name": provider,
            "status": llm_health["status"],
            "detail": llm_health["detail"],
        },
        "dce_service": " + ".join(f"{c.id}({c.kind})" for c in registry.all()),
        "platform": " + ".join(c.label for c in registry.all()),
    }


@app.get("/api/sources")
async def list_sources():
    """
    Data source catalogue for the UI source selector.

    `auto` is offered alongside the real sources: it lets the user defer to the
    router, which is the default.
    """
    return {
        "default": registry.default_source_id,
        "auto_supported": True,
        "sources": registry.public_catalogue(),
    }


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for taking natural language prompts, calling LLM + DCE,
    and returning formatted responses with MySQL data.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if request.source and request.source not in ("auto",) and registry.get(request.source) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown data source '{request.source}'. Known: "
                   f"{', '.join(['auto'] + registry.ids())}",
        )

    logger.info(
        f"Received chat request (DCE): {request.message} "
        f"[source={request.source or 'auto'}]"
    )

    # Route to a data source, then run that source's prompt-execution loop
    response_data = await llm_service.process_chat(
        request.message, request.history, requested_source=request.source
    )
    return response_data


@app.get("/api/schema")
async def schema_endpoint(source: Optional[str] = Query(None)):
    """
    Exposes a data source's schema to the frontend explorer.

    Defaults to the primary source when `source` is omitted, so existing
    callers keep the response they had before multi-source support.
    """
    source_id = source or registry.default_source_id
    ctx = registry.get(source_id)
    if ctx is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown data source '{source_id}'. Known: {', '.join(registry.ids())}",
        )

    logger.info(f"Fetching schema info for source '{source_id}'...")
    try:
        schema_overview = await run_in_threadpool(ctx.adapter.get_schema_overview)
    except Exception as e:
        logger.error(f"Failed to read schema for '{source_id}': {e}")
        schema_overview = f"Could not read schema for {ctx.label}. Error: {e}"

    return {"source": source_id, "label": ctx.label, "schema": schema_overview}


# -------------------------------------------------------------
# Chat History Management Endpoints (MySQL-backed)
# -------------------------------------------------------------

@app.get("/api/chats")
async def list_chats(
    user_id: Optional[str] = Query(None),
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
