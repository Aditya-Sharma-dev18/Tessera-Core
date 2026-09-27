from tavily import TavilyClient
import os
from dotenv import load_dotenv
load_dotenv()
client=TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

def tavily_search(query):
    response=client.search(
        max_results=5,
        query=query
    )
    results=[]
    for i,r in enumerate(response["results"],1):
        title=r.get("title","unknown")
        url=r.get("url","")
        content=r.get("content","").strip()
        if len(content)>300:
            content=content[:300].rsplit(" ",1)[0] + "..."
        results.append(f"{i}. **{title}**\n   {url}\n   {content}")    
    return "\n\n".join(results)

