# ═══════════════════════════════════════════════════════════════════════════
#  🔧  PATH FIX & SYSTEM IMPORTS
# ═══════════════════════════════════════════════════════════════════════════
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import re
import math
import uuid
import json
import certifi
import asyncio
import operator
from datetime import datetime, timedelta
from typing import TypedDict, Literal, Annotated, Optional, List, Any, Dict

# SSL certificates configuration for secure HTTPS calls
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langgraph.types import Command, interrupt
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, AnyMessage

# Verified Tools
from tools.flight_tool import search_flights
from tools.bus_tool import search_buses
from tools.rails_tool import search_trains
from tools.weather_tool import get_weather
from tools.tavily_tool import search_hotels

load_dotenv()


# ═══════════════════════════════════════════════════════════════════════════
#  🔐  DATABASE CONFIG
# ═══════════════════════════════════════════════════════════════════════════
def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment (.env).")
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    return database_url


# ═══════════════════════════════════════════════════════════════════════════
#  🧠  LLM MODELS
# ═══════════════════════════════════════════════════════════════════════════
guardrails_model = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)
supervisor_model = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)
budget_model = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)
final_agent_model = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)
parsing_model = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)

# Added max_retries=5 to handle API 429 limits gracefully
itinerary_model = ChatGroq(model="openai/gpt-oss-120b", temperature=0.2, max_retries=5)


# ═══════════════════════════════════════════════════════════════════════════
#  🗂️  STATE SCHEMA (TravelState)
# ═══════════════════════════════════════════════════════════════════════════
class SelectedEntity(TypedDict, total=False):
    name: str
    location: str
    price: int
    booking_url: Optional[str]
    details: Dict[str, Any]


class TravelState(TypedDict):
    guardrail_allowed: bool
    guardrail_reason: str
    user_query: str
    trip_constraints: dict[str, Any]
    resolved_geo: Dict[str, Any]  # Centralized geography state
    selected_agents: list[str]
    supervisor_reasoning: str

    # Raw Research Data
    flight_results: str
    rails_results: str
    bus_results: str
    hotel_results: str
    weather_results: str
    budget_results: str

    # Frontend Typed State
    travelers_count: int
    duration_days: int
    estimated_total_inr: int
    transit_options: List[Dict[str, Any]]
    selected_hotel: Optional[SelectedEntity]
    selected_transit: Optional[SelectedEntity]

    # HITL & Output
    itinerary: str
    human_feedback: str
    approved: str
    approval_request: str
    messages: Annotated[List[AnyMessage], operator.add]
    final_response: str


# ═══════════════════════════════════════════════════════════════════════════
#  🛠️️  HELPERS & PARSERS
# ═══════════════════════════════════════════════════════════════════════════
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d")


