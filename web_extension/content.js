(() => {
  // Prevent duplicate listeners when the service worker injects this script into an already loaded tab.
  if (globalThis.__escritorAutomaticoWebBridgeLoaded) return;
  globalThis.__escritorAutomaticoWebBridgeLoaded = true;

  const elementIds = new WeakMap();
  const elementsById = new Map();
  const jobs = new Map();
  let nextElementId = 1;

  function getVisibleRect(element) {
    if (!(element instanceof Element) || !element.isConnected) return null;
    if (element.getAttribute("aria-hidden") === "true") return null;
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") return null;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 ? rect : null;
  }

  function isVisible(element) {
    return getVisibleRect(element) !== null;
  }

  function compact(value, max = 90) {
    const clean = String(value || "").replace(/\s+/g, " ").trim();
    return clean.length > max ? clean.slice(0, max - 1) + "…" : clean;
  }

  function associatedLabel(el) {
    const aria = el.getAttribute("aria-label");
    if (aria) return aria;
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const text = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText || "").join(" ").trim();
      if (text) return text;
    }
    const id = el.id;
    if (id) {
      try {
        const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
        if (label?.innerText) return label.innerText;
      } catch (_error) { /* invalid selector; continue */ }
    }
    const parentLabel = el.closest("label");
    if (parentLabel?.innerText) return parentLabel.innerText;
    const title = el.getAttribute("title");
    if (title) return title;
    const name = el.getAttribute("name");
    if (name) return name;
    return el.id || "";
  }

  function editableKind(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === "textarea") return "textarea";
    if (tag === "input") return `input:${(el.getAttribute("type") || "text").toLowerCase()}`;
    if (el.isContentEditable || el.getAttribute("contenteditable") === "true" || el.getAttribute("role") === "textbox") return "editor";
    return "campo";
  }

  // Fast eligibility test without layout reads. Called for every character.
  // Keep computed style / bounding-box checks in isAllowedEditable, which is used
  // only at selection time and periodically during long jobs.
  function isWritableTarget(el) {
    if (!(el instanceof HTMLElement) || !el.isConnected) return false;
    if (el.matches("input,textarea")) {
      if (el.disabled || el.readOnly) return false;
      const type = (el.getAttribute("type") || "text").toLowerCase();
      return ["text", "search", "url", "email", "tel", "number"].includes(type);
    }
    return el.isContentEditable || el.getAttribute("contenteditable") === "true" ||
      el.getAttribute("contenteditable") === "" ||
      (el.getAttribute("role") === "textbox" && el.getAttribute("aria-readonly") !== "true");
  }

  function isAllowedEditable(el) {
    return isWritableTarget(el) && isVisible(el);
  }

  function scanFields() {
    elementsById.clear();
    const selector = 'input:not([type="password"]):not([type="hidden"]):not([type="button"]):not([type="submit"]):not([type="reset"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]), textarea, [contenteditable="true"], [contenteditable=""], [role="textbox"]';
    const fields = [];
    for (const el of document.querySelectorAll(selector)) {
      // Check writability before asking the browser for computed style/layout.
      if (!isWritableTarget(el)) continue;
      const rect = getVisibleRect(el);
      if (!rect) continue;
      let fieldId = elementIds.get(el);
      if (!fieldId) {
        fieldId = `field-${nextElementId++}-${Math.random().toString(36).slice(2, 7)}`;
        elementIds.set(el, fieldId);
      }
      elementsById.set(fieldId, el);
      const tag = el.tagName.toLowerCase();
      fields.push({
        fieldId,
        kind: editableKind(el),
        tag,
        label: compact(associatedLabel(el)),
        placeholder: compact(el.getAttribute("placeholder")),
        name: compact(el.getAttribute("name")),
        id: compact(el.id),
        type: compact(el.getAttribute("type")),
        multiline: tag === "textarea" || el.isContentEditable || el.getAttribute("contenteditable") === "true",
        rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height), viewportWidth: window.innerWidth, viewportHeight: window.innerHeight }
      });
      if (fields.length >= 150) break;
    }
    return fields;
  }

  function notify(message) {
    try { chrome.runtime.sendMessage(message, () => void chrome.runtime.lastError); } catch (_error) { /* extension may be unloading */ }
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function findRangeInTarget(target) {
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      const current = selection.getRangeAt(0);
      if (target.contains(current.startContainer) && target.contains(current.endContainer)) return current;
    }
    const range = document.createRange();
    range.selectNodeContents(target);
    range.collapse(false);
    return range;
  }

  function dispatchInput(target, data, inputType = "insertText") {
    try {
      target.dispatchEvent(new InputEvent("input", {
        bubbles: true, composed: true, inputType, data
      }));
    } catch (_error) {
      target.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    }
  }

  function insertIntoInput(target, character) {
    const tag = target.tagName.toLowerCase();
    const oldValue = target.value;
    const canSelect = typeof target.selectionStart === "number" && typeof target.selectionEnd === "number";
    const start = canSelect ? target.selectionStart : oldValue.length;
    const end = canSelect ? target.selectionEnd : start;
    let insert = character;
    if (tag === "input" && /[\r\n]/.test(insert)) insert = " ";
    if (insert === "\t") insert = "    ";
    const newValue = oldValue.slice(0, start) + insert + oldValue.slice(end);
    const prototype = tag === "textarea" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    if (setter) setter.call(target, newValue); else target.value = newValue;
    if (canSelect) {
      try { target.setSelectionRange(start + insert.length, start + insert.length); } catch (_error) { /* number input may not support it */ }
    }
    dispatchInput(target, insert, "insertText");
    return true;
  }

  function insertIntoContentEditable(target, character) {
    // The target is focused once at job start. Re-focusing for every character
    // fires redundant focus events and slows down frameworks with heavy handlers.
    const selection = window.getSelection();
    let range = findRangeInTarget(target);
    if (!selection || !selection.rangeCount || !target.contains(selection.anchorNode)) {
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
    if (character === "\n") {
      try {
        if (document.execCommand("insertParagraph", false, null)) return true;
      } catch (_error) { /* direct DOM fallback below */ }
      range = findRangeInTarget(target);
      range.deleteContents();
      const br = document.createElement("br");
      range.insertNode(br);
      range.setStartAfter(br);
      range.collapse(true);
      selection?.removeAllRanges();
      selection?.addRange(range);
      dispatchInput(target, "\n", "insertParagraph");
      return true;
    }
    try {
      if (document.execCommand("insertText", false, character)) return true;
    } catch (_error) { /* direct DOM fallback below */ }
    range = findRangeInTarget(target);
    range.deleteContents();
    const textNode = document.createTextNode(character === "\t" ? "    " : character);
    range.insertNode(textNode);
    range.setStartAfter(textNode);
    range.collapse(true);
    selection?.removeAllRanges();
    selection?.addRange(range);
    dispatchInput(target, character, "insertText");
    return true;
  }

  function insertCharacter(target, character, tabsAsSpaces) {
    // Avoid computed-style and layout queries for every keystroke. A full
    // visibility/editability check is performed periodically in runJob instead.
    if (!isWritableTarget(target)) throw new Error("El campo seleccionado ya no está disponible o dejó de ser editable.");
    if (target.matches("input,textarea")) {
      const char = character === "\t" && tabsAsSpaces ? "    " : character;
      return insertIntoInput(target, char);
    }
    return insertIntoContentEditable(target, character === "\t" && tabsAsSpaces ? "    " : character);
  }

  async function runJob(message) {
    const { job_id: jobId, field_id: fieldId, speed, text, tabs_as_spaces: tabsAsSpaces } = message;
    const target = elementsById.get(fieldId);
    if (!target || !target.isConnected) {
      notify({ type: "job_error", job_id: jobId, error: "El campo ya no existe. Pulsa 'Actualizar páginas' para detectarlo de nuevo." });
      return;
    }
    const job = { cancelled: false, paused: Boolean(message.start_paused) };
    jobs.set(jobId, job);
    const textValue = String(text ?? "");
    // Count Unicode code points without retaining a second array the size of the
    // document. This reduces peak memory noticeably for long texts.
    let total = 0;
    for (const _character of textValue) total += 1;
    const interval = 1000 / Math.max(1, Math.min(240, Number(speed) || 8));
    let sent = 0;
    let lastProgress = 0;
    // Control de ritmo por reloj monotónico: el coste de insertar un carácter
    // no se suma íntegramente al intervalo y tampoco se recuperan pausas en ráfaga.
    let nextDeadline = performance.now();
    try {
      // Keep a caret/selection already placed in the target field. If the target
      // was not focused, use the end as a predictable default for background writing.
      if (target.matches("input,textarea")) {
        const wasFocused = document.activeElement === target;
        const previousStart = typeof target.selectionStart === "number" ? target.selectionStart : null;
        const previousEnd = typeof target.selectionEnd === "number" ? target.selectionEnd : null;
        target.focus({ preventScroll: true });
        if (!wasFocused) {
          const end = String(target.value || "").length;
          try { target.setSelectionRange(end, end); } catch (_error) { /* unsupported input type */ }
        } else if (previousStart !== null && previousEnd !== null) {
          try { target.setSelectionRange(previousStart, previousEnd); } catch (_error) { /* unsupported input type */ }
        }
      } else {
        const selection = window.getSelection();
        const selectionInside = selection && selection.rangeCount && target.contains(selection.anchorNode);
        target.focus({ preventScroll: true });
        if (!selectionInside) {
          const range = document.createRange();
          range.selectNodeContents(target);
          range.collapse(false);
          selection?.removeAllRanges();
          selection?.addRange(range);
        }
      }
      notify({ type: "web_progress", job_id: jobId, sent: 0, total, status: "started" });
      for (const character of textValue) {
        if (job.cancelled) break;
        let resumedFromPause = false;
        while (job.paused && !job.cancelled) {
          resumedFromPause = true;
          await sleep(50);
        }
        if (job.cancelled) break;
        if (resumedFromPause) nextDeadline = performance.now();
        // Check visibility/geometry every 64 characters instead of on each one;
        // this catches a removed/hidden target without forcing frequent layout.
        if ((sent & 63) === 0 && !isAllowedEditable(target)) {
          throw new Error("El campo dejó de estar visible o editable. Vuelve a seleccionarlo e inténtalo de nuevo.");
        }
        insertCharacter(target, character, tabsAsSpaces);
        sent += 1;
        const now = performance.now();
        if (sent === total || now - lastProgress >= 200) {
          notify({ type: "web_progress", job_id: jobId, sent, total, status: "typing" });
          lastProgress = now;
        }
        if (sent < total) {
          nextDeadline += interval;
          const delay = nextDeadline - performance.now();
          if (delay > 0) await sleep(delay);
          else nextDeadline = performance.now();
        }
      }
      if (job.cancelled) notify({ type: "job_done", job_id: jobId, sent, total, stopped: true });
      else notify({ type: "job_done", job_id: jobId, sent, total, stopped: false });
    } catch (error) {
      notify({ type: "job_error", job_id: jobId, error: String(error?.message || error) });
    } finally {
      jobs.delete(jobId);
    }
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "scan_fields") {
      sendResponse({ fields: scanFields(), title: document.title, url: location.href });
      return false;
    }
    if (message?.type === "start_job") {
      const target = elementsById.get(String(message.field_id));
      if (!target || !target.isConnected || !isAllowedEditable(target)) {
        sendResponse({ accepted: false, error: "El campo ya no está disponible. Vuelve a escanear la página." });
        return false;
      }
      const jobId = String(message.job_id);
      if (jobs.has(jobId)) {
        sendResponse({ accepted: false, error: "La tarea ya se está ejecutando." });
        return false;
      }
      sendResponse({ accepted: true });
      void runJob(message);
      return false;
    }
    if (message?.type === "control_job") {
      const job = jobs.get(String(message.job_id));
      if (job) {
        if (message.action === "pause") job.paused = true;
        else if (message.action === "resume") job.paused = false;
        else if (message.action === "stop") { job.cancelled = true; job.paused = false; }
      }
      sendResponse({ ok: true, found: Boolean(job) });
      return false;
    }
    return false;
  });
})();
