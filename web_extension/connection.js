"use strict";

const BRIDGE_URL = "ws://127.0.0.1:8765";
const statusEl = document.getElementById("status");
const connectButton = document.getElementById("connect");
const disconnectButton = document.getElementById("disconnect");
let bridgeSocket = null;
let bridgeAuthenticated = false;
let reconnectDelay = 1000;
let reconnectTimer = null;
let heartbeatTimer = null;
let userStartedConnection = false;
let manuallyDisconnected = false;
let authState = null;

function setStatus(message) {
  statusEl.textContent = message;
}

function decodeBase64Url(value) {
  const text = String(value || "");
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - text.length % 4) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, character => character.charCodeAt(0));
}

function encodeBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function concatBytes(...arrays) {
  const result = new Uint8Array(arrays.reduce((total, array) => total + array.length, 0));
  let offset = 0;
  for (const array of arrays) { result.set(array, offset); offset += array.length; }
  return result;
}

async function hmacProof(secret, label, serverNonce, clientNonce) {
  const key = await crypto.subtle.importKey("raw", secret, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const prefix = new TextEncoder().encode(`EscritorAutomatico-Bridge-${label}-v1\0`);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, concatBytes(prefix, serverNonce, clientNonce)));
}

async function browserName() {
  const ua = globalThis.navigator?.userAgent || "";
  if (/Edg\//i.test(ua)) return "Microsoft Edge";
  if (/OPR\//i.test(ua)) return "Opera (Chromium)";
  try {
    const brands = globalThis.navigator?.userAgentData?.brands || [];
    if (brands.some(item => /brave/i.test(item.brand || ""))) return "Brave";
  } catch (_error) { /* generic Chromium fallback */ }
  try {
    const braveApi = globalThis.navigator?.brave;
    if (braveApi && typeof braveApi.isBrave === "function" && await braveApi.isBrave()) return "Brave";
  } catch (_error) { /* generic Chromium fallback */ }
  if (/Chrome\//i.test(ua)) return "Chromium compatible (Chrome / Edge / Brave)";
  return "Chromium compatible";
}

function sendToApplication(payload) {
  try {
    void chrome.runtime.sendMessage({ type: "bridge_incoming", payload }).catch(() => {});
  } catch (_error) { /* the service worker may be restarting */ }
}

function sendToSocket(payload) {
  if (!bridgeAuthenticated || !bridgeSocket || bridgeSocket.readyState !== WebSocket.OPEN) return false;
  try {
    bridgeSocket.send(JSON.stringify(payload));
    return true;
  } catch (_error) {
    return false;
  }
}

async function readPairingSecret() {
  const stored = await chrome.storage.local.get("bridgePairingCode");
  const secret = decodeBase64Url(stored?.bridgePairingCode || "");
  if (secret.length !== 32) throw new Error("No hay un código de vinculación válido. Pégalo primero en el popup de la extensión.");
  return secret;
}

async function authenticateMessage(socket, message, state) {
  if (!message || typeof message !== "object") return false;
  if (message.type === "auth_challenge" && !state.pending) {
    const secret = await state.secretPromise;
    const serverNonce = decodeBase64Url(message.nonce);
    if (serverNonce.length !== 32) return false;
    const clientNonce = crypto.getRandomValues(new Uint8Array(32));
    const proof = await hmacProof(secret, "Client", serverNonce, clientNonce);
    state.pending = { secret, serverNonce, clientNonce };
    if (socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ type: "auth_response", client_nonce: encodeBase64Url(clientNonce), proof: encodeBase64Url(proof) }));
    return true;
  }
  if (message.type === "auth_ok" && state.pending) {
    const received = decodeBase64Url(message.proof);
    const expected = await hmacProof(state.pending.secret, "Server", state.pending.serverNonce, state.pending.clientNonce);
    if (received.length !== expected.length || !received.every((value, index) => value === expected[index])) return false;
    if (bridgeSocket !== socket || socket.readyState !== WebSocket.OPEN) return false;
    state.authenticated = true;
    state.pending = null;
    bridgeAuthenticated = true;
    reconnectDelay = 1000;
    const browser = await browserName();
    if (bridgeSocket !== socket || socket.readyState !== WebSocket.OPEN) return false;
    sendToSocket({ type: "hello", browser, version: chrome.runtime.getManifest().version });
    sendToSocket({ type: "refresh_tabs", force: true });
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(() => sendToSocket({ type: "heartbeat", timestamp: Date.now() }), 15000);
    setStatus("Conexión autenticada y activa. Ya puedes volver a Escritor Automático. Mantén esta pestaña abierta mientras uses la escritura web.");
    return true;
  }
  return false;
}

function scheduleReconnect() {
  if (manuallyDisconnected || !userStartedConnection || reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    // A previous user click authorized the initial local connection. Reconnect
    // attempts reuse that already-established permission state.
    openSocket();
  }, reconnectDelay);
  reconnectDelay = Math.min(15000, Math.max(1000, reconnectDelay * 1.7));
}

