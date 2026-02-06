
import logging
import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import StructuredTool

from app.agent.graph import create_agent_graph
from app.agent.mcp_client import MCPClientManager

logger = logging.getLogger("agent-factory")


class AgentFactory:
    """Singleton factory for creating and managing the agent instance."""

    _instance: Optional["AgentFactory"] = None
    _agent = None
    _mcp_manager: Optional[MCPClientManager] = None
    _checkpointer: Optional[MemorySaver] = None
    _exit_stack: Optional[AsyncExitStack] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def initialize(cls):
        """Initialize the agent with MCP servers and tools."""
        if cls._agent is not None:
            logger.info("Agent already initialized")
            return cls._agent

        logger.info("Initializing agent...")

        # Initialize MCP manager
        cls._mcp_manager = MCPClientManager()
        cls._exit_stack = AsyncExitStack()

        # Connect to MCP servers in parallel for faster startup
        logger.info("Connecting to MCP servers in parallel...")
        await asyncio.gather(
            cls._mcp_manager.connect_to_server("poi", "app.mcp_servers.poi_search"),
            cls._mcp_manager.connect_to_server("itinerary", "app.mcp_servers.itinerary"),
            cls._mcp_manager.connect_to_server("weather", "app.mcp_servers.weather"),
        )
        logger.info("All MCP servers connected")
        # Note: Email is handled via API endpoint, not MCP server

        # Get tools from MCP servers
        tools = await cls._mcp_manager.get_langchain_tools()
        logger.info(f"Loaded {len(tools)} tools from MCP servers")

        # Add RAG tool
        try:
            from app.rag.retrieve import retrieve_context, RetrieveContextInput

            rag_tool = StructuredTool.from_function(
                func=retrieve_context,
                name="retrieve_travel_guides",
                description="Retrieve travel tips, safety info, and cultural context from Wikivoyage.",
                args_schema=RetrieveContextInput,
            )
            tools.append(rag_tool)
            logger.info(f"Added RAG tool (total: {len(tools)} tools)")
        except ImportError as e:
            logger.warning(f"RAG module dependencies missing: {e}")

        # Create checkpointer for conversation persistence
        cls._checkpointer = MemorySaver()

        # Create base agent
        base_agent = create_agent_graph(tools, checkpointer=cls._checkpointer)

        # Wrap with evaluations (doesn't change functionality, just adds background evaluations)
        from app.agent.evaluated_agent import EvaluatedAgentWrapper
        cls._agent = EvaluatedAgentWrapper(base_agent)

        logger.info("Agent initialized successfully (with evaluations)")

        return cls._agent

    @classmethod
    async def get_agent(cls):
        """Get the agent instance, initializing if necessary."""
        if cls._agent is None:
            await cls.initialize()
        return cls._agent

    @classmethod
    async def cleanup(cls):
        """Clean up resources."""
        logger.info("Cleaning up agent resources...")
        if cls._mcp_manager:
            await cls._mcp_manager.cleanup()
        if cls._exit_stack:
            await cls._exit_stack.aclose()
        cls._agent = None
        cls._mcp_manager = None
        cls._checkpointer = None
        cls._exit_stack = None
        logger.info("Cleanup complete")
