const statusEl = document.getElementById("status");
const pairingInput = document.getElementById("pairingCode");

async function updatePermissionStatus() {
  const permitted = await chrome.permissions.contains({
    permissions: ["tabs", "scripting", "webNavigation"],
    origins: ["http://*/*", "https://*/*"]
  });
  if (!permitted) {
    statusEl.textContent = "Vincula la extensión y concede acceso a los sitios web que quieras utilizar.";
  }
}

document.getElementById("savePairing").addEventListener("click", async () => {
  const code = pairingInput.value.trim();
  if (code.length < 40 || code.length > 64) {
    statusEl.textContent = "El código no tiene el formato esperado. Cópialo de nuevo desde Escritor Automático.";
    return;
  }
  try {
    await chrome.storage.local.set({ bridgePairingCode: code });
    const response = await chrome.runtime.sendMessage({ type: "extension_pairing_updated" });
    statusEl.textContent = response?.ok
      ? "Código guardado. Esperando autenticación con Escritor Automático…"
      : "Código guardado. Comprueba que Escritor Automático esté abierto y vuelve a intentar.";
  } catch (error) {
    statusEl.textContent = `No se pudo guardar el código: ${String(error?.message || error)}`;
  }
});

document.getElementById("grantPermissions").addEventListener("click", () => {
  chrome.permissions.request({
    permissions: ["tabs", "scripting", "webNavigation"],
    origins: ["http://*/*", "https://*/*"]
  }, granted => {
    if (chrome.runtime.lastError) {
      statusEl.textContent = `No se pudieron solicitar permisos: ${chrome.runtime.lastError.message}`;
      return;
    }
    statusEl.textContent = granted
      ? "Permisos concedidos. Conectando con Escritor Automático…"
      : "No se concedieron permisos. La extensión no escaneará pestañas.";
    if (granted) chrome.runtime.sendMessage({ type: "extension_pairing_updated" });
  });
});

document.getElementById("refresh").addEventListener("click", async () => {
  const permitted = await chrome.permissions.contains({
    permissions: ["tabs", "scripting"],
    origins: ["http://*/*", "https://*/*"]
  });
  if (!permitted) {
    statusEl.textContent = "Primero pulsa 'Permitir acceso a páginas' y acepta los permisos del navegador.";
    return;
  }
  try {
    const response = await chrome.runtime.sendMessage({ type: "extension_popup_refresh" });
    statusEl.textContent = response?.ok
      ? "Solicitud enviada. Revisa la pestaña Escritura del programa Python."
      : "No hay una conexión autenticada. Comprueba el código de vinculación y que el programa esté abierto.";
  } catch (error) {
    statusEl.textContent = `No se pudo sincronizar: ${String(error?.message || error)}`;
  }
});

chrome.storage.local.get("bridgePairingCode", result => {
  if (result.bridgePairingCode) pairingInput.value = result.bridgePairingCode;
  updatePermissionStatus();
});
