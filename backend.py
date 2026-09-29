import os
import uuid
import certifi
import asyncio
import operator

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage,SystemMessage,AIMessage,AnyMessage
from dotenv import load_dotenv
from pyscopy import binary, pool
from typing import TypedDict,Literal,Annotated,Optional,List,Any
from psycopy.rows import dict_row
from langgraph.graph import START,END

os.environ["SSL_CERT_FILE"]=certifi.where()   #tells the python env where to take the ca while doing ssl /https req
os.environ["REQUESTS_CA_BUNDLE"]=certifi.where()
from psycopy import ConnectionPool
from pydantic import BaseModel,Field,
from tools.flight_tool  import search_flights
from tools.bus_tool import search_buses
from tools.rails_tool import search_trains


def get_database_url():
    database_url=os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("database url not found in the env file")
    if "sslmode=" not in database_url:
        seperator="&" if "?" in database_url else "?"
        database_url=f"{database_url}{seperator}sslmode=require"
    return database_url



guardrails_model=ChatGroq(
    model="meta-llama/llama-prompt-guard-2-8b",
    temperature=0
)

supervisor_model=ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0
)
budget_model=ChatGroq(
    model="qwen/qwen3.8-27b",
    temperature=0
)
iterinary_model=ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0
)
final_agent=ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0
)

parsing_model=ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0
)

class TravelState(TypedDict):
    # Guardrail checks
    guardrail_allowed: bool       # Whether the request passed safety checks
    guardrail_reason: str         # Reason for allowing/rejecting the request

    # User input and constraints
    user_query: str               # Original user query
    trip_constraints: dict[str, Any]  # Extracted trip requirements

    # Supervisor routing
    selected_agents: list[str]    # Agents selected for this task
    supervisor_reasoning: str     # Reasoning behind agent selection

    # Travel research results
    flight_results: str           # Flight search results
    rails_results: str            # Railway search results
    bus_results: str              # Bus search results
    hotel_results: str             # Hotel search results
    weather_results: str           # Weather information
    budget_results: str            # Estimated trip budget
    itinerary: str                # Generated travel itinerary

    # Human-in-the-loop approval
    human_feedback: str           # Feedback provided by the human
    approved: str                  # Approval status: pending/approved/rejected
    approval_request: str          # Approval request shown to the human

    # Conversation history
    
    messages: Annotated[List[AnyMessage], operator.add]

    # Final response
    final_response: str            # Final response returned to the user