def _parse_date(value) -> Optional[datetime]:
    if not value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def _default_travel_date() -> str:
    return (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")


def _resolve_travel_date(constraints: dict) -> str:
    raw = constraints.get("departure_date") or constraints.get("travel_date")
    parsed = _parse_date(raw)
    if parsed and parsed.date() >= datetime.now().date():
        return parsed.strftime("%Y-%m-%d")
    return _default_travel_date()


def _safe_constraints(state: TravelState) -> dict:
    constraints = state.get("trip_constraints", {})
    if isinstance(constraints, str):
        try:
            constraints = json.loads(constraints)
        except Exception:
            constraints = {"raw_constraints": constraints}
    return constraints if isinstance(constraints, dict) else {}


def _reconcile_trip_dates(constraints: dict) -> dict:
    dep_str = constraints.get("departure_date") or constraints.get("travel_date")
    ret_str = constraints.get("return_date")
    stated_days = constraints.get("duration_days") or constraints.get("days")

    parsed_dep = _parse_date(dep_str)
    parsed_ret = _parse_date(ret_str)

    if not (parsed_dep and parsed_ret):
        return constraints

    calendar_days = (parsed_ret - parsed_dep).days + 1
    if calendar_days <= 0:
        return constraints

    try:
        stated_int = int(stated_days) if stated_days else calendar_days
    except (TypeError, ValueError):
        stated_int = calendar_days

    constraints["duration_days"] = calendar_days
    if stated_days and stated_int != calendar_days:
        constraints["original_requested_days"] = stated_int
        constraints["date_conflict_resolved"] = (
            f"Selected dates ({parsed_dep.strftime('%d %b')} to {parsed_ret.strftime('%d %b')}) "
            f"span exactly {calendar_days} days."
        )
    return constraints


def _load_json(raw) -> Optional[dict]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return None
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _to_num(value, default: float = 0.0) -> float:
    try:
        cleaned = re.sub(r"[^\d.]", "", str(value))
        return float(cleaned) if cleaned else default
    except (ValueError, TypeError):
        return default


def _extract_last_mile(bus_raw) -> Optional[dict]:
    data = _load_json(bus_raw)
    if data and isinstance(data.get("last_mile_commute"), dict):
        return data["last_mile_commute"]
    return None


_LIST_KEYS = ("recommended_buses", "recommended_flights", "trains", "hotels")
_URL_KEYS = ("booking_url", "url", "title", "snippet")


def _compact_results(raw, limit_items: int = 3, keep_urls: bool = False, char_limit: int = 700) -> str:
    data = _load_json(raw)
    if data is None:
        return str(raw or "")[:char_limit] if raw else "None"

    compact: dict = {}
    if "last_mile_commute" in data:
        compact["last_mile_commute"] = data["last_mile_commute"]

    for k, v in data.items():
        if k == "last_mile_commute":
            continue
        if k in _LIST_KEYS and isinstance(v, list):
            items = []
            for item in v[:limit_items]:
                if isinstance(item, dict) and not keep_urls:
                    item = {ik: iv for ik, iv in item.items() if ik not in _URL_KEYS}
                items.append(item)
            compact[k] = items
        else:
            compact[k] = v

    return json.dumps(compact, ensure_ascii=False)[:char_limit]


def _has_results(raw, list_key: str) -> bool:
    data = _load_json(raw)
    if not data:
        return False
    items = data.get(list_key)
    return isinstance(items, list) and len(items) > 0


# ═══════════════════════════════════════════════════════════════════════════
#  🌍  ZERO-HARDCODED DYNAMIC GEO & ECONOMIC RESOLVER
# ═══════════════════════════════════════════════════════════════════════════
class UniversalGeoResolution(BaseModel):
    origin_display: str = Field(default="Origin", description="Exact clean origin location name")
    origin_transit_city: str = Field(default="Origin", description="Single clean city or transit hub name for origin (e.g. 'Delhi', 'Mumbai')")
    origin_iata: Optional[str] = Field(None, description="Actual airport IATA code if one realistically exists")
    origin_rail_code: Optional[str] = Field(None, description="Actual IRCTC railway station code if in India and exists")

    destination_display: str = Field(default="Destination", description="Exact clean destination location name")
    destination_stay_town: str = Field(default="Destination", description="Settlement/town where hotels/guest houses exist")
    destination_transit_hub: str = Field(default="Destination", description="Single clean city or gateway hub name where long-distance transit arrives (e.g. 'Goa', 'Rishikesh', 'Chandigarh', 'Dehradun')")
    destination_iata: Optional[str] = Field(None, description="Actual airport IATA code if destination is accessible by air")
    destination_rail_code: Optional[str] = Field(None, description="Actual IRCTC railway station code if accessible by train")

    estimated_distance_km: int = Field(default=250, description="Realistic road or flight distance in km")
    is_international: bool = Field(default=False, description="True if trip crosses national international borders")
    terrain_type: str = Field(default="plains", description="Realistic terrain: 'hills', 'plains', 'coastal', 'desert', 'metro'")
    is_remote: bool = Field(default=False, description="True if destination requires onward mountain/rural road transfer")

    # Dynamic Transit Logistics
    recommended_primary_transit: Literal["flight", "train", "bus", "taxi"] = Field(
        default="bus",
        description="Most realistic logical transit mode based on distance and geography"
    )
    typical_one_way_transit_fare_inr: int = Field(default=500, description="Realistic economy per-person one-way fare for primary mode in INR")
    typical_travel_duration: str = Field(default="4h", description="Realistic journey duration (e.g., '1h 30m', '4h', '8h')")

    # Dynamic Last Mile
    last_mile_mode: str = Field(default="Local Taxi / Auto", description="Authentic local transport mode used in this specific region")
    last_mile_duration: str = Field(default="30m", description="Realistic commute duration from transit hub to final stay")
    last_mile_cost_inr: int = Field(default=150, description="Realistic per-person fare in INR for last-mile leg")
    route_advice: str = Field(default="Standard transit available.", description="Specific practical advice regarding roads, elevation, border permits, or timings")

    # Dynamic Destination Economics
    typical_daily_food_cost_per_person_inr: int = Field(default=600, description="Realistic average daily cost for 3 modest meals in INR in this destination")
    typical_daily_local_transit_inr: int = Field(default=350, description="Realistic average daily local auto/cab/metro expense in INR in this destination")
    typical_budget_stay_price_per_night_inr: int = Field(default=1500, description="Realistic entry-level clean hotel/homestay rate per night in INR for this location")
    typical_activity_fee_inr: int = Field(default=250, description="Typical entry or activity fees per person in INR")

    # Grounding Against Hallucination
    geographic_features: str = Field(
        default="Urban settlement",
        description="Physical reality summary: specify waterbodies, elevation, and terrain."
    )


_GEO_CACHE: dict[str, UniversalGeoResolution] = {}


def _fetch_geo_grounding(origin: str, destination: str) -> str:
    """Retrieves verified web snippets via Tavily for destination geography, route, and base settlement."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        q = f"{destination} location district nearest railway station airport route terrain altitude rivers waterbodies"
        res = client.search(query=q, max_results=4, search_depth="basic")
        snippets = []
        for r in res.get("results", []):
            content = (r.get("content") or "").strip()
            title = (r.get("title") or "").strip()
            if content:
                snippets.append(f"• [{title}] {content[:400]}")
        return "\n".join(snippets)
    except Exception as e:
        print(f"⚠️ Geo grounding lookup skipped: {e}")
        return ""


def _fetch_destination_attractions(destination: str) -> str:
    """Retrieves verified tourist attractions and authentic local sights via Tavily to prevent fictional places."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        q = f"{destination} top attractions places to visit tourist sights famous landmarks"
        res = client.search(query=q, max_results=4, search_depth="basic")
        items = []
        for r in res.get("results", []):
            content = (r.get("content") or "").strip()
            title = (r.get("title") or "").strip()
            if content and len(content) > 30:
                items.append(f"• [{title}]: {content[:280]}")
        return "\n".join(items)
    except Exception as e:
        print(f"⚠️ Attractions lookup skipped: {e}")
        return ""


def resolve_locations_dynamically(origin: str, destination: str) -> UniversalGeoResolution:
    """Dynamically resolves full geography, transit, and local economics with Tavily live grounding."""
    cache_key = f"{origin.lower().strip()}___{destination.lower().strip()}"
    if cache_key in _GEO_CACHE:
        return _GEO_CACHE[cache_key]

    web_grounding = _fetch_geo_grounding(origin, destination)
    grounding_block = (
        f"\nVERIFIED REAL-WORLD WEB CONTEXT FOR '{destination}':\n{web_grounding}\n"
        if web_grounding else ""
    )

    system_prompt = f"""You are an Expert Worldwide Travel Geographer & Transit Intelligence Engine.
Analyze the given origin and destination pair. Calculate physical realities, accurate transit hubs, real station/airport codes, and realistic local economics.
{grounding_block}
CRITICAL INSTRUCTIONS (STRICT ZERO-HALLUCINATION POLICY):
1. FACTUAL GROUNDING: Base all geographic and logistics attributes strictly on physical reality. If web context is provided above, trust it over any generic assumptions.

2. INTERNATIONAL & BORDER RULES (CRITICAL): If origin and destination are in different countries (`is_international` = True):
   - For Western/High-Cost countries (Europe, USA, Middle East, Japan, Australia): Scale `typical_budget_stay_price_per_night_inr` to ₹8,000-₹15,000+ and `typical_one_way_transit_fare_inr` to ₹30,000-₹80,000+. `recommended_primary_transit` MUST be 'flight'.
   - For Budget/Neighbouring Asian countries (Nepal, Bhutan, Sri Lanka, Thailand, Vietnam): Scale pricing accurately to regional realities (e.g., ₹1,500-₹4,000 per night). 
   - If the countries share a drivable/train border (e.g., India to Nepal/Bhutan/Bangladesh), you MAY allow 'bus' or 'train' if logistically accurate.

3. OVERSEAS & ISLAND RULE: If the destination is an island separated by an ocean (e.g., Havelock, Maldives), `recommended_primary_transit` MUST be 'flight' or 'ship'. EXCEPTION: If the island is connected to the mainland by a motorable road/rail bridge (e.g., Rameswaram), trains/buses are allowed.

4. DISTINGUISH TRANSIT GATEWAY HUB VS STAY BASE:
   - `destination_transit_hub`: Major transit city where flights/trains arrive.
   - `destination_stay_town`: The ACTUAL settlement/village/town.
   - For remote mountains: Set `is_remote` to True, `terrain_type` to "hills" or "mountains", and specify authentic `last_mile_mode`.

5. If in India:
   - Provide real IRCTC codes if available. For short plains distances (<150 km), primary transit must be train or regional bus.
   - Describe geography accurately (plains, landlocked, coastal, etc.).
"""
    user_prompt = f'Resolve logistics for Trip Origin: "{origin}" to Destination: "{destination}"'

    try:
        structured_llm = parsing_model.with_structured_output(UniversalGeoResolution)
        res: UniversalGeoResolution = structured_llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        # Sanitize against placeholder defaults
        if not res.destination_stay_town or res.destination_stay_town.lower() in ("destination", ""):
            res.destination_stay_town = destination
        if not res.destination_transit_hub or res.destination_transit_hub.lower() in ("destination", ""):
            res.destination_transit_hub = destination
        if not res.origin_transit_city or res.origin_transit_city.lower() in ("origin", ""):
            res.origin_transit_city = origin
        if not res.origin_display or res.origin_display.lower() in ("origin", ""):
            res.origin_display = origin
        if not res.destination_display or res.destination_display.lower() in ("destination", ""):
            res.destination_display = destination

        _GEO_CACHE[cache_key] = res
        return res
    except Exception as e:
        print(f"⚠️ Dynamic Geo Resolver fallback triggered for {origin} -> {destination}: {e}")
        # Resilient dynamic estimate without any hardcoded city names
        return UniversalGeoResolution(
            origin_display=origin,
            origin_transit_city=origin,
            origin_iata=None,
            origin_rail_code=None,
            destination_display=destination,
            destination_stay_town=destination,
            destination_transit_hub=destination,
            destination_iata=None,
            destination_rail_code=None,
            estimated_distance_km=250,
            is_international=False,
            terrain_type="plains",
            is_remote=False,
            recommended_primary_transit="bus",
            typical_one_way_transit_fare_inr=300,
            typical_travel_duration="4h",
            last_mile_mode="Local Taxi / Auto",
            last_mile_duration="30m",
            last_mile_cost_inr=150,
            route_advice="Standard transit available.",
            typical_daily_food_cost_per_person_inr=500,
            typical_daily_local_transit_inr=300,
            typical_budget_stay_price_per_night_inr=1200,
            typical_activity_fee_inr=200,
            geographic_features=f"Urban settlement of {destination}."
        )


def _generate_transit_fallback(geo: UniversalGeoResolution) -> dict:
    """Dynamically generates fallback transit structures based strictly on the resolved geo parameters."""
    origin = geo.origin_transit_city
    dest = geo.destination_transit_hub
    mode = geo.recommended_primary_transit
    fare = geo.typical_one_way_transit_fare_inr
    duration = geo.typical_travel_duration

    if mode == "flight" or geo.is_international:
        return {
            "origin": origin,
            "destination": dest,
            "transit_hub": dest,
            "total_found": 1,
            "is_estimate": True,
            "recommended_flights": [{
                "airline": "Commercial Scheduled Airline",
                "flight_number": "Economy Service",
                "departure_time": "10:30",
                "duration_hours": duration,
                "price_inr": float(fare),
                "booking_url": f"https://www.google.com/travel/flights?q=flights+from+{origin}+to+{dest}"
            }]
        }
    elif mode == "train" and geo.destination_rail_code:
        return {
            "from_station": geo.origin_rail_code or origin,
            "to_station": geo.destination_rail_code,
            "total_trains": 1,
            "trains": [{
                "train_number": "Express",
                "train_name": f"Intercity Express ({origin} - {dest})",
                "departure_time": "08:30",
                "arrival_time": "N/A",
                "travel_time_hours": duration,
                "classes": ["SL", "3A", "2S"],
                "origin_station": geo.origin_rail_code or origin,
                "destination_station": geo.destination_rail_code,
                "booking_url": "https://www.irctc.co.in",
                "price_inr": float(fare)
            }]
        }
    else:
        # Bus / Road Shuttles
        return {
            "origin": origin,
            "destination": dest,
            "transit_hub": dest,
            "total_found": 1,
            "is_estimate": True,
            "recommended_buses": [{
                "operator_name": f"Regular Intercity Transport ({origin} to {dest})",
                "bus_type": "Scheduled Transit Service",
                "departure_time": "Frequent service throughout the day",
                "duration_hours": duration,
                "estimated_price_inr": float(fare),
                "booking_url": f"https://www.redbus.in/bus-tickets/{origin.lower().replace(' ', '-')}-to-{dest.lower().replace(' ', '-')}"
            }]
        }


# ═══════════════════════════════════════════════════════════════════════════
#  🛡️  STEP 2: INPUT GUARDRAILS NODE
# ═══════════════════════════════════════════════════════════════════════════
class GuardrailsValidation(BaseModel):
    allowed: bool = Field(description="true if query is a safe, valid travel planning request; false otherwise")
    reason: str = Field(description="brief explanation for allowing or rejecting")


def guardrails_node(state: TravelState) -> dict:
    query = state.get("user_query", "").strip()
    
    # Updated System Prompt: Strict domain/safety check, ignore logistical impossibility
    system_prompt = """You are an Input Guardrail agent for the Tessera Travel Engine.
Evaluate the incoming query STRICTLY for safety and travel domain relevance. Return structured output.

CRITICAL INSTRUCTIONS:
1. ALLOW any query related to travel, tourism, transit, or vacations.
2. DO NOT evaluate geographic feasibility or transit reality. If a user asks for something impossible (e.g., "train to a high mountain", "drive across the ocean"), you MUST ALLOW IT. Downstream agents will correct their logistical mistakes.
3. REJECT ONLY if the query violates safety policies (violence, illegal acts) or is entirely unrelated to travel (e.g., coding help, math equations).
"""

    try:
        struct_guard = guardrails_model.with_structured_output(GuardrailsValidation)
        result: GuardrailsValidation = struct_guard.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f'User Query: "{query}"'}
        ])
        return {"guardrail_allowed": result.allowed, "guardrail_reason": result.reason}
    except Exception:
        q = query.lower()
        allowed = any(w in q for w in ["trip", "travel", "flight", "train", "bus", "hotel", "itinerary", "stay", "tour", "to", "visit"])
        return {
            "guardrail_allowed": allowed,
            "guardrail_reason": "Query classified as travel-related." if allowed else "Not a valid travel query."
        }


