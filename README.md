# ✦ Tessera-Core — Stateful Cyclic Multi-Agent Runtime for Combinatorial Multi-Modal Transit Synthesis

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0+-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Groq](https://img.shields.io/badge/Groq-Ultra--Fast_Inference-f55036.svg)](https://groq.com/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-FastMCP_1.2+-purple.svg)](https://modelcontextprotocol.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon_Checkpointer-blue.svg)](https://neon.tech/)
[![LangSmith](https://img.shields.io/badge/LangSmith-Observability-orange.svg)](https://smith.langchain.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](#-license)

> **A stateful cyclic multi-agent runtime for combinatorial multi-modal transit synthesis, engineered with dynamic supervisory routing, process-isolated FastMCP tool planes, zero-hallucination geospatial grounding, and checkpoint-backed human-in-the-loop (HITL) suspension primitives.**

---

## 📋 **Table of Contents**

- [Problem Statement](#-problem-statement)
- [Solution Overview](#-solution-overview)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Usage](#-usage)
- [API Endpoints](#-api-endpoints)
- [FastMCP Tool Protocol](#-fastmcp-tool-protocol)
- [Observability with LangSmith](#-observability-with-langsmith)
- [Configuration](#-configuration)
- [Deployment](#-deployment)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)
- [Contact & Support](#-contact--support)

---

## 🚨 **Problem Statement**

### **The Challenge**

Planning complex, multi-modal travel across flights, intercity railways, regional buses, accommodations, and day-by-day activities is fundamentally a **combinatorial optimization problem** fraught with execution bottlenecks:

- **Multi-Modal Fragmentation**: Transit options operate across isolated silos (aviation GDS, national railway reservation APIs like IRCTC, state roadway buses, private fleets like RedBus, hotel aggregators). No single system reconciles them concurrently.
- **Geographic Hallucinations**: Standard LLMs routinely invent impossible logistics—hallucinating rivers in landlocked towns, suggesting auto-rickshaws for 200 km Himalayan mountain ascents, confusing transit hubs (e.g. Haridwar/Rishikesh) with actual high-altitude stay settlements (e.g. Kanakchauri/Chopta), or fabricating non-existent train numbers.
- **Economic Disconnect**: Generic trip planners generate arbitrary budgets disconnected from real-world local economic baselines (regional meal averages, mountain last-mile 4x4 rates, room tariffs scaled to seasonal tiers).
- **The Black-Box Dilemma**: Autonomous AI travel planners operate as uncontrollable "fire-and-forget" bots. Travelers cannot pause the workflow, inspect live fares, provide natural language revisions, or lock in verified options before committing.
- **Ephemeral State Loss**: Multi-agent pipelines without persistent state machines fail catastrophically when a browser disconnects, an API rate-limits, or a human takes hours to review a generated draft.

### **The Gap**

There is no **open, production-grade, state-persisted multi-agent runtime** that:

- Validates incoming natural language requests via semantic input guardrails.
- Resolves geography, elevation, transit gateway hubs, and destination economics dynamically without brittle hardcoded city lists.
- Runs process-isolated tool retrieval across flights, trains, buses, hotels, and weather concurrently via the **Model Context Protocol (FastMCP)**.
- Persists state durability in a high-throughput **PostgreSQL connection pool** with zero state loss.
- Provides native **Human-in-the-Loop (HITL)** suspension gates with cyclic feedback loops for real-time plan modification.

---

## 💡 **Solution Overview**

**Tessera-Core** orchestrates specialized, autonomous agents across a cyclic **LangGraph** execution graph:

```
[User Query] ──► [Input Guardrails] ──► [Supervisor Agent]
                                                │
         ┌──────────────────────────────────────┼──────────────────────────────────────┐
         ▼                                      ▼                                      ▼
  [Flight Specialist]                   [Hotel Specialist]                   [Weather Specialist]
  (fast_flights/Amadeus)               (Tavily Live Tariffs)                (Open-Meteo Geocoding)
         │                                      │                                      │
         └──────────────────────────────────────┼──────────────────────────────────────┘
                                                ▼
                                   [Budget & Economic Engine]
                                                │
                                                ▼
                                    [Itinerary Architect]
                                                │
                                                ▼
                                  [HITL Approval Gate (Pause)]
                                         │             ▲
                        Approve / Lock   │             │ Natural Language Feedback
                                         ▼             │ (Cyclic Loop)
                              [Executive Concierge] ───┴── [Revise Itinerary]
                                         │
                                         ▼
                             [Final Travel Dossier]
```

1. **Input Guardrails** — Validates user queries with Pydantic schemas (`GuardrailsValidation`) to enforce safety and travel-domain intent. Out-of-bounds requests are rejected immediately.
2. **Supervisor Agent** — Extracts trip constraints (origin, destination, calendar dates, duration, travelers count, explicit transit mode, budget, stay tier) via structured output without hardcoded assumptions.
3. **Dynamic Geo & Economic Resolver** — Fetches live Tavily web grounding to determine elevation, terrain, transit gateway hubs, base stay settlements, and local living economics (meals, local transit, entry fees).
4. **Parallel FastMCP Tool Plane** — Dispatches concurrent asynchronous calls to search live flights (`fast_flights`/Amadeus), Indian Railways trains (RapidAPI/ConfirmTkt), intercity buses (Tavily/RedBus), hotel tariffs, and destination weather (Open-Meteo).
5. **Deterministic Budget Engine** — Serves as a synchronization barrier, deterministically matching transit options, room counts, and living expenses against user constraints with zero hallucinated math.
6. **Lead Itinerary Architect** — Constructs grounded, day-by-day schedules (DAY 01 to DAY XX) anchored strictly to verified attractions, actual road corridors, and authentic trailhead points.
7. **Human-in-the-Loop (HITL) Gate** — Uses `langgraph.types.interrupt` to suspend execution, checkpoint state to **Neon PostgreSQL**, and await human approval, natural language modification, or cancellation.
8. **Executive Concierge** — Formulates the final, locked travel dossier featuring 1-click booking deep links, verified accommodation cards, and practical packing advisories.

### **What Makes It Special**

- ✅ **Cyclic Graph with State Suspension**: True pause-and-resume capability via LangGraph `interrupt()` and `Command(resume=...)`. Checkpointed directly into PostgreSQL.
- ✅ **Zero-Hardcoded Geographic Intelligence**: Handles any location worldwide—from bustling metropolises to remote Himalayan shrines—by dynamically identifying transit hubs vs. stay towns.
- ✅ **Anthropic Model Context Protocol (FastMCP)**: Standalone `server.py` exposing travel tools via standard `stdio` transport for Claude Desktop, MCP Inspector, or internal agent consumption.
- ✅ **Deterministic Cost Accounting**: Never invents travel costs. Integrates verified unit tariffs with room formulas: `(travelers + 1) // 2 * nights`.
- ✅ **1-Click Deep Booking Links**: Automatically synthesizes pre-filtered deep links for Google Flights, ConfirmTkt/IRCTC, and RedBus.
- ✅ **Ultra-Low Latency Inference**: Powered by Groq LPU inference running `openai/gpt-oss-20b` and `openai/gpt-oss-120b`.
- ✅ **Enterprise Observability**: End-to-end tracing, latency breakdowns, and token accounting powered by LangSmith.

---

## ✨ **Features**

### 🌟 **Core Features**

| Feature | Description |
|---------|-------------|
| **🛡️ Input Guardrail Agent** | Pydantic-validated safety filter classifying incoming prompts and rejecting adversarial attacks |
| **🎯 Dynamic Supervisor** | Extracts origin, destination, dates, travelers, and preferences without hardcoded defaults |
| **🌍 Zero-Hallucination Geo Resolver** | Distinguishes gateway hubs (e.g. Rishikesh) from remote stay bases (e.g. Kanakchauri) |
| **✈️ Live Flight Search** | Scrapes and queries commercial flight schedules and fares via `fast_flights` and Amadeus |
| **🚆 Indian Railways Engine** | Queries live trains, class availability (1A, 2A, 3A, SL), departure/arrival timings, and fares |
| **🚌 Intercity Bus Search** | Structured Tavily web extraction for state roadways and private Volvo/Sleeper operators |
| **🏨 Curated Accommodations** | Retrieves real hotels, guest houses, and homestays categorized by budget, moderate, or luxury |
| **⛅ Open-Meteo Weather** | Fetches live destination temperature, windspeed, and WMO weather condition codes |
| **💰 Deterministic Budgeting** | Formulates complete cost breakdowns across transit, lodging, food, and local sightseeing |
| **🗺️ Grounded Itinerary Architect** | Synthesizes chronological day-wise plans strictly adhering to verified landmarks and routes |
| **🧑‍💼 Checkpointed HITL Gate** | Suspends pipeline execution to allow travelers to approve, modify with feedback, or cancel |
| **🔗 1-Click Booking Links** | Deep-links directly to Google Flights, ConfirmTkt, and RedBus with pre-populated parameters |

### 🚀 **Advanced Features**

| Feature | Description |
|---------|-------------|
| **⚡ Asynchronous Postgres Checkpointing** | Uses `AsyncPostgresSaver` with Neon connection pooling (`psycopg_pool`) for crash resilience |
| **🔁 Cyclic Revision Feedback Loop** | Allows travelers to enter natural language corrections that route back to the itinerary architect |
| **🔌 FastMCP stdio Server** | Run `server.py` as an isolated MCP tool plane compatible with Claude Desktop and external agents |
| **⚡ Groq LPU Acceleration** | Blazing-fast inference speeds with `gpt-oss-20b` (routing/budget) and `gpt-oss-120b` (synthesis) |
| **🎨 Polished Responsive UI** | Glassmorphism interface with execution pipeline indicators, cost meters, and review modals |
| **🛡️ Secret-Safe Configuration** | Zero-leak credential architecture utilizing `.env` and `.gitignore` |
| **🔬 LangSmith Tracing** | Full visibility into agent state transitions, tool latency, and token consumption |

### 🎯 **Use Cases**

- **Autonomous Travel Concierges**: Deploy automated travel planning for high-touch consumer travel platforms.
- **Enterprise Booking Workflows**: Embed multi-modal transit synthesis with human approval into corporate travel systems.
- **Remote / Mountain Expedition Planning**: Safely plan multi-leg mountain treks requiring transit gateways, high-altitude transfers, and ridge trail itineraries.
- **Multi-Agent Research**: Benchmark stateful cyclic graphs, tool isolation, and human-in-the-loop suspension primitives.

---

## 🛠️ **Tech Stack**

### **System Architecture**

```mermaid
graph TD
    Client[Web Browser / API Consumer] -->|HTTP / JSON| FastAPI[FastAPI Async Server]
    FastAPI --> LG[LangGraph Orchestrator]
    LG --> Checkpoint[(Neon PostgreSQL Checkpointer)]
    LG --> Groq[Groq LPU LLM Engine]
    
    subgraph Tool Plane [FastMCP Tool Plane & External APIs]
        LG --> FT[flight_tool / fast_flights & Amadeus]
        LG --> RT[rails_tool / RapidAPI RailKit & IRCTC]
        LG --> BT[bus_tool / Tavily & RedBus]
        LG --> HT[tavily_tool / Hotel Tariffs]
        LG --> WT[weather_tool / Open-Meteo API]
    end

    LG --> LS[LangSmith Observability]
```

### **Backend**

| Technology | Purpose |
|------------|---------|
| **Python 3.11+** | Primary programming language |
| **FastAPI 0.115+** | High-performance asynchronous API framework |
| **LangGraph 1.0+** | Multi-agent state graph orchestration, cyclic loops, and state suspension |
| **LangChain 0.3+** | Agent abstractions, chat models, and structured tool bindings |
| **Groq (`langchain-groq`)** | Sub-second LPU inference (`openai/gpt-oss-20b`, `openai/gpt-oss-120b`) |
| **FastMCP 1.2+** | Model Context Protocol standard over `stdio` transport (`server.py`) |
| **Neon PostgreSQL** | Cloud-native serverless PostgreSQL checkpointer database |
| **psycopg 3.2+ & psycopg-pool** | Asynchronous connection pooling with non-blocking dict rows |
| **Pydantic v2.9+** | Strict schema validation (`SupervisorOutput`, `UniversalGeoResolution`, etc.) |
| **Tavily Python** | Search API for grounded destination geography, buses, and hotels |
| **fast_flights & Amadeus** | Flight schedule scraping, IATA code resolution, and pricing |
| **Open-Meteo** | Free, open meteorological API for geocoding and live forecasts |
| **LangSmith 0.2+** | Production tracing, token evaluation, and node-level latency monitoring |

### **Frontend**

| Technology | Purpose |
|------------|---------|
| **HTML5 & Jinja2** | Server-rendered templates with clean semantic hierarchy |
| **Vanilla CSS** | Modern design system, custom CSS variables, dark/light cards, responsive layouts |
| **Vanilla JavaScript** | Asynchronous state management, dynamic pipeline stepper, modal triggers |
| **Google Fonts** | `Inter` for clean typography and `JetBrains Mono` for metadata |

---

## 🏗️ **Architecture**

### **State Graph Topology**

```mermaid
flowchart TD
    START([START]) --> Guardrails[guardrails_node]
    Guardrails -->|Blocked / Unsafe| Blocked[blocked_request_node]
    Blocked --> END_BLOCKED([END])
    
    Guardrails -->|Allowed| Supervisor[supervisor_agent]
    
    subgraph Parallel Retrieval [Parallel FastMCP Specialist Fan-Out]
        Supervisor --> Flight[flight_agent]
        Supervisor --> Hotel[hotel_agent]
        Supervisor --> Weather[weather_agent]
    end
    
    Flight --> FanInBarrier{Fan-In Barrier}
    Hotel --> FanInBarrier
    Weather --> FanInBarrier
    
    FanInBarrier --> Budget[budget_agent]
    Budget --> Itinerary[itinerary_agent]
    Itinerary --> HITL[human_approval_node - INTERRUPT]
    
    HITL -->|Approved| Final[final_agent]
    HITL -->|Revise with Feedback| Revise[revise_itinerary_node]
    Revise --> HITL
    HITL -->|Rejected / Cancelled| Reject[rejected_node]
    
    Reject --> END_REJECT([END])
    Final --> END_FINAL([END])
```

### **Data Flow Walkthrough**

1. **User Request**: The user submits a natural language travel query via the Web UI or `POST /api/plan`.
2. **Safety Guardrail**: `guardrails_node` invokes `guardrails_model` with structured output `GuardrailsValidation`. If rejected, it immediately routes to `blocked_request_node` and ends.
3. **Supervisor Extraction**: `supervisor_agent` uses `SupervisorOutput` to parse destination, origin, dates, duration, travelers, budget, transit mode, and stay tier.
4. **Dynamic Geo Resolution**: `resolve_locations_dynamically` consults Tavily grounding to determine terrain, altitude, transit gateways, stay settlements, and local living economics.
5. **Parallel Tool Fan-Out**: The graph fans out simultaneously to `flight_agent`, `hotel_agent`, and `weather_agent`. Each agent queries live APIs or the FastMCP tool plane.
6. **Fan-In & Budget Reconciliation**: `budget_agent` serves as an execution barrier. It reconciles flight/train/bus availability with room requirements (`(travelers + 1) // 2 * nights`) and local expenses.
7. **Itinerary Synthesis**: `itinerary_agent` synthesizes day-by-day itineraries (DAY 01 to DAY XX) grounded in real attractions, trailhead origins, and verified road corridors.
8. **HITL State Suspension**: `human_approval_node` executes `interrupt()`. The entire `TravelState` is frozen into **Neon PostgreSQL**.
9. **Human Decision**:
   - **Approve**: User clicks **Approve & Book**. The graph resumes execution and routes to `final_agent` to build the executive concierge dossier.
   - **Modify**: User enters feedback (e.g. *"Switch to 5-star hotels"* or *"Include more temples"*). The graph routes to `revise_itinerary_node` and loops back to `human_approval_node`.
   - **Cancel**: User rejects the plan. The graph routes to `rejected_node` and terminates.

---

## 📦 **Installation**

### **Prerequisites**

- **Python 3.11+** installed
- **PostgreSQL Database**: Free serverless instance from [Neon.tech](https://neon.tech/) (or local PostgreSQL 15+)
- **API Keys**:
  - **Groq API Key**: Ultra-fast LLM inference ([console.groq.com](https://console.groq.com/))
  - **Tavily API Key**: Web search & destination grounding ([tavily.com](https://tavily.com/))
  - **RapidAPI Key** *(Optional)*: Live Indian Railways API (`railkit-indian-railway-data`)
  - **LangSmith API Key** *(Optional)*: Observability & tracing ([smith.langchain.com](https://smith.langchain.com/))

---

### **1. Clone the Repository**

```bash
git clone https://github.com/Aditya-Sharma-dev18/Tessera-Core.git
cd Tessera-Core
```

---

### **2. Set Up Virtual Environment**

Using Conda:
```bash
conda create -n tessera python=3.11 -y
conda activate tessera
```

Or using standard Python `venv`:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

---

### **3. Install Dependencies**

```bash
pip install -r requirements.txt
```

If installing manually:
```bash
pip install langgraph langchain langchain-core langchain-community langchain-groq
pip install mcp fastapi "uvicorn[standard]" httpx requests pydantic pydantic-settings
pip install langgraph-checkpoint-postgres "psycopg[binary]" psycopg-pool
pip install fast_flights amadeus airportsdata pycountry geopy python-dateutil
pip install tavily-python jinja2 python-dotenv langsmith
```

---

### **4. Configure Environment Variables**

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# ── PostgreSQL Checkpointer (Neon Database) ───────────
DATABASE_URL=postgresql://user:password@ep-sample-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require

# ── Groq LLM Provider ─────────────────────────────────
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── Tavily Web Search & Grounding ─────────────────────
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxx

# ── RapidAPI Indian Railways (Optional) ───────────────
RAPIDAPI_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RAPIDAPI_RAIL_HOST=railkit-indian-railway-data.p.rapidapi.com

# ── LangSmith Observability (Optional) ────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxxxxxxxxxx
LANGCHAIN_PROJECT=tessera-core
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

---

### **5. Run the Application**

#### **Start the Web UI & API Server**

```bash
uvicorn app:app --reload --port 8000
```

Open **http://127.0.0.1:8000** in your browser.

#### **Run the Standalone FastMCP Server (stdio)**

```bash
python server.py
```

---

## 🎯 **Usage**

### **Quick Start (Web UI)**

1. Navigate to **http://127.0.0.1:8000**.
2. Enter your travel request or click one of the pre-configured quick prompts:
   ```text
   Plan a 5-day trip from Delhi to Goa for 2 people from 20 November 2026 to 24 November 2026 with flights, beach resorts, and complete day-wise itinerary under 45000
   ```
3. Click **Run Agents**.
4. Observe the live pipeline status stepper:
   - `Input Guardrail` ➔ `Supervisor Agent` ➔ `FastMCP Specialist Tools` ➔ `Final TravelState`.
5. Review the generated cards:
   - **Trip Summary & Cost Meter**: Total budget, duration, traveler breakdown.
   - **Transit Options**: Flights/Trains/Buses with fare per seat, round-trip totals, and pre-filled booking links.
   - **Curated Stays**: Tavily-verified accommodations matching requested budget tiers.
   - **Day-Wise Itinerary**: Chronological Morning/Afternoon/Evening schedule.
6. **Interact with the HITL Gate**:
   - **Approve & Book**: Finalizes the plan, unlocks the Executive Concierge Dossier, and locks booking links.
   - **Modify Plan**: Enter natural language revisions (e.g. *"Switch from flight to train"* or *"Stay in South Goa"*).
   - **Cancel Trip**: Discards the workflow and resets state.

---

### **Real-World Query Examples**

#### **Example 1: High-Altitude Mountain Expedition**
```text
Plan a 4-day pilgrimage from Delhi to Kartik Swami Temple for 2 people in May 2026 by bus under 20000.
```
*Result*: Resolves Rishikesh/Haridwar as the transit hub and Kanakchauri/Rudraprayag as the mountain stay base; calculates mountain shared jeeps and trail ascent; avoids fictional plains rickshaws.

#### **Example 2: 1-Day Express Tour (Zero Overnight Stay)**
```text
Plan a 1-day trip from Delhi to Agra for 2 people by train same day return without hotel stay.
```
*Result*: Automatically sets hotel accommodation to ₹0, schedules early morning departure and evening return train, and crafts a tight same-day heritage circuit.

#### **Example 3: Coastal Luxury Flight Tour**
```text
Plan a 5-day luxury trip from Mumbai to Goa for 2 people with 5-star beachfront resorts and flights.
```
*Result*: Filters for luxury 5-star resorts, computes round-trip direct airfares, includes authentic beachfront dining estimates, and provides direct booking deep links.

---

## 📡 **API Endpoints**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | `GET` | Web UI Dashboard |
| `/health` | `GET` | System health check (`{"status": "ok", "graph_ready": true}`) |
| `/api/plan` | `POST` | Starts a new travel planning run; returns state or awaiting approval payload |
| `/api/plan/{thread_id}/approve` | `POST` | Resumes an interrupted thread with approval or modification feedback |
| `/api/plan/{thread_id}/reject` | `POST` | Cancels an active thread and terminates the graph |
| `/api/plan/{thread_id}/status` | `GET` | Retrieves full persisted state snapshot for a given `thread_id` |
| `/static/*` | `GET` | Serves CSS, JavaScript, and background assets |

---

### **API Request & Response Examples**

#### **1. Start a Plan (`POST /api/plan`)**

```bash
curl -X POST http://127.0.0.1:8000/api/plan \
  -H "Content-Type: application/json" \
  -d '{"query": "Plan a 3-day trip from Delhi to Jaipur for 2 people by train under 25000"}'
```

**Response (Awaiting Approval):**
```json
{
  "thread_id": "7f8b9c2a-4d3e-4b2a-8f1e-0a9b8c7d6e5f",
  "status": "awaiting_approval",
  "approval_request": "📋 Travel Plan Ready for Review...",
  "travelers_count": 2,
  "duration_days": 3,
  "estimated_total_inr": 18400,
  "trip_constraints": {
    "origin": "Delhi",
    "destination": "Jaipur",
    "duration_days": 3,
    "travelers": 2,
    "preferred_transit_mode": "train",
    "stay_tier": "moderate"
  },
  "transit_options": [
    {
      "mode": "Train",
      "operator": "Ajmer Shatabdi Express (12015)",
      "price_per_seat": 980.0,
      "round_trip_total": 3920,
      "booking_url": "https://www.confirmtkt.com/rbooking-d/trains/from/NDLS/to/JP"
    }
  ],
  "selected_hotel": {
    "name": "Heritage Haveli Stay",
    "location": "Jaipur City Center",
    "price": 2800,
    "booking_url": "https://booking.com/..."
  },
  "itinerary": "DAY 01 — ARRIVAL & PINK CITY HERITAGE\n* Morning: Depart NDLS...",
  "approved": "pending"
}
```

#### **2. Approve or Modify (`POST /api/plan/{thread_id}/approve`)**

**To Approve:**
```bash
curl -X POST http://127.0.0.1:8000/api/plan/7f8b9c2a-4d3e-4b2a-8f1e-0a9b8c7d6e5f/approve \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "feedback": ""}'
```

**To Revise with Feedback:**
```bash
curl -X POST http://127.0.0.1:8000/api/plan/7f8b9c2a-4d3e-4b2a-8f1e-0a9b8c7d6e5f/approve \
  -H "Content-Type: application/json" \
  -d '{"decision": "feedback", "feedback": "Include a visit to Nahargarh Fort at sunset"}'
```

---

## 🔌 **FastMCP Tool Protocol**

`server.py` implements Anthropic's **Model Context Protocol (MCP)** using `FastMCP`, exposing travel search tools as a process-isolated server over standard `stdio`.

### **Exposed MCP Tools**

| Tool | Parameters | Description |
|------|------------|-------------|
| `find_flights` | `origin_iata`, `destination_iata`, `travel_date` | Returns cheapest live airfares and flight schedules |
| `find_trains` | `from_station`, `to_station`, `travel_date` | Queries Indian Railways trains, classes, and timings |
| `find_buses` | `origin_city`, `destination_city`, `travel_date` | Queries intercity bus schedules and fares |
| `find_hotels` | `city`, `budget_tier` | Returns verified hotel tariffs and booking URLs |
| `find_weather` | `city` | Returns live temperature, windspeed, and weather conditions |

### **Connect with Claude Desktop**

Add this to your Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tessera-travel-engine": {
      "command": "python",
      "args": ["d:/PROJECTS/Tessera-Core/server.py"],
      "env": {
        "GROQ_API_KEY": "gsk_xxxxxxxxxxxxxxxxxxxx",
        "TAVILY_API_KEY": "tvly-xxxxxxxxxxxxxxxxxxxx",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

---

## 🔬 **Observability with LangSmith**

Tessera-Core is instrumented with **LangSmith** for full production-grade visibility across multi-agent execution cycles.

### **What You Get**

- **Node-by-Node Tracing**: Full latency breakdown for `guardrails_node`, `supervisor_agent`, `flight_agent`, `budget_agent`, and `itinerary_agent`.
- **Parallel Fan-Out Visualization**: Inspect concurrent specialist tool executions and token costs in real time.
- **State Checkpoint Inspection**: Observe snapshot mutations, `interrupt()` triggers, and resume payloads.
- **Token Accounting**: Track prompt tokens, completion tokens, and dollar expenditures per Groq query.
- **Error Diagnostics**: Complete stack traces linked to exact graph nodes.

### **Setup**

1. Sign up at [smith.langchain.com](https://smith.langchain.com/).
2. Add your credentials to `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxx
LANGCHAIN_PROJECT=tessera-core
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

---

## 🔧 **Configuration**

### **Model Configuration (`backend.py`)**

```python
# Ultra-fast routing and deterministic evaluation
guardrails_model  = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)
supervisor_model  = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)
budget_model      = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)
final_agent_model = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)

# Deep creative synthesis and Pydantic extraction
itinerary_model   = ChatGroq(model="openai/gpt-oss-120b", temperature=0.2)
parsing_model     = ChatGroq(model="openai/gpt-oss-120b", temperature=0.0)
```

### **PostgreSQL Pool Settings**

In `backend.py`, database connectivity is managed via `psycopg_pool.AsyncConnectionPool`:

```python
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
        "sslmode": "require",
        "keepalives": 1,
    }
)
```

---

## 🚀 **Deployment**

### **Option 1: Render.com**

Deploy using `render.yaml`:

```yaml
services:
  - type: web
    name: tessera-core
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: TAVILY_API_KEY
        sync: false
      - key: RAPIDAPI_KEY
        sync: false
      - key: LANGCHAIN_TRACING_V2
        value: "true"
      - key: LANGCHAIN_API_KEY
        sync: false
      - key: LANGCHAIN_PROJECT
        value: "tessera-core"
```

---

### **Option 2: Docker Container**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t tessera-core .
docker run -p 8000:8000 --env-file .env tessera-core
```

---

## 🔧 **Troubleshooting**

### **Common Issues & Solutions**

| Issue | Cause | Solution |
|-------|-------|----------|
| `RuntimeError: Event loop is closed` / `NotImplementedError` on Windows | Default `ProactorEventLoop` incompatible with async psycopg | Set `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` before imports (handled in `app.py`) |
| `psycopg.OperationalError: SSL SYSCALL error` | Neon serverless connection timeout | Ensure `sslmode=require` is present in `DATABASE_URL` and `AsyncConnectionPool` has keepalives configured |
| `FastMCP stdio encoding error` on Windows | Windows console defaulting to `cp1252` | Set environment variable `PYTHONIOENCODING=utf-8` or rely on `sys.stdout.reconfigure(encoding="utf-8")` |
| `HTTP 429: Rate Limit Exceeded` (Groq) | Exceeded Groq free-tier TPM/RPM | Switch from `openai/gpt-oss-120b` to `openai/gpt-oss-20b` for extraction or add a brief backoff |
| `Tavily API 401 Unauthorized` | Invalid or expired API key | Verify `TAVILY_API_KEY` in `.env` |
| `Thread not found (404)` on status check | Checkpointer did not flush to PostgreSQL | Ensure `DATABASE_URL` points to an active database and `await checkpointer.setup()` completed |

---

## 🤝 **Contributing**

We welcome contributions from the community to enhance agents, add new transit connectors, or improve front-end experiences!

### **How to Contribute**

1. **Fork** the repository: [Tessera-Core on GitHub](https://github.com/Aditya-Sharma-dev18/Tessera-Core)
2. **Create** a feature branch:
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Commit** your changes following conventional commits:
   ```bash
   git commit -m "feat(agent): add European Eurail transit tool"
   ```
4. **Push** to the branch:
   ```bash
   git push origin feature/amazing-feature
   ```
5. **Open** a Pull Request.

---

## 📄 **License**

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for complete details.

```
MIT License

Copyright (c) 2026 Aditya Sharma
```

---

## 🙏 **Acknowledgments**

- **LangChain & LangGraph** teams for stateful multi-agent primitives and cyclic graph runtimes.
- **Groq** for high-throughput, low-latency LPU inference.
- **Anthropic** for the open **Model Context Protocol (FastMCP)** standard.
- **Neon Tech** for reliable, serverless PostgreSQL with instant autoscaling.
- **Tavily AI** for search intelligence and real-time grounding.
- **Open-Meteo** for weather APIs.
- **Indian Railways / ConfirmTkt, RedBus, and Google Flights** for transit ecosystems.

---

## 🏆 **Project Status**

![Status](https://img.shields.io/badge/Status-Production_Ready-brightgreen.svg)
![Build](https://img.shields.io/badge/Build-Passing-brightgreen.svg)
![Multi-Modal Transit](https://img.shields.io/badge/Multi--Modal-Flights_Trains_Buses-blue.svg)
![HITL](https://img.shields.io/badge/HITL-Checkpoint_Resumable-purple.svg)
![Observability](https://img.shields.io/badge/Observability-LangSmith-orange.svg)

---

## 📞 **Contact & Support**

- **GitHub Repository**: [Aditya-Sharma-dev18/Tessera-Core](https://github.com/Aditya-Sharma-dev18/Tessera-Core)
- **Issue Tracker**: [Report a Bug or Request a Feature](https://github.com/Aditya-Sharma-dev18/Tessera-Core/issues)
- **Author**: Aditya Sharma
- **Email**: [sharma.adityaaa0001@gmail.com](mailto:sharma.adityaaa0001@gmail.com)

---

## ⭐ **Star Us!**

If you find **Tessera-Core** useful or inspiring, please consider starring ⭐ the repository on GitHub!

---

**Crafted with ❤️ by [Aditya Sharma](https://github.com/Aditya-Sharma-dev18)**
