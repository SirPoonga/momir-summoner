"use strict";

const byId = (id) => document.getElementById(id);

let cardUpdatePollTimer = null;
let cardUpdateWasRunning = false;

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    ...options,
  });

  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    throw new Error(`Invalid response from ${url}`);
  }

  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }

  return data;
}

function displayValue(value) {
  if (value === null || value === undefined || value === "" || value === "unknown") {
    return "Unavailable";
  }
  return String(value);
}

function displayNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : "Unavailable";
}

function renderPrinter(printer = {}) {
  const status = byId("settingsPrinterStatus");
  const details = byId("settingsPrinterDetails");
  const message = printer.message || "Printer status unknown";
  const isUnknown = /unknown/i.test(message);

  status.textContent = message;
  status.className = printer.connected
    ? "printer connected"
    : isUnknown
      ? "printer unknown"
      : "printer disconnected";

  if (printer.details) {
    details.textContent = printer.details;
    details.classList.remove("hidden");
  } else {
    details.textContent = "";
    details.classList.add("hidden");
  }
}

function renderNetwork(network = {}) {
  byId("networkWifi").textContent = displayValue(network.wifi);
  byId("networkIp").textContent = displayValue(network.ip);
  byId("networkTailscale").textContent = displayValue(network.tailscale);

  const localUrl = window.location.origin;
  const localLink = byId("networkLocalUrl");
  localLink.textContent = localUrl;
  localLink.href = `${localUrl}/`;
}

function renderStatus(status = {}) {
  byId("databaseCards").textContent = displayNumber(status.cards);
  byId("databaseBackFaces").textContent = displayNumber(status.back_faces);
  byId("databasePrintedUnique").textContent = displayNumber(status.printed_unique);
  byId("databasePrintsTotal").textContent = displayNumber(status.prints_total);
  byId("lastCardStatus").textContent = status.last_card?.name || "None";
  byId("applicationStatus").textContent = "Running";
  byId("applicationStatus").className = "settings-value status-good";
}

function showSettingsError(message = "") {
  const error = byId("settingsError");
  error.textContent = message;
  error.classList.toggle("hidden", !message);
}

async function refreshDashboard() {
  try {
    const data = await requestJson("/api/dashboard");
    renderPrinter(data.printer || {});
    renderNetwork(data.network || {});
    renderStatus(data.status || {});
    showSettingsError();
  } catch (error) {
    byId("applicationStatus").textContent = "Status unavailable";
    byId("applicationStatus").className = "settings-value status-bad";
    showSettingsError(error.message || "Could not load system status.");
  }
}

function formatCardUpdateMessage(data = {}) {
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

function renderCardUpdateStatus(data = {}) {
  const running = Boolean(data.running);
  const button = byId("updateCardsBtn");
  const status = byId("cardUpdateStatus");
  const progress = byId("cardUpdateProgress");
  const progressBar = byId("cardUpdateProgressBar");

  button.disabled = running;
  if (running && data.page && data.total_pages) {
    button.textContent = `Updating ${data.page} / ${data.total_pages}`;
  } else if (running) {
    button.textContent = "Preparing Update...";
  } else {
    button.textContent = "Update Cards";
  }

  const percent = Number(data.progress_percent);
  if (running && Number.isFinite(percent)) {
    const boundedPercent = Math.max(0, Math.min(100, percent));
    progress.classList.remove("hidden");
    progressBar.style.width = `${boundedPercent}%`;
    progress.setAttribute("aria-valuenow", String(boundedPercent));
  } else {
    progress.classList.add("hidden");
    progressBar.style.width = "0%";
    progress.setAttribute("aria-valuenow", "0");
  }

  status.textContent = formatCardUpdateMessage(data);
  status.className = data.state === "error" ? "update-status error" : "update-status";

  if (running) {
    cardUpdateWasRunning = true;
  } else if (cardUpdateWasRunning) {
    cardUpdateWasRunning = false;
    refreshDashboard();
  }
}

function scheduleCardUpdatePoll(delay = 1000) {
  clearTimeout(cardUpdatePollTimer);
  cardUpdatePollTimer = setTimeout(refreshCardUpdateStatus, delay);
}

async function refreshCardUpdateStatus() {
  try {
    const data = await requestJson("/api/cards/update");
    renderCardUpdateStatus(data);
    if (data.running) {
      scheduleCardUpdatePoll();
    }
  } catch (error) {
    byId("updateCardsBtn").disabled = false;
    byId("cardUpdateStatus").textContent = "Could not read update status.";
    byId("cardUpdateStatus").className = "update-status error";
  }
}

async function startCardUpdate() {
  const approved = window.confirm(
    "Download the latest card list from Scryfall? Printed-card tracking will be kept."
  );
  if (!approved) return;

  renderCardUpdateStatus({
    running: true,
    state: "starting",
    message: "Preparing card database update...",
  });

  try {
    const data = await requestJson("/api/cards/update", {method: "POST"});
    renderCardUpdateStatus(data);
    scheduleCardUpdatePoll(750);
  } catch (error) {
    renderCardUpdateStatus({
      running: false,
      state: "error",
      error: error.message,
    });
  }
}

async function refreshAll() {
  const button = byId("refreshSettingsBtn");
  button.disabled = true;
  await Promise.allSettled([refreshDashboard(), refreshCardUpdateStatus()]);
  button.disabled = false;
}

function initSettings() {
  byId("refreshSettingsBtn").addEventListener("click", refreshAll);
  byId("updateCardsBtn").addEventListener("click", startCardUpdate);

  refreshAll();
  setInterval(() => {
    if (document.visibilityState === "visible") {
      refreshDashboard();
    }
  }, 30000);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshAll();
    }
  });
}

initSettings();