def route_after_guardrails(state: TravelState) -> str:
    return "supervisor_agent" if state.get("guardrail_allowed") else "blocked_request_node"


def blocked_request_node(state: TravelState) -> dict:
    reason = state.get("guardrail_reason", "Request did not meet safety and travel domain criteria.")
    return {
        "final_response": f"⚠️ **Request Blocked:** {reason}\nPlease enter a valid travel inquiry.",
        "approved": "rejected"
    }


# ═══════════════════════════════════════════════════════════════════════════
#  🎯  STEP 3: SUPERVISOR AGENT NODE (100% Query-Driven Extraction)
# ═══════════════════════════════════════════════════════════════════════════
KNOWN_AGENTS = ["flight_agent", "hotel_agent", "weather_agent", "budget_agent", "itinerary_agent"]


class SupervisorOutput(BaseModel):
    origin: str = Field(description="Departure location extracted directly from user query")
    destination: str = Field(description="Target destination location extracted directly from user query")
    duration_days: int = Field(default=2, description="Duration in days parsed from query or calendar. Set to 1 for day trips / 1-day tours.")
    travelers: int = Field(default=2, description="Number of travelers parsed from query; default 2 if unspecified")
    budget: Optional[int] = Field(None, description="Explicit target budget in currency value if stated")
    preferred_transit_mode: Optional[Literal["flight", "train", "bus", "any"]] = Field(
        default="any",
        description="Explicit transit mode requested by user (e.g. flight, train, bus, or any)"
    )
    stay_tier: Optional[Literal["budget", "moderate", "luxury"]] = Field(
        default="moderate",
        description="Stay category: 'luxury' for 5-star/resorts; 'budget' for cheap/hostels; else 'moderate'"
    )
    departure_date: Optional[str] = Field(None, description="Departure date in YYYY-MM-DD format if stated")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format if stated")
    reasoning: str = Field(description="Operational reasoning for the workflow")