function openSocket() {
  if (bridgeSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(bridgeSocket.readyState)) return;
  let socket;
  try {
    // This function is first called directly by the page's Connect button.
    // Initiating the loopback WebSocket here gives Chromium a document and
    // explicit user gesture for Local Network Access permission handling.
    socket = new WebSocket(BRIDGE_URL);
  } catch (error) {
    setStatus(`No se pudo crear el WebSocket local: ${String(error?.message || error)}. Comprueba que la aplicación esté abierta.`);
    scheduleReconnect();
    return;
  }
  bridgeSocket = socket;
  bridgeAuthenticated = false;
  const state = { pending: null, authenticated: false, secretPromise: readPairingSecret() };
  authState = state;
  setStatus("Intentando conectar con Escritor Automático en 127.0.0.1:8765…");
  socket.onopen = () => {
    reconnectDelay = 1000;
    setStatus("Canal local abierto. Verificando el código de vinculación…");
  };
  socket.onmessage = event => {
    let message;
    try { message = JSON.parse(event.data); } catch (_error) { return; }
    if (!state.authenticated) {
      void authenticateMessage(socket, message, state).then(ok => {
        if (!ok) {
          setStatus("La aplicación rechazó la autenticación. Copia de nuevo el código desde Escritor Automático y guárdalo en la extensión.");
          try { socket.close(1008, "Authentication failed"); } catch (_error) { /* ignore */ }
        }
      }).catch(error => {
        setStatus(String(error?.message || error));
        try { socket.close(1008, "Pairing code unavailable"); } catch (_error) { /* ignore */ }
      });
      return;
    }
    sendToApplication(message);
  };
  socket.onerror = () => {
    setStatus("No se pudo completar la conexión con 127.0.0.1:8765. Comprueba que Escritor Automático esté abierto y que el navegador permita el acceso a la red de bucle invertido/local.");
  };
  socket.onclose = event => {
    if (bridgeSocket === socket) bridgeSocket = null;
    bridgeAuthenticated = false;
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    if (event.code === 1008) {
      manuallyDisconnected = true;
      const reason = String(event.reason || "");
      if (/already connected/i.test(reason)) {
        setStatus("Ya hay otra pestaña de conexión enlazada con la aplicación. Cierra la pestaña duplicada y conserva una sola conexión.");
      } else {
        setStatus(`Conexión rechazada (${reason || "autenticación o permisos"}). Revisa el código de vinculación y vuelve a pulsar Conectar.`);
      }
      return;
    }
    if (manuallyDisconnected) {
      setStatus("Conexión cerrada. Pulsa Conectar cuando quieras volver a enlazar la extensión.");
      return;
    }
    setStatus("La conexión se interrumpió. Intentando reconectar…");
    scheduleReconnect();
  };
}

connectButton.addEventListener("click", () => {
  userStartedConnection = true;
  manuallyDisconnected = false;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = null;
  openSocket();
});

disconnectButton.addEventListener("click", () => {
  manuallyDisconnected = true;
  userStartedConnection = false;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = null;
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = null;
  try { bridgeSocket?.close(1000, "User disconnected"); } catch (_error) { /* ignore */ }
  bridgeSocket = null;
  bridgeAuthenticated = false;
  setStatus("Conexión cerrada. Pulsa Conectar cuando quieras volver a enlazar la extensión.");
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "bridge_outgoing") {
    const ok = sendToSocket(message.payload);
    try { sendResponse({ ok }); } catch (_error) { /* ignore */ }
    return false;
  }
  if (message?.type === "bridge_status_request") {
    try { sendResponse({ connected: bridgeAuthenticated }); } catch (_error) { /* ignore */ }
    return false;
  }
  if (message?.type === "bridge_pairing_updated") {
    manuallyDisconnected = true;
    userStartedConnection = true;
    try { bridgeSocket?.close(1000, "Pairing code updated"); } catch (_error) { /* ignore */ }
    bridgeSocket = null;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      manuallyDisconnected = false;
      openSocket();
    }, 300);
    setStatus("Código actualizado. Volviendo a autenticar la conexión…");
    try { sendResponse({ ok: true }); } catch (_error) { /* ignore */ }
    return false;
  }
  if (message?.type === "bridge_permissions_updated" && bridgeAuthenticated) {
    sendToSocket({ type: "refresh_tabs", force: true });
  }
});

setStatus("Listo para conectar. Abre Escritor Automático, guarda el código de vinculación y pulsa Conectar.");
