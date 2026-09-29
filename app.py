# ═══════════════════════════════════════════════════════════════════════════
#  🚀  TESSERA TRAVEL ENGINE — FastAPI Backend
# ═══════════════════════════════════════════════════════════════════════════
#  Endpoints:
#    GET  /                          → serve index.html
#    POST /api/plan                  → start a new trip planning session
#    POST /api/plan/{thread_id}/approve  → HITL approve
#    POST /api/plan/{thread_id}/reject   → HITL reject with feedback
#    GET  /api/plan/{thread_id}/status   → poll current state
# ═══════════════════════════════════════════════════════════════════════════

import os
import uuid
import json
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langgraph.types import Command

# Import your existing graph builder
from backend import build_graph, _pool   # ← adjust if module name differs

load_dotenv()


# ───────────────────────────────────────────────────────────────────────────
#  📋  REQUEST / RESPONSE SCHEMAS
# ───────────────────────────────────────────────────────────────────────────
class PlanRequest(BaseModel):
    query: str = Field(..., min_length=5, description="Natural language travel query")


class ApprovalRequest(BaseModel):
    decision: str = Field(..., description="approve | reject | feedback")
    feedback: Optional[str] = Field("", description="Optional feedback for revisions")


class PlanResponse(BaseModel):
    thread_id: str
    status: str                      # "awaiting_approval" | "completed" | "blocked" | "error"
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


# ───────────────────────────────────────────────────────────────────────────
#  🔄  LIFESPAN — graph build once at startup
# ───────────────────────────────────────────────────────────────────────────
graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph
    print("🚀 Starting Tessera Travel Engine...")
    graph = build_graph()
    print("✅ Graph compiled with Postgres checkpointer")
    yield
    # Cleanup
    try:
        _pool.close()
        print("🔒 Postgres pool closed")
    except Exception as e:
        print(f"⚠️  Pool close warning: {e}")


# ───────────────────────────────────────────────────────────────────────────
#  ⚡  FASTAPI APP
# ───────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Tessera Travel Engine",
    description="Multi-Agent Trip Planner with HITL",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ───────────────────────────────────────────────────────────────────────────
#  🏠  ROOT — Serve frontend
# ───────────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ───────────────────────────────────────────────────────────────────────────
#  🧠  HELPER — Build initial state
# ───────────────────────────────────────────────────────────────────────────
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
        "itinerary": "",
        "human_feedback": "",
        "approved": "pending",
        "approval_request": "",
        "messages": [],
        "final_response": "",
    }


def extract_interrupt(snapshot) -> Optional[Dict[str, Any]]:
    """Safely extract interrupt payload from a graph snapshot."""
    if not snapshot or not getattr(snapshot, "interrupts", None):
        return None
    first = snapshot.interrupts[0]
    return getattr(first, "value", None) or (first if isinstance(first, dict) else None)


def serialize_state(values: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-serializable objects (messages) from state."""
    safe = dict(values)
    safe.pop("messages", None)   # AIMessage objects aren't JSON-serializable
    return safe


# ───────────────────────────────────────────────────────────────────────────
#  🎯  POST /api/plan — Start new plan
# ───────────────────────────────────────────────────────────────────────────
@app.post("/api/plan", response_model=PlanResponse)
async def start_plan(req: PlanRequest):
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized yet")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        initial_state = build_initial_state(req.query)

        # Run graph until it hits interrupt OR finishes
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
                message=state_values.get("final_response", "Request blocked by guardrails"),
                **{k: state_values.get(k) for k in (
                    "guardrail_reason", "final_response"
                ) if k in state_values}
            )

        # Awaiting human approval
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
                approved="pending",
            )

        # Completed (unlikely in first run, but safe)
        return PlanResponse(
            thread_id=thread_id,
            status="completed",
            final_response=state_values.get("final_response", ""),
            itinerary=state_values.get("itinerary"),
            budget_results=state_values.get("budget_results"),
            approved=state_values.get("approved", "approved"),
        )

    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(exc)}")


# ───────────────────────────────────────────────────────────────────────────
#  ✅  POST /api/plan/{thread_id}/approve
# ───────────────────────────────────────────────────────────────────────────
@app.post("/api/plan/{thread_id}/approve", response_model=PlanResponse)
async def approve_plan(thread_id: str, req: ApprovalRequest):
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    config = {"configurable": {"thread_id": thread_id}}

    try:
        resume_payload = {"decision": req.decision, "feedback": req.feedback or ""}

        # Resume graph — it may finish OR re-interrupt (if feedback triggers revise)
        async for _ in graph.astream(Command(resume=resume_payload), config=config):
            pass

        snapshot = await graph.aget_state(config)
        interrupt_payload = extract_interrupt(snapshot)
        state_values = serialize_state(snapshot.values or {})

        # Re-interrupted → still awaiting approval
        if interrupt_payload:
            return PlanResponse(
                thread_id=thread_id,
                status="awaiting_approval",
                approval_request=interrupt_payload.get("approval_request"),
                itinerary=state_values.get("itinerary"),
                budget_results=state_values.get("budget_results"),
                approved="pending",
                message="Revised plan ready for review",
            )

        # Final completion
        return PlanResponse(
            thread_id=thread_id,
            status="completed",
            final_response=state_values.get("final_response", ""),
            itinerary=state_values.get("itinerary"),
            budget_results=state_values.get("budget_results"),
            hotel_results=state_values.get("hotel_results"),
            flight_results=state_values.get("flight_results"),
            rails_results=state_values.get("rails_results"),
            bus_results=state_values.get("bus_results"),
            weather_results=state_values.get("weather_results"),
            approved=state_values.get("approved", "approved"),
        )

    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(exc)}")


# ───────────────────────────────────────────────────────────────────────────
#  ❌  POST /api/plan/{thread_id}/reject
# ───────────────────────────────────────────────────────────────────────────
@app.post("/api/plan/{thread_id}/reject", response_model=PlanResponse)
async def reject_plan(thread_id: str, req: ApprovalRequest):
    """Shortcut — reject is just approve with decision='reject'."""
    req.decision = "reject"
    return await approve_plan(thread_id, req)


# ───────────────────────────────────────────────────────────────────────────
#  🔍  GET /api/plan/{thread_id}/status
# ───────────────────────────────────────────────────────────────────────────
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
            flight_results=state_values.get("flight_results"),
            hotel_results=state_values.get("hotel_results"),
            final_response=state_values.get("final_response"),
            approved=state_values.get("approved", "pending"),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Status lookup failed: {str(exc)}")


# ───────────────────────────────────────────────────────────────────────────
#  💚  HEALTH CHECK
# ───────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "graph_ready": graph is not None}


# ───────────────────────────────────────────────────────────────────────────
#  ▶️  RUN
# ───────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)