def supervisor_agent(state: TravelState) -> dict:
    query = state.get("user_query", "")
    today = datetime.now().strftime("%Y-%m-%d")

    system_prompt = f"""You are the Supervisor Agent of the Tessera Travel Engine.
Today's reference date is {today}.
Analyze the user's travel request and extract the parameters dynamically.
NEVER default to hardcoded cities if an origin is stated. Extract the origin and destination strictly from what the user typed.
If origin is omitted or unknown, assume 'Delhi' as default reference departure origin for domestic Indian travel (or deduce logically from context).
If the query explicitly asks for a 1-day trip, same-day return, or day tour, set duration_days = 1.
If duration is unspecified, estimate logically from the scope of travel (default 2 days for single-city trips).
If travelers count is unspecified, assume 2 travelers.
If user explicitly states transit preference (e.g. 'by train', 'by bus', 'by flight', 'rajdhani', 'road trip'), set preferred_transit_mode accordingly ('train', 'bus', 'flight'). Otherwise set 'any'.
If user mentions stay preference ('luxury', '5-star', 'resort', 'budget', 'hostel', 'cheap'), set stay_tier accordingly. Otherwise set 'moderate'.
"""

    try:
        struct_sup = supervisor_model.with_structured_output(SupervisorOutput)
        result: SupervisorOutput = struct_sup.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ])

        constraints = {
            "origin": result.origin,
            "destination": result.destination,
            "duration_days": max(1, result.duration_days),
            "travelers": max(1, result.travelers),
            "budget": result.budget,
            "preferred_transit_mode": result.preferred_transit_mode or "any",
            "stay_tier": result.stay_tier or "moderate",
            "departure_date": result.departure_date,
            "return_date": result.return_date,
            "raw_query": query
        }

        constraints = _reconcile_trip_dates(constraints)
        reasoning = result.reasoning
    except Exception as exc:
        reasoning = f"Supervisor dynamically parsed query: {exc}"
        constraints = {
            "origin": "User Origin",
            "destination": query,
            "duration_days": 2,
            "travelers": 2,
            "preferred_transit_mode": "any",
            "stay_tier": "moderate",
            "raw_query": query
        }

    # Resolve geography ONCE here before parallel branching to prevent API rate limit crashes
    geo_res = resolve_locations_dynamically(
        str(constraints.get("origin", "Delhi")), 
        str(constraints.get("destination", query))
    )

    return {
        "selected_agents": KNOWN_AGENTS,
        "trip_constraints": constraints,
        "resolved_geo": geo_res.model_dump(),
        "supervisor_reasoning": reasoning,
        "travelers_count": int(constraints["travelers"]),
        "duration_days": int(constraints["duration_days"]),
        "messages": [AIMessage(content=f"Supervisor assigned workflow for: {constraints.get('origin')} -> {constraints.get('destination')}")]
    }


# ═══════════════════════════════════════════════════════════════════════════
#  ✈️  STEP 4: SPECIALIST FAST-MCP RETRIEVAL AGENTS
# ═══════════════════════════════════════════════════════════════════════════
def flight_agent(state: TravelState) -> dict:
    """Dynamically routes across Flight, Train, and Bus tools based on user preference and real geography."""
    c = _safe_constraints(state)
    date = _resolve_travel_date(c)
    pref_mode = (c.get("preferred_transit_mode") or "any").lower()

    # Read geography directly from state (No extra LLM call)
    geo = UniversalGeoResolution(**state.get("resolved_geo", {}))
    origin_transit = geo.origin_transit_city
    dest_hub = geo.destination_transit_hub

    def try_flights():
        can_fly = (
            geo.origin_iata
            and geo.destination_iata
            and geo.origin_iata != geo.destination_iata
            and (geo.is_international or geo.estimated_distance_km > 150 or pref_mode == "flight")
        )
        if can_fly:
            try:
                res = search_flights.invoke({
                    "origin_iata": geo.origin_iata,
                    "destination_iata": geo.destination_iata,
                    "travel_date": date
                })
                rs = str(res)
                if _has_results(rs, "recommended_flights"):
                    return {"flight_results": rs, "rails_results": "", "bus_results": ""}
            except Exception as e:
                print(f"[Warning] Flight tool execution: {e}")
        return None

    def try_trains():
        if not geo.is_international and geo.origin_rail_code and geo.destination_rail_code and geo.origin_rail_code != geo.destination_rail_code:
            try:
                res = search_trains.invoke({
                    "from_station_code": geo.origin_rail_code,
                    "to_station_code": geo.destination_rail_code,
                    "travel_date": date
                })
                rs = str(res)
                if _has_results(rs, "trains"):
                    return {"flight_results": "", "rails_results": rs, "bus_results": ""}
            except Exception as e:
                print(f"[Warning] Train tool execution: {e}")
        return None

    def try_buses():
        if not geo.is_international:
            # 1. First try direct buses to destination city
            target_dest = geo.destination_display
            try:
                res = search_buses.invoke({
                    "origin_city": origin_transit,
                    "destination_city": target_dest,
                    "travel_date": date
                })
                rs = str(res)
                bus_json = _load_json(rs)
                if bus_json and _has_results(rs, "recommended_buses"):
                    return {"flight_results": "", "rails_results": "", "bus_results": rs}
            except Exception as e:
                print(f"[Warning] Direct bus tool execution: {e}")

            # 2. If direct buses not found and destination has a regional transit hub, search hub with last-mile
            if dest_hub and dest_hub.lower() != target_dest.lower():
                try:
                    res = search_buses.invoke({
                        "origin_city": origin_transit,
                        "destination_city": dest_hub,
                        "travel_date": date
                    })
                    rs = str(res)
                    bus_json = _load_json(rs)
                    if bus_json and _has_results(rs, "recommended_buses"):
                        if geo.is_remote:
                            bus_json = {
                                "last_mile_commute": {
                                    "transit_hub": dest_hub,
                                    "stay_town": geo.destination_stay_town,
                                    "mode": geo.last_mile_mode,
                                    "duration": geo.last_mile_duration,
                                    "estimated_fare_inr": geo.last_mile_cost_inr,
                                    "advice": geo.route_advice
                                },
                                **bus_json
                            }
                        return {"flight_results": "", "rails_results": "", "bus_results": json.dumps(bus_json, ensure_ascii=False)}
                except Exception as e:
                    print(f"[Warning] Hub bus tool execution: {e}")
        return None

    # 1. User Explicit Transit Mode Priority
    if pref_mode == "train":
        t_res = try_trains()
        if t_res:
            return t_res
    elif pref_mode == "bus":
        b_res = try_buses()
        if b_res:
            return b_res
    elif pref_mode == "flight":
        f_res = try_flights()
        if f_res:
            return f_res

    # 2. Standard Distance & Geographic Priority
    f_res = try_flights()
    if f_res:
        return f_res

    t_res = try_trains()
    if t_res:
        return t_res

    b_res = try_buses()
    if b_res:
        return b_res

    # 3. Dynamic Curated Fallback
    advisory_card = _generate_transit_fallback(geo)
    if geo.is_remote:
        advisory_card["last_mile_commute"] = {
            "transit_hub": dest_hub,
            "stay_town": geo.destination_stay_town,
            "mode": geo.last_mile_mode,
            "duration": geo.last_mile_duration,
            "estimated_fare_inr": geo.last_mile_cost_inr,
            "advice": geo.route_advice
        }

    fallback_json = json.dumps(advisory_card, ensure_ascii=False)
    if "recommended_flights" in advisory_card:
        return {"flight_results": fallback_json, "rails_results": "", "bus_results": ""}
    elif "trains" in advisory_card:
        return {"flight_results": "", "rails_results": fallback_json, "bus_results": ""}
    return {"flight_results": "", "rails_results": "", "bus_results": fallback_json}


