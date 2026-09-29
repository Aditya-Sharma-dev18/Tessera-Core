document.addEventListener("DOMContentLoaded", () => {
  const queryInput = document.getElementById("userQuery");
  const generateBtn = document.getElementById("generateBtn");
  const pipelineSection = document.getElementById("agentPipeline");
  const pipelineStatus = document.getElementById("pipelineStatus");
  const resultsSection = document.getElementById("resultsSection");

  const sampleButtons = document.querySelectorAll(".sample-query");
  sampleButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      queryInput.value = btn.getAttribute("data-query");
      queryInput.focus();
    });
  });

  generateBtn.addEventListener("click", async () => {
    const query = queryInput.value.trim();
    if (!query) return;

    // Reset view
    resultsSection.classList.add("hidden");
    pipelineSection.classList.remove("hidden");
    resetSteps();

    // Step 1: Input Guardrail
    setStep("step-guardrail", "active", "Validating safety & travel intent...");
    await sleep(700);
    setStep("step-guardrail", "done", "Passed validation");

    // Step 2: Supervisor Agent Routing
    setStep("step-supervisor", "active", "Supervisor decomposing constraints...");
    await sleep(800);
    setStep("step-supervisor", "done", "Selected: Flight, Hotel, Itinerary");

    // Step 3: FastMCP Specialist Calls
    setStep("step-specialists", "active", "Invoking FastMCP tools (fast_flights, Tavily)...");
    await sleep(1000);
    setStep("step-specialists", "done", "Results compiled to SharedState");

    // Step 4: Synthesizer
    setStep("step-synthesizer", "active", "Formatting final structured plan...");
    await sleep(600);
    setStep("step-synthesizer", "done", "Execution Complete");

    pipelineStatus.textContent = "Plan generated successfully";

    // Populate and show results
    renderResults(query);
    resultsSection.classList.remove("hidden");
  });

  function resetSteps() {
    ["step-guardrail", "step-supervisor", "step-specialists", "step-synthesizer"].forEach(id => {
      const el = document.getElementById(id);
      el.className = "step-badge";
    });
  }

  function setStep(stepId, state, statusText) {
    const el = document.getElementById(stepId);
    el.className = `step-badge ${state}`;
    pipelineStatus.textContent = statusText;
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function renderResults(query) {
    // Transit list populated with FastMCP-style fields
    const transitContainer = document.getElementById("transitOptionsList");
    transitContainer.innerHTML = `
      <div class="item-card">
        <div class="item-info">
          <h5>IndiGo 6E-2041 (Non-stop)</h5>
          <p>DEL 06:10 → GOI 08:45 • 2h 35m • A320neo</p>
        </div>
        <div class="item-right">
          <span class="item-price">₹4,850</span>
          <a href="#" class="book-link">1-Click Book</a>
        </div>
      </div>
      <div class="item-card">
        <div class="item-info">
          <h5>Air India AI-883 (Non-stop)</h5>
          <p>DEL 11:20 → GOI 14:00 • 2h 40m • A321</p>
        </div>
        <div class="item-right">
          <span class="item-price">₹5,200</span>
          <a href="#" class="book-link">1-Click Book</a>
        </div>
      </div>
    `;

    // Stays list
    const hotelContainer = document.getElementById("hotelOptionsList");
    hotelContainer.innerHTML = `
      <div class="item-card">
        <div class="item-info">
          <h5>BloomSuites | Calangute</h5>
          <p>4.3★ • Pool, Free Breakfast, High-speed Wi-Fi</p>
        </div>
        <div class="item-right">
          <span class="item-price">₹3,400/night</span>
          <a href="#" class="book-link">Reserve</a>
        </div>
      </div>
      <div class="item-card">
        <div class="item-info">
          <h5>Zostel Plus South Goa</h5>
          <p>4.6★ • Beachside, Co-working space</p>
        </div>
        <div class="item-right">
          <span class="item-price">₹2,100/night</span>
          <a href="#" class="book-link">Reserve</a>
        </div>
      </div>
    `;

    // Itinerary List
    const itineraryContainer = document.getElementById("itineraryDaysList");
    itineraryContainer.innerHTML = `
      <div class="day-box">
        <h6>DAY 01 // ARRIVAL</h6>
        <p>Morning flight arrival at GOI. Check-in, relaxed lunch at Thalassa, sunset walk at Vagator Beach.</p>
      </div>
      <div class="day-box">
        <h6>DAY 02 // HERITAGE & CAFES</h6>
        <p>Explore Fontainhas Latin Quarter, historical churches in Old Goa, dinner at Mum's Kitchen.</p>
      </div>
      <div class="day-box">
        <h6>DAY 03 // SOUTH COAST</h6>
        <p>Day trip to Palolem and Cola Beach lagoon. Sunset boat ride and beachside shack dinner.</p>
      </div>
      <div class="day-box">
        <h6>DAY 04 // DEPARTURE</h6>
        <p>Souvenir shopping in Panjim, beachside breakfast, return flight back to Delhi.</p>
      </div>
    `;
  }

  // HITL Button actions
  document.getElementById("approveBtn").addEventListener("click", () => {
    alert("Plan Approved! Redirecting to booking confirmation deep links.");
  });

  document.getElementById("rejectBtn").addEventListener("click", () => {
    const feedback = prompt("What changes would you like the Supervisor Agent to make? (e.g., 'Change to luxury resort' or 'Shift travel to trains')");
    if (feedback) {
      alert(`Feedback recorded: "${feedback}". Re-routing agents...`);
    }
  });
});