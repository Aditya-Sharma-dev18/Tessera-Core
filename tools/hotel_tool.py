import os
import json
from langchain_core.tools import tool
from tavily import TavilyClient

@tool
def search_hotels(city: str, budget_tier: str = "moderate") -> str:
    """Live hotel search tool using Tavily web search."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return json.dumps({"error": "TAVILY_API_KEY missing"})

    try:
        tavily = TavilyClient(api_key=tavily_key)
        query = f"top rated hotels in {city} price per night {budget_tier} reviews booking"
        res = tavily.search(query=query, search_depth="basic", max_results=4)
        
        hotels = []
        for r in res.get("results", []):
            hotels.append({
                "title": r.get("title"),
                "snippet": r.get("content"),
                "url": r.get("url")
            })
        return json.dumps({"city": city, "hotels": hotels})
    except Exception as e:
        return json.dumps({"error": f"Hotel search failed: {str(e)}"})