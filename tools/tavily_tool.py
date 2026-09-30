# ═══════════════════════════════════════════════════════════════════════════
#  🏨  TAVILY HOTEL TOOL — Grounded Pydantic Extraction
# ═══════════════════════════════════════════════════════════════════════════
import os
import re
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


class RawHotel(BaseModel):
    name: str = Field(description="Exact hotel or homestay name (no aggregator headlines)")
    location: Optional[str] = Field(default=None, description="Neighborhood, landmark or town")
    rating: Optional[str] = Field(default="", description="Rating if mentioned e.g. 4.3★")
    price_per_night: Optional[int] = Field(default=None, description="Per room per night price in INR")
    amenities: Optional[str] = Field(default="Standard Room", description="Key amenities e.g. Wi-Fi, AC, Breakfast")
    url: Optional[str] = Field(default="", description="Direct booking or OTA URL from snippet")


class HotelSearchModel(BaseModel):
    hotels: List[RawHotel] = Field(default_factory=list, description="List of authentic hotels found")


def _to_num(value, default: float = 0.0) -> float:
    try:
        cleaned = re.sub(r"[^\d.]", "", str(value))
        return float(cleaned) if cleaned else default
    except (ValueError, TypeError):
        return default


@tool
def search_hotels(city: str, budget_tier: str = "moderate") -> str:
    """
    Search real verified hotels and homestays with realistic pricing tailored to budget tier.
    """
    tavily_key = os.getenv("TAVILY_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    if not tavily_key or not groq_key:
        return json.dumps({"city": city, "hotels": [], "error": "API keys missing"}, ensure_ascii=False)

    tier = budget_tier.lower() if budget_tier else "moderate"

    if tier == "luxury":
        query = f"luxury 5 star hotels resorts in {city} room tariff price per night booking makemytrip"
        default_price = 7500
    elif tier == "budget":
        query = f"budget hotels homestay guest house in {city} room price per night tariff goibibo"
        default_price = 1200
    else:
        query = f"hotels in {city} room tariff price per night makemytrip goibibo"
        default_price = 2500

    try:
        tavily = TavilyClient(api_key=tavily_key)
        res = tavily.search(query=query, search_depth="advanced", max_results=5)

        context_parts = []
        for r in res.get("results", []):
            context_parts.append(
                f"Title: {r.get('title', '')}\n"
                f"URL: {r.get('url', '')}\n"
                f"Snippet: {(r.get('content') or '')[:500]}"
            )
        context = "\n\n".join(context_parts)

        if not context.strip():
            return json.dumps({"city": city, "hotels": [], "error": "No verified search results found"}, ensure_ascii=False)

        llm = ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=groq_key,
            temperature=0.0,
            max_tokens=2048,
        )

        extraction_prompt = f"""You are a strict Hotel Data Extractor. Extract REAL accommodation options from the search snippets for '{city}' tailored to '{tier}' tier.

SEARCH SNIPPETS:
{context[:4000]}

STRICT RULES:
1. ACTUAL PROPERTY NAMES ONLY: Reject aggregator headlines like 'Top 10 Hotels in...', 'Booking.com', 'Tripadvisor'.
2. Extract numeric tariff in INR if found. Otherwise leave None.
"""
        structured_llm = llm.with_structured_output(HotelSearchModel)
        parsed: HotelSearchModel = structured_llm.invoke([
            {"role": "system", "content": "Extract genuine hotel properties from search context."},
            {"role": "user", "content": extraction_prompt}
        ])

        aggregator_keywords = ["top 10", "best hotels", "booking.com", "tripadvisor", "makemytrip", "goibibo", "hotels in"]
        hotels = []
        seen = set()

        for h in parsed.hotels:
            name = (h.name or "").strip()
            if not name or name.lower() in seen:
                continue
            if any(k in name.lower() for k in aggregator_keywords):
                continue
            seen.add(name.lower())

            price = h.price_per_night or default_price
            if price <= 0:
                price = default_price

            hotels.append({
                "name": name,
                "location": h.location or city,
                "rating": h.rating or "",
                "price_per_night": int(price),
                "price_is_estimate": h.price_per_night is None,
                "amenities": h.amenities or "Standard Room",
                "url": h.url or f"https://www.google.com/travel/hotels/{city}",
                "title": name,
                "snippet": f"{h.location or city} • ₹{price}/night"
            })

        return json.dumps({
            "city": city,
            "budget_tier": tier,
            "total_found": len(hotels),
            "hotels": hotels[:5]
        }, indent=2, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"city": city, "hotels": [], "error": str(e)}, ensure_ascii=False)