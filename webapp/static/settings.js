"use strict";

const byId = (id) => document.getElementById(id);
const DEFAULT_MARGINS = {left: 25, top: 45, right: 25, bottom: 40};
let cardUpdatePollTimer = null;
let cardUpdateWasRunning = false;

async function requestJson(url, options = {}) {
  const response = await fetch(url, {cache: "no-store", ...options});
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

// MOMIR_THERMAL_PRINTER_SETTINGS_START
let thermalPreviewObjectUrl = null;

function showPrinterModeMessage(message = "", kind = "") {
  const element = byId("printerModeStatus");
  element.textContent = message;
  element.className = `settings-note margin-message ${kind}`.trim();
}

function setPrinterTypeVisibility(type) {
  const isThermal = type === "thermal_58mm";
  byId("thermalPrinterSettings").classList.toggle("hidden", !isThermal);
  byId("photoPrinterSettings").classList.toggle("hidden", isThermal);
  byId("photoPrinterNote").classList.toggle("hidden", isThermal);
}

function fillPrinterSettings(settings = {}) {
  const thermal = settings.thermal || {};
  byId("printerType").value = settings.type || "photo";
  byId("thermalTransport").value =
    thermal.transport || "bluetooth_rfcomm";
  byId("thermalBluetoothAddress").value =
    thermal.bluetooth_address || "10:22:33:05:45:58";
  byId("thermalRfcommChannel").value =
    thermal.rfcomm_channel ?? 1;
  byId("thermalColumns").value = thermal.columns ?? 32;
  byId("thermalPaperWidth").value =
    thermal.paper_width_pixels ?? 384;
  byId("thermalQrSize").value =
    thermal.qr_size_pixels ?? 144;
  setPrinterTypeVisibility(byId("printerType").value);
}

function printerSettingsValues() {
  return {
    type: byId("printerType").value,
    thermal: {
      transport: byId("thermalTransport").value,
      bluetooth_address:
        byId("thermalBluetoothAddress").value.trim(),
      rfcomm_channel:
        Number(byId("thermalRfcommChannel").value),
      columns: Number(byId("thermalColumns").value),
      paper_width_pixels:
        Number(byId("thermalPaperWidth").value),
      qr_size_pixels:
        Number(byId("thermalQrSize").value),
    },
  };
}

async function loadPrinterSettings() {
  try {
    const data = await requestJson("/api/printer/settings");
    fillPrinterSettings(data.settings || {});
    showPrinterModeMessage();
  } catch (error) {
    showPrinterModeMessage(
      error.message || "Could not load printer settings.",
      "error",
    );
  }
}

async function savePrinterMode(event) {
  event.preventDefault();
  const button = byId("savePrinterModeBtn");
  button.disabled = true;
  showPrinterModeMessage("Saving printer settings...");
  try {
    const data = await requestJson("/api/printer/settings", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({settings: printerSettingsValues()}),
    });
    fillPrinterSettings(data.settings || {});
    const thermal = data.settings.thermal || {};
    let message = "Photo printer mode saved.";
    if (data.settings.type === "thermal_58mm") {
      message =
        thermal.transport === "bluetooth_rfcomm"
          ? `Bluetooth thermal printer saved: ${thermal.bluetooth_address}, channel ${thermal.rfcomm_channel}.`
          : "Thermal mock mode saved.";
    }
    showPrinterModeMessage(message, "success");
    await refreshDashboard();
  } catch (error) {
    showPrinterModeMessage(
      error.message || "Could not save printer settings.",
      "error",
    );
  } finally {
    button.disabled = false;
  }
}

