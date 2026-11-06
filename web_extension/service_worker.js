const MAX_TEXT_BYTES = 6 * 1024 * 1024;
const MAX_IDENTIFIER_CHARS = 128;

function safeString(value, maxLength = MAX_IDENTIFIER_CHARS) {
  return typeof value === "string" && value.length > 0 && value.length <= maxLength;
}

function isValidBridgeCommand(message) {
  if (!message || typeof message !== "object" || Array.isArray(message) || typeof message.type !== "string") return false;
  if (message.type === "refresh_tabs") return message.force === undefined || typeof message.force === "boolean";
  if (message.type === "preview_tab") {
    return Number.isSafeInteger(Number(message.tab_id)) && safeString(String(message.request_id || "")) &&
      safeString(String(message.client_id || "")) && (message.selected_field_id === undefined || typeof message.selected_field_id === "string");
  }
  if (message.type === "start_job") {
    if (!Number.isSafeInteger(Number(message.tab_id)) || !Number.isSafeInteger(Number(message.frame_id ?? 0))) return false;
    if (!safeString(String(message.job_id ?? "")) || !safeString(String(message.field_id ?? ""))) return false;
    if (typeof message.text !== "string" || new TextEncoder().encode(message.text).length > MAX_TEXT_BYTES) return false;
    const speed = Number(message.speed);
    return Number.isFinite(speed) && speed >= 1 && speed <= 240 &&
      (message.tabs_as_spaces === undefined || typeof message.tabs_as_spaces === "boolean") &&
      (message.start_paused === undefined || typeof message.start_paused === "boolean");
  }
  if (message.type === "control_job") {
    return Number.isSafeInteger(Number(message.tab_id)) && Number.isSafeInteger(Number(message.frame_id ?? 0)) &&
      safeString(String(message.job_id ?? "")) && ["pause", "resume", "stop"].includes(message.action);
  }
  return false;
}
let refreshTimer = null;
let refreshing = false;
let pendingForceRefresh = false;
const tabCache = new Map();
const CACHE_TTL_MS = 12000;
// Avoid flooding the browser with hundreds of iframe messages during a full scan.
const MAX_FRAMES_PER_TAB = 12;
const FRAME_SCAN_CONCURRENCY = 4;

// The WebSocket lives in connection.html (a persistent extension document),
// not in this MV3 service worker. This avoids Chromium Local Network Access
// prompts being triggered from a worker without a Document/user gesture.
function bridgeSend(payload) {
  try {
    void chrome.runtime.sendMessage({ type: "bridge_outgoing", payload }).catch(() => {});
    return true;
  } catch (_error) {
    return false;
  }
}

function requestTabRefresh(force = false) {
  bridgeSend({ type: "refresh_tabs", force: Boolean(force) });
}

async function callContentScript(tabId, frameId, message) {
  const options = Number.isInteger(frameId) ? { frameId } : undefined;
  const send = async () => options
    ? chrome.tabs.sendMessage(tabId, message, options)
    : chrome.tabs.sendMessage(tabId, message);
  try {
    return await send();
  } catch (_firstError) {
    try {
      const target = Number.isInteger(frameId) ? { tabId, frameIds: [frameId] } : { tabId };
      await chrome.scripting.executeScript({ target, files: ["content.js"] });
      await new Promise(resolve => setTimeout(resolve, 40));
      return await send();
    } catch (error) {
      throw error;
    }
  }
}

async function scanFrame(tabId, frameId) {
  try {
    const result = await callContentScript(tabId, frameId, { type: "scan_fields" });
    return (result?.fields || []).map(field => ({ ...field, frameId }));
  } catch (_error) {
    return [];
  }
}

async function sanitizedPageUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (!(["http:", "https:"].includes(url.protocol))) return "";
    url.search = "";
    url.hash = "";
    return url.href.slice(0, 2048);
  } catch (_error) { return ""; }
}

