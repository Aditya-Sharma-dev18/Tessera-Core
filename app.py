# ═══════════════════════════════════════════════════════════════════════════
#  🔧  WINDOWS EVENT LOOP FIX — MUST BE FIRST
# ═══════════════════════════════════════════════════════════════════════════
import sys
import asyncio

if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("[Tessera] Windows SelectorEventLoop policy set")

import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ═══════════════════════════════════════════════════════════════════════════
#  📦  IMPORTS
# ═══════════════════════════════════════════════════════════════════════════
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langgraph.types import Command

load_dotenv()

# Local imports
from backend import build_graph, _pool


# ═══════════════════════════════════════════════════════════════════════════
#  📋  SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════
class PlanRequest(BaseModel):
    query: str = Field(..., min_length=5)


class ApprovalRequest(BaseModel):
    decision: str
    feedback: Optional[str] = ""


class PlanResponse(BaseModel):
    thread_id: str
    status: str
    message: Optional[str] = None
    approval_request: Optional[str] = None
    trip_constraints: Optional[Dict[str, Any]] = None
    selected_agents: Optional[list] = None
    flight_results: Optional[str] = None
    rails_results: Optional[str] = None
    bus_results: Optional[str] = None
    hotel_results: Optional[str] = None
    weather_results: Optional[str] = None
    budget_results: Optional[str] = None
    itinerary: Optional[str] = None
    final_response: Optional[str] = None
    approved: Optional[str] = None
    # Typed fields for direct frontend rendering
    travelers_count: Optional[int] = None
    duration_days: Optional[int] = None
    estimated_total_inr: Optional[int] = None
    transit_options: Optional[List[Dict[str, Any]]] = None
    selected_hotel: Optional[Dict[str, Any]] = None
    selected_transit: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════════════════
