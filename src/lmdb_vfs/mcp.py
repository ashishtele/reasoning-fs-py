"""MCP (Model Context Protocol) server for VFS.

Industry-standard protocol that agents (Cursor, Claude, etc.) already speak.
Enables seamless integration with MCP-compatible agents.

See: https://modelcontextprotocol.io/
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from .vfs import VFS
from .shell import VFSShell
from .errors import VFSError, FileNotFound


# Optional aiohttp import for async server
try:
    import aiohttp
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    web = None


@dataclass
class MCPSchema:
    """MCP tool schema for VFS operations."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


# MCP Tool Definitions
MCP_TOOLS = [
    MCPSchema(
        name="read_file",
        description="Read the contents of a file",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"}
            },
            "required": ["path"]
        }
    ),
    MCPSchema(
        name="write_file",
        description="Write content to a file",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["path", "content"]
        }
    ),
    MCPSchema(
        name="list_directory",
        description="List directory contents",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"}
            },
            "required": ["path"]
        }
    ),
    MCPSchema(
        name="search_files",
        description="Find files matching a pattern",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.py')"},
                "path": {"type": "string", "description": "Search path (optional)"}
            },
            "required": ["pattern"]
        }
    ),
    MCPSchema(
        name="search_content",
        description="Search for text pattern in files",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text pattern to search"},
                "path": {"type": "string", "description": "Search path (optional)"}
            },
            "required": ["pattern"]
        }
    ),
    MCPSchema(
        name="create_directory",
        description="Create a new directory",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to create"}
            },
            "required": ["path"]
        }
    ),
    MCPSchema(
        name="delete_file",
        description="Delete a file",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to delete"}
            },
            "required": ["path"]
        }
    ),
    MCPSchema(
        name="shell_command",
        description="Execute a UNIX shell command (ls, cat, grep, find, cd, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command (e.g., 'ls /docs', 'grep pattern')"}
            },
            "required": ["command"]
        }
    ),
]


class MCPVFS:
    """MCP-compatible VFS server.
    
    Implements the Model Context Protocol for seamless agent integration.
    
    Example:
        >>> vfs = VFS("db.lmdb")
        >>> mcp = MCPVFS(vfs)
        >>> await mcp.handle_request({
        ...     "jsonrpc": "2.0",
        ...     "id": 1,
        ...     "method": "initialize",
        ...     "params": {"protocolVersion": "2024-11-05"}
        ... })
    """
    
    def __init__(self, vfs: VFS):
        """Initialize MCP server with VFS backend.
        
        Args:
            vfs: VFS instance to use for operations.
        """
        self.vfs = vfs
        self.shell = VFSShell(vfs)
        self._initialized = False
        self._client_info = {}
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an incoming MCP request.
        
        Args:
            request: MCP request object (JSON-RPC format).
        
        Returns:
            MCP response object.
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        # Route to appropriate handler
        if method == "initialize":
            return await self._handle_initialize(request)
        elif method == "initialized":
            return await self._handle_initialized(request)
        elif method == "tools/list":
            return await self._handle_tools_list(request)
        elif method == "tools/call":
            return await self._handle_tools_call(request, params)
        elif method == "resources/list":
            return await self._handle_resources_list(request)
        elif method == "resources/read":
            return await self._handle_resources_read(request, params)
        else:
            return self._error(request_id, -32601, f"Method not found: {method}")
    
    async def _handle_initialize(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        self._initialized = True
        self._client_info = request.get("params", {})
        
        return self._result(request.get("id"), {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "logging": {}
            },
            "serverInfo": {
                "name": "lmdb-vfs-mcp",
                "version": "0.2.0"
            }
        })
    
    async def _handle_initialized(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialized notification."""
        return self._result(request.get("id"), None)
    
    async def _handle_tools_list(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request."""
        return self._result(request.get("id"), {
            "tools": [asdict(t) for t in MCP_TOOLS]
        })
    
    async def _handle_tools_call(self, request: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "read_file":
                content = self.vfs.read(arguments["path"])
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": content}]
                })
            
            elif tool_name == "write_file":
                self.vfs.write(arguments["path"], arguments["content"])
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": f"Successfully wrote to {arguments['path']}"}]
                })
            
            elif tool_name == "list_directory":
                items = self.vfs.listdir(arguments["path"])
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": "\n".join(items)}]
                })
            
            elif tool_name == "search_files":
                results = self.vfs.find(arguments["pattern"], arguments.get("path"))
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": "\n".join(results)}]
                })
            
            elif tool_name == "search_content":
                results = self.vfs.grep(arguments["pattern"], arguments.get("path"))
                formatted = [f"{p}:{ln}:{line}" for p, ln, line in results]
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": "\n".join(formatted)}]
                })
            
            elif tool_name == "create_directory":
                self.vfs.mkdir(arguments["path"])
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": f"Created directory {arguments['path']}"}]
                })
            
            elif tool_name == "delete_file":
                self.vfs.delete(arguments["path"])
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": f"Deleted {arguments['path']}"}]
                })
            
            elif tool_name == "shell_command":
                result = self.shell.execute(arguments["command"])
                if isinstance(result, list):
                    result = "\n".join(str(r) for r in result)
                return self._result(request.get("id"), {
                    "content": [{"type": "text", "text": str(result)}]
                })
            
            else:
                return self._error(request.get("id"), -32602, f"Unknown tool: {tool_name}")
        
        except FileNotFound as e:
            return self._error(request.get("id"), -32000, f"File not found: {e}")
        except VFSError as e:
            return self._error(request.get("id"), -32000, str(e))
        except Exception as e:
            return self._error(request.get("id"), -32000, f"Internal error: {e}")
    
    async def _handle_resources_list(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/list request."""
        # List all files as resources
        all_files = self.vfs.find("*", ".")
        return self._result(request.get("id"), {
            "resources": [
                {
                    "uri": f"vfs://{f}",
                    "name": f,
                    "mimeType": "text/plain"
                }
                for f in all_files
            ]
        })
    
    async def _handle_resources_read(self, request: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri", "")
        # Extract path from vfs:// URI
        path = uri.replace("vfs://", "")
        
        try:
            content = self.vfs.read(path)
            return self._result(request.get("id"), {
                "contents": [{
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": content
                }]
            })
        except FileNotFound:
            return self._error(request.get("id"), -32000, f"Resource not found: {uri}")
    
    def _result(self, request_id: Any, result: Any) -> Dict[str, Any]:
        """Create a successful response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }
    
    def _error(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }


