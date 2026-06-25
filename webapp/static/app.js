let lastCard = null;
let searchTimer = null;
let selectionController = null;
let searchController = null;
let previewController = null;
let selectionSequence = 0;
let previewObjectUrl = null;
let dashboardTimer = null;
let cardUpdatePollTimer = null;
let cardUpdateRunning = false;
let showingBack = false;
let currentPreviewUrls = {front: null, back: null};

function $(id) {
  return document.getElementById(id);
}

function setStatus(message) {
  $("status").textContent = message;
}

function setCardActionsEnabled(enabled) {
  const disabled = !enabled || cardUpdateRunning;
  $("printBtn").disabled = disabled;
  $("reprintBtn").disabled = disabled;
  $("backBtn").disabled = disabled || !lastCard?.has_back;
  $("viewBackBtn").disabled = disabled || !lastCard?.has_back;

  const alreadyPrinted = Boolean(
    lastCard?.printed || Number(lastCard?.printed_count) > 0
  );
  $("markPrintedBtn").disabled = disabled || alreadyPrinted;
  $("markPrintedBtn").textContent = alreadyPrinted
    ? "Marked as Printed"
    : "Mark as Printed";
}

function renderPrintedStatus(card) {
  const icon = $("cardPrintedIcon");
  const printed = Boolean(card?.printed || Number(card?.printed_count) > 0);
  icon.classList.toggle("hidden", !printed);
  icon.setAttribute("aria-hidden", printed ? "false" : "true");
}

function setSelectedMana(mv) {
  document.querySelectorAll("#manaButtons button").forEach((button) => {
    button.classList.toggle("selected", Number(button.dataset.mv) === Number(mv));
  });
}

function clearPreviewObjectUrl() {
  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = null;
  }
}

async function loadPreview(previewUrl, cardName) {
  if (previewController) previewController.abort();
  previewController = new AbortController();
  const controller = previewController;

  const shell = $("previewShell");
  const loading = $("previewLoading");
  const img = $("preview");

  shell.classList.remove("hidden");
  loading.textContent = "Rendering preview...";
  loading.classList.remove("hidden");
  img.classList.add("hidden");
  img.removeAttribute("src");
  clearPreviewObjectUrl();

  try {
    const response = await fetch(previewUrl, {
      signal: controller.signal,
      cache: "force-cache",
    });
    if (!response.ok) throw new Error(`Preview failed (${response.status})`);

    const blob = await response.blob();
    if (controller !== previewController) return;

    previewObjectUrl = URL.createObjectURL(blob);
    img.alt = `${cardName} rendered card preview`;
    img.onload = () => {
      if (controller !== previewController) return;
      loading.classList.add("hidden");
      img.classList.remove("hidden");
    };
    img.onerror = () => {
      if (controller !== previewController) return;
      loading.textContent = "Preview unavailable";
    };
    img.src = previewObjectUrl;
  } catch (error) {
    if (error.name === "AbortError") return;
    loading.textContent = "Preview unavailable";
  }
}

function faceData() {
  return showingBack && lastCard?.back ? lastCard.back : lastCard;
}

function renderSelectedFace(loadImage = true) {
  const face = faceData();
  if (!face || !lastCard) return;

  $("cardName").textContent = face.name || lastCard.name;
  renderPrintedStatus(lastCard);

  $("cardMeta").textContent = showingBack
    ? `${face.type_line ?? ""} | Back face`
    : (face.type_line ?? "");
  $("cardText").textContent = face.oracle_text || "";
  $("viewBackBtn").textContent = showingBack ? "View Front" : "View Back";

  if (loadImage) {
    const url = showingBack ? currentPreviewUrls.back : currentPreviewUrls.front;
    if (url) loadPreview(url, face.name || lastCard.name);
  }
}

function toggleCardFace() {
  if (!lastCard?.has_back) return;
  showingBack = !showingBack;
  renderSelectedFace(true);
}

function showCard(card, previewUrl, backPreviewUrl = null) {
  lastCard = card;
  showingBack = false;
  currentPreviewUrls = {front: previewUrl, back: backPreviewUrl};
  renderSelectedFace(true);
  setCardActionsEnabled(true);
}


