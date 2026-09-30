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

    // ⚠️ Update transit badge dynamically
    updateTransitBadge(data);

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

  // ⚠️ NEW: Update transit type badge
  function updateTransitBadge(data) {
    const badge = document.getElementById("transitTypeBadge");
    if (!badge) return;
    const types = [];
    if (parseTransit(data.flight_results, "recommended_flights").length) types.push("Flights");
    if (parseTransit(data.rails_results, "trains").length) types.push("Trains");
    if (parseTransit(data.bus_results, "recommended_buses").length) types.push("Buses");
    badge.textContent = types.length ? types.join(" + ") : "—";
  }

  // ═══════════════════════════════════════════════════════════════
  //  COMBINE TRANSIT
  // ═══════════════════════════════════════════════════════════════
  function combineTransit(flightsRaw, railsRaw, busesRaw) {
    const items = [];
    const allRaws = [flightsRaw, railsRaw, busesRaw];

    const tryParse = (raw) => {
      if (!raw) return null;
      try {
        return typeof raw === "string" ? JSON.parse(raw) : raw;
      } catch { return null; }
    };

    for (const raw of allRaws) {
      const data = tryParse(raw);
      if (!data) continue;

      const flights = data.recommended_flights || data.flights;
      if (Array.isArray(flights)) flights.forEach(f => items.push({ type: "flight", ...f }));

      const trains = data.trains;
      if (Array.isArray(trains)) trains.forEach(t => items.push({ type: "train", ...t }));

      const buses = data.recommended_buses || data.buses;
      if (Array.isArray(buses)) buses.forEach(b => items.push({ type: "bus", ...b }));
    }

    const seen = new Set();
    const unique = [];
    for (const item of items) {
      const key = `${item.airline || item.train_name || item.operator_name}|${item.departure_time}|${item.price_inr || item.estimated_price_inr}`;
      if (!seen.has(key)) { seen.add(key); unique.push(item); }
    }

    if (!unique.length) return "";

    return unique.slice(0, 6).map(item => {
      const icon = item.type === "flight" ? "✈️" : item.type === "train" ? "🚆" : "🚌";
      const name = item.airline || item.train_name || item.operator_name || "Option";
      const dep = item.departure_time || "—";
      const duration = item.flight_type || item.travel_time_hours || item.duration_hours || "";
      const price = item.price_inr || item.estimated_price_inr || 0;

      // ⚠️ Compute arrival if missing
      let arr = item.arrival_time || "";
      if (!arr && duration && dep !== "—") {
        arr = computeArrival(dep, duration);
      }
      if (!arr) arr = "—";

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

  // ⚠️ NEW: Compute arrival time from departure + duration
  function computeArrival(depTime, durationStr) {
    try {
      const [dh, dm] = depTime.split(":").map(Number);
      if (isNaN(dh) || isNaN(dm)) return "";

      const hMatch = String(durationStr).match(/(\d+)\s*h/i);
      const mMatch = String(durationStr).match(/(\d+)\s*m/i);
      const totalMin = (parseInt(hMatch?.[1] || 0) * 60) + parseInt(mMatch?.[1] || 0);
      if (totalMin <= 0) return "";

      let arrMin = dh * 60 + dm + totalMin;
      const dayOffset = Math.floor(arrMin / 1440);
      arrMin = arrMin % 1440;
      const arrH = Math.floor(arrMin / 60);
      const arrM = arrMin % 60;
      const suffix = dayOffset > 0 ? ` (+${dayOffset}d)` : "";
      return `${String(arrH).padStart(2, "0")}:${String(arrM).padStart(2, "0")}${suffix}`;
    } catch {
      return "";
    }
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

      return hotels.slice(0, 4).map(h => {
        const name = h.name || h.title || "Hotel";
        const rating = h.rating || "";
        const price = h.price_per_night || 0;
        const amenities = h.amenities || h.snippet || h.content || "";
        const location = h.location || "";
        const url = h.url || h.booking_url || "#";

        let subtitle = "";
        if (rating && location) subtitle = `${rating} • ${location}`;
        else if (rating) subtitle = rating;
        else if (location) subtitle = location;
        else subtitle = String(amenities).slice(0, 110);

        const priceHtml = price > 0
          ? `<span class="item-price">₹${Number(price).toLocaleString()}<span style="font-size:10px;color:#9597a0;">/night</span></span>`
          : `<span class="item-price" style="font-size:11px;color:#9597a0;">Check price</span>`;

        return `
          <div class="item-card">
            <div class="item-info">
              <h5>${name}</h5>
              <p>${subtitle}</p>
            </div>
            <div class="item-right">
              ${priceHtml}
              <a href="${url}" target="_blank" class="book-link">View →</a>
            </div>
          </div>
        `;
      }).join("");
    } catch (e) {
      console.warn("renderHotels parse failed:", e);
      return "";
    }
  }

  // ═══════════════════════════════════════════════════════════════
  //  ITINERARY — Markdown → HTML
  // ═══════════════════════════════════════════════════════════════
  function renderMarkdownAsDays(md) {
    if (!md) return `<p style="color:#8189a8;">No itinerary generated.</p>`;

    const dayRegex = /(?:^|\n)\s*(?:#{1,4}\s*|\*\*\s*)?(?:DAY|Day)\s*0*(\d+)[\s—\-–:]+([^\n]*)\n([\s\S]*?)(?=(?:\n\s*(?:#{1,4}\s*|\*\*\s*)?(?:DAY|Day)\s*0*\d+)|$)/gi;

    const days = [];
    let match;
    while ((match = dayRegex.exec(md)) !== null) {
      days.push({
        num: match[1],
        title: (match[2] || "").trim().replace(/\*\*/g, "").replace(/^[—\-–:\s]+/, "").trim(),
        content: match[3].trim()
      });
    }

    if (days.length >= 2) {
      return days.map(d => `
        <div class="day-box">
          <h6>DAY ${String(d.num).padStart(2, '0')}${d.title ? ` — ${d.title.toUpperCase()}` : ''}</h6>
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

    html = html.replace(/^###\s+(.+)$/gm, '<h4 class="md-h">$1</h4>');
    html = html.replace(/^##\s+(.+)$/gm,  '<h4 class="md-h">$1</h4>');
    html = html.replace(/^#\s+(.+)$/gm,   '<h4 class="md-h">$1</h4>');

    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Tables
    html = html.replace(
      /(^\|.+\|\s*$\n^\|[-:|\s]+\|\s*$\n(?:^\|.+\|\s*$\n?)+)/gm,
      (tableBlock) => {
        const lines = tableBlock.trim().split('\n').filter(l => l.trim());
        if (lines.length < 2) return tableBlock;
        const headers = lines[0].split('|').filter(c => c.trim()).map(c => c.trim());
        const rows = lines.slice(2).map(row =>
          row.split('|').filter(c => c.trim()).map(c => c.trim())
        );
        const headerHtml = headers.map(h =>
          `<th style="text-align:left;padding:8px 10px;background:rgba(99,102,241,0.08);color:#4f46e5;font-weight:600;font-size:12px;border-bottom:1px solid rgba(99,102,241,0.15);">${h}</th>`
        ).join("");
        const rowsHtml = rows.map(row =>
          `<tr>${row.map(cell =>
            `<td style="padding:8px 10px;border-bottom:1px solid rgba(0,0,0,0.05);font-size:12.5px;color:#111215;">${cell}</td>`
          ).join("")}</tr>`
        ).join("");
        return `<table style="width:100%;border-collapse:collapse;margin:12px 0;border-radius:8px;overflow:hidden;border:1px solid rgba(99,102,241,0.15);">
          <thead><tr>${headerHtml}</tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table>`;
      }
    );

    html = html.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>');

    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" target="_blank" class="md-link">$1</a>');

    html = html.replace(/&lt;(https?:\/\/[^\s&]+)&gt;/g,
      '<a href="$1" target="_blank" class="md-link">$1</a>');

    html = html.replace(/^&gt;\s*(.+)$/gm, '<div class="md-tip">$1</div>');

    html = html.replace(/^\s*---+\s*$/gm, '<hr class="md-hr">');

    html = html.replace(/^\s*[-•]\s+(.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>[\s\S]*?<\/li>\s*)+/g,
      m => `<ul class="md-ul">${m}</ul>`);

    html = html.replace(/\n{2,}/g, '</p><p>');
    html = html.replace(/(?<!<\/li>|<\/ul>|<\/h4>|<\/div>|<\/p>|<\/table>)\n/g, '<br>');

    return `<div class="md-body"><p>${html}</p></div>`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // ═══════════════════════════════════════════════════════════════
  //  EXTRACT TOTAL
  // ═══════════════════════════════════════════════════════════════
  function extractFirstINR(text) {
    if (!text) return null;
    const str = String(text);

    const totalMatch = str.match(/\*{0,2}TOTAL\*{0,2}\s*[:\-]?\s*\*{0,2}\s*₹\s*([\d,]+)/i);
    if (totalMatch) return `₹${totalMatch[1]}`;

    const altMatch = str.match(/(?:Grand|Estimated|Final|Overall)\s+Total[:\s]*₹?\s*([\d,]+)/i);
    if (altMatch) return `₹${altMatch[1]}`;

    const allMatches = [...str.matchAll(/₹\s*([\d,]+)/g)];
    if (allMatches.length === 0) return null;

    return `₹${allMatches[allMatches.length - 1][1]}`;
  }
});