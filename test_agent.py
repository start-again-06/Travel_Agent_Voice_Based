import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env before imports
load_dotenv()

from app.agent.mcp_client import MCPClientManager
from app.agent.graph import create_agent_graph
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage
from app.agent.prompts import PLANNER_SYSTEM_PROMPT

async def test_agent():
    print("=== Testing Voice Travel Agent ===\n")

    # 1. Setup MCP Clients
    mcp_manager = MCPClientManager()

    try:
        # Start Servers
        print("Connecting to MCP servers...")
        await mcp_manager.connect_to_server("poi", "app.mcp_servers.poi_search")
        await mcp_manager.connect_to_server("itinerary", "app.mcp_servers.itinerary")
        await mcp_manager.connect_to_server("weather", "app.mcp_servers.weather")
        print("[OK] Connected to MCP Servers.\n")

        # 2. Get Tools
        tools = await mcp_manager.get_langchain_tools()
        print(f"[OK] Loaded {len(tools)} tools from MCP servers")

        # Add RAG tool
        try:
            from app.rag.retrieve import retrieve_context, RetrieveContextInput
            from langchain_core.tools import StructuredTool

            rag_tool = StructuredTool.from_function(
                func=retrieve_context,
                name="retrieve_travel_guides",
                description="Retrieve travel tips, safety info, and cultural context from Wikivoyage.",
                args_schema=RetrieveContextInput
            )
            tools.append(rag_tool)
            print(f"[OK] Added RAG tool (total: {len(tools)} tools)\n")
        except ImportError as e:
            print(f"[WARN] Warning: RAG module dependencies missing: {e}\n")

        # Print available tools
        print("Available tools:")
        for i, tool in enumerate(tools, 1):
            print(f"  {i}. {tool.name}: {tool.description[:60]}...")
        print()

        # 3. Build Agent with Checkpointer
        checkpointer = MemorySaver()
        agent = create_agent_graph(tools, checkpointer=checkpointer)
        print("[OK] Agent graph compiled successfully\n")

        # 4. Test the agent with a simple query
        print("=" * 60)
        print("TEST 1: Simple travel query")
        print("=" * 60)

        thread_id = "test-session-1"
        config = {"configurable": {"thread_id": thread_id}}

        test_query = "I want to visit Paris for 2 days. Can you suggest some must-see attractions?"

        input_messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            ("user", test_query)
        ]

        print(f"\nUser: {test_query}\n")
        print("Agent: ", end="", flush=True)

        full_response = []

        async for event in agent.astream({"messages": input_messages}, config=config, stream_mode="updates"):
            for node, values in event.items():
                if node == "chatbot":
                    last_msg = values["messages"][-1]
                    if last_msg.content:
                        print(last_msg.content)
                        full_response.append(last_msg.content)
                    elif last_msg.tool_calls:
                        tool_names = [tc['name'] for tc in last_msg.tool_calls]
                        print(f"\n[Calling Tools: {tool_names}]")
                elif node == "tools":
                    print("[Tool execution completed]")

        print("\n" + "=" * 60)
        print("TEST RESULT")
        print("=" * 60)

        if full_response:
            print("[OK] Agent successfully generated output!")
            print(f"[OK] Response length: {len(' '.join(full_response))} characters")
            print("\n[SUCCESS] AGENT IS WORKING CORRECTLY")
        else:
            print("[ERROR] Agent did not generate a response")
            print("[ERROR] AGENT HAS ISSUES")

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await mcp_manager.cleanup()
        print("\nTest complete. Shutdown successful.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_agent())