async function requestCard(url, body, loadingMessage) {
  const sequence = ++selectionSequence;
  if (selectionController) selectionController.abort();
  selectionController = new AbortController();

  $("cardName").textContent = loadingMessage;
  renderPrintedStatus(null);
  setCardActionsEnabled(false);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
      signal: selectionController.signal,
    });
    const data = await response.json();

    if (sequence !== selectionSequence) return;
    if (!response.ok || !data.ok) {
      $("cardName").textContent = data.error || "Card selection failed";
      setCardActionsEnabled(Boolean(lastCard));
      return;
    }

    showCard(data.card, data.preview_url, data.back_preview_url || null);
    setStatus(`Selected ${data.card.name}.`);
  } catch (error) {
    if (error.name === "AbortError") return;
    if (sequence !== selectionSequence) return;
    $("cardName").textContent = "Connection error";
    setStatus("Could not reach the Momir server.");
    setCardActionsEnabled(Boolean(lastCard));
  }
}

function summon(mv) {
  setSelectedMana(mv);
  return requestCard(
    "/api/summon",
    {mana_value: mv},
    `Choosing mana value ${mv}...`,
  );
}

async function runPrint(endpoint, workingText, successText) {
  setStatus(workingText);
  $("printBtn").disabled = true;
  $("reprintBtn").disabled = true;
  $("backBtn").disabled = true;
  $("viewBackBtn").disabled = true;
  $("markPrintedBtn").disabled = true;

  try {
    const response = await fetch(endpoint, {method: "POST"});
    const data = await response.json();
    if (data.ok && data.card && lastCard?.id === data.card.id) {
      lastCard = {...lastCard, ...data.card};
      renderPrintedStatus(lastCard);
    }
    setStatus(data.ok ? successText : (data.error || "Print failed."));
  } catch (error) {
    setStatus("Could not reach the Momir server.");
  } finally {
    setCardActionsEnabled(Boolean(lastCard));
    refreshDashboard(false);
  }
}

function printCurrent() {
  return runPrint("/api/print", "Preparing and printing...", "Print sent.");
}

function reprintLast() {
  return runPrint("/api/reprint", "Reprinting...", "Reprint sent.");
}

function printBack() {
  return runPrint("/api/print_back", "Printing back...", "Back printed.");
}

async function markCurrentPrinted() {
  if (!lastCard) return;

  setStatus("Marking card as printed...");
  setCardActionsEnabled(false);

  try {
    const response = await fetch("/api/mark_printed", {method: "POST"});
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Could not mark the card as printed.");
    }

    if (data.card && lastCard?.id === data.card.id) {
      lastCard = {...lastCard, ...data.card};
      renderPrintedStatus(lastCard);
    }
    setStatus(`${lastCard.name} marked as printed.`);
    refreshDashboard(false);
  } catch (error) {
    setStatus(error.message || "Could not reach the Momir server.");
  } finally {
    setCardActionsEnabled(Boolean(lastCard));
  }
}

function renderSearchResults(rows) {
  const results = $("searchResults");
  results.replaceChildren();

  for (const card of rows) {
    const button = document.createElement("button");
    button.className = "resultBtn";
    button.type = "button";

    const name = document.createElement("b");
    name.textContent = card.name;
    button.appendChild(name);
    button.appendChild(document.createElement("br"));
    button.append(card.type_line || "Creature");
    button.addEventListener("click", () => selectSearchedCard(card.id));
    results.appendChild(button);
  }
}

async function searchCards() {
  const query = $("searchBox").value.trim();
  if (searchController) searchController.abort();

  if (!query) {
    $("searchResults").replaceChildren();
    return;
  }

  searchController = new AbortController();
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
      signal: searchController.signal,
    });
    const rows = await response.json();
    renderSearchResults(rows);
  } catch (error) {
    if (error.name !== "AbortError") {
      $("searchResults").textContent = "Search unavailable";
    }
  }
}

function selectSearchedCard(id) {
  return requestCard(
    "/api/select",
    {id},
    "Loading selected card...",
  );
}

function updateDashboard(data) {
  const printer = data.printer || {};
  const network = data.network || {};
  const stats = data.status || {};

  const printerElement = $("printerStatus");
  printerElement.textContent = printer.message || "Printer status unknown";
  printerElement.className = printer.connected
    ? "printer connected"
    : "printer disconnected";

  $("status").innerHTML =
    `Cards: ${stats.cards ?? "?"}<br>` +
    `Stored back faces: ${stats.back_faces ?? "?"}<br>` +
    `Unique printed: ${stats.printed_unique ?? "?"}<br>` +
    `Total prints: ${stats.prints_total ?? "?"}<br>` +
    `Last card: ${stats.last_card ? stats.last_card.name : "None"}`;

  $("networkFooter").innerHTML =
    `Printer: ${printer.message || "unknown"}<br>` +
    `WiFi: ${network.wifi || "unknown"}<br>` +
    `IP: ${network.ip || "unknown"}<br>` +
    `Tail: ${network.tailscale || "unknown"}<br>` +
    `Cards: ${stats.cards ?? "?"} | Backs: ${stats.back_faces ?? "?"} | Printed: ${stats.printed_unique ?? "?"}`;
}

