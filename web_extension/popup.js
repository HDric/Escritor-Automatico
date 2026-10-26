const statusEl = document.getElementById("status");
document.getElementById("refresh").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "extension_popup_refresh" }, response => {
    const err = chrome.runtime.lastError;
    if (err || !response?.ok) {
      statusEl.textContent = "No hay conexión con Escritor automático. Abre el programa, entra al modo web y pulsa “Actualizar páginas”. Esto también aplica a Brave.";
    } else {
      statusEl.textContent = "Solicitud enviada. Revisa la pestaña Escritura del programa Python.";
    }
  });
});
chrome.runtime.getPlatformInfo(() => {
  statusEl.textContent = "Extensión activa para Brave/Chrome/Edge. Abre Escritor automático, entra al modo web y pulsa “Actualizar páginas”.";
});
