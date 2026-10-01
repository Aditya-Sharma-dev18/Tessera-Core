import sys
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

import os
import re
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from tavily import TavilyClient
from dotenv import load_dotenv

from utils.deep_links import DeepLinkGenerator

load_dotenv()


class RawBus(BaseModel):
    operator_name: str = Field(description="Name of the bus operator or state transport corporation")
    bus_type: Optional[str] = Field(default="Intercity Bus", description="Type of bus: AC Sleeper, Volvo, Seater, etc.")
    departure_time: Optional[str] = Field(default=None, description="Departure time e.g. 21:00 or Frequent Service")
    duration_hours: Optional[str] = Field(default=None, description="Total journey time e.g. 5h 30m")
    estimated_price_inr: Optional[float] = Field(default=None, description="Per person one-way fare in INR")


class BusSearchModel(BaseModel):
    buses: List[RawBus] = Field(default_factory=list, description="List of authentic buses found")


def _to_num(value) -> Optional[float]:
    if value is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(value))
        val = float(cleaned) if cleaned else None
        return val if (val is not None and val > 0) else None
    except (ValueError, TypeError):
        return None


@tool
def search_buses(origin_city: str, destination_city: str, travel_date: str) -> str:
    """
    Search authentic intercity bus options strictly from live search results.
    Never invents fake fares, fake durations, or fake operators.
    """
    tavily_key = os.getenv("TAVILY_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    from_city = origin_city.strip().title()
    to_city = destination_city.strip().title()
    deep_link = DeepLinkGenerator.get_bus_link(from_city, to_city, travel_date)

    if not tavily_key or not groq_key:
        return json.dumps({
            "origin": from_city,
            "destination": to_city,
            "travel_date": travel_date,
            "total_found": 0,
            "recommended_buses": [],
            "booking_url": deep_link,
            "error": "API keys missing"
        })

    try:
        tavily = TavilyClient(api_key=tavily_key)
        query = f"{from_city} to {to_city} bus ticket fare timetable state transport roadways redbus"
        search_res = tavily.search(query=query, search_depth="basic", max_results=3)

        context_snippets = "\n".join(
            [(r.get("content") or "") for r in search_res.get("results", [])]
        )

        if not context_snippets.strip():
            return json.dumps({
                "origin": from_city,
                "destination": to_city,
                "travel_date": travel_date,
                "total_found": 0,
                "recommended_buses": [],
                "booking_url": deep_link
            })

        llm = ChatGroq(
            model="openai/gpt-oss-20b",
            api_key=groq_key,
            temperature=0.0,
            max_tokens=3072,
        )

        extraction_prompt = f"""You are a strict data extraction parser. Extract up to 4 verified bus details between {from_city} and {to_city} from the search snippets.

SEARCH SNIPPETS:
{context_snippets[:3000]}

STRICT EXTRACTION RULES:
1. OPERATORS: Extract up to 4 real operator names explicitly mentioned in the text (e.g. State Roadways / private operators).
2. TIMINGS & DURATION: Extract departure time and duration ONLY if stated. Otherwise leave None.
3. PRICING: Extract numeric fare in INR ONLY if stated. Do not guess.
"""
        structured_llm = llm.with_structured_output(BusSearchModel)
        parsed_result: BusSearchModel = structured_llm.invoke([
            {"role": "system", "content": "Extract verified bus schedules from search snippets."},
            {"role": "user", "content": extraction_prompt}
        ])

        buses = []
        seen = set()
        for b in parsed_result.buses:
            op = (b.operator_name or "").strip()
            if not op or op.lower() in seen:
                continue
            seen.add(op.lower())

            price = _to_num(b.estimated_price_inr)
            buses.append({
                "operator_name": op,
                "bus_type": b.bus_type or "Intercity Bus",
                "departure_time": str(b.departure_time) if b.departure_time else "Frequent Service",
                "duration_hours": str(b.duration_hours) if b.duration_hours else None,
                "estimated_price_inr": price,
                "price_is_estimate": price is None,
                "booking_url": deep_link,
            })

        return json.dumps({
            "origin": from_city,
            "destination": to_city,
            "travel_date": travel_date,
            "total_found": len(buses),
            "recommended_buses": buses[:3],
            "booking_url": deep_link,
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "origin": from_city,
            "destination": to_city,
            "travel_date": travel_date,
            "total_found": 0,
            "recommended_buses": [],
            "error": str(e),
            "booking_url": deep_link
        }, ensure_ascii=False)