def hotel_agent(state: TravelState) -> dict:
    c = _safe_constraints(state)
    geo = UniversalGeoResolution(**state.get("resolved_geo", {}))
    stay_tier = (c.get("stay_tier") or "").lower()
    budget_raw = c.get("budget")

    if stay_tier in ("luxury", "budget", "moderate"):
        budget_tier = stay_tier
    elif budget_raw:
        b_val = int(_to_num(budget_raw, 20000))
        budget_tier = "budget" if b_val < 15000 else "luxury" if b_val > 50000 else "moderate"
    else:
        budget_tier = "moderate"

    stay_city = geo.destination_stay_town
    if not stay_city or stay_city.lower() in ("destination", "user destination", ""):
        stay_city = str(c.get("destination") or "City Center")

    try:
        results = search_hotels.invoke({
            "city": stay_city,
            "budget_tier": budget_tier,
            "base_rate": geo.typical_budget_stay_price_per_night_inr or 2000
        })
    except Exception as exc:
        results = f"Hotel research lookup failed: {exc}"

    return {"hotel_results": str(results)}


def weather_agent(state: TravelState) -> dict:
    geo = UniversalGeoResolution(**state.get("resolved_geo", {}))
    try:
        results = get_weather.invoke({"city": geo.destination_stay_town})
    except Exception as e:
        results = f"Weather lookup unavailable: {e}"

    return {"weather_results": str(results)}


