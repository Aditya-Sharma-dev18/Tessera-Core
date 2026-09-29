# ═══════════════════════════════════════════════════════════════════════════
#  🏨  TAVILY TOOL — Hotel search via Tavily web search
# ═══════════════════════════════════════════════════════════════════════════
import os
import json
from langchain_core.tools import tool
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()


# ───────────────────────────────────────────────────────────────────────────
#  🏨  search_hotels — LangChain @tool (invoked by hotel_agent)
# ───────────────────────────────────────────────────────────────────────────
@tool
def search_hotels(city: str, budget_tier: str = "moderate") -> str:
    """
    Search top-rated hotels and stays in a city using live Tavily web search.

    Args:
        city: Destination city (e.g., 'Goa', 'Manali', 'Dubai').
        budget_tier: 'budget' | 'moderate' | 'luxury' — controls query phrasing.

    Returns:
        JSON string with {city, budget_tier, hotels: [{title, snippet, url}]}
    """
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return json.dumps({"error": "TAVILY_API_KEY missing from environment"})

    try:
        tavily = TavilyClient(api_key=tavily_key)
        query = (
            f"top rated hotels in {city} "
            f"{budget_tier} price per night reviews booking"
        )
        res = tavily.search(query=query, search_depth="basic", max_results=4)

        hotels = []
        for r in res.get("results", []):
            hotels.append({
                "title": r.get("title", "Hotel"),
                "snippet": (r.get("content") or "")[:300],
                "url": r.get("url", ""),
            })

        return json.dumps({
            "city": city,
            "budget_tier": budget_tier,
            "total_found": len(hotels),
            "hotels": hotels,
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Hotel search failed: {str(e)}"})


# ───────────────────────────────────────────────────────────────────────────
#  🔍  tavily_search — generic web search (optional, kept for reuse)
# ───────────────────────────────────────────────────────────────────────────
def tavily_search(query: str, max_results: int = 5) -> str:
    """Generic Tavily web search — returns formatted markdown string."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return "Error: TAVILY_API_KEY missing"

    try:
        client = TavilyClient(api_key=tavily_key)
        response = client.search(query=query, max_results=max_results)

        results = []
        for i, r in enumerate(response.get("results", []), 1):
            title = r.get("title", "Unknown")
            url = r.get("url", "")
            content = (r.get("content") or "").strip()
            if len(content) > 300:
                content = content[:300].rsplit(" ", 1)[0] + "..."
            results.append(f"{i}. **{title}**\n   {url}\n   {content}")

        return "\n\n".join(results)

    except Exception as e:
        return f"Tavily search failed: {str(e)}"


# ───────────────────────────────────────────────────────────────────────────
#  🧪  Direct test
# ───────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing search_hotels (Goa, moderate)...")
    print(search_hotels.invoke({"city": "Goa", "budget_tier": "moderate"}))