#  🔄  LIFESPAN
# ═══════════════════════════════════════════════════════════════════════════
graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph
    print("🚀 Starting Tessera Travel Engine...")

    # 1. Pool open
    await _pool.open()

    # 2. Build graph (async — checkpointer setup inside build_graph)
    graph = await build_graph()
    print("✅ Graph compiled with Async Postgres checkpointer")

    yield

    # Shutdown
    try:
        await _pool.close()
        print("🔒 Postgres pool closed")
    except Exception as e:
        print(f"⚠️  Pool close warning: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  ⚡  APP
# ═══════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title="Tessera Travel Engine",
    description="Multi-Agent Trip Planner with HITL",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ═══════════════════════════════════════════════════════════════════════════
#  🏠  ROOT
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


# ═══════════════════════════════════════════════════════════════════════════
#  🧠  HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def build_initial_state(user_query: str) -> Dict[str, Any]:
    return {
        "user_query": user_query,
        "guardrail_allowed": False,
        "guardrail_reason": "",
        "trip_constraints": {},
        "selected_agents": [],
        "supervisor_reasoning": "",
        "flight_results": "",
        "rails_results": "",
        "bus_results": "",
        "hotel_results": "",
        "weather_results": "",
        "budget_results": "",
        "travelers_count": 2,
        "duration_days": 2,
        "estimated_total_inr": 0,
        "transit_options": [],
        "selected_hotel": None,
        "selected_transit": None,
        "itinerary": "",
        "human_feedback": "",
        "approved": "pending",
        "approval_request": "",
        "messages": [],
        "final_response": "",
    }


def extract_interrupt(snapshot) -> Optional[Dict[str, Any]]:
    if not snapshot or not getattr(snapshot, "interrupts", None):
        return None
    first = snapshot.interrupts[0]
    return getattr(first, "value", None) or (first if isinstance(first, dict) else None)


def serialize_state(values: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(values or {})
    safe.pop("messages", None)
    return safe


# ═══════════════════════════════════════════════════════════════════════════
#  🎯  POST /api/plan
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/api/plan", response_model=PlanResponse)
async def start_plan(req: PlanRequest):
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized yet")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        initial_state = build_initial_state(req.query)

        async for _ in graph.astream(initial_state, config=config):
            pass

        snapshot = await graph.aget_state(config)
        interrupt_payload = extract_interrupt(snapshot)
        state_values = serialize_state(snapshot.values or {})

        # Blocked by guardrails
        if state_values.get("approved") == "rejected" and not interrupt_payload:
            return PlanResponse(
                thread_id=thread_id,
                status="blocked",
                message=state_values.get("final_response", "Blocked by guardrails"),
                final_response=state_values.get("final_response"),
                approved="rejected",
            )

        # Awaiting approval
        if interrupt_payload:
            return PlanResponse(
                thread_id=thread_id,
                status="awaiting_approval",
                approval_request=interrupt_payload.get("approval_request"),
                trip_constraints=state_values.get("trip_constraints"),
                selected_agents=state_values.get("selected_agents"),
                flight_results=state_values.get("flight_results"),
                rails_results=state_values.get("rails_results"),
                bus_results=state_values.get("bus_results"),
                hotel_results=state_values.get("hotel_results"),
                weather_results=state_values.get("weather_results"),
                budget_results=state_values.get("budget_results"),
                itinerary=state_values.get("itinerary"),
                final_response=state_values.get("final_response"),
                approved="pending",
                travelers_count=state_values.get("travelers_count"),
                duration_days=state_values.get("duration_days"),
                estimated_total_inr=state_values.get("estimated_total_inr"),
                transit_options=state_values.get("transit_options"),
                selected_hotel=state_values.get("selected_hotel"),
                selected_transit=state_values.get("selected_transit"),
            )

        # Completed
        return PlanResponse(
            thread_id=thread_id,
            status="completed",
            final_response=state_values.get("final_response", ""),
            itinerary=state_values.get("itinerary"),
            budget_results=state_values.get("budget_results"),
            trip_constraints=state_values.get("trip_constraints"),
            flight_results=state_values.get("flight_results"),
            rails_results=state_values.get("rails_results"),
            bus_results=state_values.get("bus_results"),
            hotel_results=state_values.get("hotel_results"),
            weather_results=state_values.get("weather_results"),
            approved=state_values.get("approved", "approved"),
            travelers_count=state_values.get("travelers_count"),
            duration_days=state_values.get("duration_days"),
            estimated_total_inr=state_values.get("estimated_total_inr"),
            transit_options=state_values.get("transit_options"),
            selected_hotel=state_values.get("selected_hotel"),
            selected_transit=state_values.get("selected_transit"),
        )

    except Exception as exc:
        import traceback
        print("\n" + "=" * 70)
        print("❌ ERROR IN /api/plan")
        print("=" * 70)
        traceback.print_exc()
        print("=" * 70 + "\n")
        raise HTTPException(
            status_code=500,
            detail=f"Planning failed: {type(exc).__name__}: {str(exc)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  ✅  POST /api/plan/{thread_id}/approve
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/api/plan/{thread_id}/approve", response_model=PlanResponse)
async def approve_plan(thread_id: str, req: ApprovalRequest):
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    config = {"configurable": {"thread_id": thread_id}}

    try:
        resume_payload = {"decision": req.decision, "feedback": req.feedback or ""}

        async for _ in graph.astream(Command(resume=resume_payload), config=config):
            pass

        snapshot = await graph.aget_state(config)
        interrupt_payload = extract_interrupt(snapshot)
        state_values = serialize_state(snapshot.values or {})

        if interrupt_payload:
            return PlanResponse(
                thread_id=thread_id,
                status="awaiting_approval",
                approval_request=interrupt_payload.get("approval_request"),
                itinerary=state_values.get("itinerary"),
                budget_results=state_values.get("budget_results"),
                trip_constraints=state_values.get("trip_constraints"),
                flight_results=state_values.get("flight_results"),
                rails_results=state_values.get("rails_results"),
                bus_results=state_values.get("bus_results"),
                hotel_results=state_values.get("hotel_results"),
                weather_results=state_values.get("weather_results"),
                approved="pending",
                message="Revised plan ready for review",
                travelers_count=state_values.get("travelers_count"),
                duration_days=state_values.get("duration_days"),
                estimated_total_inr=state_values.get("estimated_total_inr"),
                transit_options=state_values.get("transit_options"),
                selected_hotel=state_values.get("selected_hotel"),
                selected_transit=state_values.get("selected_transit"),
            )

        return PlanResponse(
            thread_id=thread_id,
            status="completed",
            final_response=state_values.get("final_response", ""),
            itinerary=state_values.get("itinerary"),
            budget_results=state_values.get("budget_results"),
            trip_constraints=state_values.get("trip_constraints"),
            hotel_results=state_values.get("hotel_results"),
            flight_results=state_values.get("flight_results"),
            rails_results=state_values.get("rails_results"),
            bus_results=state_values.get("bus_results"),
            weather_results=state_values.get("weather_results"),
            approved=state_values.get("approved", "approved"),
            travelers_count=state_values.get("travelers_count"),
            duration_days=state_values.get("duration_days"),
            estimated_total_inr=state_values.get("estimated_total_inr"),
            transit_options=state_values.get("transit_options"),
            selected_hotel=state_values.get("selected_hotel"),
            selected_transit=state_values.get("selected_transit"),
        )

    except Exception as exc:
        import traceback
        print("\n" + "=" * 70)
        print("❌ ERROR IN /api/plan/{thread_id}/approve")
        print("=" * 70)
        traceback.print_exc()
        print("=" * 70 + "\n")
        raise HTTPException(
            status_code=500,
            detail=f"Approval failed: {type(exc).__name__}: {str(exc)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  ❌  POST /api/plan/{thread_id}/reject
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/api/plan/{thread_id}/reject", response_model=PlanResponse)
async def reject_plan(thread_id: str, req: ApprovalRequest):
    req.decision = "reject"
    return await approve_plan(thread_id, req)


# ═══════════════════════════════════════════════════════════════════════════
#  🔍  GET /api/plan/{thread_id}/status
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/api/plan/{thread_id}/status", response_model=PlanResponse)
async def plan_status(thread_id: str):
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    config = {"configurable": {"thread_id": thread_id}}

    try:
        snapshot = await graph.aget_state(config)
        if snapshot is None or not snapshot.values:
            raise HTTPException(status_code=404, detail="Thread not found")

        interrupt_payload = extract_interrupt(snapshot)
        state_values = serialize_state(snapshot.values)

        return PlanResponse(
            thread_id=thread_id,
            status="awaiting_approval" if interrupt_payload else "completed",
            approval_request=(interrupt_payload or {}).get("approval_request"),
            itinerary=state_values.get("itinerary"),
            budget_results=state_values.get("budget_results"),
            trip_constraints=state_values.get("trip_constraints"),
            flight_results=state_values.get("flight_results"),
            rails_results=state_values.get("rails_results"),
            bus_results=state_values.get("bus_results"),
            hotel_results=state_values.get("hotel_results"),
            weather_results=state_values.get("weather_results"),
            final_response=state_values.get("final_response"),
            approved=state_values.get("approved", "pending"),
            travelers_count=state_values.get("travelers_count"),
            duration_days=state_values.get("duration_days"),
            estimated_total_inr=state_values.get("estimated_total_inr"),
            transit_options=state_values.get("transit_options"),
            selected_hotel=state_values.get("selected_hotel"),
            selected_transit=state_values.get("selected_transit"),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Status lookup failed: {str(exc)}")


# ═══════════════════════════════════════════════════════════════════════════
#  💚  HEALTH
# ═══════════════════════════════════════════════════════════════════════════
@app.get("/health")
async def health():
    return {"status": "ok", "graph_ready": graph is not None}


# ═══════════════════════════════════════════════════════════════════════════
#  ▶️  RUN — with proper Windows event loop
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn

    # Force SelectorEventLoop on Windows (psycopg async requirement)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)

    config = uvicorn.Config(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    try:
        loop.run_until_complete(server.serve())
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        loop.close()