document.addEventListener("DOMContentLoaded", () => {
  const queryInput = document.getElementById("userQuery");
  const generateBtn = document.getElementById("generateBtn");
  const pipelineSection = document.getElementById("agentPipeline");
  const pipelineStatus = document.getElementById("pipelineStatus");
  const resultsSection = document.getElementById("resultsSection");

  // Track current thread for HITL resume
  let currentThreadId = null;

  // Sample query buttons
  document.querySelectorAll(".sample-query").forEach(btn => {
    btn.addEventListener("click", () => {
      queryInput.value = btn.getAttribute("data-query");
      queryInput.focus();
    });
  });

  // ─────────────────────────────────────────────────────────────
  //  RUN AGENTS
  // ─────────────────────────────────────────────────────────────
  generateBtn.addEventListener("click", async () => {
    const query = queryInput.value.trim();
    if (!query) return;

    generateBtn.disabled = true;
    resultsSection.classList.add("hidden");
    pipelineSection.classList.remove("hidden");
    resetSteps();

    try {
      // Step 1 — Guardrails (visual)
      setStep("step-guardrail", "active", "Validating safety & travel intent...");

      // Step 2 — Hit backend
      setStep("step-supervisor", "active", "Dispatching to supervisor + specialists...");

      const response = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const data = await response.json();
      currentThreadId = data.thread_id;

      // Mark visual steps done
      setStep("step-guardrail", "done", "Passed validation");
      setStep("step-supervisor", "done", `Selected: ${(data.selected_agents || []).join(", ")}`);
      setStep("step-specialists", "done", "Tools executed");
      setStep("step-synthesizer", "done", "Awaiting your review");

      pipelineStatus.textContent = data.status === "blocked"
        ? "⛔ Request blocked"
        : "✅ Plan ready for review";

      // Blocked case
      if (data.status === "blocked") {
        alert(data.message || "Request blocked by guardrails.");
        return;
      }

      // Render real results
      renderResults(data);
      resultsSection.classList.remove("hidden");

    } catch (err) {
      console.error(err);
      pipelineStatus.textContent = `❌ Error: ${err.message}`;
      alert(`Failed to generate plan: ${err.message}`);
    } finally {
      generateBtn.disabled = false;
    }
  });

  // ─────────────────────────────────────────────────────────────
  //  HITL — Approve
  // ─────────────────────────────────────────────────────────────
  document.getElementById("approveBtn").addEventListener("click", async () => {
    if (!currentThreadId) return alert("No active plan");

    try {
      const res = await fetch(`/api/plan/${currentThreadId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: "approve", feedback: "" })
      });
      const data = await res.json();
      if (data.status === "completed") {
        alert("✅ Plan approved! Opening booking links...");
        renderResults(data);
      }
    } catch (e) {
      alert(`Approval failed: ${e.message}`);
    }
  });

  // ─────────────────────────────────────────────────────────────
  //  HITL — Reject / Modify
  // ─────────────────────────────────────────────────────────────
  document.getElementById("rejectBtn").addEventListener("click", async () => {
    if (!currentThreadId) return alert("No active plan");

    const feedback = prompt(
      "What changes should the agents make?\n(e.g., 'Make it cheaper', 'Add a beach day')"
    );
    if (!feedback) return;

    try {
      pipelineSection.classList.remove("hidden");
      pipelineStatus.textContent = "🔁 Re-routing with your feedback...";

      const res = await fetch(`/api/plan/${currentThreadId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: "feedback", feedback })
      });
      const data = await res.json();

      if (data.status === "awaiting_approval") {
        pipelineStatus.textContent = "✅ Revised plan ready";
        renderResults(data);
      } else if (data.status === "completed") {
        pipelineStatus.textContent = "✅ Final plan ready";
        renderResults(data);
      }
    } catch (e) {
      alert(`Revision failed: ${e.message}`);
    }
  });

  // ─────────────────────────────────────────────────────────────
  //  RENDER HELPERS
  // ─────────────────────────────────────────────────────────────
  function resetSteps() {
    ["step-guardrail", "step-supervisor", "step-specialists", "step-synthesizer"]
      .forEach(id => {
        const el = document.getElementById(id);
        if (el) el.className = "step-badge";
      });
  }

  function setStep(stepId, state, statusText) {
    const el = document.getElementById(stepId);
    if (el) el.className = `step-badge ${state}`;
    if (statusText) pipelineStatus.textContent = statusText;
  }

  function renderResults(data) {
    // ---- Itinerary ----
    const itineraryContainer = document.getElementById("itineraryDaysList");
    itineraryContainer.innerHTML = renderMarkdownAsDays(data.itinerary || "");

    // ---- Transit ----
    const transitContainer = document.getElementById("transitOptionsList");
    transitContainer.innerHTML = renderTransit(data.flight_results)
      || renderTransit(data.rails_results)
      || renderTransit(data.bus_results)
      || `<p style="color:#9597a0;font-size:13px;">No transit data available.</p>`;

    // ---- Hotels ----
    const hotelContainer = document.getElementById("hotelOptionsList");
    hotelContainer.innerHTML = renderHotels(data.hotel_results)
      || `<p style="color:#9597a0;font-size:13px;">No hotel data available.</p>`;

    // ---- Budget ----
    const costEl = document.getElementById("resTotalCost");
    if (costEl && data.budget_results) {
      costEl.textContent = extractFirstINR(data.budget_results) || "—";
    }
  }

  function renderTransit(rawJson) {
    if (!rawJson) return "";
    try {
      const data = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
      const items = data.recommended_flights
        || data.trains
        || data.recommended_buses
        || [];

      if (!items.length) return "";

      return items.slice(0, 4).map(item => `
        <div class="item-card">
          <div class="item-info">
            <h5>${item.airline || item.train_name || item.operator_name || "Option"}</h5>
            <p>${item.departure_time || ""} → ${item.arrival_time || ""} • ${item.flight_type || item.travel_time_hours || item.duration_hours || ""}</p>
          </div>
          <div class="item-right">
            <span class="item-price">₹${(item.price_inr || item.estimated_price_inr || 0).toLocaleString()}</span>
            <a href="${item.booking_url || '#'}" target="_blank" class="book-link">Book →</a>
          </div>
        </div>
      `).join("");
    } catch {
      return "";
    }
  }

  function renderHotels(rawJson) {
    if (!rawJson) return "";
    try {
      const data = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
      const hotels = data.hotels || data.results || [];
      if (!hotels.length) return "";

      return hotels.slice(0, 4).map(h => `
        <div class="item-card">
          <div class="item-info">
            <h5>${h.title || "Hotel"}</h5>
            <p>${(h.snippet || h.content || "").slice(0, 100)}...</p>
          </div>
          <div class="item-right">
            <a href="${h.url || '#'}" target="_blank" class="book-link">View →</a>
          </div>
        </div>
      `).join("");
    } catch {
      return "";
    }
  }

  function renderMarkdownAsDays(md) {
    if (!md) return `<p style="color:#9597a0;">No itinerary generated.</p>`;

    // Extract day blocks by regex
    const dayRegex = /(?:^|\n)#{1,4}\s*(?:Day\s*)?(\d+)[^\n]*\n([\s\S]*?)(?=\n#{1,4}\s*(?:Day\s*)?\d+|$)/gi;
    const days = [];
    let match;
    while ((match = dayRegex.exec(md)) !== null) {
      days.push({
        num: match[1],
        content: match[2].trim().slice(0, 300)
      });
    }

    if (!days.length) {
      // Fallback — split by lines
      return `<div class="day-box"><h6>ITINERARY</h6><p>${md.slice(0, 600)}</p></div>`;
    }

    return days.map(d => `
      <div class="day-box">
        <h6>DAY ${String(d.num).padStart(2, '0')}</h6>
        <p>${d.content.replace(/\n+/g, ' ')}</p>
      </div>
    `).join("");
  }

  function extractFirstINR(text) {
    const m = String(text).match(/₹\s*([\d,]+)/);
    return m ? `₹${m[1]}` : null;
  }
});