async function refreshDashboard(updateStatusPanel = true) {
  if (document.visibilityState === "hidden") return;

  try {
    const response = await fetch("/api/dashboard", {cache: "no-store"});
    const data = await response.json();
    if (updateStatusPanel) {
      updateDashboard(data);
    } else {
      const savedStatus = $("status").innerHTML;
      updateDashboard(data);
      $("status").innerHTML = savedStatus;
    }
  } catch (error) {
    $("networkFooter").textContent = "Network status unavailable";
  }
}


function formatCardUpdateMessage(data) {
  if (data.state === "complete" && data.summary) {
    return (
      `Update complete. ${data.summary.added} added, ` +
      `${data.summary.removed} removed, ${data.summary.imported} creatures total, ` +
      `${data.summary.with_back ?? 0} with stored back faces.`
    );
  }
  if (data.state === "error") {
    return `Update failed: ${data.error || "Unknown error"}`;
  }
  return data.message || "Ready to update when a new set is available.";
}

function renderCardUpdateStatus(data) {
  cardUpdateRunning = Boolean(data.running);
  const button = $("updateCardsBtn");
  const status = $("cardUpdateStatus");
  const progress = $("cardUpdateProgress");
  const progressBar = $("cardUpdateProgressBar");

  button.disabled = cardUpdateRunning;
  if (cardUpdateRunning && data.page && data.total_pages) {
    button.textContent = `Updating ${data.page} / ${data.total_pages}`;
  } else if (cardUpdateRunning) {
    button.textContent = "Preparing Update...";
  } else {
    button.textContent = "Update Cards";
  }

  const percent = Number(data.progress_percent);
  if (cardUpdateRunning && Number.isFinite(percent)) {
    progress.classList.remove("hidden");
    progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    progress.setAttribute("aria-valuenow", String(percent));
  } else {
    progress.classList.add("hidden");
    progressBar.style.width = "0%";
    progress.setAttribute("aria-valuenow", "0");
  }

  status.textContent = formatCardUpdateMessage(data);
  status.className = data.state === "error" ? "update-status error" : "update-status";
  setCardActionsEnabled(Boolean(lastCard));
}

function scheduleCardUpdatePoll(delay = 1000) {
  clearTimeout(cardUpdatePollTimer);
  cardUpdatePollTimer = setTimeout(refreshCardUpdateStatus, delay);
}

async function refreshCardUpdateStatus() {
  try {
    const response = await fetch("/api/cards/update", {cache: "no-store"});
    const data = await response.json();
    renderCardUpdateStatus(data);

    if (data.running) {
      scheduleCardUpdatePoll();
    } else if (data.state === "complete") {
      refreshDashboard(false);
    }
  } catch (error) {
    $("cardUpdateStatus").textContent = "Could not read update status.";
    $("updateCardsBtn").disabled = false;
  }
}

async function startCardUpdate() {
  const approved = window.confirm(
    "Download the latest card list from Scryfall? Printed-card tracking will be kept."
  );
  if (!approved) return;

  cardUpdateRunning = true;
  renderCardUpdateStatus({
    running: true,
    state: "starting",
    message: "Preparing card database update...",
  });

  try {
    const response = await fetch("/api/cards/update", {method: "POST"});
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Unable to start update");
    }
    renderCardUpdateStatus(data);
    scheduleCardUpdatePoll(750);
  } catch (error) {
    cardUpdateRunning = false;
    renderCardUpdateStatus({
      running: false,
      state: "error",
      error: error.message,
    });
  }
}

function init() {
  const mana = $("manaButtons");
  for (let value = 1; value <= 16; value += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = value;
    button.dataset.mv = value;
    button.addEventListener("click", () => summon(value));
    mana.appendChild(button);
  }

  $("printBtn").addEventListener("click", printCurrent);
  $("reprintBtn").addEventListener("click", reprintLast);
  $("viewBackBtn").addEventListener("click", toggleCardFace);
  $("backBtn").addEventListener("click", printBack);
  $("markPrintedBtn").addEventListener("click", markCurrentPrinted);
  $("updateCardsBtn").addEventListener("click", startCardUpdate);
  $("searchBox").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchCards, 350);
  });

  // Let the controls paint first, then perform the slower Bluetooth status check.
  setTimeout(refreshDashboard, 250);
  setTimeout(refreshCardUpdateStatus, 350);
  dashboardTimer = setInterval(refreshDashboard, 30000);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshDashboard();
      refreshCardUpdateStatus();
    }
  });
}

init();