# ═══════════════════════════════════════════════════════════════════════════
#  💰  STEP 5: DYNAMIC BUDGET AGENT (Scaled to Destination Economics)
# ═══════════════════════════════════════════════════════════════════════════
def budget_agent(state: TravelState) -> dict:
    """Computes realistic budget using verified tool prices or dynamic destination economics."""
    c = _safe_constraints(state)
    geo = UniversalGeoResolution(**state.get("resolved_geo", {}))

    duration = max(1, int(state.get("duration_days") or c.get("duration_days") or 2))
    nights = max(0, duration - 1)
    travelers = max(1, int(state.get("travelers_count") or c.get("travelers") or 2))
    rooms = max(1, (travelers + 1) // 2) if nights > 0 else 0
    budget_limit = int(_to_num(c.get("budget", 0)))
    stay_tier = (c.get("stay_tier") or "moderate").lower()

    # 1. Deterministic Hotel Selection
    hotel_raw = _load_json(state.get("hotel_results", "{}")) or {}
    hotels_list = hotel_raw.get("hotels", [])

    selected_hotel: SelectedEntity
    if nights == 0:
        # 1-day trip: No overnight accommodation required
        selected_hotel = {
            "name": f"Day Trip (No Overnight Stay in {geo.destination_stay_town})",
            "location": geo.destination_stay_town,
            "price": 0,
            "booking_url": None,
            "details": {"note": "Same-day return, hotel room not required"}
        }
        hotel_cost = 0
    elif hotels_list:
        valid_hotels = [h for h in hotels_list if _to_num(h.get("price_per_night", 0)) > 0]
        if valid_hotels:
            if stay_tier == "luxury":
                chosen = max(valid_hotels, key=lambda x: _to_num(x.get("price_per_night", 0)))
            elif stay_tier == "budget":
                chosen = min(valid_hotels, key=lambda x: _to_num(x.get("price_per_night", 99999)))
            else:
                sorted_h = sorted(valid_hotels, key=lambda x: _to_num(x.get("price_per_night", 0)))
                chosen = sorted_h[len(sorted_h) // 2]

            selected_hotel = {
                "name": str(chosen.get("name", "Verified Accommodation")),
                "location": str(chosen.get("location", geo.destination_stay_town)),
                "price": int(_to_num(chosen.get("price_per_night", geo.typical_budget_stay_price_per_night_inr))),
                "booking_url": chosen.get("url") or chosen.get("booking_url"),
                "details": chosen
            }
        else:
            selected_hotel = {
                "name": f"Verified Stay ({geo.destination_stay_town})",
                "location": geo.destination_stay_town,
                "price": geo.typical_budget_stay_price_per_night_inr,
                "booking_url": None,
                "details": {}
            }
        hotel_cost = selected_hotel["price"] * nights * rooms
    else:
        selected_hotel = {
            "name": f"Verified Stay ({geo.destination_stay_town})",
            "location": geo.destination_stay_town,
            "price": geo.typical_budget_stay_price_per_night_inr,
            "booking_url": None,
            "details": {}
        }
        hotel_cost = selected_hotel["price"] * nights * rooms

    # 2. Deterministic Transit Selection
    flight_data = _load_json(state.get("flight_results", "{}")) or {}
    train_data = _load_json(state.get("rails_results", "{}")) or {}
    bus_data = _load_json(state.get("bus_results", "{}")) or {}

    transit_mode = geo.recommended_primary_transit.title()
    transit_name = f"Direct {transit_mode} ({geo.origin_transit_city} to {geo.destination_transit_hub})"
    unit_fare = geo.typical_one_way_transit_fare_inr
    booking_url = None
    last_mile = _extract_last_mile(bus_data)

    if flight_data.get("recommended_flights"):
        f = flight_data["recommended_flights"][0]
        transit_mode = "Flight"
        transit_name = f.get("airline", "Commercial Scheduled Airline")
        unit_fare = int(_to_num(f.get("price_inr", unit_fare)))
        booking_url = f.get("booking_url")
    elif train_data.get("trains"):
        t = train_data["trains"][0]
        transit_mode = "Train"
        transit_name = f"{t.get('train_name', 'Express')} ({t.get('train_number', 'IR')})"
        unit_fare = int(_to_num(t.get("price_inr") or t.get("fare", unit_fare)))
        booking_url = t.get("booking_url") or "https://www.confirmtkt.com"
    elif bus_data.get("recommended_buses"):
        b = bus_data["recommended_buses"][0]
        transit_mode = "Bus"
        transit_name = b.get("operator_name", "Intercity Service")
        unit_fare = int(_to_num(b.get("estimated_price_inr", unit_fare)))
        booking_url = b.get("booking_url")

    last_mile_fare = int(_to_num(last_mile.get("estimated_fare_inr", geo.last_mile_cost_inr))) if last_mile else (geo.last_mile_cost_inr if geo.is_remote else 0)
    total_transit_cost = int((unit_fare * 2 * travelers) + (last_mile_fare * 2 * travelers))

    selected_transit: SelectedEntity = {
        "name": transit_name,
        "location": transit_mode,
        "price": unit_fare,
        "booking_url": booking_url,
        "details": {"round_trip_total": total_transit_cost, "last_mile": last_mile}
    }

    transit_options = [{
        "mode": transit_mode,
        "operator": transit_name,
        "price_per_seat": unit_fare,
        "round_trip_total": total_transit_cost,
        "last_mile_details": last_mile,
        "booking_url": booking_url
    }]

    # 3. Dynamic Living Costs (scaled to stay tier and geo intelligence)
    if stay_tier == "luxury":
        food_unit = max(1400, int(geo.typical_daily_food_cost_per_person_inr * 2.0))
        local_unit = max(1200, int(geo.typical_daily_local_transit_inr * 2.2))
        activities_unit = max(500, int(geo.typical_activity_fee_inr * 2.0))
    elif stay_tier == "budget":
        food_unit = max(350, int(geo.typical_daily_food_cost_per_person_inr * 0.75))
        local_unit = max(200, int(geo.typical_daily_local_transit_inr * 0.7))
        activities_unit = max(150, int(geo.typical_activity_fee_inr * 0.75))
    else:
        food_unit = geo.typical_daily_food_cost_per_person_inr
        local_unit = geo.typical_daily_local_transit_inr
        activities_unit = geo.typical_activity_fee_inr

    food_cost = food_unit * duration * travelers
    local_transport = local_unit * duration * travelers
    activities_cost = activities_unit * travelers

    total_expense = int(total_transit_cost + hotel_cost + food_cost + local_transport + activities_cost)

    budget_status = ""
    if budget_limit > 0:
        diff = budget_limit - total_expense
        if diff >= 0:
            budget_status = f"\nStatus: Within Budget (Savings: ₹{diff:,})"
        else:
            budget_status = f"\nStatus: Over Budget by ₹{abs(diff):,}"

    last_mile_note = f" + Last-mile {last_mile.get('mode', 'local commute')}" if last_mile else ""
    hotel_note = (
        f"- Accommodation: ₹0 (Day trip, no overnight stay required)\n"
        if nights == 0 else
        f"- Accommodation ({nights} Nights @ {selected_hotel['name']} [₹{selected_hotel['price']:,}/night]): ₹{hotel_cost:,}\n"
    )

    breakdown = f"""**Trip Cost Breakdown ({travelers} Travelers, {duration} Day{'s' if duration > 1 else ''} / {nights} Nights):**
- Transit ({transit_mode}: {transit_name}{last_mile_note}, Round-Trip): ₹{total_transit_cost:,}
{hotel_note}- Food & Dining: ₹{food_cost:,}
- Local Commute & Sightseeing: ₹{local_transport:,}
- Activities & Admission: ₹{activities_cost:,}

**TOTAL ESTIMATED EXPENSE: ₹{total_expense:,}**{budget_status}
"""

    return {
        "budget_results": breakdown,
        "estimated_total_inr": total_expense,
        "travelers_count": travelers,
        "duration_days": duration,
        "selected_hotel": selected_hotel,
        "selected_transit": selected_transit,
        "transit_options": transit_options
    }


# ═══════════════════════════════════════════════════════════════════════════
#  📝  STEP 6: GROUNDED ITINERARY AGENT
# ═══════════════════════════════════════════════════════════════════════════
def itinerary_agent(state: TravelState) -> dict:
    c = _safe_constraints(state)
    query = state.get("user_query", "")
    hotel = state.get("selected_hotel") or {"name": "Verified Stay", "price": 1000, "location": "City Center"}
    transit = state.get("selected_transit") or {"name": "Regular Transit", "price": 100}
    geo = UniversalGeoResolution(**state.get("resolved_geo", {}))

    total_days = max(1, int(state.get("duration_days") or c.get("duration_days") or 2))
    destination = geo.destination_display
    origin = geo.origin_display
    is_day_trip = (total_days == 1)

    stay_town = geo.destination_stay_town or destination
    hotel_name = hotel.get('name', 'Verified Stay')
    hotel_price = hotel.get('price', 1500)

    stay_instructions = (
        f"- For this 1-DAY TRIP, travelers do NOT stay overnight in {destination}. Schedule morning arrival and evening return transit back to {origin}."
        if is_day_trip else
        f"- For Days 1 to {max(1, total_days - 1):02d}: Travelers stay overnight at: '{hotel_name}' in {stay_town} (Rate: ₹{hotel_price:,}/night).\n"
        f"   - For Day {total_days:02d} (Final Departure Day): Travelers return home to {origin}. On this final day, '* Stay:' MUST indicate: 'Return journey to {origin} (Home departure, no overnight hotel needed)'."
    )

    # Fetch real attractions to eliminate fictitious sightseeing
    attractions = _fetch_destination_attractions(destination)
    attractions_section = (
        f"\nVERIFIED REAL-WORLD ATTRACTIONS IN '{destination}':\n{attractions}\n"
        if attractions else ""
    )

    remote_guidelines = ""
    if geo.is_remote:
        remote_guidelines = f"""
4. MULTI-LEG MOUNTAIN & REMOTE ROUTE LOGISTICS:
   - Transit Gateway Hub: {geo.destination_transit_hub}
   - Actual Destination Base: {stay_town}
   - Mountain Transfer Mode: {geo.last_mile_mode} ({geo.last_mile_duration})
   - Route Guidance: {geo.route_advice}
   - DAY 1 REALISTIC PROGRESSION: Travelers take transit from {origin} to gateway hub ({geo.destination_transit_hub}), then embark on the scenic mountain journey up to {stay_town}. Check into accommodation in {stay_town} and acclimatize.
   - EXPLORATION DAYS: Conduct excursions or treks to {destination}. Celebrate authentic geographical landmarks ({geo.geographic_features}).
   - FINAL DAY: Descend from {stay_town} via gateway hub ({geo.destination_transit_hub}) for return transit to {origin}.
   - ABSOLUTE ZERO HALLUCINATION: NEVER suggest auto-rickshaws, e-rickshaws, or scooters for cross-district mountain routes. NEVER claim travelers can take a 30-minute auto ride from a plains/foothills city to a high Himalayan peak 180 km away!
"""

    stay_line_example = (
        f"Same-day evening return to {origin} (No hotel required)"
        if is_day_trip else
        f"[For intermediate days: {stay_town} — {hotel_name} (₹{hotel_price:,}/night); For final Day {total_days:02d}: Return journey to {origin} (Home departure, no overnight hotel needed)]"
    )

    # 🟢 NEW LOGIC: Dynamic Payment Advice based on Geography 🟢
    if geo.is_international:
        payment_advice = "recommend multi-currency Forex cards, international credit cards, and carrying local currency (Euros/Dollars); NEVER mention UPI or INR."
    else:
        payment_advice = "recommend UPI [GPay/PhonePe] and cash in ₹100/₹500 for local street stalls; NEVER mention discontinued ₹2000 currency notes."

    prompt = f"""You are the Lead Itinerary Architect. Synthesize a strictly grounded day-by-day plan.

ABSOLUTE HARD RULES (DO NOT DEVIATE):
1. TRIP TIMING & FLOW:
   - Total trip duration: {total_days} DAY(S).
   - Traveler journey: Origin '{origin}' to Destination '{destination}'.
   {stay_instructions}
   - Inbound transit on Day 1 morning; Outbound transit on Day {total_days:02d} evening.

2. STRICT OUTPUT FORMAT:
   - Output ONLY the chronological days (DAY 01 to DAY {total_days:02d}) and end with "## Practical Tips".
   - DO NOT output any cost tables or Markdown pipe tables (|---|). Dedicated cards handle budget.
   - For each day, use this EXACT structure:
     DAY XX — [THEME / TITLE]
     * Morning: [Detailed morning activity or travel leg]
     * Afternoon: [Afternoon sightseeing, meal spot, or key milestone]
     * Evening: [Sunset viewpoint, cultural activity, or dinner]
     * Stay: {stay_line_example}

3. GEOGRAPHIC & FACTUAL REALISM (ZERO TOLERANCE FOR HALLUCINATIONS):
   - Destination: {destination}. Physical features: {geo.geographic_features}.
   - Base town / Stay town: {stay_town}.
   {attractions_section}
   - STRICT ATTRACTION GROUNDING: Base activities strictly on verified landmarks (such as those listed above), authentic local bazaars, or real nature preserves (e.g. Sandi Bird Sanctuary, Prahlad Kund for Hardoi).
   - WATERBODY FACT-CHECK: If the destination is landlocked or has no river flowing through it (e.g. Hardoi, Shahjahanpur, Jaipur center), NEVER invent riverfronts, rivers (e.g. NEVER invent the Saryu river in Hardoi — Saryu is in Ayodhya!), river walks, ghats, or boat rides!
   - NO CROSS-DISTRICT INVENTIONS: DO NOT place attractions from neighboring or distant districts into this destination (e.g. Kakori belongs to Lucknow, NOT Hardoi; Beatles Ashram belongs to Rishikesh, NOT anywhere else).
   - TRAILHEAD ACCURACY: Verify where trails begin (e.g. Tungnath & Chandrashila begins directly from roadside at Chopta base, NOT from Sari village; Sari village is only for Deoria Tal).
   - ROUTE INTEGRITY: Stick strictly to authentic road corridors. For Chopta/Tungnath, route is via Rishikesh -> Devprayag -> Srinagar -> Rudraprayag -> Kund -> Ukhimath -> Dugalbitta -> Chopta. DO NOT invent detours to Kanakchauri or Gaurikund.
   - TRANSIT FACTUALITY: DO NOT invent fictitious 5-digit train numbers or inverted schedules. If an exact train number is not verified from tool data, refer to it by its authentic service name (e.g., 'Morning Intercity Express / Superfast') rather than guessing numbers like '22436' or '12055'.
{remote_guidelines}
User Query: {query}
Transit Details: {transit.get('name', 'Direct Transit')}

End with "## Practical Tips" (weather, local transit, cash & payments advice: {payment_advice}, recommend official online monument ticketing, altitude/clothing).
"""
    response = itinerary_model.invoke(prompt)
    return {"itinerary": response.content, "messages": [response]}


# ═══════════════════════════════════════════════════════════════════════════
#  🧑‍💼  STEP 7: HUMAN-IN-THE-LOOP (HITL GATE)
# ═══════════════════════════════════════════════════════════════════════════
def human_approval_node(state: TravelState) -> dict:
    itinerary = state.get("itinerary", "")
    budget = state.get("budget_results", "")

    approval_request = (
        f"📋 **Travel Plan Ready for Review**\n\n"
        f"{budget}\n\n"
        f"Draft Itinerary Preview:\n{itinerary[:500]}...\n\n"
        f"Approve to finalize, or specify modifications."
    )

    human_input = interrupt({
        "type": "approval_request",
        "question": "Do you approve this travel plan?",
        "draft_itinerary": itinerary,
        "draft_budget": budget,
        "approval_request": approval_request
    })

    if isinstance(human_input, bool):
        decision = "approve" if human_input else "reject"
        feedback = ""
    elif isinstance(human_input, dict):
        decision = str(human_input.get("decision", "")).strip().lower()
        feedback = str(human_input.get("feedback", "")).strip()
    else:
        decision = str(human_input).strip().lower()
        feedback = ""

    status = "approved" if decision in ("approve", "approved", "yes", "y", "ok", "true", "1") else (
        "rejected" if decision in ("reject", "rejected", "no", "n", "false", "0") else "pending"
    )

    return {
        "approved": status,
        "human_feedback": feedback or (str(human_input) if status == "pending" else ""),
        "approval_request": approval_request,
        "messages": [AIMessage(content=f"Human Review: {status}")]
    }


def route_after_approval(state: TravelState) -> str:
    status = state.get("approved", "pending")
    if status == "approved":
        return "final_agent"
    if status == "rejected":
        return "rejected_node"
    return "revise_itinerary_node"


def revise_itinerary_node(state: TravelState) -> dict:
    total_days = max(1, int(state.get("duration_days") or 2))
    hotel = state.get('selected_hotel', {})
    origin = state.get('trip_constraints', {}).get('origin', 'Origin')
    hotel_name = hotel.get('name', 'Selected Hotel')
    hotel_price = hotel.get('price', 1500)

    # 🟢 NEW LOGIC: Dynamic Payment Advice for Revisions 🟢
    geo_dict = state.get("resolved_geo", {})
    is_international = geo_dict.get("is_international", False)

    if is_international:
        payment_advice = "recommend multi-currency Forex cards, international credit cards, and carrying local currency (Euros/Dollars); NEVER mention UPI or INR."
    else:
        payment_advice = "recommend UPI [GPay/PhonePe] and cash in ₹100/₹500 for local street stalls; NEVER mention discontinued ₹2000 currency notes."

    prompt = f"""You are the Itinerary Architect. Revise the itinerary based on user feedback:
Feedback: "{state.get('human_feedback', '')}"
Current Itinerary:
{state.get('itinerary', '')}

Maintain the locked stay: {hotel_name}.
STRICT FORMAT: Maintain the chronological days (DAY XX — [TITLE]) with '* Morning:', '* Afternoon:', '* Evening:', '* Stay:'.
On intermediate days (Day 01 to Day {max(1, total_days - 1):02d}), '* Stay:' MUST indicate '{hotel_name} (₹{hotel_price:,}/night)'.
On final Day {total_days:02d}, '* Stay:' MUST indicate 'Return journey to {origin} (Home departure, no overnight hotel needed)'.
Do NOT output any markdown pipe tables (|---|).
End with '## Practical Tips' (Payment advice: {payment_advice}, recommend official online monument ticketing).
"""
    response = itinerary_model.invoke(prompt)
    return {
        "itinerary": response.content,
        "approved": "pending",
        "messages": [AIMessage(content="Itinerary revised.")]
    }


def rejected_node(state: TravelState) -> dict:
    return {
        "final_response": "❌ Travel plan creation cancelled by user request.",
        "approved": "rejected"
    }


# ═══════════════════════════════════════════════════════════════════════════
#  🏁  STEP 8: FINAL RESPONSE CONCIERGE
# ═══════════════════════════════════════════════════════════════════════════
def final_agent(state: TravelState) -> dict:
    itinerary = state.get("itinerary", "")
    budget = state.get("budget_results", "")
    hotel = state.get("selected_hotel", {})
    transit = state.get("selected_transit", {})

    prompt = f"""You are the Executive Travel Concierge. Present the approved travel plan in polished Markdown:
1. Trip Summary & Overview
2. Day-Wise Final Itinerary
3. Cost Analysis & Budget
4. Verified Transit (Include {transit.get('name')}, fare: ₹{transit.get('price')})
5. Curated Stay (Locked: {hotel.get('name')} at ₹{hotel.get('price')}/night in {hotel.get('location')})
6. Practical Local Advice

Data:
{itinerary}

Budget:
{budget}
"""
    response = final_agent_model.invoke([
        SystemMessage(content="You are a professional travel concierge delivering clean plans."),
        HumanMessage(content=prompt)
    ])
    return {"final_response": response.content, "messages": [response]}


# ═══════════════════════════════════════════════════════════════════════════
#  💾  POSTGRES POOL & PARALLEL GRAPH COMPILATION
# ═══════════════════════════════════════════════════════════════════════════
DATABASE_URL = get_database_url()

_pool = AsyncConnectionPool(
    conninfo=DATABASE_URL,
    max_size=5,
    min_size=0,
    max_idle=30,
    max_lifetime=300,
    timeout=30,
    kwargs={
        "autocommit": True,
        "row_factory": dict_row,
        "prepare_threshold": None,
        "keepalives": 1,
        "keepalives_idle": 15,
        "keepalives_interval": 5,
        "keepalives_count": 3,
    },
    open=False,
    check=AsyncConnectionPool.check_connection,
)


async def build_graph():
    if _pool.closed:
        await _pool.open()

    workflow = StateGraph(TravelState)

    # 1. Register Nodes
    workflow.add_node("guardrails_node", guardrails_node)
    workflow.add_node("blocked_request_node", blocked_request_node)
    workflow.add_node("supervisor_agent", supervisor_agent)

    # Retrieval Workers (Parallel execution)
    workflow.add_node("flight_agent", flight_agent)
    workflow.add_node("hotel_agent", hotel_agent)
    workflow.add_node("weather_agent", weather_agent)

    # Synthesis & Aggregation
    workflow.add_node("budget_agent", budget_agent)
    workflow.add_node("itinerary_agent", itinerary_agent)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("revise_itinerary_node", revise_itinerary_node)
    workflow.add_node("rejected_node", rejected_node)
    workflow.add_node("final_agent", final_agent)

    # 2. Graph Wiring
    workflow.add_edge(START, "guardrails_node")
    workflow.add_conditional_edges(
        "guardrails_node",
        route_after_guardrails,
        {"supervisor_agent": "supervisor_agent", "blocked_request_node": "blocked_request_node"}
    )
    workflow.add_edge("blocked_request_node", END)

    # Parallel Fan-Out: Supervisor triggers all retrieval tools at once
    workflow.add_edge("supervisor_agent", "flight_agent")
    workflow.add_edge("supervisor_agent", "hotel_agent")
    workflow.add_edge("supervisor_agent", "weather_agent")

    # Fan-In Barrier: Budget agent waits for all parallel research to finish
    workflow.add_edge(["flight_agent", "hotel_agent", "weather_agent"], "budget_agent")

    # Pipeline forward
    workflow.add_edge("budget_agent", "itinerary_agent")
    workflow.add_edge("itinerary_agent", "human_approval_node")

    # HITL Gates
    workflow.add_conditional_edges(
        "human_approval_node",
        route_after_approval,
        {
            "final_agent": "final_agent",
            "revise_itinerary_node": "revise_itinerary_node",
            "rejected_node": "rejected_node"
        }
    )
    workflow.add_edge("revise_itinerary_node", "human_approval_node")
    workflow.add_edge("rejected_node", END)
    workflow.add_edge("final_agent", END)

    checkpointer = AsyncPostgresSaver(_pool)
    await checkpointer.setup()

    return workflow.compile(checkpointer=checkpointer)