async function scanTab(tab, force = false) {
  if (!tab || !Number.isInteger(tab.id) || !/^https?:\/\//i.test(tab.url || "")) return null;
  const cached = tabCache.get(tab.id);
  if (!force && cached && cached.url === (tab.url || "") && Date.now() - cached.scannedAt < CACHE_TTL_MS) {
    return { ...cached.data, title: tab.title || cached.data.title, active: Boolean(tab.active), windowId: tab.windowId };
  }
  let frames = [{ frameId: 0 }];
  try {
    const foundFrames = await chrome.webNavigation.getAllFrames({ tabId: tab.id });
    if (Array.isArray(foundFrames) && foundFrames.length) {
      // Always prioritize the main frame, then inspect a bounded number of iframes.
      const mainFrame = foundFrames.find(frame => frame.frameId === 0) || { frameId: 0 };
      const otherFrames = foundFrames.filter(frame => Number.isInteger(frame.frameId) && frame.frameId !== 0);
      frames = [mainFrame, ...otherFrames].slice(0, MAX_FRAMES_PER_TAB);
    }
  } catch (_error) {
    // Some restricted pages do not expose frame metadata; try the main frame.
  }
  // Limit simultaneous scans per tab; many tabs with many iframes can otherwise
  // create a burst of hundreds of extension messages and make the browser lag.
  const fieldsByFrame = [];
  for (let i = 0; i < frames.length; i += FRAME_SCAN_CONCURRENCY) {
    const batch = frames.slice(i, i + FRAME_SCAN_CONCURRENCY);
    fieldsByFrame.push(...await Promise.all(batch.map(frame => scanFrame(tab.id, frame.frameId))));
  }
  const data = {
    tabId: tab.id,
    windowId: tab.windowId,
    title: tab.title || "Página sin título",
    url: sanitizedPageUrl(tab.url || ""),
    active: Boolean(tab.active),
    fields: fieldsByFrame.flat().slice(0, 150),
    frameCount: frames.length
  };
  tabCache.set(tab.id, { data, url: tab.url || "", scannedAt: Date.now() });
  return data;
}

async function refreshTabs(force = false) {
  const permitted = await chrome.permissions.contains({ permissions: ["tabs", "scripting", "webNavigation"], origins: ["http://*/*", "https://*/*"] });
  if (!permitted) {
    bridgeSend({ type: "tabs_error", error: "Faltan permisos de la extensión. Abre su popup, pulsa 'Permitir acceso a páginas' y acepta los permisos solicitados." });
    return;
  }
  if (refreshing) {
    if (force) pendingForceRefresh = true;
    return;
  }
  refreshing = true;
  try {
    const tabs = await chrome.tabs.query({});
    const webTabs = tabs.filter(tab => /^https?:\/\//i.test(tab.url || "")).slice(0, 120);
    const results = new Array(webTabs.length);
    let nextIndex = 0;
    const workerCount = Math.min(6, webTabs.length);
    await Promise.all(Array.from({ length: workerCount }, async () => {
      while (nextIndex < webTabs.length) {
        const index = nextIndex++;
        results[index] = await scanTab(webTabs[index], force);
      }
    }));
    const browser = await browserName();
    bridgeSend({ type: "tabs_result", browser, tabs: results.filter(Boolean) });
  } catch (error) {
    bridgeSend({ type: "tabs_error", error: String(error?.message || error) });
  } finally {
    refreshing = false;
    if (pendingForceRefresh) {
      pendingForceRefresh = false;
      void refreshTabs(true);
    }
  }
}

function debouncedRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    requestTabRefresh();
  }, 900);
}

