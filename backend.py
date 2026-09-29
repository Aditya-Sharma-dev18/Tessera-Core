import os
import uuid
import certifi
import asyncio

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage,SystemMessage,AIMessage,AnyMessage
from dotenv import load_dotenv
from pyscopy import binary, pool
from typing import TypedDict,Literal,Annotated,Optional
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



