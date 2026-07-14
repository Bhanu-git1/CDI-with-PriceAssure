import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import settings

logger = logging.getLogger("mcp-client")

class MCPSalesforceClient:
    """Manages the lifecycle and calls to the local FastMCP Salesforce server."""
    
    def __init__(self):
        # Resolve the absolute path to the salesforce_server.py file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Up one level, then to mcp_server/salesforce_server.py
        server_path = os.path.abspath(os.path.join(current_dir, "..", "mcp_server", "salesforce_server.py"))
        
        # Build environment variables for the MCP subprocess
        env_vars = {
            **os.environ,
            "SF_USERNAME": settings.SF_USERNAME,
            "SF_PASSWORD": settings.SF_PASSWORD,
            "SF_SECURITY_TOKEN": settings.SF_SECURITY_TOKEN,
            "SF_DOMAIN": settings.SF_DOMAIN,
        }

        # Pass session-based credentials if available (for Salesforce frontend context)
        if settings.SF_SESSION_ID:
            env_vars["SF_SESSION_ID"] = settings.SF_SESSION_ID
        if settings.SF_INSTANCE_URL:
            env_vars["SF_INSTANCE_URL"] = settings.SF_INSTANCE_URL

        # Configure connection to the server via stdio
        self.server_params = StdioServerParameters(
            command=sys.executable,  # runs with the same python interpreter
            args=[server_path],
            env=env_vars
        )
        self._session = None
        self._exit_stack = None

    async def start(self):
        """Starts the MCP server process and initializes the connection session."""
        if self._session:
            return
            
        logger.info("Starting local FastMCP Salesforce server...")
        try:
            # We manage stdio client lifecycle
            self._stdio_ctx = stdio_client(self.server_params)
            read_stream, write_stream = await self._stdio_ctx.__aenter__()
            
            # Start the client session
            self._session_ctx = ClientSession(read_stream, write_stream)
            self._session = await self._session_ctx.__aenter__()
            
            # Initialize connection
            await self._session.initialize()
            logger.info("Successfully connected to MCP Salesforce server.")
            
        except Exception as e:
            logger.error(f"Failed to launch or connect to MCP server: {e}")
            await self.stop()
            raise e

    async def stop(self):
        """Stops the MCP server and cleans up processes/streams."""
        logger.info("Stopping MCP connection...")
        if hasattr(self, "_session_ctx") and self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error exiting session: {e}")
            self._session = None
            
        if hasattr(self, "_stdio_ctx") and self._stdio_ctx:
            try:
                await self._stdio_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error exiting stdio process: {e}")
            self._stdio_ctx = None

    async def list_tools(self):
        """Fetch all tools exposed by the MCP server."""
        if not self._session:
            await self.start()
        return await self._session.list_tools()

    async def execute_tool(self, name: str, arguments: dict):
        """Execute a tool on the MCP server."""
        if not self._session:
            await self.start()
        logger.info(f"Invoking MCP tool '{name}' with arguments: {arguments}")
        result = await self._session.call_tool(name, arguments)
        # FastMCP tools return results inside a content list
        if result and hasattr(result, 'content') and len(result.content) > 0:
            return result.content[0].text
        return str(result)

    async def read_resource(self, uri: str):
        """Read a schema/data resource from the MCP server."""
        if not self._session:
            await self.start()
        logger.info(f"Reading MCP resource '{uri}'")
        result = await self._session.read_resource(uri)
        if result and hasattr(result, 'contents') and len(result.contents) > 0:
            return result.contents[0].text
        return str(result)

# Single global client instance
sf_mcp_client = MCPSalesforceClient()
