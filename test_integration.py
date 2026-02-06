
import asyncio
import sys
import os
import io
from dotenv import load_dotenv

load_dotenv()

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.agent.mcp_client import MCPClientManager
from app.agent.graph import create_agent_graph
from app.agent.evaluated_agent import EvaluatedAgentWrapper
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage
from app.agent.prompts import PLANNER_SYSTEM_PROMPT

async def test_integration():
    print("=" * 70)
    print("Testing Integration")
    print("=" * 70)
    print("\n[1] Setting up MCP clients...")
    mcp_manager = MCPClientManager()

    try:
        await mcp_manager.connect_to_server("poi", "app.mcp_servers.poi_search")
        await mcp_manager.connect_to_server("itinerary", "app.mcp_servers.itinerary")
        await mcp_manager.connect_to_server("weather", "app.mcp_servers.weather")
        print("[OK] Connected to MCP servers")

        tools = await mcp_manager.get_langchain_tools()
        print(f"[OK] Loaded {len(tools)} tools")

        try:
            from app.rag.retrieve import retrieve_context, RetrieveContextInput
            from langchain_core.tools import StructuredTool

            rag_tool = StructuredTool.from_function(
                func=retrieve_context,
                name="retrieve_travel_guides",
                description="Retrieve travel tips from Wikivoyage.",
                args_schema=RetrieveContextInput
            )
            tools.append(rag_tool)
            print(f"[OK] Added RAG tool (total: {len(tools)} tools)")
        except ImportError:
            print("[WARN] RAG module dependencies missing")

        print("\n[2] Creating agent with evaluations...")
        checkpointer = MemorySaver()
        base_agent = create_agent_graph(tools, checkpointer=checkpointer)

        agent = EvaluatedAgentWrapper(base_agent)
        print("[OK] Agent created with evaluation wrapper")

        print("\n[3] Testing agent...")
        thread_id = "test-session"
        config = {"configurable": {"thread_id": thread_id}}

        print("\nSending test query: 'Create a 1-day itinerary for Paris'")

        input_messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            ("user", "Create a 1-day itinerary for Paris starting tomorrow. I like museums and food.")
        ]

        response_count = 0
        async for event in agent.astream({"messages": input_messages}, config=config, stream_mode="updates"):
            response_count += 1
            for node, values in event.items():
                if node == "chatbot":
                    last_msg = values["messages"][-1]
                    if hasattr(last_msg, "content") and last_msg.content:
                        print(f"\n[Agent Response #{response_count}]")
                        # Print first 200 chars
                        content = last_msg.content
                        if len(content) > 200:
                            print(content[:200] + "...")
                        else:
                            print(content)

        print("\n" + "=" * 70)
        print("Test Results:")
        print("=" * 70)
        print("[OK] Agent responded without errors")
        print("[OK] Evaluation wrapper did not break existing functionality")

        if os.path.exists("evaluation_results.json"):
            print("[OK] Evaluation results file created: evaluation_results.json")
            import json
            with open("evaluation_results.json", "r") as f:
                results = json.load(f)
                overall = results.get("overall", {})
                print(f"  - Evaluations run: {overall.get('total_evals', 0)}")
                print(f"  - Passed: {overall.get('passed_evals', 0)}")
                print(f"  - Failed: {overall.get('failed_evals', 0)}")
        else:
            print("[WARN] Evaluation results file not created yet (may run after completion)")

        print("\n[OK] Integration test complete!")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await mcp_manager.cleanup()
        print("\nCleanup complete.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_integration())
