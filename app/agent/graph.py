
import os
import logging
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from .prompts import (
    get_clarifying_prompt,
    get_planning_prompt,
    get_reviewing_prompt,
    PLANNER_SYSTEM_PROMPT
)

logger = logging.getLogger("agent-graph")

class State(TypedDict):
    messages: Annotated[list, add_messages]

def create_agent_graph(tools, checkpointer=None):
    # Initialize LLM
    llm = ChatGroq(
        model="qwen/qwen3-32b",
        api_key=os.environ.get("GROQ_API_KEY"),
        temperature=0.5,
        max_tokens=None,
        timeout=None,
        max_retries=2,
    )

    # Bind tools with parallel tool calling disabled to reduce iterations
    llm_with_tools = llm.bind_tools(tools, parallel_tool_calls=False)
    
    # Define Nodes
    def chatbot(state: State):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}
    
    # Build Graph
    graph_builder = StateGraph(State)
    
    graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("tools", ToolNode(tools=tools))
    
    graph_builder.add_edge(START, "chatbot")
    graph_builder.add_conditional_edges(
        "chatbot",
        tools_condition,
    )
    graph_builder.add_edge("tools", "chatbot")

    # Compile with recursion limit to prevent excessive tool calls
    return graph_builder.compile(
        checkpointer=checkpointer,
        debug=False
    )

def get_system_message():
    return SystemMessage(content=PLANNER_SYSTEM_PROMPT)