async function handleBridgeCommand(message) {
  if (message && message.type === "diagnostic_ping") {
    const diagnosticId = message.diagnostic_id;
    if (!safeString(diagnosticId, 64)) return;
    bridgeSend({
      type: "diagnostic_pong",
      diagnostic_id: diagnosticId,
      extension_version: chrome.runtime.getManifest().version,
      timestamp: Date.now()
    });
    return;
  }
  if (message && message.type === "start_job" && typeof message.text === "string" &&
      new TextEncoder().encode(message.text).length > MAX_TEXT_BYTES) {
    bridgeSend({ type: "job_error", job_id: String(message.job_id || ""),
      error: "El texto supera el límite de seguridad de 6 MiB. Divídelo en partes más pequeñas." });
    return;
  }
  if (!isValidBridgeCommand(message)) return;
  if (message.type === "refresh_tabs") {
    await refreshTabs(Boolean(message.force));
    return;
  }
  if (message.type === "preview_tab") {
    const tabId = Number(message.tab_id);
    try {
      const tab = await chrome.tabs.get(tabId);
      if (!tab || !Number.isInteger(tab.windowId)) throw new Error("No se encontró la pestaña seleccionada.");
      await chrome.windows.update(tab.windowId, { focused: true });
      await chrome.tabs.update(tabId, { active: true });
      // Espera a que Chrome/Edge pinte la pestaña y vuelve a medir los campos
      // para evitar dibujar recuadros con coordenadas antiguas.
      await new Promise(resolve => setTimeout(resolve, 450));
      const currentTab = await chrome.tabs.get(tabId);
      const freshScan = await scanTab(currentTab, true);
      await new Promise(resolve => setTimeout(resolve, 120));
      const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 62 });
      bridgeSend({ type: "preview_image", request_id: String(message.request_id || ""),
        client_id: String(message.client_id || ""), selected_field_id: String(message.selected_field_id || ""),
        tab_id: tabId, title: currentTab.title || "Página web", url: await sanitizedPageUrl(currentTab.url || ""),
        fields: freshScan?.fields || [], data_url: dataUrl });
    } catch (error) {
      bridgeSend({ type: "preview_error", request_id: String(message.request_id || ""),
        error: `No se pudo obtener la vista previa. Asegúrate de que Chrome/Edge esté visible y la página esté abierta. ${String(error?.message || error)}` });
    }
    return;
  }
  if (message.type === "start_job") {
    const tabId = Number(message.tab_id);
    const frameId = Number(message.frame_id ?? 0);
    try {
      const result = await callContentScript(tabId, frameId, {
        type: "start_job",
        job_id: String(message.job_id),
        field_id: String(message.field_id),
        text: String(message.text ?? ""),
        speed: Math.max(1, Math.min(240, Number(message.speed) || 8)),
        tabs_as_spaces: message.tabs_as_spaces !== false
      });
      if (result?.accepted) bridgeSend({ type: "job_accepted", job_id: message.job_id });
      else bridgeSend({ type: "job_error", job_id: message.job_id, error: result?.error || "El campo seleccionado ya no está disponible. Vuelve a escanear las páginas." });
    } catch (error) {
      bridgeSend({ type: "job_error", job_id: message.job_id, error: `No se pudo acceder al campo. Recarga la página y escanéala de nuevo. ${String(error?.message || error)}` });
    }
    return;
  }
  if (message.type === "control_job") {
    try {
      await callContentScript(Number(message.tab_id), Number(message.frame_id ?? 0), {
        type: "control_job", action: String(message.action), job_id: String(message.job_id)
      });
    } catch (_error) {
      if (message.action === "stop") bridgeSend({ type: "job_error", job_id: message.job_id, error: "La pestaña cambió o dejó de estar disponible." });
    }
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "bridge_incoming") {
    const expectedUrl = chrome.runtime.getURL("connection.html");
    if (sender.id !== chrome.runtime.id || !String(sender.url || "").startsWith(expectedUrl)) {
      try { sendResponse({ ok: false, error: "Origen de conexión no válido." }); } catch (_error) { /* ignore */ }
      return false;
    }
    void handleBridgeCommand(message.payload).then(() => {
      try { sendResponse({ ok: true }); } catch (_error) { /* ignore */ }
    }).catch(error => {
      try { sendResponse({ ok: false, error: String(error?.message || error) }); } catch (_error) { /* ignore */ }
    });
    return true;
  }
  if (message?.type === "web_progress" || message?.type === "job_done" || message?.type === "job_error") {
    bridgeSend(message);
    return false;
  }
  if (message?.type === "extension_pairing_updated") {
    // Notify an already-open connection page. If it is not open yet, the popup
    // will tell the user to open it and start the connection manually.
    void chrome.runtime.sendMessage({ type: "bridge_pairing_updated" }).catch(() => {});
    try { sendResponse({ ok: true }); } catch (_error) { /* popup may have closed */ }
    return false;
  }
  if (message?.type === "extension_popup_refresh") {
    void chrome.runtime.sendMessage({ type: "bridge_status_request" }).then(response => {
      const connected = Boolean(response?.connected);
      if (connected) requestTabRefresh(true);
      try { sendResponse({ ok: connected }); } catch (_error) { /* popup may have closed */ }
    }).catch(() => {
      try { sendResponse({ ok: false }); } catch (_error) { /* popup may have closed */ }
    });
    return true;
  }
});

chrome.tabs.onCreated.addListener(debouncedRefresh);
chrome.tabs.onRemoved.addListener(tabId => {
  tabCache.delete(tabId);
  debouncedRefresh();
});
chrome.tabs.onActivated.addListener(debouncedRefresh);
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  // Invalidate stale field IDs after navigation/reload. Debouncing avoids scanning repeatedly
  // while a page streams title/progress updates (especially on heavier web apps).
  if (changeInfo.status === "complete" || changeInfo.url) {
    tabCache.delete(tabId);
    debouncedRefresh();
  }
});
// The user starts the local WebSocket from connection.html with an explicit click.
