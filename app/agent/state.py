from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class DayPlan(TypedDict):
    day: int
    activities: List[Dict[str, Any]] # {time, place, description, lat, lon}
    summary: str

class Itinerary(TypedDict):
    title: str
    days: List[DayPlan]
    meta: Dict[str, Any] # {total_cost_est, ...}

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_preferences: Dict[str, Any] # {destination, start_date, duration_days, interests, budget}
    itinerary: Itinerary
    dialog_state: str # "COLLECTING_INFO", "PLANNING", "REVIEWING", "EDITING"
    error: str
