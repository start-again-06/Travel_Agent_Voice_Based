
import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env before imports
load_dotenv()

from app.agent.mcp_client import MCPClientManager
from app.agent.graph import create_agent_graph, get_system_message

from langgraph.checkpoint.memory import MemorySaver

async def main():
    print("Initializing Voice Travel Agent...")

    # Log LangSmith configuration
    import os
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        print(f"LangSmith tracing: ENABLED (Project: {os.getenv('LANGSMITH_PROJECT', 'default')})")
    else:
        print("LangSmith tracing: DISABLED")

    # 1. Setup MCP Clients
    mcp_manager = MCPClientManager()
    
    try:
        # Start Servers
        await mcp_manager.connect_to_server("poi", "app.mcp_servers.poi_search")
        await mcp_manager.connect_to_server("itinerary", "app.mcp_servers.itinerary")
        await mcp_manager.connect_to_server("weather", "app.mcp_servers.weather")
        
        print("Connected to MCP Servers.")
        
        # 2. Get Tools
        tools = await mcp_manager.get_langchain_tools()
        
        # Add RAG tool
        # Wrapping import in try/except to avoid crash if dependencies not ready yet
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
        except ImportError:
            print("Warning: RAG module dependencies missing. RAG tool disabled.")

        # 3. Build Agent with Checkpointer
        checkpointer = MemorySaver()
        # Note: create_agent_graph needs modification to accept checkpointer or we act differently?
        # create_react_agent accepts checkpointer. StateGraph.compile(checkpointer=...)
        # I need to modify create_agent_graph in app/agent/graph.py too.

        # Let's import the builder and compile here or modify the function.
        # I'll let create_agent_graph take an optional checkpointer.
        from app.agent.graph import create_agent_graph
        base_agent = create_agent_graph(tools, checkpointer=checkpointer)

        # Wrap agent with evaluations (doesn't change functionality)
        from app.agent.evaluated_agent import EvaluatedAgentWrapper
        agent = EvaluatedAgentWrapper(base_agent)
        
        # 4. Chat Loop
        print("\n--- Travel Agent Ready (Type 'quit' to exit) ---\n")
        
        thread_id = "session-1"
        config = {"configurable": {"thread_id": thread_id}}
        
        # Initial system message needs to be set.
        # With persistence, we only send NEW messages.
        
        # First run: Initialize system message if history is empty?
        # LangGraph handles this if we pass system message as input. 
        # But for persistent graph, we usually set SystemMessage in the graph definition or State 0.
        # Here I'll just rely on "Add Messages" behavior.
        
        from langchain_core.messages import SystemMessage
        from app.agent.prompts import PLANNER_SYSTEM_PROMPT
        
        # Send system message once (if new session) is tricky in Loop.
        # Actually my graph definition hardcoded `chatbot` node invocation? No.
        # My graph calls `llm_with_tools.invoke(state["messages"])`.
        
        # I'll just prepend SystemMessage to the first user input?
        # Or better: check history.
        
        first_turn = True
        
        while True:
            user_input = input("You: ")
            if user_input.lower() in ["quit", "exit"]:
                break
            
            input_messages = [("user", user_input)]
            if first_turn:
                 input_messages.insert(0, SystemMessage(content=PLANNER_SYSTEM_PROMPT))
                 first_turn = False
            
            print("Agent: ", end="", flush=True)
            
            async for event in agent.astream({"messages": input_messages}, config=config, stream_mode="updates"):
                for node, values in event.items():
                    if node == "chatbot":
                        last_msg = values["messages"][-1]
                        if last_msg.content:
                            print(last_msg.content)
                        elif last_msg.tool_calls:
                            print(f"[Calling Tools: {[tc['name'] for tc in last_msg.tool_calls]}]...")
                    elif node == "tools":
                        print(f"[Tool Output Received]")
            
    finally:
        await mcp_manager.cleanup()
        print("Shutdown complete.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