class AsyncMCPVFS(MCPVFS):
    """Async MCP server with HTTP/WebSocket support."""
    
    def __init__(self, vfs: VFS, host: str = "127.0.0.1", port: int = 8000):
        """Initialize async MCP server.
        
        Args:
            vfs: VFS instance to use for operations.
            host: Server host.
            port: Server port.
        """
        super().__init__(vfs)
        self.host = host
        self.port = port
        self.server = None
    
    async def start(self):
        """Start the MCP server."""
        if not HAS_AIOHTTP:
            raise ImportError("aiohttp is required for async server. Install with: pip install aiohttp")
        
        app = web.Application()
        app.router.add_post("/mcp", self._handle_http)
        app.router.add_get("/mcp", self._handle_websocket)
        
        self.server = await web._run_app(app, host=self.host, port=self.port)
    
    async def _handle_http(self, request: web.Request) -> web.Response:
        """Handle HTTP MCP requests."""
        try:
            body = await request.json()
            response = await self.handle_request(body)
            return web.json_response(response)
        except Exception as e:
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket MCP connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    request = json.loads(msg.data)
                    response = await self.handle_request(request)
                    await ws.send_json(response)
                except Exception as e:
                    await ws.send_json({"error": str(e)})
        
        return ws


def create_mcp_server(vfs: VFS, host: str = "127.0.0.1", port: int = 8000):
    """Create and start an MCP server.
    
    Convenience function to quickly spin up an MCP server.
    
    Example:
        >>> vfs = VFS("db.lmdb")
        >>> create_mcp_server(vfs)  # Runs until Ctrl+C
    """
    import asyncio
    import signal
    
    mcp = AsyncMCPVFS(vfs, host, port)
    
    def signal_handler():
        asyncio.get_event_loop().stop()
    
    signal.signal(signal.SIGINT, lambda s, f: signal_handler())
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
    
    asyncio.run(mcp.start())


# Export for convenience
__all__ = ["MCPVFS", "AsyncMCPVFS", "create_mcp_server", "MCP_TOOLS"]
