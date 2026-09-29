document.addEventListener("DOMContentLoaded", () => {
  const queryInput = document.getElementById("userQuery");
  const generateBtn = document.getElementById("generateBtn");
  const pipelineSection = document.getElementById("agentPipeline");
  const pipelineStatus = document.getElementById("pipelineStatus");
  const resultsSection = document.getElementById("resultsSection");

  let currentThreadId = null;

  document.querySelectorAll(".sample-query").forEach(btn => {
    btn.addEventListener("click", () => {
      queryInput.value = btn.getAttribute("data-query");
      queryInput.focus();
    });
  });

  // ─── RUN AGENTS ───
  generateBtn.addEventListener("click", async () => {
    const query = queryInput.value.trim();
    if (!query) return;

    generateBtn.disabled = true;
    generateBtn.querySelector("span").textContent = "Running...";
    resultsSection.classList.add("hidden");
    pipelineSection.classList.remove("hidden");
    resetSteps();

    try {
      setStep("step-guardrail", "active", "Validating safety & travel intent...");
      setStep("step-supervisor", "active", "Dispatching to supervisor + specialists...");

      const response = await fetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Server ${response.status}: ${errText.slice(0, 200)}`);
      }

      const data = await response.json();
      console.log("Backend response:", data);
      currentThreadId = data.thread_id;

      setStep("step-guardrail", "done", "Passed validation");
      setStep("step-supervisor", "done", `Selected: ${(data.selected_agents || []).join(", ") || "—"}`);
      setStep("step-specialists", "done", "Tools executed");
      setStep("step-synthesizer", "done", "Awaiting your review");

      pipelineStatus.textContent = data.status === "blocked"
        ? "⛔ Request blocked"
        : "✅ Plan ready for review";

      if (data.status === "blocked") {
        alert(data.message || "Request blocked by guardrails.");
        return;
      }

      renderResults(data);
      resultsSection.classList.remove("hidden");

    } catch (err) {
      console.error("Plan error:", err);
      pipelineStatus.textContent = `❌ Error: ${err.message}`;
      alert(`Failed to generate plan: ${err.message}`);
    } finally {
      generateBtn.disabled = false;
      generateBtn.querySelector("span").textContent = "Run Agents";
    }
  });

  // ─── APPROVE ───
  document.getElementById("approveBtn").addEventListener("click", async () => {
    if (!currentThreadId) return alert("No active plan");
    try {
      const res = await fetch(`/api/plan/${currentThreadId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: "approve", feedback: "" })
      });
      const data = await res.json();
      console.log("Approve response:", data);
      if (data.status === "completed") {
        alert("✅ Plan approved! Booking links ready.");
        renderResults(data);
      } else if (data.status === "awaiting_approval") {
        alert("Plan still awaiting review.");
        renderResults(data);
      }
    } catch (e) {
      alert(`Approval failed: ${e.message}`);
    }
  });

  // ─── MODIFY ───
  document.getElementById("rejectBtn").addEventListener("click", async () => {
    if (!currentThreadId) return alert("No active plan");
    const feedback = prompt("What changes should the agents make?\n(e.g., 'Make it cheaper')");
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
      console.log("Revise response:", data);

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

  // ─── HELPERS ───
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

  // ═══════════════════════════════════════════════════════════════
  //  RENDER RESULTS
  // ═══════════════════════════════════════════════════════════════
  function renderResults(data) {
    const itineraryText = data.itinerary || data.final_response || "";
    document.getElementById("itineraryDaysList").innerHTML = renderMarkdownAsDays(itineraryText);

    const transitContainer = document.getElementById("transitOptionsList");
    const transitHtml = combineTransit(data.flight_results, data.rails_results, data.bus_results);
    transitContainer.innerHTML = transitHtml
      || `<p style="color:#8189a8;font-size:13px;">No transit data available.</p>`;

    const hotelContainer = document.getElementById("hotelOptionsList");
    hotelContainer.innerHTML = renderHotels(data.hotel_results)
      || `<p style="color:#8189a8;font-size:13px;">No hotel data available.</p>`;

    const costEl = document.getElementById("resTotalCost");
    if (costEl && data.budget_results) {
      costEl.textContent = extractFirstINR(data.budget_results) || "—";
    }

    const destEl = document.getElementById("resDestination");
    if (destEl && data.trip_constraints) {
      try {
        const c = typeof data.trip_constraints === "string"
          ? JSON.parse(data.trip_constraints) : data.trip_constraints;
        const from = c.origin || c.from || "Origin";
        const to = c.destination || c.to || "Destination";
        destEl.textContent = `${from} to ${to}`;
      } catch {}
    }

    if (data.trip_constraints) {
      try {
        const c = typeof data.trip_constraints === "string"
          ? JSON.parse(data.trip_constraints) : data.trip_constraints;
        const days = c.duration_days || c.days || c.duration || "?";
        const travelers = c.travelers || c.people || c.passengers || "?";
        const durEl = document.getElementById("resDuration");
        if (durEl) durEl.textContent = `${days} Days • ${travelers} Travelers`;
      } catch (e) {
        console.warn("Could not parse trip_constraints:", e);
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════
  //  COMBINE TRANSIT
  // ═══════════════════════════════════════════════════════════════
  function combineTransit(flightsRaw, railsRaw, busesRaw) {
    const items = [];

    const flights = parseTransit(flightsRaw, "recommended_flights");
    flights.forEach(f => items.push({ type: "flight", ...f }));

    const trains = parseTransit(railsRaw, "trains");
    trains.forEach(t => items.push({ type: "train", ...t }));

    const buses = parseTransit(busesRaw, "recommended_buses");
    buses.forEach(b => items.push({ type: "bus", ...b }));

    if (!items.length) return "";

    return items.slice(0, 6).map(item => {
      const icon = item.type === "flight" ? "✈️" : item.type === "train" ? "🚆" : "🚌";
      const name = item.airline || item.train_name || item.operator_name || "Option";
      const dep = item.departure_time || "—";
      const arr = item.arrival_time || "—";
      const duration = item.flight_type || item.travel_time_hours || item.duration_hours || "";
      const price = item.price_inr || item.estimated_price_inr || 0;

      return `
        <div class="item-card">
          <div class="item-info">
            <h5>${icon} ${name}</h5>
            <p>${dep} → ${arr}${duration ? " • " + duration : ""}</p>
          </div>
          <div class="item-right">
            <span class="item-price">₹${Number(price).toLocaleString()}</span>
            <a href="${item.booking_url || '#'}" target="_blank" class="book-link">Book →</a>
          </div>
        </div>
      `;
    }).join("");
  }

  function parseTransit(rawJson, key) {
    if (!rawJson) return [];
    try {
      const data = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
      const items = data[key] || data.results || [];
      return Array.isArray(items) ? items : [];
    } catch {
      return [];
    }
  }

  // ═══════════════════════════════════════════════════════════════
  //  HOTELS
  // ═══════════════════════════════════════════════════════════════
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
            <p>${(h.snippet || h.content || "").slice(0, 110)}...</p>
          </div>
          <div class="item-right">
            <a href="${h.url || '#'}" target="_blank" class="book-link">View →</a>
          </div>
        </div>
      `).join("");
    } catch { return ""; }
  }

  // ═══════════════════════════════════════════════════════════════
  //  ITINERARY — Markdown → HTML
  // ═══════════════════════════════════════════════════════════════
  function renderMarkdownAsDays(md) {
    if (!md) return `<p style="color:#8189a8;">No itinerary generated.</p>`;

    const dayRegex = /(?:^|\n)(?:#+\s*)?(?:Day\s+)(\d+)[^\n]*\n([\s\S]*?)(?=(?:\n(?:#+\s*)?Day\s+\d+)|$)/gi;
    const days = [];
    let match;
    while ((match = dayRegex.exec(md)) !== null) {
      days.push({ num: match[1], content: match[2].trim() });
    }

    if (days.length) {
      return days.map(d => `
        <div class="day-box">
          <h6>DAY ${String(d.num).padStart(2, '0')}</h6>
          <div class="day-content">${markdownToHtml(d.content)}</div>
        </div>
      `).join("");
    }

    return `<div class="day-box">
      <h6>ITINERARY</h6>
      <div class="day-content">${markdownToHtml(md)}</div>
    </div>`;
  }

  // ═══════════════════════════════════════════════════════════════
  //  MINI MARKDOWN → HTML
  // ═══════════════════════════════════════════════════════════════
  function markdownToHtml(md) {
    if (!md) return "";

    let html = escapeHtml(md);

    // Headers
    html = html.replace(/^###\s+(.+)$/gm, '<h4 class="md-h">$1</h4>');
    html = html.replace(/^##\s+(.+)$/gm,  '<h4 class="md-h">$1</h4>');
    html = html.replace(/^#\s+(.+)$/gm,   '<h4 class="md-h">$1</h4>');

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Italic (after bold)
    html = html.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>');

    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, 
      '<a href="$2" target="_blank" class="md-link">$1</a>');

    // Raw URLs in angle brackets <https://...>
    html = html.replace(/&lt;(https?:\/\/[^\s&]+)&gt;/g,
      '<a href="$1" target="_blank" class="md-link">$1</a>');

    // Blockquote / Tip
    html = html.replace(/^&gt;\s*(.+)$/gm, '<div class="md-tip">$1</div>');

    // Horizontal rule
    html = html.replace(/^\s*---+\s*$/gm, '<hr class="md-hr">');

    // Bullets — convert "- item" to <li>
    html = html.replace(/^\s*[-•]\s+(.+)$/gm, '<li>$1</li>');

    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>[\s\S]*?<\/li>\s*)+/g, 
      m => `<ul class="md-ul">${m}</ul>`);

    // Paragraph splitting
    html = html.replace(/\n{2,}/g, '</p><p>');
    html = html.replace(/(?<!<\/li>|<\/ul>|<\/h4>|<\/div>|<\/p>)\n/g, '<br>');

    return `<div class="md-body"><p>${html}</p></div>`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function extractFirstINR(text) {
    const m = String(text).match(/₹\s*([\d,]+)/);
    return m ? `₹${m[1]}` : null;
  }
});