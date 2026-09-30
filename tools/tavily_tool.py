# ═══════════════════════════════════════════════════════════════════════════
#  🏨  TAVILY HOTEL TOOL — with LLM extraction for real hotel names
# ═══════════════════════════════════════════════════════════════════════════
import os
import json
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


# ───────────────────────────────────────────────────────────────────────────
#  🏨  search_hotels — Tavily + LLM structured extraction
# ───────────────────────────────────────────────────────────────────────────
@tool
def search_hotels(city: str, budget_tier: str = "moderate") -> str:
    """
    Search real hotels with names, prices, ratings using Tavily + LLM.
    """
    tavily_key = os.getenv("TAVILY_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    if not tavily_key:
        return json.dumps({"error": "TAVILY_API_KEY missing", "hotels": []})
    if not groq_key:
        return json.dumps({"error": "GROQ_API_KEY missing", "hotels": []})

    raw_text = ""  # will be set inside try

    try:
        # ─── Step 1: Tavily search ───
        tavily = TavilyClient(api_key=tavily_key)
        query = f"best {budget_tier} hotels in {city} with prices booking.com tripadvisor"
        res = tavily.search(query=query, search_depth="advanced", max_results=5)

        context_parts = []
        for r in res.get("results", []):
            context_parts.append(
                f"Title: {r.get('title', '')}\n"
                f"URL: {r.get('url', '')}\n"
                f"Content: {(r.get('content') or '')[:500]}"
            )
        context = "\n\n".join(context_parts)

        if not context.strip():
            return json.dumps({"city": city, "hotels": [], "error": "No results"})

        # ─── Step 2: LLM extracts JSON ───
        llm = ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=groq_key,
            temperature=0,
            max_tokens=2048,
        )

        extraction_prompt = f"""You are a hotel data extractor. Extract SPECIFIC hotels from search results.

SEARCH RESULTS:
{context[:4000]}

RULES:
1. Extract ACTUAL HOTEL NAMES (not "Top 10" website titles)

2. Extract price per night in INR (TRY HARDER):
   - Look for "$37", "₹2,500", "Rs 3,000", "TL 1,139", "R$ 336"
   - "$37/night" → 3100
   - "₹2,500/night" → 2500
   - If multiple prices, use the LOWEST for "budget", MIDDLE for "moderate", HIGHEST for "luxury"
   - If truly no price → ESTIMATE based on hotel tier:
     * Hostel/budget → 800
     * 3-star → 2000  
     * 4-star → 4000
     * 5-star/luxury → 8000
   - NEVER return 0. Always estimate if uncertain.

3. Extract rating if present ("9.6/10", "4.5★", "Very Good 8.4")

4. Extract location/area ("Mall Road", "Old Manali")

5. Extract amenities ("Pool, Free Breakfast")

OUTPUT — ONLY valid JSON:

{{
  "hotels": [
    {{
      "name": "The Hosteller Shimla",
      "location": "Mall Road, Shimla",
      "rating": "8.2/10",
      "price_per_night": 1200,
      "amenities": "Wi-Fi, Common Area",
      "url": "https://..."
    }}
  ]
}}

Extract UP TO 5 hotels. Return {{"hotels": []}} if truly none found.
"""

        response = llm.invoke(extraction_prompt)
        raw_text = response.content.strip()

        # Clean markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        # Extract JSON block
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            raw_text = raw_text[json_start:json_end]

        parsed = json.loads(raw_text)
        raw_hotels = parsed.get("hotels", [])

        # ─── Step 3: Normalize output ───
        hotels = []
        for h in raw_hotels[:5]:
            name = h.get("name") or h.get("title") or "Hotel"
            hotels.append({
                "name": name,
                "location": h.get("location", ""),
                "rating": h.get("rating", ""),
                "price_per_night": int(h.get("price_per_night") or 0),
                "amenities": h.get("amenities", ""),
                "url": h.get("url") or h.get("booking_url", ""),
                # Backward compatible
                "title": name,
                "snippet": f"{h.get('rating', '')} • {h.get('location', '')}".strip(" •"),
            })

        return json.dumps({
            "city": city,
            "budget_tier": budget_tier,
            "total_found": len(hotels),
            "hotels": hotels,
        }, indent=2)

    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse failed: {e}")
        print(f"Raw LLM output: {raw_text[:500]}")
        return json.dumps({
            "city": city,
            "hotels": [],
            "error": f"JSON parse failed: {str(e)}"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "city": city,
            "hotels": [],
            "error": f"Hotel search failed: {str(e)}"
        })


# ───────────────────────────────────────────────────────────────────────────
#  🧪  Test
# ───────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing search_hotels (Manali)...")
    result = search_hotels.invoke({"city": "Manali", "budget_tier": "moderate"})
    print(result)