async function previewCurrentThermalCard() {
  const button = byId("previewThermalBtn");
  const wrap = byId("thermalPreviewWrap");
  const image = byId("thermalPreviewImage");
  button.disabled = true;
  showPrinterModeMessage("Rendering current card...");
  try {
    const response = await fetch(
      `/preview/thermal/current.png?t=${Date.now()}`,
      {cache: "no-store"},
    );
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "No current card is selected.");
    }
    const blob = await response.blob();
    if (thermalPreviewObjectUrl) {
      URL.revokeObjectURL(thermalPreviewObjectUrl);
    }
    thermalPreviewObjectUrl = URL.createObjectURL(blob);
    image.src = thermalPreviewObjectUrl;
    wrap.classList.remove("hidden");
    showPrinterModeMessage("Thermal preview rendered.", "success");
  } catch (error) {
    wrap.classList.add("hidden");
    showPrinterModeMessage(
      error.message || "Could not render a thermal preview.",
      "error",
    );
  } finally {
    button.disabled = false;
  }
}
// MOMIR_THERMAL_PRINTER_SETTINGS_END

function fillMarginFields(margins) {
  byId("marginLeft").value = margins.left;
  byId("marginTop").value = margins.top;
  byId("marginRight").value = margins.right;
  byId("marginBottom").value = margins.bottom;
}

function marginValues() {
  return {
    left: Number(byId("marginLeft").value),
    top: Number(byId("marginTop").value),
    right: Number(byId("marginRight").value),
    bottom: Number(byId("marginBottom").value),
  };
}

function showMarginMessage(message = "", kind = "") {
  const element = byId("printerMarginStatus");
  element.textContent = message;
  element.className = `settings-note margin-message ${kind}`.trim();
}

async function loadPrinterMargins() {
  try {
    const data = await requestJson("/api/printer/margins");
    fillMarginFields(data.margins);
    showMarginMessage();
  } catch (error) {
    showMarginMessage(error.message || "Could not load printer margins.", "error");
  }
}

async function savePrinterMargins(event = null, values = null) {
  event?.preventDefault();
  const saveButton = byId("savePrinterMarginsBtn");
  const defaultButton = byId("defaultPrinterMarginsBtn");
  saveButton.disabled = true;
  defaultButton.disabled = true;
  showMarginMessage("Saving margins...");
  try {
    const data = await requestJson("/api/printer/margins", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({margins: values || marginValues()}),
    });
    fillMarginFields(data.margins);
    showMarginMessage(
      "Margins saved. New previews and prints will use these values.",
      "success",
    );
  } catch (error) {
    showMarginMessage(error.message || "Could not save printer margins.", "error");
  } finally {
    saveButton.disabled = false;
    defaultButton.disabled = false;
  }
}

function restoreDefaultMargins() {
  fillMarginFields(DEFAULT_MARGINS);
  savePrinterMargins(null, DEFAULT_MARGINS);
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
    if (data.running) scheduleCardUpdatePoll();
  } catch (error) {
    byId("updateCardsBtn").disabled = false;
    byId("cardUpdateStatus").textContent = "Could not read update status.";
    byId("cardUpdateStatus").className = "update-status error";
  }
}

async function startCardUpdate() {
  const approved = window.confirm(
    "Download the latest card list from Scryfall? Printed-card tracking will be kept.",
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
    renderCardUpdateStatus({running: false, state: "error", error: error.message});
  }
}

async function refreshAll() {
  const button = byId("refreshSettingsBtn");
  button.disabled = true;
  await Promise.allSettled([
    refreshDashboard(),
    refreshCardUpdateStatus(),
    loadPrinterMargins(),
    loadPrinterSettings(),
  ]);
  button.disabled = false;
}

function initSettings() {
  byId("refreshSettingsBtn").addEventListener("click", refreshAll);
  byId("updateCardsBtn").addEventListener("click", startCardUpdate);
  byId("printerMarginForm").addEventListener("submit", savePrinterMargins);
  byId("printerModeForm").addEventListener("submit", savePrinterMode);
  byId("printerType").addEventListener("change", (event) => {
    setPrinterTypeVisibility(event.target.value);
    showPrinterModeMessage();
  });
  byId("previewThermalBtn").addEventListener("click", previewCurrentThermalCard);
  byId("defaultPrinterMarginsBtn").addEventListener("click", restoreDefaultMargins);
  refreshAll();
  setInterval(() => {
    if (document.visibilityState === "visible") refreshDashboard();
  }, 30000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refreshAll();
  });
}

initSettings();
