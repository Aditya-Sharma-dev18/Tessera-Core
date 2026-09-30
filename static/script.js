document.addEventListener("DOMContentLoaded", () => {
  const queryInput = document.getElementById("userQuery");
  const generateBtn = document.getElementById("generateBtn");
  const pipelineSection = document.getElementById("agentPipeline");
  const pipelineStatus = document.getElementById("pipelineStatus");
  const resultsSection = document.getElementById("resultsSection");

  let currentThreadId = null;

  // Check backend engine health
  fetch("/health")
    .then(r => r.json())
    .then(h => {
      const btn = document.getElementById("liveStatusBtn");
      if (btn) {
        if (h.status === "ok") {
          btn.textContent = "● Engine: Active";
          btn.style.color = "#10b981";
          btn.style.borderColor = "#a7f3d0";
        }
      }
    })
    .catch(() => {
      const btn = document.getElementById("liveStatusBtn");
      if (btn) btn.textContent = "○ Engine: Ready";
    });

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
        pipelineStatus.textContent = "🎉 Trip approved & finalized!";
        alert("✅ Plan approved! Booking links locked and concierge dossier ready.");
        renderResults(data);
      } else if (data.status === "awaiting_approval") {
        pipelineStatus.textContent = "Plan ready for final confirmation";
        renderResults(data);
      }
    } catch (e) {
      alert(`Approval failed: ${e.message}`);
    }
  });

  // ─── MODIFY ───
  document.getElementById("rejectBtn").addEventListener("click", async () => {
    if (!currentThreadId) return alert("No active plan");
    const feedback = prompt("What modifications should the travel architect make?\n(e.g., 'Make it cheaper', 'Include more temples', 'Change hotel')");
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

  // ─── CANCEL ───
  const cancelBtn = document.getElementById("cancelPlanBtn");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", async () => {
      if (!currentThreadId) return alert("No active plan");
      if (!confirm("Are you sure you want to cancel this travel plan?")) return;

      try {
        const res = await fetch(`/api/plan/${currentThreadId}/reject`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision: "reject", feedback: "User cancelled" })
        });
        const data = await res.json();
        pipelineStatus.textContent = "❌ Travel plan creation cancelled.";
        alert("Plan creation cancelled.");
      } catch (e) {
        alert(`Cancel failed: ${e.message}`);
      }
    });
  }

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

    // 1. TRANSIT OPTIONS (Direct structured array ko priority di gayi hai)
    const transitContainer = document.getElementById("transitOptionsList");
    let transitHtml = "";
    if (Array.isArray(data.transit_options) && data.transit_options.length > 0) {
      transitHtml = renderStructuredTransit(data.transit_options);
    } else {
      transitHtml = combineTransit(data.flight_results, data.rails_results, data.bus_results);
    }
    transitContainer.innerHTML = transitHtml
      || `<p style="color:#8189a8;font-size:13px;">No transit data available.</p>`;

    updateTransitBadge(data);

    // 2. CURATED HOTELS (Selected hotel highlight ke saath)
    const hotelContainer = document.getElementById("hotelOptionsList");
    hotelContainer.innerHTML = renderHotels(data.hotel_results, data.selected_hotel)
      || `<p style="color:#8189a8;font-size:13px;">No hotel data available.</p>`;

    // 3. ESTIMATED TOTAL (Direct numeric field first — No regex trap!)
    const costEl = document.getElementById("resTotalCost");
    if (costEl) {
      if (typeof data.estimated_total_inr === "number" && data.estimated_total_inr > 0) {
        costEl.textContent = `₹${data.estimated_total_inr.toLocaleString()}`;
      } else if (data.budget_results) {
        costEl.textContent = extractAccurateTotal(data.budget_results) || "—";
      } else {
        costEl.textContent = "—";
      }
    }

    // 4. DESTINATION & ORIGIN
    const destEl = document.getElementById("resDestination");
    if (destEl) {
      let from = "Origin";
      let to = "Destination";
      if (data.trip_constraints) {
        try {
          const c = typeof data.trip_constraints === "string"
            ? JSON.parse(data.trip_constraints) : data.trip_constraints;
          from = c.origin || c.from || from;
          to = c.destination || c.to || to;
        } catch {}
      }
      destEl.textContent = `${from} to ${to}`;
    }

    // 5. DURATION & TRAVELERS (Root state fields first)
    const durEl = document.getElementById("resDuration");
    if (durEl) {
      let days = data.duration_days;
      let travelers = data.travelers_count;

      if (!days || !travelers) {
        try {
          const c = typeof data.trip_constraints === "string"
            ? JSON.parse(data.trip_constraints) : (data.trip_constraints || {});
          days = days || c.duration_days || c.days || 2;
          travelers = travelers || c.travelers || c.people || 2;
        } catch {
          days = days || 2;
          travelers = travelers || 2;
        }
      }
      durEl.textContent = `${days} Days • ${travelers} Travelers`;
    }

    // 6. EXECUTIVE CONCIERGE DOSSIER (Rendered when completed)
    const dossierCard = document.getElementById("finalConciergeCard");
    const dossierContent = document.getElementById("finalConciergeContent");
    if (dossierCard && dossierContent) {
      if (data.final_response && (data.status === "completed" || data.approved === "approved")) {
        dossierContent.innerHTML = markdownToHtml(data.final_response);
        dossierCard.classList.remove("hidden");
      } else {
        dossierCard.classList.add("hidden");
      }
    }
  }

  function updateTransitBadge(data) {
    const badge = document.getElementById("transitTypeBadge");
    if (!badge) return;
    const types = [];
    if (parseTransit(data.flight_results, "recommended_flights").length) types.push("Flights");
    if (parseTransit(data.rails_results, "trains").length) types.push("Trains");
    if (parseTransit(data.bus_results, "recommended_buses").length) types.push("Buses");
    if (!types.length && Array.isArray(data.transit_options) && data.transit_options.length) {
      types.push(data.transit_options[0].mode || "Transit");
    }
    badge.textContent = types.length ? types.join(" + ") : "—";
  }

  // ═══════════════════════════════════════════════════════════════
  //  STRUCTURED TRANSIT RENDERER
  // ═══════════════════════════════════════════════════════════════
  function renderStructuredTransit(options) {
    return options.map(item => {
      const mode = (item.mode || "Transit").toLowerCase();
      const icon = mode.includes("flight") ? "✈️" : mode.includes("train") ? "🚆" : "🚌";
      const name = item.operator || item.name || "Transit Service";
      const price = item.price_per_seat || item.price || 0;
      const url = item.booking_url || "#";
      const lastMileDesc = item.last_mile_details ? ` • + Last-mile (${item.last_mile_details.mode || 'Local'})` : "";

      return `
        <div class="item-card">
          <div class="item-info">
            <h5>${icon} ${name}</h5>
            <p>${item.mode || "Express"}${lastMileDesc}</p>
          </div>
          <div class="item-right">
            <span class="item-price">₹${Number(price).toLocaleString()}</span>
            <a href="${url}" target="_blank" class="book-link">Book →</a>
          </div>
        </div>
      `;
    }).join("");
  }

  function combineTransit(flightsRaw, railsRaw, busesRaw) {
    const items = [];
    const tryParse = (raw) => {
      if (!raw) return null;
      try { return typeof raw === "string" ? JSON.parse(raw) : raw; } catch { return null; }
    };

    [flightsRaw, railsRaw, busesRaw].forEach(raw => {
      const data = tryParse(raw);
      if (!data) return;
      if (Array.isArray(data.recommended_flights)) data.recommended_flights.forEach(f => items.push({ type: "flight", ...f }));
      if (Array.isArray(data.trains)) data.trains.forEach(t => items.push({ type: "train", ...t }));
      if (Array.isArray(data.recommended_buses)) data.recommended_buses.forEach(b => items.push({ type: "bus", ...b }));
    });

    const seen = new Set();
    const unique = items.filter(item => {
      const key = `${item.airline || item.train_name || item.operator_name}|${item.departure_time}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    if (!unique.length) return "";

    return unique.slice(0, 6).map(item => {
      const icon = item.type === "flight" ? "✈️" : item.type === "train" ? "🚆" : "🚌";
      const name = item.airline || item.train_name || item.operator_name || "Option";
      const dep = item.departure_time || "—";
      const duration = item.flight_type || item.travel_time_hours || item.duration_hours || "";
      const price = item.price_inr || item.estimated_price_inr || 0;

      let arr = item.arrival_time || "";
      if (!arr && duration && dep !== "—") arr = computeArrival(dep, duration);
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

  function computeArrival(depTime, durationStr) {
    try {
      const [dh, dm] = depTime.split(":").map(Number);
      if (isNaN(dh) || isNaN(dm)) return "";
      const hMatch = String(durationStr).match(/(\d+)\s*h/i);
      const mMatch = String(durationStr).match(/(\d+)\s*m/i);
      const totalMin = (parseInt(hMatch?.[1] || 0) * 60) + parseInt(mMatch?.[1] || 0);
      if (totalMin <= 0) return "";
      let arrMin = (dh * 60 + dm + totalMin) % 1440;
      const arrH = Math.floor(arrMin / 60);
      const arrM = arrMin % 60;
      return `${String(arrH).padStart(2, "0")}:${String(arrM).padStart(2, "0")}`;
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
    } catch { return []; }
  }

  // ═══════════════════════════════════════════════════════════════
  //  HOTELS RENDERER (With Selected Stay Highlight)
  // ═══════════════════════════════════════════════════════════════
  function renderHotels(rawJson, selectedHotel) {
    if (selectedHotel && selectedHotel.price === 0) {
      return `
        <div class="item-card selected-card" style="border: 1px solid #10b981; background: rgba(16, 185, 129, 0.04);">
          <div class="item-info">
            <h5>☀️ Day Trip (Same-Day Return)</h5>
            <p>No overnight stay required in ${selectedHotel.location || 'destination'}. Full-day exploration plan.</p>
          </div>
          <div class="item-right">
            <span class="item-price" style="color: #10b981; font-weight: 600;">₹0 Stay Cost</span>
          </div>
        </div>
      `;
    }
    if (!rawJson) return "";
    try {
      const data = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
      const hotels = data.hotels || data.results || [];
      if (!hotels.length) return "";

      const selectedName = selectedHotel?.name?.toLowerCase().trim() || "";

      return hotels.slice(0, 4).map(h => {
        const name = h.name || h.title || "Hotel";
        const isSelected = selectedName && name.toLowerCase().includes(selectedName);
        const rating = h.rating || "";
        const price = h.price_per_night || 0;
        const location = h.location || "";
        const url = h.url || h.booking_url || "#";

        let subtitle = rating && location ? `${rating} • ${location}` : (rating || location || "Verified Stay");
        if (isSelected) subtitle = `⭐ Primary Pick • ${subtitle}`;

        const priceHtml = price > 0
          ? `<span class="item-price">₹${Number(price).toLocaleString()}<span style="font-size:10px;color:#9597a0;">/night</span></span>`
          : `<span class="item-price" style="font-size:11px;color:#9597a0;">Check price</span>`;

        return `
          <div class="item-card ${isSelected ? 'selected-card' : ''}" style="${isSelected ? 'border: 1px solid #4f46e5; background: rgba(79, 70, 229, 0.04);' : ''}">
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
      console.warn("renderHotels failed:", e);
      return "";
    }
  }

  // ═══════════════════════════════════════════════════════════════
  //  ITINERARY & MARKDOWN
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

function markdownToHtml(md) {
  if (!md) return "";

  // 1. Normalize line endings (\r\n -> \n)
  let text = String(md).replace(/\r\n/g, "\n").trim();
  text = escapeHtml(text);

  // 2. Robust Markdown Table Parser
  text = text.replace(
    /(?:^|\n)(\|.+?\|\n\|(?:\s*[-:]+[-|\s:]*)\|\n(?:\|.+?\|\n?)+)(?=\n|$)/g,
    (match, tableBlock) => {
      const rows = tableBlock.trim().split("\n").map(r => r.trim()).filter(Boolean);
      if (rows.length < 2) return match;

      const parseRow = (rowStr) =>
        rowStr
          .replace(/^\||\|$/g, "")
          .split("|")
          .map(cell => cell.trim());

      const headers = parseRow(rows[0]);
      // rows[1] separator line hoti hai (|---|---|), usko chhod do
      const bodyRows = rows.slice(2).map(parseRow);

      const thead = headers
        .map(h => `<th style="padding:10px 12px;background:#f3f4f6;color:#374151;font-weight:600;font-size:12px;text-align:left;border-bottom:2px solid #e5e7eb;">${h}</th>`)
        .join("");

      const tbody = bodyRows
        .map(row => `
          <tr style="border-bottom:1px solid #f3f4f6;">
            ${row.map(cell => `<td style="padding:10px 12px;font-size:12.5px;color:#1f2937;">${cell}</td>`).join("")}
          </tr>
        `).join("");

      return `
        <div style="overflow-x:auto;margin:14px 0;border:1px solid #e5e7eb;border-radius:8px;">
          <table style="width:100%;border-collapse:collapse;background:#ffffff;">
            <thead><tr>${thead}</tr></thead>
            <tbody>${tbody}</tbody>
          </table>
        </div>
      `;
    }
  );

  // 3. Headings, bold, italic, links
  text = text.replace(/^###\s+(.+)$/gm, '<h5 class="md-h" style="margin:12px 0 6px;font-weight:600;color:#111827;">$1</h5>');
  text = text.replace(/^##\s+(.+)$/gm,  '<h4 class="md-h" style="margin:14px 0 8px;font-weight:700;color:#111827;">$1</h4>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>');
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="md-link" style="color:#4f46e5;text-decoration:underline;">$1</a>');
  text = text.replace(/^\s*[-•]\s+(.+)$/gm, '<li>$1</li>');
  text = text.replace(/(<li>[\s\S]*?<\/li>\s*)+/g, m => `<ul style="margin:8px 0;padding-left:20px;">${m}</ul>`);
  text = text.replace(/\n{2,}/g, '</p><p style="margin:8px 0;">');
  text = text.replace(/(?<!<\/li>|<\/ul>|<\/h4>|<\/h5>|<\/div>|<\/p>)\n/g, '<br>');

  return `<div class="md-body"><p style="margin:8px 0;">${text}</p></div>`;
}

  function escapeHtml(str) {
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ═══════════════════════════════════════════════════════════════
  //  ACCURATE TOTAL EXTRACTION (Fixed Regex)
  // ═══════════════════════════════════════════════════════════════
  function extractAccurateTotal(text) {
    if (!text) return null;
    const str = String(text);

    // Pehle strict line dhoondein: "TOTAL ESTIMATED EXPENSE: ₹..." ya "TOTAL: ₹..."
    const explicitMatch = str.match(/TOTAL(?:\s+ESTIMATED\s+EXPENSE)?\s*[:\-]?\s*(?:\*\*)?₹\s*([\d,]+)/i);
    if (explicitMatch) return `₹${explicitMatch[1]}`;

    // Table row match: "| Total | ₹... |"
    const tableMatch = str.match(/\|\s*Total\s*\|\s*₹?\s*([\d,]+)/i);
    if (tableMatch) return `₹${tableMatch[1]}`;

    const approxMatch = str.match(/Total\s*[≈=:]\s*₹?\s*([\d,]+)/i);
    if (approxMatch) return `₹${approxMatch[1]}`;

    return null;
  }
});