
import asyncio
import os
import sys
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.tools import Tool, StructuredTool
from pydantic import create_model 
from typing import Any, Callable

class MCPClientManager:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions = {} # name -> session

    async def connect_to_server(self, name: str, script_path: str):
        """Connect to a local python script MCP server."""
        # Use the same python executable
        python_exe = sys.executable
        
        server_params = StdioServerParameters(
            command=python_exe,
            args=["-m", script_path],
            env=os.environ.copy()
        )
        
        # Connect
        read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        
        await session.initialize()
        self.sessions[name] = session
        return session

    async def get_langchain_tools(self) -> list[StructuredTool]:
        tools = []
        for name, session in self.sessions.items():
            result = await session.list_tools()
            for tool_info in result.tools:
                # Create a dynamic function to call this tool
                async def _call_mcp_tool(**kwargs):
                    return await session.call_tool(tool_info.name, arguments=kwargs)
                
                # Create Pydantic model for schema
                # Simplified: assuming schema is compliant with Pydantic V2 dynamic creation
                # For robust implementation, we would parse json schema.
                # Here we just pass **kwargs so validation is light on client side, heavy on server side.
                
                tools.append(StructuredTool.from_function(
                    coroutine=_call_mcp_tool,
                    name=tool_info.name,
                    description=tool_info.description,
                ))
        return tools

    async def cleanup(self):
        await self.exit_stack.aclose()
