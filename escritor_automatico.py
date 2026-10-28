"""Escritor Automático multiplataforma para Windows y Linux, con GUI Tkinter.

La aplicación detecta el sistema operativo y selecciona el backend de teclado apropiado.
Algunas funciones (Word COM y escritura en segundo plano Win32) siguen siendo exclusivas
de Windows; Linux permite escritura en primer plano y uso del puente web en escritorios compatibles.
"""
from __future__ import annotations

import ctypes
import html
import importlib
import json
import math
import os
import platform
import queue
import shutil
import subprocess
import re
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from html.parser import HTMLParser
from pathlib import Path
from updater import APP_VERSION, UpdateError, UpdateManager

# python-docx se importa de forma diferida: no ralentiza el inicio si el usuario
# solo quiere escribir texto o usar el editor básico.
APP_NAME = f"Escritor automático v{APP_VERSION} — detección Windows/Linux"
WEB_EXTENSION_ID = "gokleoeeegcjpahldnbmepeeokjafodl"
SYSTEM_NAME = platform.system()
IS_WINDOWS = SYSTEM_NAME == "Windows" or sys.platform == "win32"
IS_LINUX = SYSTEM_NAME == "Linux" or sys.platform.startswith("linux")
IS_SUPPORTED_OS = IS_WINDOWS or IS_LINUX
LINUX_SESSION_TYPE = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()

def detect_system_label() -> str:
    """Devuelve una etiqueta legible y segura del sistema operativo detectado."""
    if IS_WINDOWS:
        version = platform.release() or ""
        return f"Windows {version}".strip()
    if IS_LINUX:
        distro = "Linux"
        try:
            distro = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
        except (AttributeError, OSError, ValueError):
            pass
        session = LINUX_SESSION_TYPE
        if not session:
            session = "Wayland" if os.environ.get("WAYLAND_DISPLAY") else ("X11" if os.environ.get("DISPLAY") else "sesión gráfica no detectada")
        return f"{distro} · sesión {session}"
    return f"Sistema no validado ({SYSTEM_NAME or sys.platform})"

PLATFORM_LABEL = detect_system_label()


# -------- Simulación de teclado de Windows (sin dependencias externas) --------
class WindowsKeyboard:
    """Envía pulsaciones Unicode usando SendInput de Windows."""
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    INPUT_KEYBOARD = 1
    VK_RETURN = 0x0D
    VK_TAB = 0x09
    VK_CONTROL = 0x11
    VK_V = 0x56

    def __init__(self):
        if not IS_WINDOWS:
            raise OSError("La escritura automática de esta versión requiere Windows 10/11.")
        from ctypes import wintypes
        self.ct = ctypes
        self.wintypes = wintypes
        self.ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", self.ULONG_PTR)]
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", self.ULONG_PTR)]
        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]
        class INPUTUNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
        class INPUT(ctypes.Structure):
            _anonymous_ = ("union",)
            _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]
        self.INPUT = INPUT
        self.KEYBDINPUT = KEYBDINPUT
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT

    def _send_many(self, events):
        """Envía un lote de eventos de teclado con una sola llamada al sistema."""
        if not events:
            return
        inputs = (self.INPUT * len(events))()
        for index, (vk, scan, flags) in enumerate(events):
            item = self.INPUT()
            item.type = self.INPUT_KEYBOARD
            item.ki = self.KEYBDINPUT(vk, scan, flags, 0, 0)
            inputs[index] = item
        sent = self.user32.SendInput(len(inputs), inputs, ctypes.sizeof(self.INPUT))
        if sent != len(inputs):
            raise ctypes.WinError(ctypes.get_last_error())

    def _send(self, vk=0, scan=0, flags=0):
        self._send_many([(vk, scan, flags)])

    def virtual_key(self, vk: int):
        self._send_many([(vk, 0, 0), (vk, 0, self.KEYEVENTF_KEYUP)])

    def unicode_char(self, char: str):
        # Envía pulsación y liberación en una sola llamada a SendInput.
        # Reduce las llamadas al sistema a la mitad por unidad UTF-16 sin
        # cambiar el comportamiento ni eliminar caracteres Unicode/emoji.
        encoded = char.encode("utf-16-le", errors="surrogatepass")
        units = [int.from_bytes(encoded[pos:pos + 2], "little")
                 for pos in range(0, len(encoded), 2)]
        inputs = (self.INPUT * (len(units) * 2))()
        idx = 0
        for unit in units:
            down = self.INPUT()
            down.type = self.INPUT_KEYBOARD
            down.ki = self.KEYBDINPUT(0, unit, self.KEYEVENTF_UNICODE, 0, 0)
            up = self.INPUT()
            up.type = self.INPUT_KEYBOARD
            up.ki = self.KEYBDINPUT(0, unit, self.KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP, 0, 0)
            inputs[idx] = down
            inputs[idx + 1] = up
            idx += 2
        sent = self.user32.SendInput(len(inputs), inputs, ctypes.sizeof(self.INPUT))
        if sent != len(inputs):
            raise ctypes.WinError(ctypes.get_last_error())

    def type_char(self, char: str, tabs_as_spaces: bool):
        if char == "\n":
            self.virtual_key(0x0D)
        elif char == "\t" and tabs_as_spaces:
            for _ in range(4):
                self.unicode_char(" ")
        elif char == "\t":
            self.virtual_key(self.VK_TAB)
        elif char == "\r":
            return
        else:
            self.unicode_char(char)

    def paste(self):
        self._send_many([
            (self.VK_CONTROL, 0, 0),
            (self.VK_V, 0, 0),
            (self.VK_V, 0, self.KEYEVENTF_KEYUP),
            (self.VK_CONTROL, 0, self.KEYEVENTF_KEYUP),
        ])


class LinuxKeyboard:
    """Envía pulsaciones en Linux mediante pynput (principalmente X11/XWayland).

    Wayland puede restringir la inyección global de teclas por diseño; en ese caso
    las aplicaciones nativas pueden no recibir los eventos. No se usan privilegios root.
    """
    def __init__(self):
        if not IS_LINUX:
            raise OSError("El backend pynput de esta aplicación está reservado para Linux.")
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise RuntimeError(
                "No se detectó una sesión gráfica Linux (DISPLAY/WAYLAND_DISPLAY). "
                "Ejecuta Escritor Automático desde el escritorio, no desde una terminal SSH sin entorno gráfico."
            )
        try:
            pynput_keyboard = importlib.import_module("pynput.keyboard")
            self._keyboard = pynput_keyboard.Controller()
            self._key = pynput_keyboard.Key
        except Exception as exc:
            detail = str(exc)
            if LINUX_SESSION_TYPE == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
                hint = " En Wayland, la inyección de teclas puede estar limitada; prueba una sesión X11/Xorg si no funciona."
            else:
                hint = " Comprueba que X11/XWayland esté disponible y que pynput esté instalado."
            raise RuntimeError("No se pudo inicializar el teclado de Linux: " + detail + hint) from exc

    def _tap(self, key):
        self._keyboard.press(key)
        self._keyboard.release(key)

    def virtual_key(self, vk: int):
        mapping = {0x0D: self._key.enter, 0x09: self._key.tab, 0x11: self._key.ctrl_l, 0x56: "v"}
        key = mapping.get(vk)
        if key is None:
            raise ValueError(f"Tecla virtual no compatible con Linux: {vk}")
        self._tap(key)

    def unicode_char(self, char: str):
        self._keyboard.type(char)

    def type_char(self, char: str, tabs_as_spaces: bool):
        if char == "\n":
            self._tap(self._key.enter)
        elif char == "\t" and tabs_as_spaces:
            self._keyboard.type("    ")
        elif char == "\t":
            self._tap(self._key.tab)
        elif char == "\r":
            return
        else:
            try:
                self._keyboard.type(char)
            except Exception as exc:
                raise RuntimeError(
                    f"Linux no pudo inyectar el carácter {char!r}. En X11 se admiten más caracteres; "
                    "Wayland o la distribución de teclado pueden limitar algunos símbolos."
                ) from exc

    def paste(self):
        with self._keyboard.pressed(self._key.ctrl_l):
            self._keyboard.press("v")
            self._keyboard.release("v")


def create_keyboard_backend():
    """Selecciona el backend de teclado del sistema detectado."""
    if IS_WINDOWS:
        return WindowsKeyboard()
    if IS_LINUX:
        return LinuxKeyboard()
    raise OSError(f"Sistema no compatible para entrada de teclado: {SYSTEM_NAME or sys.platform}.")


# -------- Puente seguro local para extensión Chromium (Chrome/Edge/Brave) --------
class WebPageBridge:
    """Servidor WebSocket solo en loopback para comunicarse con la extensión Chromium.

    No acepta conexiones desde páginas web normales: el origen debe ser la extensión esperada.
    La extensión comunica metadatos/campos al programa, pero no envía al programa el texto
    preexistente de los campos. El contenido del campo puede manipularse localmente al insertar.
    """
    HOST = "127.0.0.1"
    PORT = 8765
    MAX_MESSAGE_BYTES = 8 * 1024 * 1024
    MAX_PREVIEW_DATA_URL_CHARS = 7_500_000
    MAX_TABS = 120
    MAX_FIELDS_PER_TAB = 150
    ALLOWED_INBOUND_TYPES = frozenset({
        "hello", "heartbeat", "tabs_result", "tabs_error", "preview_image",
        "preview_error", "job_accepted", "job_error", "web_progress", "job_done",
    })

    def __init__(self):
        self.events: queue.Queue = queue.Queue(maxsize=30)
        self._lock = threading.RLock()
        self._clients: dict[str, dict] = {}
        self._server = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self.error: str | None = None

    def _emit(self, event: dict) -> None:
        """Queue bridge events without allowing a stalled GUI to grow memory forever."""
        try:
            self.events.put_nowait(event)
        except queue.Full:
            # The UI polls frequently; saturated queues are treated as a dropped status update.
            pass

    @staticmethod
    def _bounded_string(value, maximum: int, allow_empty: bool = True) -> bool:
        return isinstance(value, str) and len(value) <= maximum and (allow_empty or bool(value))

    @classmethod
    def _valid_fields(cls, fields) -> bool:
        if not isinstance(fields, list) or len(fields) > cls.MAX_FIELDS_PER_TAB:
            return False
        string_limits = {
            "fieldId": 128, "kind": 48, "tag": 24, "label": 180,
            "placeholder": 180, "name": 180, "id": 180, "type": 48,
        }
        rect_keys = ("x", "y", "width", "height", "viewportWidth", "viewportHeight")
        for field in fields:
            if not isinstance(field, dict):
                return False
            for key, limit in string_limits.items():
                if key in field and not cls._bounded_string(field[key], limit):
                    return False
            rect = field.get("rect", {})
            if not isinstance(rect, dict):
                return False
            for key in rect_keys:
                value = rect.get(key)
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                if abs(value) > 100_000 or not math.isfinite(value):
                    return False
        return True

    @classmethod
    def _valid_inbound_message(cls, message: dict) -> bool:
        kind = message.get("type")
        if not isinstance(kind, str) or kind not in cls.ALLOWED_INBOUND_TYPES:
            return False
        if kind == "hello":
            return cls._bounded_string(message.get("browser", "Chromium"), 80) and cls._bounded_string(message.get("version", ""), 40)
        if kind == "heartbeat":
            stamp = message.get("timestamp")
            return isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and abs(stamp) <= 10**16 and math.isfinite(stamp)
        if kind == "tabs_result":
            tabs = message.get("tabs")
            if not isinstance(tabs, list) or len(tabs) > cls.MAX_TABS:
                return False
            if not cls._bounded_string(message.get("browser", "Chromium"), 80):
                return False
            for tab in tabs:
                if not isinstance(tab, dict) or isinstance(tab.get("tabId"), bool) or not isinstance(tab.get("tabId"), int):
                    return False
                if not cls._bounded_string(tab.get("title", ""), 512) or not cls._bounded_string(tab.get("url", ""), 2048):
                    return False
                fields = tab.get("fields", [])
                if not cls._valid_fields(fields):
                    return False
            return True
        if kind in ("tabs_error", "preview_error", "job_error"):
            return cls._bounded_string(message.get("error", ""), 1200)
        if kind == "preview_image":
            data_url = message.get("data_url")
            if not isinstance(data_url, str) or len(data_url) > cls.MAX_PREVIEW_DATA_URL_CHARS:
                return False
            if not data_url.startswith("data:image/jpeg;base64,"):
                return False
            if not cls._bounded_string(message.get("request_id", ""), 128) or not cls._bounded_string(message.get("client_id", ""), 64):
                return False
            if not cls._bounded_string(message.get("title", ""), 512) or not cls._bounded_string(message.get("url", ""), 2048):
                return False
            if not cls._bounded_string(message.get("selected_field_id", ""), 128):
                return False
            if not cls._valid_fields(message.get("fields", [])):
                return False
            return isinstance(message.get("tab_id"), int) and not isinstance(message.get("tab_id"), bool)
        if kind in ("job_accepted", "job_done", "web_progress"):
            job_id = message.get("job_id")
            if not cls._bounded_string(job_id, 128, allow_empty=False):
                return False
            if kind == "web_progress":
                sent, total = message.get("sent", 0), message.get("total", 0)
                return all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 10_000_000 for v in (sent, total))
            if kind == "job_done":
                return isinstance(message.get("stopped", False), bool)
            return True
        return False

    def start(self):
        if self._thread and self._thread.is_alive():
            if self.error:
                raise RuntimeError(self.error)
            return
        self._thread = threading.Thread(target=self._serve, daemon=True, name="web-extension-bridge")
        self._thread.start()
        if not self._ready.wait(3):
            raise RuntimeError("El puente del navegador no respondió a tiempo.")
        if self.error:
            raise RuntimeError(self.error)

    def _serve(self):
        try:
            from websockets.sync.server import serve
            # Restringe el puente a la extensión incluida con este paquete, compatible con navegadores Chromium.
            # Su ID se fija mediante la clave pública incluida en manifest.json.
            allowed_origins = [f"chrome-extension://{WEB_EXTENSION_ID}"]
            with serve(
                self._handle_client, self.HOST, self.PORT,
                origins=allowed_origins, max_size=self.MAX_MESSAGE_BYTES,
                max_queue=4, compression=None,
                open_timeout=5, close_timeout=2, ping_interval=20, ping_timeout=20,
            ) as server:
                self._server = server
                self._ready.set()
                server.serve_forever()
        except Exception as exc:
            self.error = (
                f"No se pudo iniciar el puente web en {self.HOST}:{self.PORT}. "
                f"Comprueba que websockets esté instalado y que el puerto esté libre. Detalle: {exc}"
            )
            self._ready.set()
            self._emit({"event": "bridge_error", "error": self.error})

    def _handle_client(self, websocket):
        client_id = uuid.uuid4().hex
        with self._lock:
            self._clients[client_id] = {"ws": websocket, "lock": threading.Lock(), "browser": "Chromium"}
        self._emit({"event": "connected", "client_id": client_id})
        recent_messages = deque()
        try:
            for raw in websocket:
                # The websocket limit also applies at the protocol layer; this is a
                # second guard before JSON parsing and before data reaches Tkinter.
                if not isinstance(raw, str) or len(raw.encode("utf-8", errors="replace")) > self.MAX_MESSAGE_BYTES:
                    continue
                now = time.monotonic()
                while recent_messages and now - recent_messages[0] > 10.0:
                    recent_messages.popleft()
                recent_messages.append(now)
                if len(recent_messages) > 30:
                    try:
                        websocket.close(code=1008, reason="Rate limit exceeded")
                    except Exception:
                        pass
                    break
                try:
                    message = json.loads(raw)
                    if not isinstance(message, dict) or not self._valid_inbound_message(message):
                        continue
                except (ValueError, TypeError, UnicodeError):
                    continue
                self._emit({"event": "message", "client_id": client_id, "data": message})
        except Exception:
            pass
        finally:
            with self._lock:
                self._clients.pop(client_id, None)
            self._emit({"event": "disconnected", "client_id": client_id})

    def clients(self) -> list[str]:
        with self._lock:
            return list(self._clients)

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def send(self, client_id: str, payload: dict) -> bool:
        with self._lock:
            client = self._clients.get(client_id)
        if not client:
            return False
        try:
            with client["lock"]:
                client["ws"].send(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception:
            return False

    def close(self):
        server = self._server
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        with self._lock:
            clients = list(self._clients.values())
        for client in clients:
            try:
                client["ws"].close()
            except Exception:
                pass


# -------- Envío de caracteres a una ventana en segundo plano (Windows) --------
class BackgroundWindowWriter:
    """Publica mensajes WM_CHAR en el control que conserva el foco de una ventana.

    Este mecanismo funciona con controles Win32 compatibles (por ejemplo, algunos
    controles Edit/RichEdit), pero no todos los programas aceptan mensajes sintéticos.
    No puede garantizar escritura en navegador, Discord, juegos ni controles propios.
    """
    WM_CHAR = 0x0102
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    VK_TAB = 0x09

    def __init__(self, target_hwnd: int):
        if not IS_WINDOWS:
            raise OSError("La escritura en segundo plano requiere Windows 10/11.")
        self.target_hwnd = int(target_hwnd)
        from ctypes import wintypes
        self.wintypes = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.IsWindow.argtypes = [wintypes.HWND]
        self.user32.IsWindow.restype = wintypes.BOOL
        self.user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
        self.user32.IsChild.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.PostMessageW.restype = wintypes.BOOL

        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                        ("rcCaret", RECT)]
        self.GUITHREADINFO = GUITHREADINFO
        self.user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
        self.user32.GetGUIThreadInfo.restype = wintypes.BOOL
        self.control_hwnd = None

    @staticmethod
    def _as_int(handle):
        if handle is None:
            return 0
        return int(handle if isinstance(handle, int) else (handle.value or 0))

    def resolve_control(self) -> int:
        """Obtiene el control enfocado dentro de la ventana seleccionada, si existe."""
        if not self.user32.IsWindow(self.target_hwnd):
            raise RuntimeError("La ventana seleccionada ya no existe. Actualiza la lista de ventanas.")
        pid = self.wintypes.DWORD()
        thread_id = self.user32.GetWindowThreadProcessId(self.target_hwnd, ctypes.byref(pid))
        info = self.GUITHREADINFO()
        info.cbSize = ctypes.sizeof(self.GUITHREADINFO)
        if thread_id and self.user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            focus_hwnd = self._as_int(info.hwndFocus)
            if focus_hwnd and self.user32.IsWindow(focus_hwnd):
                if focus_hwnd == self.target_hwnd or self.user32.IsChild(self.target_hwnd, focus_hwnd):
                    self.control_hwnd = focus_hwnd
                    return focus_hwnd
        # Algunos programas aceptan WM_CHAR directamente en la ventana principal.
        self.control_hwnd = self.target_hwnd
        return self.target_hwnd

    def _post(self, message: int, wparam: int, lparam: int = 1):
        hwnd = self.control_hwnd or self.target_hwnd
        if not self.user32.IsWindow(hwnd):
            raise RuntimeError("El control de destino dejó de existir durante la escritura.")
        ok = self.user32.PostMessageW(hwnd, message, wparam, lparam)
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

    def _unicode_char(self, char: str):
        # WM_CHAR recibe unidades UTF-16; los caracteres fuera del BMP se envían como pareja.
        encoded = char.encode("utf-16-le", errors="surrogatepass")
        for pos in range(0, len(encoded), 2):
            unit = int.from_bytes(encoded[pos:pos + 2], "little")
            self._post(self.WM_CHAR, unit, 1)

    def type_char(self, char: str, tabs_as_spaces: bool):
        if char == "\r":
            return
        if char == "\n":
            # Los controles de edición Win32 interpretan CR como retorno de línea.
            self._unicode_char("\r")
        elif char == "\t" and tabs_as_spaces:
            for _ in range(4):
                self._unicode_char(" ")
        elif char == "\t":
            self._post(self.WM_KEYDOWN, self.VK_TAB, 1)
            self._post(self.WM_KEYUP, self.VK_TAB, 0xC0000001)
        else:
            self._unicode_char(char)


# -------- Automatización de Microsoft Word en segundo plano (COM) --------
class WordAutomationWriter:
    """Escribe carácter por carácter en el documento de Word abierto, aunque esté detrás de otra ventana.

    Requiere Microsoft Word de escritorio y pywin32. No activa ni trae Word al frente.
    La posición de inserción es la selección/cursor que quedó en Word al terminar la cuenta regresiva.
    """
    def __init__(self):
        self.pythoncom = None
        self.word = None
        self.selection = None
        self.document = None
        # Cachés: COM es relativamente costoso, por lo que el formato solo se
        # vuelve a aplicar cuando cambia entre segmentos o párrafos.
        self._last_style: dict | None = None
        self._last_paragraph_style: dict | None = None

    def initialize(self, page_setup: dict | None = None):
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError(
                "El modo Word requiere pywin32. Cierra el programa y ejecuta "
                "instalar_dependencias.bat; después vuelve a abrirlo."
            ) from exc
        pythoncom.CoInitialize()
        self.pythoncom = pythoncom
        try:
            self.word = win32com.client.GetActiveObject("Word.Application")
        except Exception as exc:
            raise RuntimeError(
                "No encuentro Microsoft Word abierto. Abre Word, deja abierto el documento "
                "de destino y vuelve a intentarlo."
            ) from exc
        try:
            if self.word.Documents.Count < 1:
                raise RuntimeError("Abre un documento en Word antes de iniciar la escritura.")
            self.selection = self.word.Selection
            self.document = self.selection.Document
            if page_setup:
                self.apply_page_setup(page_setup)
        except Exception:
            self.cleanup()
            raise

    def apply_page_setup(self, page_setup: dict):
        """Aplica márgenes/tamaño de página importados o elegidos en la interfaz.

        En Word, los márgenes pertenecen a una sección completa, no a un párrafo.
        Por eso este ajuste se aplica a la sección donde está el cursor.
        """
        if not page_setup or self.selection is None:
            return
        try:
            section = self.selection.Range.Sections(1)
        except Exception:
            section = self.document.Sections(1)
        setup = section.PageSetup
        # Fija primero la orientación: Word puede intercambiar ancho/alto cuando
        # cambia entre vertical y horizontal.
        orientation = page_setup.get("orientation")
        if orientation in (0, 1):
            try:
                setup.Orientation = int(orientation)  # 0 vertical, 1 horizontal en Word
            except Exception:
                pass
        names = {
            "page_width_pt": "PageWidth", "page_height_pt": "PageHeight",
            "top_margin_pt": "TopMargin", "bottom_margin_pt": "BottomMargin",
            "left_margin_pt": "LeftMargin", "right_margin_pt": "RightMargin",
            "gutter_pt": "Gutter", "header_distance_pt": "HeaderDistance",
            "footer_distance_pt": "FooterDistance",
        }
        for key, prop in names.items():
            value = page_setup.get(key)
            if value is not None:
                try:
                    setattr(setup, prop, float(value))
                except Exception:
                    pass

    def apply_paragraph_format(self, meta: dict | None):
        """Aplica formato de párrafo, separado del formato de los caracteres."""
        if self.selection is None or not meta:
            return
        if meta == self._last_paragraph_style:
            return
        pf = self.selection.ParagraphFormat
        scalar_map = {
            "left_indent_pt": "LeftIndent", "right_indent_pt": "RightIndent",
            "first_line_indent_pt": "FirstLineIndent", "space_before_pt": "SpaceBefore",
            "space_after_pt": "SpaceAfter",
        }
        for key, prop in scalar_map.items():
            if key in meta and meta[key] is not None:
                setattr(pf, prop, float(meta[key]))
        alignment = meta.get("alignment")
        if alignment is not None:
            pf.Alignment = {"left": 0, "center": 1, "right": 2, "justify": 3}.get(alignment, 0)
        spacing_type = meta.get("line_spacing_type")
        spacing_value = meta.get("line_spacing_value")
        if spacing_type:
            # WdLineSpacing: Single=0, 1.5=1, Double=2, AtLeast=3, Exactly=4, Multiple=5.
            rules = {"single": 0, "one_point_five": 1, "double": 2,
                     "at_least": 3, "exactly": 4, "multiple": 5}
            pf.LineSpacingRule = rules.get(spacing_type, 0)
            if spacing_type == "multiple" and spacing_value is not None:
                # La automatización COM expresa el interlineado múltiple en puntos.
                # 12 pt es la base convencional usada por Word para LinesToPoints.
                pf.LineSpacing = 12.0 * float(spacing_value)
            elif spacing_type in ("exactly", "at_least") and spacing_value is not None:
                pf.LineSpacing = float(spacing_value)
        for key, prop in (("keep_together", "KeepTogether"),
                          ("keep_with_next", "KeepWithNext"),
                          ("page_break_before", "PageBreakBefore")):
            if key in meta and meta[key] is not None:
                setattr(pf, prop, -1 if meta[key] else 0)
        self._last_paragraph_style = dict(meta)

    def _apply_style(self, style: dict):
        # Los diccionarios de estilo son pequeños; compararlos en Python es mucho
        # más barato que consultar y modificar repetidamente propiedades COM.
        if style == self._last_style:
            return
        font = self.selection.Font
        if style.get("family"):
            font.Name = str(style["family"])
        if style.get("size"):
            font.Size = float(style["size"])
        font.Bold = -1 if style.get("bold") else 0
        font.Italic = -1 if style.get("italic") else 0
        font.Underline = 1 if style.get("underline") else 0
        if style.get("strike"):
            font.StrikeThrough = -1
        else:
            font.StrikeThrough = 0
        color = style.get("color")
        if color and re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)):
            red, green, blue = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            font.Color = red | (green << 8) | (blue << 16)
        else:
            font.Color = -16777216  # wdColorAutomatic
        self._last_style = dict(style)

    def type_soft_break(self):
        """Inserta un salto manual de línea sin crear un párrafo nuevo en Word."""
        if self.selection is None:
            raise RuntimeError("La conexión con Word no está inicializada.")
        # Word representa los saltos manuales como un carácter de control vertical.
        self.selection.TypeText("\v")

    def type_char(self, char: str, tabs_as_spaces: bool, style: dict | None = None):
        if self.selection is None:
            raise RuntimeError("La conexión con Word no está inicializada.")
        if char == "\r":
            return
        if char not in ("\n", "\t") and style:
            self._apply_style(style)
        if char == "\n":
            self.selection.TypeParagraph()
            # Word puede heredar los formatos del párrafo previo. En el siguiente
            # comienzo de párrafo se aplicará el formato importado correspondiente.
            self._last_style = None
            self._last_paragraph_style = None
        elif char == "\t" and tabs_as_spaces:
            self.selection.TypeText("    ")
        elif char == "\t":
            self.selection.TypeText("\t")
        else:
            self.selection.TypeText(char)

    def cleanup(self):
        self.selection = None
        self.document = None
        self.word = None
        self._last_style = None
        self._last_paragraph_style = None
        if self.pythoncom is not None:
            try:
                self.pythoncom.CoUninitialize()
            except Exception:
                pass
            self.pythoncom = None


# -------- Portapapeles HTML enriquecido (Windows) --------
def set_windows_clipboard_html(fragment: str, plain_text: str) -> None:
    """Coloca HTML Format y CF_UNICODETEXT en el portapapeles de Windows."""
    if not IS_WINDOWS:
        # Tkinter fallback: al menos deja el contenido de texto accesible.
        raise OSError("El pegado con formato está disponible en Windows.")
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p

    html_format = user32.RegisterClipboardFormatW("HTML Format")
    fragment = fragment.replace("\r\n", "\n")
    html_prefix = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body><!--StartFragment-->"
    html_suffix = "<!--EndFragment--></body></html>"
    html_doc = html_prefix + fragment + html_suffix
    header_template = (
        "Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\n"
        "StartFragment:{:010d}\r\nEndFragment:{:010d}\r\n"
    )
    blank_header = header_template.format(0, 0, 0, 0).encode("ascii")
    start_html = len(blank_header)
    start_fragment = start_html + len(html_prefix.encode("utf-8"))
    end_fragment = start_fragment + len(fragment.encode("utf-8"))
    end_html = start_html + len(html_doc.encode("utf-8"))
    cf_html = header_template.format(start_html, end_html, start_fragment, end_fragment).encode("ascii") + html_doc.encode("utf-8")
    text_bytes = plain_text.encode("utf-16-le") + b"\x00\x00"

    formats = [(html_format, cf_html), (13, text_bytes)]  # 13 = CF_UNICODETEXT
    if not user32.OpenClipboard(None):
        raise ctypes.WinError(ctypes.get_last_error())
    allocated: list[tuple[int, int]] = []
    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        for fmt, data in formats:
            handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                raise ctypes.WinError(ctypes.get_last_error())
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(fmt, handle):
                kernel32.GlobalFree(handle)
                raise ctypes.WinError(ctypes.get_last_error())
    finally:
        user32.CloseClipboard()


def get_windows_clipboard_html() -> tuple[str, str] | None:
    """Devuelve (documento HTML completo, fragmento HTML) del portapapeles de Windows."""
    if not IS_WINDOWS:
        return None
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    fmt = user32.RegisterClipboardFormatW("HTML Format")
    if not user32.OpenClipboard(None):
        return None
    handle = None
    ptr = None
    try:
        handle = user32.GetClipboardData(fmt)
        if not handle:
            return None
        size = kernel32.GlobalSize(handle)
        if not size:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        raw = ctypes.string_at(ptr, size).rstrip(b"\x00")
        decoded = raw.decode("utf-8", errors="replace")
        def offset(name):
            match = re.search(rf"^{name}:(\d+)", decoded, flags=re.M)
            return int(match.group(1)) if match else None
        start_html, end_html = offset("StartHTML"), offset("EndHTML")
        start_fragment, end_fragment = offset("StartFragment"), offset("EndFragment")
        if start_html is not None and end_html is not None and 0 <= start_html < end_html <= len(raw):
            full_html = raw[start_html:end_html].decode("utf-8", errors="replace")
        else:
            full_html = decoded
        if start_fragment is not None and end_fragment is not None and 0 <= start_fragment < end_fragment <= len(raw):
            fragment = raw[start_fragment:end_fragment].decode("utf-8", errors="replace")
        else:
            fragment = full_html
        return full_html, fragment
    finally:
        if ptr:
            try: kernel32.GlobalUnlock(handle)
            except Exception: pass
        user32.CloseClipboard()


class HtmlImporter(HTMLParser):
    """Importador simple de HTML que conserva texto y formatos en línea básicos."""
    def __init__(self, app, insert_at: str | None = None, class_styles: dict[str, str] | None = None):
        super().__init__(convert_charrefs=True)
        self.app = app
        self.stack: list[dict] = [{}]
        self.pending_space = False
        self.in_pre = False
        self.list_stack: list[tuple[str, int]] = []
        self.ordered_counter = 0
        self.current_paragraph_start: str | None = None
        self.current_paragraph_meta: dict = {}
        self._ignored_tags: list[str] = []
        self.cursor = app.editor.index(insert_at) if insert_at else app.editor.index("end-1c")
        self.class_styles = class_styles or {}

    def _insert(self, text: str) -> tuple[str, str]:
        start = self.app.editor.index(self.cursor)
        if text:
            self.app.editor.insert(start, text)
        end = self.app.editor.index(f"{start}+{len(text)}c")
        self.cursor = end
        return start, end

    def _combined_css(self, attrs: dict) -> str:
        pieces = []
        for class_name in attrs.get("class", "").split():
            css = self.class_styles.get(class_name)
            if css: pieces.append(css)
        if attrs.get("style"): pieces.append(attrs["style"])
        return ";".join(pieces)

    def _style_from_css(self, css: str) -> dict:
        result = {}
        for piece in css.split(";"):
            if ":" not in piece:
                continue
            key, value = piece.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            if key == "font-family": result["family"] = value.split(",", 1)[0].strip("\"' ")
            elif key == "font-size":
                converted = self.app._css_length_to_pt(value)
                if converted is not None:
                    result["size"] = converted
                else:
                    match = re.search(r"([\d.]+)", value)
                    if match: result["size"] = float(match.group(1))
            elif key == "font-weight" and (value == "bold" or (value.isdigit() and int(value) >= 600)): result["bold"] = True
            elif key == "font-style" and value == "italic": result["italic"] = True
            elif key == "text-decoration":
                if "underline" in value: result["underline"] = True
                if "line-through" in value: result["strike"] = True
            elif key == "color": result["color"] = value
        return result

    def _break(self):
        # Usa el cursor de inserción actual para que la importación HTML se pueda
        # hacer al final del editor o en la posición actual del portapapeles.
        try:
            if self.app.editor.compare(self.cursor, "==", "1.0"):
                return
            last = self.app.editor.get(f"{self.cursor}-1c", self.cursor)
        except tk.TclError:
            last = ""
        if last and last != "\n":
            self._insert("\n")

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if self._ignored_tags:
            if tag in ("head", "style", "script", "title"):
                self._ignored_tags.append(tag)
            return
        if tag in ("head", "style", "script", "title"):
            self._ignored_tags.append(tag)
            return
        if tag == "br":
            start, end = self._insert("\n")
            self.app.editor.tag_add(self.app.soft_break_tag, start, end)
            return
        if tag in ("p", "div", "li", "h1", "h2", "h3", "pre"):
            self._break()
            self.current_paragraph_start = self.app.editor.index(self.cursor)
            combined_css = self._combined_css(attrs)
            self.current_paragraph_meta = self.app._paragraph_meta_from_css(combined_css)
            spacing_type = attrs.get("data-line-spacing-type", "").strip().lower()
            if spacing_type in ("single", "one_point_five", "double", "multiple", "exactly", "at_least"):
                self.current_paragraph_meta["line_spacing_type"] = spacing_type
                try:
                    self.current_paragraph_meta["line_spacing_value"] = float(attrs.get("data-line-spacing-value", "1"))
                except (TypeError, ValueError):
                    pass
            for attr, key in (("data-keep-together", "keep_together"),
                              ("data-keep-with-next", "keep_with_next"),
                              ("data-page-break-before", "page_break_before")):
                if attr in attrs:
                    self.current_paragraph_meta[key] = attrs[attr].strip().lower() in ("1", "true", "yes")
            if tag == "li":
                prefix = "• " if not self.list_stack or self.list_stack[-1][0] == "ul" else f"{self.list_stack[-1][1]}. "
                self._insert(prefix)
                if self.list_stack and self.list_stack[-1][0] == "ol":
                    kind, count = self.list_stack[-1]
                    self.list_stack[-1] = (kind, count + 1)
        if tag == "ul": self.list_stack.append(("ul", 0))
        elif tag == "ol": self.list_stack.append(("ol", 1))
        if tag == "pre": self.in_pre = True
        style = {}
        if tag in ("b", "strong"): style["bold"] = True
        elif tag in ("i", "em"): style["italic"] = True
        elif tag == "u": style["underline"] = True
        elif tag == "s" or tag == "strike": style["strike"] = True
        style.update(self._style_from_css(self._combined_css(attrs)))
        combined = dict(self.stack[-1]); combined.update(style)
        self.stack.append(combined)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "br":
            return
        if self._ignored_tags:
            if tag in self._ignored_tags:
                # Cierra el nivel más reciente del bloque que se está ignorando.
                reverse_index = len(self._ignored_tags) - 1 - self._ignored_tags[::-1].index(tag)
                del self._ignored_tags[reverse_index:]
            return
        if len(self.stack) > 1: self.stack.pop()
        if tag in ("p", "div", "li", "h1", "h2", "h3", "pre"):
            self._break()
            if self.current_paragraph_start is not None:
                try:
                    self.app._set_paragraph_meta_range(
                        self.current_paragraph_start, self.app.editor.index(self.cursor),
                        self.current_paragraph_meta, remove_overlap=False
                    )
                except Exception:
                    pass
            self.current_paragraph_start = None
            self.current_paragraph_meta = {}
        if tag == "ul" or tag == "ol":
            if self.list_stack: self.list_stack.pop()
        if tag == "pre": self.in_pre = False

    def handle_data(self, data):
        if self._ignored_tags or not data:
            return
        if not self.in_pre:
            if data.isspace():
                # Conserva un espacio semántico entre spans (común al copiar desde
                # Word), pero ignora la indentación con saltos de línea del HTML.
                try:
                    previous = self.app.editor.get(f"{self.cursor}-1c", self.cursor)
                except tk.TclError:
                    previous = ""
                if self.current_paragraph_start is None or not previous or previous == "\n":
                    return
                data = " "
            else:
                data = re.sub(r"\s+", " ", data)
        self.cursor = self.app.insert_styled(data, self.stack[-1], at_index=self.cursor)


class EscritorAutomatico:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.stop_event = threading.Event()
        self.pause_event = threading.Event(); self.pause_event.set()
        self.worker: threading.Thread | None = None
        self.closing = False
        self.hotkey_thread: threading.Thread | None = None
        self.hotkey_listener = None
        self._pynput_keyboard_module = None
        self.format_tags: dict[str, dict] = {}
        # Búsqueda O(1) de los estilos ya creados en lugar de comparar cada
        # estilo contra todos los anteriores al importar documentos grandes.
        self._style_tag_cache: dict[str, str] = {}
        self.paragraph_tags: dict[str, dict] = {}
        self.paragraph_meta: dict[str, dict] = {}
        self.soft_break_tag = "__soft_break"
        self.imported_page_setup: dict | None = None
        self.page_setup: dict | None = None
        self._active_theme_fonts: dict[str, str] = {"major": "Arial", "minor": "Arial"}
        self._tag_counter = 0
        self._count_update_id = None
        self._startup_tasks_started = False
        self.update_manager = UpdateManager()
        self.update_preferences = self.update_manager.load_preferences()
        self.auto_update_var = tk.BooleanVar(master=root, value=self.update_preferences.get("check_on_start", True))
        self._update_check_running = False
        self._update_download_window = None
        self.web_bridge: WebPageBridge | None = None
        self.web_client_browsers: dict[str, str] = {}
        self.web_tab_map: dict[str, dict] = {}
        self.web_field_map: dict[str, dict] = {}
        self.web_active_target: dict | None = None
        self.web_job_id: str | None = None
        self.web_job_dispatched = False
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        # Mostrar la ventana antes de enumerar otras ventanas y activar el hilo
        # de teclas rápidas; reduce la sensación de demora al arrancar.
        self.root.after(140, self._finish_startup_tasks)
        self.root.after(250, self._poll_web_bridge)
        self.root.after(2800, self._automatic_update_check)

    def _build_ui(self):
        """Construye una interfaz dividida por tareas para reducir la carga visual."""
        # Tema y jerarquía visual coherente. Se conservan los widgets/variables
        # que utiliza el motor de escritura para no alterar la lógica funcional.
        try:
            if "clam" in ttk.Style(self.root).theme_names():
                ttk.Style(self.root).theme_use("clam")
        except tk.TclError:
            pass
        style = ttk.Style(self.root)
        app_bg = "#f4f6fb"
        panel_bg = "#ffffff"
        text_fg = "#1f2937"
        muted_fg = "#64748b"
        border_color = "#d7deea"
        try:
            self.root.configure(background=app_bg)
        except tk.TclError:
            pass
        style.configure("TFrame", background=app_bg)
        style.configure("App.TFrame", padding=0, background=app_bg)
        style.configure("Page.TFrame", padding=14, background=app_bg)
        style.configure("TLabel", font=("Segoe UI", 10), background=app_bg, foreground=text_fg)
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"), foreground="#172033", background=app_bg)
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground=muted_fg, background=app_bg)
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#243047", background=app_bg)
        style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground=muted_fg, background=app_bg)
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 9), foreground=text_fg, background=panel_bg)
        style.map("TButton", background=[("active", "#eaf0fb"), ("pressed", "#dbe6fa")])
        style.configure("Accent.TButton", padding=(14, 7), font=("Segoe UI", 10, "bold"),
                        foreground="#ffffff", background="#2563eb")
        style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af"), ("disabled", "#9db8f5")])
        style.configure("TNotebook", tabmargins=(4, 4, 4, 0), background=app_bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), font=("Segoe UI", 10),
                        background="#e7ecf5", foreground="#40506a")
        style.map("TNotebook.Tab", background=[("selected", panel_bg), ("active", "#f8fafc")],
                  foreground=[("selected", "#1d4ed8")])
        style.configure("TLabelframe", padding=10, background=app_bg, bordercolor=border_color)
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"), background=app_bg, foreground="#243047")
        for widget_style in ("TEntry", "TCombobox", "TSpinbox"):
            style.configure(widget_style, fieldbackground=panel_bg, foreground=text_fg)

        self.root.title(f"Escritor automático v{APP_VERSION}")
        self.root.geometry("1040x730")
        self.root.minsize(820, 600)

        shell = ttk.Frame(self.root, style="App.TFrame", padding=(16, 12, 16, 10))
        shell.pack(fill="both", expand=True)

        # Encabezado breve: evita ocupar espacio con instrucciones largas.
        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0, 10))
        ttk.Button(
            header, text=f"Buscar actualizaciones · v{APP_VERSION}",
            command=lambda: self._check_for_updates(manual=True),
        ).pack(side="right", anchor="ne", padx=(12, 0), pady=(2, 0))
        ttk.Label(header, text="Escritor automático", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Prepara el texto, revisa el formato y elige cómo escribirlo.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(
            header, text=f"Sistema detectado automáticamente: {PLATFORM_LABEL}",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(3, 0))
        ttk.Checkbutton(
            header, text="Comprobar actualizaciones automáticamente al iniciar",
            variable=self.auto_update_var, command=self._save_update_preferences,
        ).pack(anchor="w", pady=(4, 0))

        # Las funciones se separan en pestañas para mostrar solo las opciones
        # relacionadas con la tarea actual.
        self.main_notebook = ttk.Notebook(shell)

        text_tab = ttk.Frame(self.main_notebook, style="Page.TFrame")
        format_tab = ttk.Frame(self.main_notebook, style="Page.TFrame")
        # La pestaña Escritura tiene su propio lienzo desplazable y barra lateral.
        # Texto y Formato mantienen su comportamiento y distribución anteriores.
        output_page = ttk.Frame(self.main_notebook, style="App.TFrame")
        self.main_notebook.add(text_tab, text="1. Texto")
        self.main_notebook.add(format_tab, text="2. Formato")
        self.main_notebook.add(output_page, text="3. Escritura")

        self.output_canvas = tk.Canvas(
            output_page, background=app_bg, highlightthickness=0, borderwidth=0,
            yscrollincrement=24,
        )
        self.output_scrollbar = ttk.Scrollbar(
            output_page, orient="vertical", command=self.output_canvas.yview,
        )
        self.output_canvas.configure(yscrollcommand=self.output_scrollbar.set)
        self.output_scrollbar.pack(side="right", fill="y")
        self.output_canvas.pack(side="left", fill="both", expand=True)
        output_tab = ttk.Frame(self.output_canvas, style="Page.TFrame")
        self._output_canvas_window = self.output_canvas.create_window(
            (0, 0), window=output_tab, anchor="nw", tags=("output-content",),
        )

        def _fit_output_content(_event=None):
            self.output_canvas.configure(scrollregion=self.output_canvas.bbox("all"))

        def _fit_output_width(event):
            self.output_canvas.itemconfigure(self._output_canvas_window, width=event.width)

        output_tab.bind("<Configure>", _fit_output_content, add="+")
        self.output_canvas.bind("<Configure>", _fit_output_width, add="+")

        # ── Pestaña Texto ──────────────────────────────────────────────────
        filebar = ttk.Frame(text_tab)
        filebar.pack(fill="x", pady=(0, 10))
        ttk.Button(filebar, text="Abrir documento…", command=self.open_file).pack(side="left", padx=(0, 6))
        self.clipboard_format_button = ttk.Button(filebar, text="Pegar con formato", command=self.paste_formatted_from_clipboard)
        self.clipboard_format_button.pack(side="left", padx=6)
        if IS_LINUX:
            self.clipboard_format_button.configure(state="disabled")
        ttk.Button(filebar, text="Pegar texto", command=lambda: self.editor.event_generate("<<Paste>>")).pack(side="left", padx=6)
        ttk.Button(filebar, text="Guardar HTML…", command=self.save_html).pack(side="left", padx=6)
        ttk.Button(filebar, text="Vaciar", command=self.clear_editor).pack(side="right", padx=(6, 0))

        editor_heading = ttk.Frame(text_tab)
        editor_heading.pack(fill="x", pady=(0, 5))
        ttk.Label(editor_heading, text="Contenido", style="Section.TLabel").pack(side="left")
        self.count_status = tk.StringVar(value="0 caracteres")
        ttk.Label(editor_heading, textvariable=self.count_status, style="Hint.TLabel").pack(side="right")

        edit_frame = ttk.Frame(text_tab)
        edit_frame.pack(fill="both", expand=True)
        self.editor = tk.Text(
            edit_frame, wrap="word", undo=True, height=12,
            font=("Arial", 11), padx=12, pady=10,
            relief="solid", borderwidth=1, insertwidth=2,
            selectbackground="#cfe0ff", selectforeground="#172033",
        )
        yscroll = ttk.Scrollbar(edit_frame, orient="vertical", command=self.editor.yview)
        self.editor.configure(yscrollcommand=yscroll.set)
        self.editor.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        edit_frame.rowconfigure(0, weight=1)
        edit_frame.columnconfigure(0, weight=1)
        self.editor.tag_configure("__default", font=("Arial", 11))
        self.editor.tag_configure(self.soft_break_tag)
        self.editor.insert("1.0", "")

        # Barra de herramientas compacta. Se mantienen todos los comandos útiles,
        # pero se agrupan bajo una sola etiqueta en vez de competir con el editor.
        toolbar = ttk.LabelFrame(text_tab, text="Formato rápido", padding=(8, 7))
        toolbar.pack(fill="x", pady=(10, 0))
        self.font_family = tk.StringVar(value="Arial")
        self.font_combo = ttk.Combobox(
            toolbar, textvariable=self.font_family,
            values=("Arial", "Calibri", "Times New Roman", "Courier New", "Verdana", "Tahoma", "Segoe UI"),
            width=18,
        )
        self.font_combo.pack(side="left", padx=(0, 6))
        self.font_combo.bind("<Return>", lambda _e: self.apply_format(family=self.font_family.get()))
        self.font_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_format(family=self.font_family.get()))
        self.font_size = tk.IntVar(value=11)
        ttk.Spinbox(toolbar, from_=5, to=72, width=5, textvariable=self.font_size,
                    command=lambda: self.apply_format(size=self.font_size.get())).pack(side="left", padx=(0, 8))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(toolbar, text="Negrita", command=lambda: self.apply_format(bold=True)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Cursiva", command=lambda: self.apply_format(italic=True)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Subrayado", command=lambda: self.apply_format(underline=True)).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Color…", command=self.choose_color).pack(side="left", padx=3)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(toolbar, text="• Viñeta", command=lambda: self.prefix_lines("• ")).pack(side="left", padx=3)
        ttk.Button(toolbar, text="1. Numerar", command=self.number_lines).pack(side="left", padx=3)
        ttk.Label(text_tab, text="Consejo: DOCX y “Pegar con formato” conservan más información que un archivo TXT.",
                  style="Hint.TLabel").pack(anchor="w", pady=(7, 0))

        # ── Pestaña Formato: el usuario elige entre párrafo y página ─────────
        ttk.Label(format_tab, text="Formato del documento", style="Section.TLabel").pack(anchor="w", pady=(0, 3))
        ttk.Label(
            format_tab,
            text="El formato de párrafo controla el interlineado y las sangrías; los márgenes afectan a la página completa.",
            style="Hint.TLabel", wraplength=900,
        ).pack(anchor="w", pady=(0, 10))
        format_notebook = ttk.Notebook(format_tab)
        format_notebook.pack(fill="both", expand=True)
        paragraph_tab = ttk.Frame(format_notebook, padding=12)
        page_tab = ttk.Frame(format_notebook, padding=12)
        format_notebook.add(paragraph_tab, text="Párrafo")
        format_notebook.add(page_tab, text="Márgenes de página")

        paragraph_box = ttk.LabelFrame(paragraph_tab, text="Interlineado y espaciado", padding=12)
        paragraph_box.pack(fill="x", pady=(0, 12))
        ttk.Label(paragraph_box, text="Interlineado").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.line_spacing_var = tk.StringVar(value="Conservar formato")
        self.line_spacing_combo = ttk.Combobox(
            paragraph_box, textvariable=self.line_spacing_var, state="readonly", width=23,
            values=("Conservar formato", "Sencillo (1,0)", "1,15", "1,5", "Doble (2,0)", "Exacto 12 pt", "Mínimo 12 pt"),
        )
        self.line_spacing_combo.grid(row=0, column=1, sticky="w", padx=(0, 22), pady=5)
        ttk.Label(paragraph_box, text="Espacio antes (cm)").grid(row=0, column=2, sticky="w", padx=(0, 7), pady=5)
        self.space_before_var = tk.StringVar(value="")
        ttk.Entry(paragraph_box, textvariable=self.space_before_var, width=9).grid(row=0, column=3, sticky="w", pady=5)
        ttk.Label(paragraph_box, text="Espacio después (cm)").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.space_after_var = tk.StringVar(value="")
        ttk.Entry(paragraph_box, textvariable=self.space_after_var, width=9).grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(paragraph_box, text="Los campos vacíos mantienen el formato original.", style="Hint.TLabel").grid(
            row=1, column=2, columnspan=2, sticky="w", padx=(10, 0), pady=5
        )
        paragraph_box.columnconfigure(4, weight=1)

        indent_box = ttk.LabelFrame(paragraph_tab, text="Sangrías", padding=12)
        indent_box.pack(fill="x", pady=(0, 10))
        ttk.Label(indent_box, text="Izquierda (cm)").grid(row=0, column=0, sticky="w", padx=(0, 7), pady=5)
        self.left_indent_var = tk.StringVar(value="")
        ttk.Entry(indent_box, textvariable=self.left_indent_var, width=9).grid(row=0, column=1, sticky="w", padx=(0, 20), pady=5)
        ttk.Label(indent_box, text="Primera línea (cm)").grid(row=0, column=2, sticky="w", padx=(0, 7), pady=5)
        self.first_indent_var = tk.StringVar(value="")
        ttk.Entry(indent_box, textvariable=self.first_indent_var, width=9).grid(row=0, column=3, sticky="w", padx=(0, 20), pady=5)
        ttk.Label(indent_box, text="Derecha (cm)").grid(row=0, column=4, sticky="w", padx=(0, 7), pady=5)
        self.right_indent_var = tk.StringVar(value="")
        ttk.Entry(indent_box, textvariable=self.right_indent_var, width=9).grid(row=0, column=5, sticky="w", pady=5)
        ttk.Button(paragraph_tab, text="Aplicar a párrafos seleccionados", command=self.apply_paragraph_controls).pack(anchor="w", pady=(2, 0))
        ttk.Label(paragraph_tab, text="Selecciona texto en la pestaña Texto o coloca allí el cursor.", style="Hint.TLabel").pack(anchor="w", pady=(7, 0))

        page_box = ttk.LabelFrame(page_tab, text="Configuración de página", padding=12)
        page_box.pack(fill="x", anchor="n")
        ttk.Label(page_box, text="Tipo de margen").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
        self.page_margin_preset = tk.StringVar(value="Conservar del documento")
        self.page_margin_combo = ttk.Combobox(
            page_box, textvariable=self.page_margin_preset, state="readonly", width=27,
            values=("Conservar del documento", "Normal (2,54 cm)", "Estrechos (1,27 cm)",
                    "Moderados (1,91/2,54 cm)", "Anchos (5,08/2,54 cm)", "Personalizados (cm)"),
        )
        self.page_margin_combo.grid(row=0, column=1, sticky="w", padx=(0, 20), pady=6)
        self.page_margin_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_page_margin_preset_changed())
        ttk.Label(page_box, text="Superior (cm)").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        self.page_top_var = tk.StringVar(value="")
        ttk.Entry(page_box, textvariable=self.page_top_var, width=10).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(page_box, text="Inferior (cm)").grid(row=1, column=2, sticky="w", padx=(24, 10), pady=6)
        self.page_bottom_var = tk.StringVar(value="")
        ttk.Entry(page_box, textvariable=self.page_bottom_var, width=10).grid(row=1, column=3, sticky="w", pady=6)
        ttk.Label(page_box, text="Izquierdo (cm)").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        self.page_left_var = tk.StringVar(value="")
        ttk.Entry(page_box, textvariable=self.page_left_var, width=10).grid(row=2, column=1, sticky="w", pady=6)
        ttk.Label(page_box, text="Derecho (cm)").grid(row=2, column=2, sticky="w", padx=(24, 10), pady=6)
        self.page_right_var = tk.StringVar(value="")
        ttk.Entry(page_box, textvariable=self.page_right_var, width=10).grid(row=2, column=3, sticky="w", pady=6)
        ttk.Button(page_box, text="Aplicar márgenes", command=self.apply_page_margins).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        self.page_setup_status = tk.StringVar(
            value="“Conservar” deja intactos los márgenes del documento de destino si no se ha importado una configuración."
        )
        ttk.Label(page_box, textvariable=self.page_setup_status, style="Hint.TLabel", wraplength=760).grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )
        for col in (1, 3):
            page_box.columnconfigure(col, weight=1)

        # ── Pestaña Escritura ───────────────────────────────────────────────
        ttk.Label(output_tab, text="Cómo quieres escribir", style="Section.TLabel").pack(anchor="w", pady=(0, 3))
        ttk.Label(output_tab, text="Selecciona un modo. La descripción de abajo explica cuándo usarlo.",
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 10))
        modes = ttk.LabelFrame(output_tab, text="Modo de salida", padding=12)
        modes.pack(fill="x", pady=(0, 12))
        self.mode = tk.StringVar(value="type")
        if IS_LINUX:
            mode_rows = [
                ("type", "Ventana activa (Linux)", "Escribe carácter por carácter mediante pynput. Funciona mejor en X11/Xorg; Wayland puede restringir la entrada global."),
                ("web", "Página web en Chromium (con extensión)", "Detecta páginas y campos compatibles en Brave, Chrome y Edge. Google Docs usa el teclado de Linux y debe quedar al frente con el cursor colocado."),
            ]
        else:
            mode_rows = [
                ("type", "Ventana activa", "Escribe carácter por carácter en la aplicación que esté al frente; no conserva estilos."),
                ("rich", "Microsoft Word con formato", "Escribe en Word letra por letra y aplica los estilos reconocidos; requiere Word de escritorio."),
                ("paste", "Pegar con formato", "Pega el contenido enriquecido de una vez; no muestra la escritura carácter por carácter."),
                ("background", "Otra aplicación en segundo plano (experimental)", "Adecuado para algunos controles Win32; no es fiable en páginas web modernas."),
                ("web", "Página web en Chrome, Edge o Brave (con extensión)", "Detecta campos editables y escribe en segundo plano cuando la página lo admite. Google Docs usa el teclado real y debe quedar al frente con el cursor colocado."),
            ]
        self._mode_help_texts = {value: description for value, _label, description in mode_rows}
        for row, (value, label, _description) in enumerate(mode_rows):
            ttk.Radiobutton(modes, text=label, value=value, variable=self.mode).grid(
                row=row, column=0, sticky="w", pady=4
            )
        self.mode_help_var = tk.StringVar(value=self._mode_help_texts["type"])
        ttk.Label(modes, textvariable=self.mode_help_var, style="Hint.TLabel", wraplength=830).grid(
            row=len(mode_rows), column=0, sticky="w", padx=(24, 0), pady=(5, 0)
        )
        self.mode.trace_add("write", self._on_mode_change)

        # Zona de destinos: solo se muestra el panel pertinente al modo elegido.
        target_container = ttk.Frame(output_tab)
        target_container.pack(fill="x", pady=(0, 12))

        target_box = ttk.LabelFrame(target_container, text="Ventana de destino", padding=12)
        self.target_box = target_box
        ttk.Label(target_box, text="Para aplicaciones de escritorio compatibles con mensajes Win32.", style="Hint.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 7)
        )
        self.target_window = tk.StringVar(value="")
        self.window_map: dict[str, int] = {}
        self.window_combo = ttk.Combobox(target_box, textvariable=self.target_window, state="readonly", width=48)
        self.window_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(target_box, text="Actualizar ventanas", command=self.refresh_target_windows).grid(row=1, column=1, sticky="w")
        target_box.columnconfigure(0, weight=1)

        self.web_target_box = ttk.LabelFrame(target_container, text="Destino web", padding=12)
        ttk.Label(
            self.web_target_box,
            text="La extensión detecta sitios y campos editables. El contenido que ya esté escrito no se transmite al programa.",
            style="Hint.TLabel", wraplength=820,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.web_connection_var = tk.StringVar(value="Extensión no conectada. Instálala desde la carpeta web_extension.")
        ttk.Label(self.web_target_box, textvariable=self.web_connection_var, style="Hint.TLabel", wraplength=820).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(self.web_target_box, text="Página web / pestaña").grid(row=2, column=0, sticky="w", pady=(0, 4))
        ttk.Label(self.web_target_box, text="Campo de texto").grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(0, 4))
        self.web_tab_var = tk.StringVar(value="")
        self.web_field_var = tk.StringVar(value="")
        self.web_tab_combo = ttk.Combobox(self.web_target_box, textvariable=self.web_tab_var, state="readonly", width=42)
        self.web_tab_combo.grid(row=3, column=0, sticky="ew", padx=(0, 8))
        self.web_field_combo = ttk.Combobox(self.web_target_box, textvariable=self.web_field_var, state="readonly", width=38)
        self.web_field_combo.grid(row=3, column=1, sticky="ew", padx=(0, 8))
        self.web_tab_combo.bind("<<ComboboxSelected>>", self._update_web_fields)
        web_buttons = ttk.Frame(self.web_target_box)
        web_buttons.grid(row=3, column=2, sticky="w")
        ttk.Button(web_buttons, text="Actualizar páginas", command=self.refresh_web_pages).pack(anchor="w")
        ttk.Button(web_buttons, text="Vista previa de página", command=self.preview_web_page).pack(anchor="w", pady=(5, 0))
        web_tools = ttk.Frame(self.web_target_box)
        web_tools.grid(row=4, column=0, columnspan=3, sticky="w", pady=(9, 0))
        ttk.Button(web_tools, text="Abrir carpeta de extensión", command=self.open_web_extension_folder).pack(side="left")
        ttk.Label(
            self.web_target_box,
            text="Para campos web comunes se usa la extensión. Google Docs usa teclado real y debe quedar al frente, con el cursor puesto. No funciona en páginas internas del navegador ni en campos protegidos.",
            style="Hint.TLabel", wraplength=820,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.web_target_box.columnconfigure(0, weight=3)
        self.web_target_box.columnconfigure(1, weight=3)
        self._update_target_panels()

        timing_box = ttk.LabelFrame(output_tab, text="Velocidad y preparación", padding=12)
        timing_box.pack(fill="x")
        ttk.Label(timing_box, text="Velocidad").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        self.speed = tk.IntVar(value=8)
        ttk.Spinbox(timing_box, from_=1, to=240, width=7, textvariable=self.speed).grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(timing_box, text="caracteres por segundo").grid(row=0, column=2, sticky="w", padx=(7, 22), pady=5)
        ttk.Label(timing_box, text="Cuenta regresiva").grid(row=0, column=3, sticky="w", padx=(0, 8), pady=5)
        self.countdown = tk.IntVar(value=10)
        ttk.Spinbox(timing_box, from_=1, to=30, width=7, textvariable=self.countdown).grid(row=0, column=4, sticky="w", pady=5)
        self.tabs_as_spaces = tk.BooleanVar(value=True)
        ttk.Checkbutton(timing_box, text="Convertir tabulaciones en 4 espacios", variable=self.tabs_as_spaces).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0)
        )

        # Estado y acciones permanecen visibles independientemente de la pestaña.
        footer = ttk.Frame(shell, padding=(0, 10, 0, 0))
        footer.pack(fill="x", side="bottom")
        self.status = tk.StringVar(value="Listo. 1) Prepara el texto  2) Revisa el formato  3) Elige el modo de escritura.")
        ttk.Label(footer, textvariable=self.status, wraplength=960, style="Hint.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Separator(footer, orient="horizontal").pack(fill="x", pady=(0, 8))
        controls = ttk.Frame(footer)
        controls.pack(fill="x")
        ttk.Label(controls, text="Atajos: F8 detener · F9 pausar/reanudar", style="Hint.TLabel").pack(side="left")
        ttk.Button(controls, text="Iniciar escritura", style="Accent.TButton", command=self.start).pack(side="right", padx=(8, 0))
        ttk.Button(controls, text="Detener  F8", command=self.stop).pack(side="right", padx=4)
        ttk.Button(controls, text="Pausar / reanudar  F9", command=self.pause_toggle).pack(side="right", padx=4)

        # La rueda del ratón desplaza la pestaña Escritura incluso si el puntero
        # está sobre uno de sus controles (radiobuttons, campos o botones).
        def _bind_output_wheel(widget):
            widget.bind("<MouseWheel>", self._scroll_output_content, add="+")
            widget.bind("<Button-4>", self._scroll_output_content, add="+")
            widget.bind("<Button-5>", self._scroll_output_content, add="+")
            for child in widget.winfo_children():
                _bind_output_wheel(child)

        _bind_output_wheel(output_page)

        # Empaquetar la zona expandible al final evita que tape parte de la barra de acciones.
        self.main_notebook.pack(fill="both", expand=True)

        self.editor.bind("<<Modified>>", self._modified)
        self.editor.edit_modified(False)
        if IS_LINUX:
            if LINUX_SESSION_TYPE == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
                self.status.set("Linux detectado. La escritura está disponible mediante pynput; Wayland puede restringir la entrada global. Para mejor compatibilidad, usa una sesión X11/Xorg.")
            else:
                self.status.set("Linux detectado. La escritura usa pynput y la extensión web funciona mediante el puente local; comprueba que la sesión gráfica X11 esté disponible.")
        elif not IS_WINDOWS:
            self.status.set("Sistema operativo detectado, pero la escritura está limitada a Windows y Linux.")

    def _save_update_preferences(self):
        """Guarda la preferencia de comprobación en el perfil del usuario."""
        try:
            prefs = self.update_manager.load_preferences()
            prefs["check_on_start"] = bool(self.auto_update_var.get())
            self.update_manager.save_preferences(prefs)
            self.update_preferences = prefs
        except UpdateError as exc:
            try:
                self.status.set(f"No se pudo guardar la preferencia de actualizaciones: {exc}")
            except tk.TclError:
                pass

    def _automatic_update_check(self):
        if not self.closing and bool(self.auto_update_var.get()):
            self._check_for_updates(manual=False)

    def _check_for_updates(self, manual: bool = True):
        """Comprueba GitHub en un hilo secundario para no bloquear Tkinter."""
        if self.closing:
            return
        if self._update_check_running:
            if manual:
                messagebox.showinfo("Actualizaciones", "Ya se está comprobando si hay una versión nueva.", parent=self.root)
            return
        self._update_check_running = True
        if manual:
            self.status.set("Comprobando si hay actualizaciones publicadas…")

        def worker():
            try:
                release = self.update_manager.check_latest_release()
                error = None
            except Exception as exc:
                release = None
                error = str(exc)
            try:
                self.root.after(0, lambda r=release, e=error, m=manual: self._update_check_finished(r, e, m))
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True, name="update-check").start()

    def _update_check_finished(self, release, error: str | None, manual: bool):
        self._update_check_running = False
        if self.closing:
            return
        if error:
            if manual:
                self.status.set("No se pudo comprobar la actualización.")
                messagebox.showerror("Error al comprobar actualizaciones", error, parent=self.root)
            return
        if release is None:
            if manual:
                messagebox.showinfo("Actualizaciones", "GitHub no devolvió información de una versión publicada.", parent=self.root)
            return
        version = release.get("version", "")
        if not release.get("is_update"):
            if manual:
                messagebox.showinfo(
                    "Actualizaciones",
                    f"Ya tienes la versión {APP_VERSION}. La última versión publicada detectada es {version}.",
                    parent=self.root,
                )
                self.status.set("La aplicación está actualizada.")
            return
        prefs = self.update_manager.load_preferences()
        ignored = prefs.get("ignored_versions", [])
        if not manual:
            if version in ignored:
                return
            try:
                snoozed = prefs.get("snoozed_version") == version and float(prefs.get("snoozed_until", 0)) > time.time()
            except (TypeError, ValueError):
                snoozed = False
            if snoozed:
                return
        self.status.set(f"Hay disponible una actualización a la versión {version}.")
        self._show_update_available_dialog(release)

    def _show_update_available_dialog(self, release: dict):
        dialog = tk.Toplevel(self.root)
        dialog.title("Actualización disponible")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.geometry("560x400")
        dialog.grab_set()
        panel = ttk.Frame(dialog, padding=18)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Hay una versión nueva", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            panel,
            text=f"Instalada: {APP_VERSION}     Disponible: {release.get('version')}\nLa actualización no se instalará hasta que lo confirmes.",
            justify="left", wraplength=515,
        ).pack(anchor="w", pady=(8, 10))
        ttk.Label(panel, text="Notas de la versión", style="Section.TLabel").pack(anchor="w")
        notes_frame = ttk.Frame(panel)
        notes_frame.pack(fill="both", expand=True, pady=(5, 8))
        notes = tk.Text(notes_frame, height=8, wrap="word", relief="solid", borderwidth=1)
        notes_scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=notes_scroll.set)
        notes.pack(side="left", fill="both", expand=True)
        notes_scroll.pack(side="right", fill="y")
        body = (release.get("body") or "No se publicaron notas para esta versión.").strip()
        notes.insert("1.0", body[:3500])
        notes.configure(state="disabled")
        auto_var = tk.BooleanVar(master=dialog, value=bool(self.auto_update_var.get()))

        def save_preference():
            self.auto_update_var.set(bool(auto_var.get()))
            self._save_update_preferences()

        ttk.Checkbutton(
            panel, text="Comprobar actualizaciones automáticamente al iniciar",
            variable=auto_var, command=save_preference,
        ).pack(anchor="w", pady=(0, 10))
        buttons = ttk.Frame(panel)
        buttons.pack(fill="x")

        def later():
            save_preference()
            try:
                prefs = self.update_manager.load_preferences()
                prefs["snoozed_version"] = release.get("version", "")
                prefs["snoozed_until"] = time.time() + 7 * 24 * 60 * 60
                self.update_manager.save_preferences(prefs)
            except UpdateError:
                pass
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

        def ignore_version():
            save_preference()
            try:
                prefs = self.update_manager.load_preferences()
                ignored = list(prefs.get("ignored_versions", []))
                version = release.get("version")
                if version and version not in ignored:
                    ignored.append(version)
                prefs["ignored_versions"] = ignored[-100:]
                self.update_manager.save_preferences(prefs)
            except UpdateError as exc:
                messagebox.showwarning("Preferencias", str(exc), parent=dialog)
            later()

        def download():
            save_preference()
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            self._download_update(release)

        ttk.Button(buttons, text="Ignorar esta versión", command=ignore_version).pack(side="left")
        ttk.Button(buttons, text="Más tarde", command=later).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Descargar actualización", style="Accent.TButton", command=download).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", later)
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")

    def _download_update(self, release: dict):
        """Descarga el paquete en segundo plano y verifica su SHA-256."""
        progress = tk.Toplevel(self.root)
        progress.title("Descargando actualización")
        progress.transient(self.root)
        progress.resizable(False, False)
        frame = ttk.Frame(progress, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Descargando la versión {release.get('version')}…").pack(anchor="w", pady=(0, 10))
        bar = ttk.Progressbar(frame, mode="indeterminate", length=380)
        bar.pack(fill="x")
        bar.start(12)
        ttk.Label(frame, text="Se comprobará la suma SHA-256 antes de permitir la instalación.", wraplength=380).pack(anchor="w", pady=(10, 0))
        self._update_download_window = progress
        progress.protocol("WM_DELETE_WINDOW", lambda: None)
        progress.grab_set()

        def worker():
            try:
                prepared = self.update_manager.download_and_prepare(release)
                error = None
            except Exception as exc:
                prepared = None
                error = str(exc)
            try:
                self.root.after(0, lambda p=prepared, e=error, w=progress, r=release: self._update_download_finished(w, p, e, r))
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True, name="update-download").start()

    def _update_download_finished(self, progress, prepared, error: str | None, release: dict):
        try:
            if progress.winfo_exists():
                progress.grab_release()
                progress.destroy()
        except tk.TclError:
            pass
        self._update_download_window = None
        if self.closing:
            return
        if error:
            messagebox.showerror("No se pudo preparar la actualización", error, parent=self.root)
            return
        if not prepared:
            return
        description = (
            f"La versión {prepared['version']} se descargó y su SHA-256 coincide con el archivo de sumas publicado.\n\n"
            f"SHA-256: {prepared['sha256']}\n\n"
            "¿Quieres ejecutar el instalador ahora? La aplicación se cerrará para completar la actualización. "
            "Si ya cargaste la extensión del navegador, puede que tengas que pulsar Recargar en la página de extensiones después."
        )
        accepted = messagebox.askyesno("Actualización verificada", description, parent=self.root)
        if not accepted:
            messagebox.showinfo(
                "Actualización descargada",
                f"El paquete verificado quedó guardado en:\n{prepared.get('archive') or prepared['path']}\n\nPuedes instalarlo cuando te convenga.",
                parent=self.root,
            )
            return
        try:
            if prepared["kind"] == "windows":
                import subprocess
                subprocess.Popen([str(prepared["path"])], cwd=str(prepared["path"].parent), close_fds=True)
                self.close()
                return
            if prepared["kind"] == "linux":
                import subprocess
                import shlex
                log_path = Path(prepared["root"]) / "update-install.log"
                # Un proceso independiente espera a que esta aplicación salga antes de
                # reemplazar la carpeta instalada. No se usa shell para construir rutas
                # a partir de texto remoto; las rutas se pasan como argumentos.
                wait_and_install = (
                    'pid="$1"; installer="$2"; logfile="$3"; '
                    'while kill -0 "$pid" 2>/dev/null; do sleep 0.5; done; '
                    'bash "$installer" > "$logfile" 2>&1'
                )
                subprocess.Popen(
                    ["bash", "-c", wait_and_install, "escritor-auto-updater", str(os.getpid()),
                     str(prepared["path"]), str(log_path)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    close_fds=True, start_new_session=True,
                )
                self.close()
                return
            raise UpdateError("El paquete preparado no corresponde a este sistema operativo.")
        except Exception as exc:
            messagebox.showerror("No se pudo iniciar el instalador", str(exc), parent=self.root)

    def _scroll_output_content(self, event):
        """Desplaza solo la pestaña Escritura; no afecta Texto ni Formato."""
        try:
            if getattr(event, "num", None) == 4:
                self.output_canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                self.output_canvas.yview_scroll(3, "units")
            else:
                delta = int(-getattr(event, "delta", 0) / 120)
                if delta == 0 and getattr(event, "delta", 0):
                    delta = -1 if event.delta > 0 else 1
                if delta:
                    self.output_canvas.yview_scroll(delta * 3, "units")
        except (tk.TclError, AttributeError):
            pass
        return "break"

    def _finish_startup_tasks(self):
        """Ejecuta tareas secundarias solo después de que la ventana ya se mostró."""
        if self.closing or self._startup_tasks_started:
            return
        self._startup_tasks_started = True
        self._start_hotkeys()
        if IS_WINDOWS:
            self.refresh_target_windows()

    def _on_mode_change(self, *_args):
        try:
            self.mode_help_var.set(self._mode_help_texts.get(self.mode.get(), ""))
        except tk.TclError:
            pass
        self._update_target_panels()

    def _update_target_panels(self):
        if not hasattr(self, "target_box"):
            return
        self.target_box.pack_forget()
        self.web_target_box.pack_forget()
        if self.mode.get() == "background":
            self.target_box.pack(fill="x")
        elif self.mode.get() == "web":
            self.web_target_box.pack(fill="x")

    def preview_web_page(self):
        """Solicita una captura de la pestaña seleccionada y muestra campos detectados."""
        label = self.web_tab_var.get()
        tab = self.web_tab_map.get(label)
        if not tab:
            messagebox.showinfo("Selecciona una página", "Primero selecciona la página web que quieres previsualizar.", parent=self.root)
            return
        if self.web_bridge is None:
            try:
                bridge = WebPageBridge()
                bridge.start()
                self.web_bridge = bridge
            except Exception as exc:
                messagebox.showerror("Puente web no disponible", str(exc), parent=self.root)
                return
        client_id = tab.get("client_id", "")
        request_id = uuid.uuid4().hex
        selected_field = self.web_field_map.get(self.web_field_var.get()) or {}
        if not self.web_bridge.send(client_id, {
            "type": "preview_tab", "tab_id": tab.get("tabId"), "request_id": request_id,
            "client_id": client_id, "selected_field_id": selected_field.get("fieldId", ""),
        }):
            messagebox.showerror("Extensión desconectada", "No se pudo enviar la solicitud. Recarga la extensión y pulsa 'Actualizar páginas'.", parent=self.root)
            return
        self._pending_preview_request = request_id
        self.web_connection_var.set("Abriendo la pestaña seleccionada y capturando la vista previa…")
        self.status.set("Vista previa solicitada. La pestaña del navegador pasará al frente unos instantes.")

    def _show_web_preview(self, data: dict):
        try:
            import base64
            from io import BytesIO
            from PIL import Image, ImageTk, ImageDraw
        except Exception:
            messagebox.showerror("Falta Pillow", "Comprueba que Pillow esté incluido en la instalación para mostrar la vista previa.", parent=self.root)
            return
        try:
            data_url = data.get("data_url")
            if not isinstance(data_url, str) or len(data_url) > WebPageBridge.MAX_PREVIEW_DATA_URL_CHARS:
                raise ValueError("La captura supera el límite de tamaño permitido.")
            prefix = "data:image/jpeg;base64,"
            if not data_url.startswith(prefix):
                raise ValueError("La vista previa debe ser una imagen JPEG válida.")
            encoded = data_url[len(prefix):]
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise ValueError("La captura contiene datos base64 inválidos.") from exc
            if len(image_bytes) > 5_500_000:
                raise ValueError("La captura supera el límite de tamaño permitido.")
            # Only decode the JPEG images expected from captureVisibleTab. Check
            # dimensions before full pixel decoding to reduce decompression-bomb risk.
            with Image.open(BytesIO(image_bytes)) as probe:
                if probe.format != "JPEG":
                    raise ValueError("El formato de la captura no coincide con JPEG.")
                if not probe.width or not probe.height or probe.width * probe.height > 40_000_000:
                    raise ValueError("La resolución de la captura excede el límite permitido.")
                probe.verify()
            with Image.open(BytesIO(image_bytes)) as source_image:
                image = source_image.convert("RGB")
            original_size = image.size
            tab_id = int(data.get("tab_id", -1))
            preview_client = str(data.get("client_id") or "")
            tab = next((t for t in self.web_tab_map.values()
                        if int(t.get("tabId", -2)) == tab_id
                        and (not preview_client or t.get("client_id") == preview_client)), {})
            fields = data.get("fields") if isinstance(data.get("fields"), list) else (tab.get("fields") or [])
            selected_field_id = str(data.get("selected_field_id") or "")
            draw = ImageDraw.Draw(image)
            for idx, field in enumerate(fields, start=1):
                rect = field.get("rect") or {}
                try:
                    vw = max(1, int(rect.get("viewportWidth", image.width)))
                    vh = max(1, int(rect.get("viewportHeight", image.height)))
                    sx, sy = image.width / vw, image.height / vh
                    x, y = round(int(rect["x"]) * sx), round(int(rect["y"]) * sy)
                    w, h = round(int(rect["width"]) * sx), round(int(rect["height"]) * sy)
                except (KeyError, TypeError, ValueError):
                    continue
                if w > 0 and h > 0:
                    # Clip untrusted field coordinates to the captured image.
                    x0 = max(0, min(image.width - 1, x))
                    y0 = max(0, min(image.height - 1, y))
                    x1 = max(0, min(image.width - 1, x + w))
                    y1 = max(0, min(image.height - 1, y + h))
                    if x1 < x0 or y1 < y0:
                        continue
                    selected = bool(selected_field_id and field.get("fieldId") == selected_field_id)
                    outline = (25, 205, 115) if selected else (255, 70, 70)
                    label_text = f"Seleccionado {idx}" if selected else f"Campo {idx}"
                    draw.rectangle((x0, y0, x1, y1), outline=outline, width=max(3 if selected else 2, round(image.width / 1200 * (4 if selected else 3))))
                    draw.text((min(image.width - 1, x0 + 3), max(0, y0 - 16)), label_text, fill=outline, stroke_width=2, stroke_fill=(255, 255, 255))
            win = tk.Toplevel(self.root)
            win.title(f"Vista previa — {data.get('title') or 'Página web'}")
            win.geometry("1050x760")
            win.minsize(640, 420)
            outer = ttk.Frame(win, padding=10)
            outer.pack(fill="both", expand=True)
            ttk.Label(outer, text=f"{data.get('title') or 'Página web'}  |  {data.get('url') or ''}", wraplength=1000).pack(fill="x", pady=(0, 6))
            if "docs.google.com/document" in str(data.get("url", "")):
                note = "Google Docs no expone un campo de texto web convencional. Para escribir, el programa usará el teclado del sistema: cierra esta vista previa, pulsa Iniciar y durante la cuenta regresiva cambia a Docs y haz clic en el punto exacto donde debe comenzar el texto."
            elif fields:
                note = f"Se muestran {len(fields)} campos detectados en rojo; el campo elegido se marca en verde. Comprueba que el recuadro coincida con el lugar donde quieres escribir."
            else:
                note = "No se detectaron campos editables compatibles en esta página."
            ttk.Label(outer, text=note, wraplength=1000).pack(fill="x", pady=(0, 8))
            canvas_frame = ttk.Frame(outer)
            canvas_frame.pack(fill="both", expand=True)
            canvas = tk.Canvas(canvas_frame, background="#222", highlightthickness=0)
            xscroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
            yscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
            canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            canvas_frame.rowconfigure(0, weight=1); canvas_frame.columnconfigure(0, weight=1)
            max_w, max_h = 1500, 1100
            scale = min(1.0, max_w / image.width, max_h / image.height)
            if scale < 1:
                image = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            canvas.create_image(0, 0, anchor="nw", image=photo)
            canvas.image = photo
            canvas.configure(scrollregion=(0, 0, image.width, image.height))
            ttk.Label(outer, text=f"Resolución capturada: {original_size[0]} × {original_size[1]} píxeles" + (f" · vista reducida al {round(scale*100)}%" if scale < 1 else "")).pack(anchor="w", pady=(6, 0))
        except Exception as exc:
            messagebox.showerror("No se pudo mostrar la vista previa", str(exc), parent=self.root)

    def open_web_extension_folder(self):
        folder = Path(__file__).with_name("web_extension")
        if not folder.is_dir():
            messagebox.showerror("No encuentro la extensión", "La carpeta web_extension no está junto al programa. Vuelve a extraer el ZIP completo.", parent=self.root)
            return
        try:
            if IS_WINDOWS:
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif IS_LINUX:
                opener = shutil.which("xdg-open")
                if opener:
                    subprocess.Popen([opener, str(folder)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                else:
                    messagebox.showinfo("Carpeta de extensión", str(folder), parent=self.root)
            else:
                messagebox.showinfo("Carpeta de extensión", str(folder), parent=self.root)
        except Exception as exc:
            messagebox.showerror("No se pudo abrir la carpeta", str(exc), parent=self.root)

    def refresh_web_pages(self):
        if not IS_SUPPORTED_OS:
            messagebox.showinfo("Sistema no compatible", "El puente web está disponible en Windows y Linux.", parent=self.root)
            return
        if self.web_bridge is None:
            bridge = WebPageBridge()
            try:
                bridge.start()
            except Exception as exc:
                messagebox.showerror("No se pudo iniciar el puente web", str(exc), parent=self.root)
                return
            self.web_bridge = bridge
        clients = self.web_bridge.clients()
        if not clients:
            self.web_connection_var.set("Servidor local listo; esperando la extensión de Chrome/Edge/Brave. Instálala, actívala y vuelve a pulsar Actualizar páginas.")
            self.status.set("Esperando a la extensión del navegador en 127.0.0.1:8765.")
            messagebox.showinfo(
                "Conecta la extensión del navegador",
                "1. Abre brave://extensions, chrome://extensions o edge://extensions.\n"
                "2. Activa el modo de desarrollador.\n"
                "3. Pulsa 'Cargar descomprimida' y selecciona la carpeta web_extension incluida en el ZIP.\n"
                "4. Abre o recarga la página web y vuelve aquí a pulsar 'Actualizar páginas'.\n\n"
                "La extensión necesita permiso para acceder a sitios web HTTP/HTTPS para identificar las pestañas y campos editables.",
                parent=self.root,
            )
            return
        sent = 0
        for client_id in clients:
            if self.web_bridge.send(client_id, {"type": "refresh_tabs", "request_id": uuid.uuid4().hex, "force": True}):
                sent += 1
        if sent:
            self.web_connection_var.set(f"Extensión conectada ({sent} conexión/es). Buscando pestañas y campos editables…")
            self.status.set("Consultando las páginas abiertas en Chrome/Edge/Brave…")
        else:
            self.web_connection_var.set("La conexión con la extensión se perdió. Recarga la extensión y prueba otra vez.")

    def _update_web_fields(self, *_args):
        label = self.web_tab_var.get()
        previous_field = self.web_field_var.get()
        tab = self.web_tab_map.get(label)
        self.web_field_map = {}
        if not tab:
            self.web_field_combo["values"] = ()
            self.web_field_var.set("")
            return
        fields = tab.get("fields") or []
        labels = []
        for index, field in enumerate(fields, 1):
            kind = field.get("kind", "campo")
            description = field.get("label") or field.get("placeholder") or field.get("name") or field.get("id") or kind
            description = re.sub(r"\s+", " ", str(description)).strip()
            if len(description) > 62:
                description = description[:59] + "…"
            frame_info = f" · iframe {field.get('frameId')}" if field.get("frameId", 0) else ""
            field_label = f"{index}. [{kind}]{frame_info} {description or 'Campo editable'}"
            if field_label in self.web_field_map:
                field_label += f" · {field.get('fieldId', '')[-4:]}"
            self.web_field_map[field_label] = field
            labels.append(field_label)
        self.web_field_combo["values"] = labels
        if labels:
            self.web_field_var.set(previous_field if previous_field in self.web_field_map else labels[0])
        else:
            self.web_field_var.set("")

    def _poll_web_bridge(self):
        if self.closing:
            return
        bridge = self.web_bridge
        if bridge is not None:
            for _ in range(300):
                try:
                    event = bridge.events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle_web_bridge_event(event)
                except Exception:
                    # Un problema de sincronización de páginas no debe tumbar el editor.
                    pass
        try:
            self.root.after(250, self._poll_web_bridge)
        except tk.TclError:
            pass

    def _handle_web_bridge_event(self, event: dict):
        kind = event.get("event")
        client_id = event.get("client_id", "")
        if kind == "bridge_error":
            self.web_connection_var.set(event.get("error", "Falló el puente web."))
            return
        if kind == "connected":
            self.web_connection_var.set("Extensión detectada; identificando navegador…")
            return
        if kind == "disconnected":
            self.web_client_browsers.pop(client_id, None)
            self.web_tab_map = {label: tab for label, tab in self.web_tab_map.items() if tab.get("client_id") != client_id}
            self._rebuild_web_tab_combo()
            connected = self.web_bridge.client_count() if self.web_bridge else 0
            self.web_connection_var.set(f"Extensión desconectada ({connected} conexiones restantes)." if connected else "Extensión desconectada. Abre o recarga la extensión y actualiza las páginas.")
            if self.web_active_target and self.web_active_target.get("client_id") == client_id and self.web_job_dispatched:
                self.web_job_id = None
                self.web_active_target = None
                self.web_job_dispatched = False
                self.status.set("Se perdió la conexión con la extensión; la escritura web se ha detenido.")
            return
        if kind != "message":
            return
        data = event.get("data") or {}
        message_type = data.get("type")
        if message_type == "hello":
            browser = str(data.get("browser") or "Chromium")
            self.web_client_browsers[client_id] = browser
            self.web_connection_var.set(f"Extensión conectada: {browser}. Sincronizando pestañas…")
            if self.web_bridge:
                self.web_bridge.send(client_id, {"type": "refresh_tabs", "request_id": uuid.uuid4().hex, "force": True})
        elif message_type == "tabs_result":
            browser = self.web_client_browsers.get(client_id, str(data.get("browser") or "Chromium"))
            self.web_tab_map = {label: tab for label, tab in self.web_tab_map.items() if tab.get("client_id") != client_id}
            pages = data.get("tabs") if isinstance(data.get("tabs"), list) else []
            for tab in pages:
                try:
                    tab_id = int(tab.get("tabId"))
                except (TypeError, ValueError):
                    continue
                url = str(tab.get("url") or "")
                title = str(tab.get("title") or "Página web")
                try:
                    domain = urlsplit(url).netloc or url
                except Exception:
                    domain = url
                label = f"{browser} · {title[:55]} — {domain[:38]} (pestaña {tab_id}, {client_id[:4]})"
                self.web_tab_map[label] = {
                    **tab, "tabId": tab_id, "client_id": client_id,
                    "browser": browser, "label": label,
                }
            self._rebuild_web_tab_combo()
            page_count = len(pages)
            editable_count = sum(len(p.get("fields") or []) for p in pages)
            self.web_connection_var.set(f"{browser}: {page_count} páginas detectadas · {editable_count} campos editables compatibles.")
            self.status.set(f"Búsqueda web terminada: {page_count} páginas y {editable_count} campos compatibles.")
        elif message_type == "preview_image":
            if getattr(self, "_pending_preview_request", None) == data.get("request_id"):
                self._pending_preview_request = None
                self._show_web_preview(data)
                self.web_connection_var.set("Vista previa cargada. Comprueba visualmente la ubicación del área de escritura.")
        elif message_type == "preview_error":
            if getattr(self, "_pending_preview_request", None) == data.get("request_id"):
                self._pending_preview_request = None
                self.web_connection_var.set(str(data.get("error", "No se pudo obtener la vista previa.")))
                messagebox.showwarning("Vista previa no disponible", self.web_connection_var.get(), parent=self.root)
        elif message_type == "tabs_error":
            self.web_connection_var.set(f"No se pudieron consultar todas las páginas: {data.get('error', 'error desconocido')}")
        elif message_type == "job_accepted":
            if data.get("job_id") == self.web_job_id:
                self.status.set("La página web aceptó la escritura. Escribiendo letra por letra en segundo plano… F8 detiene · F9 pausa.")
        elif message_type == "web_progress":
            if data.get("job_id") == self.web_job_id:
                sent = int(data.get("sent", 0) or 0)
                total = int(data.get("total", 0) or 0)
                self.status.set(f"Escribiendo en la página web… {sent}/{total} caracteres · F8 detiene · F9 pausa.")
        elif message_type == "job_done":
            if data.get("job_id") == self.web_job_id:
                self.web_job_id = None
                self.web_active_target = None
                self.web_job_dispatched = False
                self.status.set("Escritura detenida." if data.get("stopped") else "Texto escrito completamente en la página web.")
        elif message_type == "job_error":
            if data.get("job_id") == self.web_job_id:
                self.web_job_id = None
                self.web_active_target = None
                self.web_job_dispatched = False
                self.status.set(f"No se pudo escribir en la página web: {data.get('error', 'error desconocido')}")

    def _rebuild_web_tab_combo(self):
        labels = sorted(self.web_tab_map, key=lambda label: (not bool(self.web_tab_map[label].get("active")), label.casefold()))
        previous = self.web_tab_var.get()
        self.web_tab_combo["values"] = labels
        if previous in self.web_tab_map:
            self.web_tab_var.set(previous)
        elif labels:
            self.web_tab_var.set(labels[0])
        else:
            self.web_tab_var.set("")
        self._update_web_fields()

    def _on_mousewheel(self, event):
        # El editor de texto conserva su propia barra vertical; la barra exterior desplaza el resto de controles.
        try:
            if event.widget.winfo_class() == "Text":
                return
            delta = int(-1 * (event.delta / 120))
            if delta:
                self.main_canvas.yview_scroll(delta, "units")
        except Exception:
            pass

    def _on_mousewheel_linux(self, event):
        try:
            if event.widget.winfo_class() == "Text":
                return
            self.main_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        except Exception:
            pass

    def refresh_target_windows(self):
        """Enumera ventanas visibles de otros programas por su título."""
        if not IS_WINDOWS:
            self.window_map = {}
            self.window_combo["values"] = ()
            return
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        entries = []

        def visit(hwnd, _lparam):
            handle = int(hwnd if isinstance(hwnd, int) else (hwnd.value or 0))
            if not user32.IsWindowVisible(handle):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            if pid.value == os.getpid():
                return True
            length = user32.GetWindowTextLengthW(handle)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(min(length + 1, 1024))
            user32.GetWindowTextW(handle, buffer, len(buffer))
            title = buffer.value.strip()
            if title:
                label = f"{title[:100]}  [HWND 0x{handle:X}]"
                entries.append((label, handle))
            return True

        callback = enum_proc_type(visit)
        if not user32.EnumWindows(callback, 0) and hasattr(self, "status"):
            self.status.set("No se pudieron enumerar las ventanas de Windows.")
        entries.sort(key=lambda item: item[0].casefold())
        previous = self.target_window.get()
        self.window_map = {label: handle for label, handle in entries}
        labels = list(self.window_map)
        self.window_combo["values"] = labels
        if previous in self.window_map:
            self.target_window.set(previous)
        elif labels:
            self.target_window.set(labels[0])
        else:
            self.target_window.set("")
        if hasattr(self, "status"):
            self.status.set(f"Se detectaron {len(labels)} ventanas de otros programas. Selecciona el destino para usar el modo en segundo plano.")

    def _modified(self, _event=None):
        """Programa un recuento diferido para no leer todo el texto en cada tecla."""
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        if self._count_update_id is not None:
            try:
                self.root.after_cancel(self._count_update_id)
            except tk.TclError:
                pass
        # Un intervalo algo mayor evita recalcular el contador constantemente
        # mientras el usuario escribe documentos grandes.
        self._count_update_id = self.root.after(300, self._update_count_status)

    def _update_count_status(self):
        self._count_update_id = None
        if self.closing:
            return
        try:
            # Cuenta dentro de Tcl/Tk, sin copiar todo el documento a Python ni
            # crear una lista temporal mediante splitlines().
            counts = self.editor.count("1.0", "end-1c", "chars", "lines")
            if not counts:
                chars, newline_count = 0, 0
            else:
                chars, newline_count = int(counts[0]), int(counts[1])
            # Tk cuenta saltos de línea; splitlines() cuenta líneas no vacías
            # finales como lo hacía la versión anterior.
            if chars and self.editor.get("end-2c", "end-1c") != "\n":
                lines = newline_count + 1
            else:
                lines = newline_count
        except (tk.TclError, TypeError, ValueError):
            return
        self.count_status.set(f"{chars:,} caracteres · {lines:,} líneas")

    @staticmethod
    def _cm_to_pt(value: float) -> float:
        return float(value) * 72.0 / 2.54

    @staticmethod
    def _pt_to_cm(value: float | int | None) -> str:
        if value is None:
            return ""
        return f"{float(value) * 2.54 / 72.0:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _css_length_to_pt(raw: str) -> float | None:
        """Convierte longitudes CSS habituales a puntos."""
        match = re.fullmatch(r"\s*(-?[\d.]+)\s*(pt|px|cm|mm|in|pc)?\s*", raw or "", flags=re.I)
        if not match:
            return None
        value = float(match.group(1))
        unit = (match.group(2) or "px").lower()
        factor = {"pt": 1.0, "px": 0.75, "cm": 72.0 / 2.54,
                  "mm": 72.0 / 25.4, "in": 72.0, "pc": 12.0}[unit]
        return value * factor

    def _paragraph_meta_from_css(self, css: str) -> dict:
        """Lee interlineado/sangrías/espaciado de un atributo style de párrafo."""
        result: dict = {}
        styles = {}
        for piece in (css or "").split(";"):
            if ":" in piece:
                key, value = piece.split(":", 1)
                styles[key.strip().lower()] = value.strip()
        if styles.get("text-align") in ("left", "center", "right", "justify"):
            result["alignment"] = styles["text-align"]
        # Microsoft Word utiliza propiedades Mso además de CSS estándar al copiar
        # contenido enriquecido. Se interpretan como formato de párrafo, sin
        # confundir sus sangrías con los márgenes de página (@page).
        length_map = {
            "margin-left": "left_indent_pt", "mso-para-margin-left": "left_indent_pt",
            "margin-right": "right_indent_pt", "mso-para-margin-right": "right_indent_pt",
            "text-indent": "first_line_indent_pt", "margin-top": "space_before_pt",
            "mso-margin-top-alt": "space_before_pt", "margin-bottom": "space_after_pt",
            "mso-margin-bottom-alt": "space_after_pt",
        }
        for css_key, meta_key in length_map.items():
            if css_key in styles:
                value = self._css_length_to_pt(styles[css_key])
                if value is not None:
                    result[meta_key] = value
        line_height = styles.get("line-height")
        mso_rule = styles.get("mso-line-height-rule", "").strip().lower()
        if line_height and line_height.lower() != "normal":
            percent = re.fullmatch(r"([\d.]+)%", line_height)
            if percent:
                ratio = float(percent.group(1)) / 100.0
                if abs(ratio - 1.0) < 0.005:
                    result["line_spacing_type"], result["line_spacing_value"] = "single", 1.0
                elif abs(ratio - 1.5) < 0.005:
                    result["line_spacing_type"], result["line_spacing_value"] = "one_point_five", 1.5
                elif abs(ratio - 2.0) < 0.005:
                    result["line_spacing_type"], result["line_spacing_value"] = "double", 2.0
                else:
                    result["line_spacing_type"], result["line_spacing_value"] = "multiple", ratio
            elif re.fullmatch(r"[\d.]+", line_height):
                ratio = float(line_height)
                if abs(ratio - 1.0) < 0.005:
                    result["line_spacing_type"], result["line_spacing_value"] = "single", 1.0
                elif abs(ratio - 1.5) < 0.005:
                    result["line_spacing_type"], result["line_spacing_value"] = "one_point_five", 1.5
                elif abs(ratio - 2.0) < 0.005:
                    result["line_spacing_type"], result["line_spacing_value"] = "double", 2.0
                else:
                    result["line_spacing_type"], result["line_spacing_value"] = "multiple", ratio
            else:
                value = self._css_length_to_pt(line_height)
                if value is not None:
                    result["line_spacing_type"] = "at_least" if mso_rule in ("at-least", "at_least") else "exactly"
                    result["line_spacing_value"] = value
        # En HTML de Word, mso-line-height-rule distingue un valor exacto de
        # uno mínimo. Si line-height es un múltiplo/porcentaje y hay font-size
        # declarado, convertirlo a puntos para conservar esa distinción.
        if line_height and mso_rule in ("at-least", "at_least", "exactly"):
            absolute = self._css_length_to_pt(line_height)
            if absolute is not None:
                result["line_spacing_type"] = "at_least" if mso_rule in ("at-least", "at_least") else "exactly"
                result["line_spacing_value"] = absolute
            else:
                ratio_match = re.fullmatch(r"([\d.]+)%", line_height)
                if ratio_match:
                    ratio = float(ratio_match.group(1)) / 100.0
                elif re.fullmatch(r"[\d.]+", line_height):
                    ratio = float(line_height)
                else:
                    ratio = None
                font_size_pt = self._css_length_to_pt(styles.get("font-size", ""))
                if ratio is not None and font_size_pt is not None:
                    result["line_spacing_type"] = "at_least" if mso_rule in ("at-least", "at_least") else "exactly"
                    result["line_spacing_value"] = ratio * font_size_pt
        if styles.get("page-break-before", "").strip().lower() in ("always", "page"):
            result["page_break_before"] = True
        return result

    def _paragraph_tk_options(self, meta: dict) -> dict:
        """Aproxima el formato de párrafo en el editor Tk; la exportación retiene los valores exactos."""
        px_per_pt = 96.0 / 72.0
        opts: dict = {}
        alignment = meta.get("alignment")
        if alignment in ("left", "center", "right", "justify"):
            # Tk Text no ofrece alineación justificada; la información exacta
            # permanece en los metadatos y sí se exporta a Word/HTML.
            opts["justify"] = "left" if alignment == "justify" else alignment
        left = float(meta.get("left_indent_pt") or 0.0)
        right = float(meta.get("right_indent_pt") or 0.0)
        first = float(meta.get("first_line_indent_pt") or 0.0)
        opts["lmargin1"] = max(0, int(round((left + first) * px_per_pt)))
        opts["lmargin2"] = max(0, int(round(left * px_per_pt)))
        opts["rmargin"] = max(0, int(round(right * px_per_pt)))
        before = float(meta.get("space_before_pt") or 0.0)
        after = float(meta.get("space_after_pt") or 0.0)
        if before: opts["spacing1"] = max(0, int(round(before * px_per_pt)))
        if after: opts["spacing3"] = max(0, int(round(after * px_per_pt)))
        line_type = meta.get("line_spacing_type")
        line_value = meta.get("line_spacing_value")
        extra_px = 0.0
        if line_type == "multiple" and line_value is not None:
            extra_px = max(0.0, (float(line_value) - 1.0) * 16.0)
        elif line_type in ("exactly", "at_least") and line_value is not None:
            extra_px = max(0.0, float(line_value) * px_per_pt - 16.0)
        if extra_px:
            opts["spacing2"] = int(round(extra_px))
        return opts

    def _paragraph_meta_at(self, index: str) -> dict:
        result: dict = {}
        for tag in self.editor.tag_names(index):
            if tag in self.paragraph_meta:
                result.update(self.paragraph_meta[tag])
        return result

    def _paragraph_tag_at(self, index: str) -> str | None:
        for tag in self.editor.tag_names(index):
            if tag in self.paragraph_meta:
                return tag
        return None

    def _set_paragraph_meta_range(self, start: str, end: str, meta: dict, remove_overlap: bool = True):
        """Aplica metadatos a un rango de párrafo y configura la vista previa del editor."""
        try:
            if self.editor.compare(end, "<", start) or self.editor.compare(end, "==", start):
                return
        except tk.TclError:
            return
        if remove_overlap:
            for old_tag in tuple(self.paragraph_tags):
                try:
                    self.editor.tag_remove(old_tag, start, end)
                except tk.TclError:
                    pass
        self._tag_counter += 1
        tag = f"para_fmt_{self._tag_counter}"
        cleaned = {key: value for key, value in meta.items() if value is not None}
        opts = self._paragraph_tk_options(cleaned)
        self.editor.tag_configure(tag, **opts)
        self.editor.tag_add(tag, start, end)
        self.paragraph_tags[tag] = opts
        self.paragraph_meta[tag] = cleaned

    def _soft_break_offsets(self, text: str) -> set[int]:
        """Offsets de saltos manuales de línea, diferenciados de los saltos de párrafo."""
        positions: set[int] = set()
        for start, _end in zip(self.editor.tag_ranges(self.soft_break_tag)[0::2],
                               self.editor.tag_ranges(self.soft_break_tag)[1::2]):
            offset = self._text_offset(start)
            if 0 <= offset < len(text) and text[offset] == "\n":
                positions.add(offset)
        return positions

    def _paragraph_runs(self, text: str) -> list[tuple[int, int, dict]]:
        """Devuelve rangos por párrafo (incluye saltos de línea) con su formato."""
        if not text:
            return []
        starts = [0]
        starts.extend(i + 1 for i, char in enumerate(text) if char == "\n")
        runs = []
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(text)
            # Las etiquetas del párrafo se extienden también al salto de línea,
            # de modo que los párrafos vacíos tengan un formato identificable.
            try:
                meta = self._paragraph_meta_at(f"1.0+{start}c")
            except tk.TclError:
                meta = {}
            runs.append((start, end, meta))
        return runs

    def _selected_line_range(self) -> tuple[int, int]:
        try:
            start_index, end_index = self.editor.index("sel.first"), self.editor.index("sel.last")
        except tk.TclError:
            start_index = self.editor.index("insert linestart")
            end_index = self.editor.index("insert lineend")
        first = int(start_index.split(".")[0])
        last = int(end_index.split(".")[0])
        # Si la selección termina justo al inicio de la línea siguiente, no la incluye.
        if last > first and end_index.endswith(".0"):
            last -= 1
        return first, max(first, last)

    @staticmethod
    def _parse_cm_entry(raw: str, label: str, allow_negative: bool = False) -> float | None:
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            value = float(raw.replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"El campo '{label}' debe ser un número en centímetros.") from exc
        if value < 0 and not allow_negative:
            raise ValueError(f"El campo '{label}' no puede ser negativo.")
        if abs(value) > 50:
            raise ValueError(f"El valor de '{label}' parece demasiado grande (máximo 50 cm).")
        return value

    def apply_paragraph_controls(self):
        try:
            changes: dict = {}
            spacing = self.line_spacing_var.get()
            spacing_map = {
                "Sencillo (1,0)": ("multiple", 1.0), "1,15": ("multiple", 1.15),
                "1,5": ("multiple", 1.5), "Doble (2,0)": ("multiple", 2.0),
                "Exacto 12 pt": ("exactly", 12.0), "Mínimo 12 pt": ("at_least", 12.0),
            }
            if spacing in spacing_map:
                changes["line_spacing_type"], changes["line_spacing_value"] = spacing_map[spacing]
            entries = (
                (self.space_before_var.get(), "Espacio antes", "space_before_pt", False),
                (self.space_after_var.get(), "Espacio después", "space_after_pt", False),
                (self.left_indent_var.get(), "Sangría izquierda", "left_indent_pt", False),
                (self.first_indent_var.get(), "Primera línea", "first_line_indent_pt", True),
                (self.right_indent_var.get(), "Sangría derecha", "right_indent_pt", False),
            )
            for raw, label, key, allow_negative in entries:
                value = self._parse_cm_entry(raw, label, allow_negative)
                if value is not None:
                    changes[key] = self._cm_to_pt(value)
            if not changes:
                self.status.set("No hay cambios de párrafo para aplicar.")
                return
            first_line, last_line = self._selected_line_range()
            for line in range(first_line, last_line + 1):
                start = f"{line}.0"
                try:
                    end = self.editor.index(f"{line}.0 lineend + 1c")
                except tk.TclError:
                    end = self.editor.index("end")
                current = self._paragraph_meta_at(start)
                current.update(changes)
                self._set_paragraph_meta_range(start, end, current, remove_overlap=True)
            self.editor.tag_raise("sel")
            self.status.set(f"Formato aplicado a {last_line - first_line + 1} párrafo(s). Los valores se conservarán al exportar a Word/HTML.")
        except Exception as exc:
            messagebox.showerror("Formato de párrafo", str(exc), parent=self.root)

    def on_page_margin_preset_changed(self):
        preset = self.page_margin_preset.get()
        presets = {
            "Normal (2,54 cm)": (2.54, 2.54, 2.54, 2.54),
            "Estrechos (1,27 cm)": (1.27, 1.27, 1.27, 1.27),
            "Moderados (1,91/2,54 cm)": (2.54, 2.54, 1.91, 1.91),
            "Anchos (5,08/2,54 cm)": (2.54, 2.54, 5.08, 5.08),
        }
        if preset in presets:
            top, bottom, left, right = presets[preset]
            self.page_top_var.set(f"{top:.2f}")
            self.page_bottom_var.set(f"{bottom:.2f}")
            self.page_left_var.set(f"{left:.2f}")
            self.page_right_var.set(f"{right:.2f}")
            self.page_setup_status.set("Tipo seleccionado, todavía no aplicado. Pulsa 'Aplicar márgenes de página' para confirmarlo.")
        elif preset == "Personalizados (cm)":
            self.page_setup_status.set("Introduce los cuatro valores en centímetros y pulsa 'Aplicar márgenes de página'.")
        elif preset == "Conservar del documento":
            self._refresh_page_margin_fields(self.imported_page_setup)

    def _refresh_page_margin_fields(self, setup: dict | None):
        vars_and_keys = (
            (self.page_top_var, "top_margin_pt"), (self.page_bottom_var, "bottom_margin_pt"),
            (self.page_left_var, "left_margin_pt"), (self.page_right_var, "right_margin_pt"),
        )
        for var, key in vars_and_keys:
            var.set(self._pt_to_cm(setup.get(key)) if setup and setup.get(key) is not None else "")
        if setup:
            top = self._pt_to_cm(setup.get("top_margin_pt")) or "?"
            bottom = self._pt_to_cm(setup.get("bottom_margin_pt")) or "?"
            left = self._pt_to_cm(setup.get("left_margin_pt")) or "?"
            right = self._pt_to_cm(setup.get("right_margin_pt")) or "?"
            self.page_setup_status.set(
                f"Configuración activa: superior {top} cm · inferior {bottom} cm · izquierda {left} cm · derecha {right} cm. "
                "Se aplicará a la sección de Word donde esté el cursor."
            )
        else:
            self.page_setup_status.set("Sin márgenes importados: 'Conservar del documento' dejará intactos los márgenes del destino.")

    def apply_page_margins(self):
        preset = self.page_margin_preset.get()
        if preset == "Conservar del documento":
            self.page_setup = dict(self.imported_page_setup) if self.imported_page_setup else None
            self._refresh_page_margin_fields(self.page_setup)
            self.status.set("Se conservará la configuración de página del documento importado; si no había, se respetará Word.")
            return
        if preset == "Personalizados (cm)":
            try:
                values = {
                    "top_margin_pt": self._cm_to_pt(self._parse_cm_entry(self.page_top_var.get(), "Margen superior") or 0),
                    "bottom_margin_pt": self._cm_to_pt(self._parse_cm_entry(self.page_bottom_var.get(), "Margen inferior") or 0),
                    "left_margin_pt": self._cm_to_pt(self._parse_cm_entry(self.page_left_var.get(), "Margen izquierdo") or 0),
                    "right_margin_pt": self._cm_to_pt(self._parse_cm_entry(self.page_right_var.get(), "Margen derecho") or 0),
                }
                if any(values[key] <= 0 for key in values):
                    raise ValueError("Todos los márgenes personalizados deben ser mayores que cero.")
            except Exception as exc:
                messagebox.showerror("Márgenes de página", str(exc), parent=self.root)
                return
        else:
            top, bottom, left, right = {
                "Normal (2,54 cm)": (2.54, 2.54, 2.54, 2.54),
                "Estrechos (1,27 cm)": (1.27, 1.27, 1.27, 1.27),
                "Moderados (1,91/2,54 cm)": (2.54, 2.54, 1.91, 1.91),
                "Anchos (5,08/2,54 cm)": (2.54, 2.54, 5.08, 5.08),
            }.get(preset, (2.54, 2.54, 2.54, 2.54))
            values = {"top_margin_pt": self._cm_to_pt(top), "bottom_margin_pt": self._cm_to_pt(bottom),
                      "left_margin_pt": self._cm_to_pt(left), "right_margin_pt": self._cm_to_pt(right)}
        base = dict(self.page_setup or self.imported_page_setup or {})
        base.update(values)
        self.page_setup = base
        self._refresh_page_margin_fields(self.page_setup)
        self.status.set("Márgenes de página configurados. No alteran las sangrías de los párrafos.")

    def _extract_page_setup(self, document) -> dict | None:
        try:
            section = document.sections[0]
        except Exception:
            return None
        def points(value):
            return float(value.pt) if value is not None else None
        return {
            "top_margin_pt": points(section.top_margin),
            "bottom_margin_pt": points(section.bottom_margin),
            "left_margin_pt": points(section.left_margin),
            "right_margin_pt": points(section.right_margin),
            "gutter_pt": points(section.gutter),
            "header_distance_pt": points(section.header_distance),
            "footer_distance_pt": points(section.footer_distance),
            "page_width_pt": points(section.page_width),
            "page_height_pt": points(section.page_height),
            "orientation": int(section.orientation) if section.orientation is not None else None,
        }

    def _extract_page_setup_from_html(self, content: str) -> dict | None:
        page = re.search(r"@page(?:\s+[\w-]+)?\s*\{([^}]*)\}", content, flags=re.I | re.S)
        if not page:
            return None
        declarations = {}
        for part in page.group(1).split(";"):
            if ":" in part:
                key, value = part.split(":", 1)
                declarations[key.strip().lower()] = value.strip()
        result = {}
        css_names = {"margin-top": "top_margin_pt", "margin-bottom": "bottom_margin_pt",
                     "margin-left": "left_margin_pt", "margin-right": "right_margin_pt",
                     "--word-gutter": "gutter_pt", "mso-gutter-margin": "gutter_pt",
                     "--word-header-distance": "header_distance_pt", "mso-header-margin": "header_distance_pt",
                     "--word-footer-distance": "footer_distance_pt", "mso-footer-margin": "footer_distance_pt"}
        for css_name, key in css_names.items():
            if css_name in declarations:
                value = self._css_length_to_pt(declarations[css_name])
                if value is not None: result[key] = value
        size_values = re.findall(r"-?[\d.]+\s*(?:pt|px|cm|mm|in|pc)?", declarations.get("size", ""), flags=re.I)
        size_points = [self._css_length_to_pt(value) for value in size_values]
        if len(size_points) >= 2 and size_points[0] is not None and size_points[1] is not None:
            result["page_width_pt"], result["page_height_pt"] = size_points[0], size_points[1]
            result["orientation"] = 1 if size_points[0] > size_points[1] else 0
        orientation_css = declarations.get("--word-orientation", "").strip().lower()
        if orientation_css in ("portrait", "landscape"):
            result["orientation"] = 1 if orientation_css == "landscape" else 0
        if "margin" in declarations:
            pieces = declarations["margin"].split()
            vals = [self._css_length_to_pt(value) for value in pieces]
            if len(vals) == 1 and vals[0] is not None:
                result.update({key: vals[0] for key in ("top_margin_pt", "bottom_margin_pt", "left_margin_pt", "right_margin_pt")})
            elif len(vals) == 2 and all(v is not None for v in vals):
                result.update({"top_margin_pt": vals[0], "bottom_margin_pt": vals[0], "left_margin_pt": vals[1], "right_margin_pt": vals[1]})
            elif len(vals) == 4 and all(v is not None for v in vals):
                result.update(dict(zip(("top_margin_pt", "right_margin_pt", "bottom_margin_pt", "left_margin_pt"), vals)))
        return result or None

    def _page_css(self) -> str:
        if not self.page_setup:
            return ""
        names = (("top_margin_pt", "margin-top"), ("right_margin_pt", "margin-right"),
                 ("bottom_margin_pt", "margin-bottom"), ("left_margin_pt", "margin-left"))
        declarations = []
        for key, css_name in names:
            if self.page_setup.get(key) is not None:
                declarations.append(f"{css_name}:{float(self.page_setup[key]):g}pt")
        width, height = self.page_setup.get("page_width_pt"), self.page_setup.get("page_height_pt")
        if width is not None and height is not None:
            declarations.append(f"size:{float(width):g}pt {float(height):g}pt")
        for key, css_names in (("gutter_pt", ("mso-gutter-margin", "--word-gutter")),
                               ("header_distance_pt", ("mso-header-margin", "--word-header-distance")),
                               ("footer_distance_pt", ("mso-footer-margin", "--word-footer-distance"))):
            if self.page_setup.get(key) is not None:
                for css_name in css_names:
                    declarations.append(f"{css_name}:{float(self.page_setup[key]):g}pt")
        if self.page_setup.get("orientation") in (0, 1):
            declarations.append("--word-orientation:" + ("landscape" if self.page_setup["orientation"] == 1 else "portrait"))
        return "@page{" + ";".join(declarations) + "}" if declarations else ""

    def _style_at(self, index: str) -> dict:
        style = {"family": "Arial", "size": 11}
        tags = self.editor.tag_names(index)
        for tag in tags:
            if tag in self.format_tags:
                style.update(self.format_tags[tag])
        return style

    def _text_offset(self, index: str) -> int:
        """Convierte un índice Tk Text (línea.columna) en un offset de caracteres."""
        counted = self.editor.count("1.0", index, "chars")
        return int(counted[0]) if counted else 0

    def _collect_style_runs(self) -> list[tuple[int, int, dict]]:
        """Devuelve segmentos contiguos con el mismo formato sin consultar cada carácter.

        En documentos largos, llamar a ``tag_names`` para cada carácter genera
        decenas de miles de viajes entre Python y Tcl. Aquí consultamos los rangos
        de cada etiqueta y hacemos una pasada lineal por sus límites.
        """
        text = self.editor.get("1.0", "end-1c")
        if not text:
            return []

        all_names = list(self.editor.tag_names())
        priority = {name: pos for pos, name in enumerate(all_names)}
        # Cada offset lleva (etiquetas que salen, etiquetas que entran).
        events: dict[int, tuple[set[str], set[str]]] = {}

        for tag in self.format_tags:
            if tag not in priority:
                continue
            ranges = self.editor.tag_ranges(tag)
            for start_idx, end_idx in zip(ranges[0::2], ranges[1::2]):
                start = max(0, min(len(text), self._text_offset(start_idx)))
                end = max(0, min(len(text), self._text_offset(end_idx)))
                if end <= start:
                    continue
                if start not in events:
                    events[start] = (set(), set())
                if end not in events:
                    events[end] = (set(), set())
                events[start][1].add(tag)
                events[end][0].add(tag)

        boundaries = sorted({0, len(text), *events.keys()})
        active: set[str] = set()
        runs: list[tuple[int, int, dict]] = []
        for pos, next_pos in zip(boundaries, boundaries[1:]):
            if pos in events:
                remove_tags, add_tags = events[pos]
                active.difference_update(remove_tags)
                active.update(add_tags)
            if next_pos <= pos:
                continue
            style = {"family": "Arial", "size": 11}
            for tag in sorted(active, key=lambda name: priority.get(name, -1)):
                style.update(self.format_tags.get(tag, {}))
            if runs and runs[-1][1] == pos and runs[-1][2] == style:
                previous_start, _previous_end, previous_style = runs[-1]
                runs[-1] = (previous_start, next_pos, previous_style)
            else:
                runs.append((pos, next_pos, style))
        return runs

    def _tag_for_style(self, style: dict) -> str:
        cleaned = {k: v for k, v in style.items() if v not in (None, False, "")}
        key = json.dumps(cleaned, sort_keys=True, ensure_ascii=False)
        cached = self._style_tag_cache.get(key)
        if cached is not None:
            return cached
        self._tag_counter += 1
        tag = f"fmt_{self._tag_counter}"
        self.format_tags[tag] = cleaned
        self._style_tag_cache[key] = tag
        family = cleaned.get("family", "Arial")
        size = cleaned.get("size", 11)
        font = (family, max(5, int(round(float(size)))))
        if cleaned.get("bold"): font = (family, max(5, int(round(float(size)))), "bold")
        if cleaned.get("italic"):
            font = (family, max(5, int(round(float(size)))) , "bold italic" if cleaned.get("bold") else "italic")
        opts = {"font": font}
        if cleaned.get("underline"): opts["underline"] = 1
        if cleaned.get("strike"): opts["overstrike"] = 1
        if cleaned.get("color"): opts["foreground"] = cleaned["color"]
        self.editor.tag_configure(tag, **opts)
        return tag

    def insert_styled(self, text: str, style: dict | None = None, at_index: str | None = None):
        if not text:
            return self.editor.index(at_index or "end-1c")
        start = self.editor.index(at_index or "end-1c")
        self.editor.insert(start, text)
        end = self.editor.index(f"{start}+{len(text)}c")
        if style:
            tag = self._tag_for_style(style)
            self.editor.tag_add(tag, start, end)
        return end

    def apply_format(self, **changes):
        try:
            start, end = self.editor.index("sel.first"), self.editor.index("sel.last")
        except tk.TclError:
            self.status.set("Selecciona primero el texto que quieres formatear.")
            return
        # Procesa segmentos contiguos de formato, no cada carácter individual.
        # En selecciones grandes esto reduce miles de llamadas Tkinter.
        start_offset = self._text_offset(start)
        end_offset = self._text_offset(end)
        runs = self._collect_style_runs()
        for old in tuple(self.format_tags):
            self.editor.tag_remove(old, start, end)
        for run_start, run_end, old_style in runs:
            a, b = max(run_start, start_offset), min(run_end, end_offset)
            if a >= b:
                continue
            style = dict(old_style)
            style.update(changes)
            tag = self._tag_for_style(style)
            self.editor.tag_add(tag, f"1.0+{a}c", f"1.0+{b}c")
        self.editor.tag_raise("sel")

    def choose_color(self):
        chosen = colorchooser.askcolor(title="Color del texto", parent=self.root)[1]
        if chosen: self.apply_format(color=chosen)

    def prefix_lines(self, prefix: str):
        try:
            start = self.editor.index("sel.first linestart")
            end = self.editor.index("sel.last lineend")
        except tk.TclError:
            start = self.editor.index("insert linestart")
            end = self.editor.index("insert lineend")
        lines = self.editor.get(start, end).split("\n")
        for offset in range(len(lines) - 1, -1, -1):
            pos = f"{start}+{offset} lines lineend" if offset == 0 else f"{start}+{offset} lines linestart"
            # Calculate by explicit line number to avoid index arithmetic ambiguity.
            line_number = int(start.split(".")[0]) + offset
            self.editor.insert(f"{line_number}.0", prefix)

    def number_lines(self):
        try: start = int(self.editor.index("sel.first linestart").split(".")[0]); end = int(self.editor.index("sel.last lineend").split(".")[0])
        except tk.TclError:
            start = end = int(self.editor.index("insert").split(".")[0])
        for line in range(end, start - 1, -1):
            self.editor.insert(f"{line}.0", f"{line - start + 1}. ")

    def clear_editor(self):
        if messagebox.askyesno("Limpiar", "¿Borrar todo el texto del editor?", parent=self.root):
            self.editor.delete("1.0", "end")
            self.format_tags.clear(); self._style_tag_cache.clear(); self.paragraph_tags.clear(); self.paragraph_meta.clear(); self.count_status.set("0 caracteres · 0 líneas")

    def open_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="Abrir documento", filetypes=[("Archivos compatibles", "*.txt *.html *.htm *.docx"), ("Todos los archivos", "*.*")])
        if not path: return
        try:
            suffix = Path(path).suffix.lower()
            self.editor.delete("1.0", "end")
            self.format_tags.clear(); self._style_tag_cache.clear(); self.paragraph_tags.clear(); self.paragraph_meta.clear(); self._tag_counter = 0
            self.imported_page_setup = None
            self.page_setup = None
            if suffix == ".txt":
                content = Path(path).read_text(encoding="utf-8-sig", errors="replace")
                self.editor.insert("1.0", content)
            elif suffix in (".html", ".htm"):
                content = Path(path).read_text(encoding="utf-8-sig", errors="replace")
                self.imported_page_setup = self._extract_page_setup_from_html(content)
                self.page_setup = dict(self.imported_page_setup) if self.imported_page_setup else None
                parser = HtmlImporter(self, class_styles=self._html_class_styles(content)); parser.feed(content); parser.close()
            elif suffix == ".docx":
                self._open_docx(path)
            else:
                raise ValueError("Tipo de archivo no compatible.")
            self.page_margin_preset.set("Conservar del documento")
            self._refresh_page_margin_fields(self.page_setup)
            self.status.set(f"Documento cargado: {os.path.basename(path)}")
            self.editor.edit_modified(True); self._modified()
        except Exception as exc:
            messagebox.showerror("No se pudo abrir el documento", f"{exc}\n\n{traceback.format_exc()}", parent=self.root)

    @staticmethod
    def _html_class_styles(source: str) -> dict[str, str]:
        """Extrae reglas CSS por clase (Word suele utilizar clases MsoNormal/MsoTitle)."""
        result: dict[str, str] = {}
        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", source, flags=re.S):
            selector_group, declarations = match.group(1).strip(), match.group(2).strip()
            if selector_group.startswith("@") or not declarations:
                continue
            for selector in selector_group.split(","):
                for class_name in re.findall(r"\.([A-Za-z_][\w-]*)", selector):
                    result[class_name] = ";".join((result.get(class_name, ""), declarations)).strip(";")
        return result

    def paste_formatted_from_clipboard(self):
        """Importa el fragmento HTML enriquecido copiado desde Word u otra aplicación."""
        try:
            if IS_LINUX:
                messagebox.showinfo(
                    "Función solo de Windows",
                    "La lectura del formato HTML enriquecido desde el portapapeles usa una API de Windows. "
                    "En Linux puedes abrir un DOCX/HTML desde 'Abrir documento…' o pegar texto plano.",
                    parent=self.root,
                )
                return
            clipboard = get_windows_clipboard_html()
            if not clipboard:
                messagebox.showinfo(
                    "Portapapeles sin formato HTML",
                    "No encuentro formato HTML enriquecido en el portapapeles. Copia el contenido desde Word y vuelve a intentarlo; si solo necesitas texto, utiliza 'Pegar texto'.",
                    parent=self.root,
                )
                return
            full_html, fragment = clipboard
            class_styles = self._html_class_styles(full_html)
            # Algunos programas incluyen @page junto con el HTML copiado. Si lo
            # hacen, mantenemos esa configuración de página aparte del formato
            # del párrafo; un simple texto seleccionado normalmente no contiene
            # márgenes completos y no sobrescribe la configuración actual.
            clipboard_page_setup = self._extract_page_setup_from_html(full_html)
            if clipboard_page_setup:
                self.imported_page_setup = dict(clipboard_page_setup)
                self.page_setup = dict(clipboard_page_setup)
                self.page_margin_preset.set("Conservar del documento")
                self._refresh_page_margin_fields(self.page_setup)
            try:
                insert_at = self.editor.index("sel.first")
                end = self.editor.index("sel.last")
                self.editor.delete(insert_at, end)
            except tk.TclError:
                insert_at = self.editor.index("insert")
            parser = HtmlImporter(self, insert_at=insert_at, class_styles=class_styles)
            parser.feed(fragment)
            parser.close()
            self.editor.mark_set("insert", parser.cursor)
            self.editor.see("insert")
            self.editor.edit_modified(True)
            self._modified()
            self.status.set("Contenido del portapapeles importado con los estilos HTML disponibles. Comprueba el resultado antes de escribir en Word.")
        except Exception as exc:
            messagebox.showerror("No se pudo pegar con formato", f"{exc}\n\n{traceback.format_exc()}", parent=self.root)

    @staticmethod
    def _effective_paragraph_property(paragraph, name: str):
        """Resuelve un atributo de párrafo heredado desde sus estilos de Word."""
        try:
            value = getattr(paragraph.paragraph_format, name)
        except Exception:
            value = None
        if value is not None:
            return value
        style = getattr(paragraph, "style", None)
        seen = set()
        while style is not None and id(style) not in seen:
            seen.add(id(style))
            try:
                value = getattr(style.paragraph_format, name)
            except Exception:
                value = None
            if value is not None:
                return value
            style = getattr(style, "base_style", None)
        return None

    @staticmethod
    def _effective_run_property(run, paragraph, name: str):
        """Resuelve las propiedades de fuente directas, de estilo de carácter y de párrafo."""
        try:
            value = getattr(run.font, name)
        except Exception:
            value = None
        if value is not None:
            return value
        style = getattr(run, "style", None)
        seen = set()
        while style is not None and id(style) not in seen:
            seen.add(id(style))
            try:
                value = getattr(style.font, name)
            except Exception:
                value = None
            if value is not None:
                return value
            style = getattr(style, "base_style", None)
        style = getattr(paragraph, "style", None)
        seen.clear()
        while style is not None and id(style) not in seen:
            seen.add(id(style))
            try:
                value = getattr(style.font, name)
            except Exception:
                value = None
            if value is not None:
                return value
            style = getattr(style, "base_style", None)
        return None

    def _docx_paragraph_meta(self, paragraph) -> dict:
        pf = paragraph.paragraph_format
        alignment = self._effective_paragraph_property(paragraph, "alignment")
        align_map = {0: "left", 1: "center", 2: "right", 3: "justify"}
        meta: dict = {"alignment": align_map.get(int(alignment), "left") if alignment is not None else "left"}
        for prop, key in (("left_indent", "left_indent_pt"), ("right_indent", "right_indent_pt"),
                          ("first_line_indent", "first_line_indent_pt"), ("space_before", "space_before_pt"),
                          ("space_after", "space_after_pt")):
            value = self._effective_paragraph_property(paragraph, prop)
            meta[key] = float(value.pt) if value is not None and hasattr(value, "pt") else (float(value) if value is not None else 0.0)
        line_rule = self._effective_paragraph_property(paragraph, "line_spacing_rule")
        line_value = self._effective_paragraph_property(paragraph, "line_spacing")
        if line_rule is None:
            if isinstance(line_value, (float, int)):
                line_rule = 5
            elif line_value is not None and hasattr(line_value, "pt"):
                line_rule = 4
            else:
                line_rule = 0
        rule_map = {0: "single", 1: "one_point_five", 2: "double", 3: "at_least", 4: "exactly", 5: "multiple"}
        try:
            rule_num = int(line_rule)
        except Exception:
            rule_num = 0
        meta["line_spacing_type"] = rule_map.get(rule_num, "single")
        if meta["line_spacing_type"] == "multiple":
            meta["line_spacing_value"] = float(line_value) if line_value is not None else 1.0
        elif meta["line_spacing_type"] in ("exactly", "at_least"):
            meta["line_spacing_value"] = float(line_value.pt) if hasattr(line_value, "pt") else (float(line_value) if line_value is not None else 12.0)
        else:
            meta["line_spacing_value"] = {"single": 1.0, "one_point_five": 1.5, "double": 2.0}.get(meta["line_spacing_type"], 1.0)
        for prop, key in (("keep_together", "keep_together"), ("keep_with_next", "keep_with_next"),
                          ("page_break_before", "page_break_before")):
            value = self._effective_paragraph_property(paragraph, prop)
            meta[key] = bool(value) if value is not None else False
        return meta

    def _docx_theme_fonts(self, document) -> dict[str, str]:
        """Lee las fuentes mayor/menor del tema DOCX para no reemplazarlas por Arial."""
        fonts = {"major": "Arial", "minor": "Arial"}
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        try:
            for relationship in document.part.rels.values():
                if relationship.reltype.endswith("/theme") and not relationship.is_external:
                    root = ET.fromstring(relationship.target_part.blob)
                    for key, path in (("major", ".//a:fontScheme/a:majorFont/a:latin"),
                                      ("minor", ".//a:fontScheme/a:minorFont/a:latin")):
                        node = root.find(path, ns)
                        if node is not None and node.attrib.get("typeface"):
                            fonts[key] = node.attrib["typeface"]
                    break
        except Exception:
            pass
        return fonts

    def _theme_font_for_object(self, obj) -> str | None:
        """Obtiene una familia explícita o resuelve asciiTheme/hAnsiTheme del objeto DOCX."""
        try:
            if hasattr(obj, "font") and obj.font.name:
                return str(obj.font.name)
        except Exception:
            pass
        try:
            from docx.oxml.ns import qn
            element = getattr(obj, "_element", None)
            rpr = getattr(element, "rPr", None) if element is not None else None
            rfonts = getattr(rpr, "rFonts", None) if rpr is not None else None
            if rfonts is None and element is not None:
                # CT_RPr may expose rFonts via child lookup depending on the object.
                try: rfonts = element.rPr.rFonts
                except Exception: rfonts = None
            if rfonts is not None:
                direct = rfonts.get(qn("w:ascii")) or rfonts.get(qn("w:hAnsi"))
                if direct:
                    return direct
                theme = (rfonts.get(qn("w:asciiTheme")) or rfonts.get(qn("w:hAnsiTheme"))
                         or rfonts.get(qn("w:cstheme")) or "")
                if theme.startswith("major"):
                    return self._active_theme_fonts.get("major")
                if theme.startswith("minor"):
                    return self._active_theme_fonts.get("minor")
        except Exception:
            pass
        return None

    def _effective_docx_run_style(self, run, paragraph, document) -> dict:
        family = self._effective_run_property(run, paragraph, "name")
        if not family:
            objects = [run, getattr(run, "style", None), getattr(paragraph, "style", None)]
            try: objects.append(document.styles["Normal"])
            except Exception: pass
            for obj in objects:
                if obj is not None:
                    family = self._theme_font_for_object(obj)
                    if family:
                        break
        if not family:
            family = self._active_theme_fonts.get("minor") or "Arial"
        size = self._effective_run_property(run, paragraph, "size")
        normal_font = None
        try:
            normal_font = document.styles["Normal"].font
        except Exception:
            pass
        family = family or (normal_font.name if normal_font else None) or "Arial"
        if size is not None and hasattr(size, "pt"):
            size_pt = float(size.pt)
        else:
            normal_size = normal_font.size if normal_font else None
            size_pt = float(normal_size.pt) if normal_size is not None and hasattr(normal_size, "pt") else 11.0
        style = {"family": family, "size": size_pt}
        for prop, key in (("bold", "bold"), ("italic", "italic"), ("underline", "underline"), ("strike", "strike")):
            value = self._effective_run_property(run, paragraph, prop)
            if value:
                style[key] = True
        try:
            # El color RGB directo se conserva; si depende del tema, se deja el color automático.
            color = run.font.color
            if color and color.rgb:
                style["color"] = f"#{color.rgb}"
            else:
                inherited = None
                cstyle = getattr(run, "style", None)
                while cstyle is not None and inherited is None:
                    try:
                        c = cstyle.font.color
                        inherited = f"#{c.rgb}" if c and c.rgb else None
                    except Exception:
                        pass
                    cstyle = getattr(cstyle, "base_style", None)
                if inherited:
                    style["color"] = inherited
        except Exception:
            pass
        return style

    def _docx_list_prefix(self, document, paragraph, counters: dict) -> str:
        """Convierte numeración automática/viñetas DOCX a prefijos visibles en el editor."""
        try:
            ppr = paragraph._p.pPr
            num_pr = ppr.numPr if ppr is not None else None
            num_id = int(num_pr.numId.val) if num_pr is not None and num_pr.numId is not None else None
            level = int(num_pr.ilvl.val) if num_pr is not None and num_pr.ilvl is not None else 0
            if num_id is None:
                return ""
            numbering = document.part.numbering_part.element
            num_nodes = numbering.xpath(f'./w:num[@w:numId="{num_id}"]')
            abstract_id = int(num_nodes[0].abstractNumId.val) if num_nodes else None
            if abstract_id is None:
                return ""
            abstract_nodes = numbering.xpath(f'./w:abstractNum[@w:abstractNumId="{abstract_id}"]')
            if not abstract_nodes:
                return ""
            levels = abstract_nodes[0].xpath(f'./w:lvl[@w:ilvl="{level}"]')
            if not levels:
                levels = abstract_nodes[0].xpath('./w:lvl[@w:ilvl="0"]')
            if not levels:
                return ""
            lvl = levels[0]
            fmt = lvl.numFmt.val if lvl.numFmt is not None else "decimal"
            template = lvl.lvlText.val if lvl.lvlText is not None else ("•" if fmt == "bullet" else f"%{level + 1}.")
            if fmt == "bullet":
                return template + " "
            key = (num_id, level)
            counters[key] = counters.get(key, 0) + 1
            for deeper in range(level + 1, 9):
                counters[(num_id, deeper)] = 0
            def replace_level(match):
                requested = int(match.group(1)) - 1
                count = counters.get((num_id, requested), 1)
                if fmt in ("upperRoman", "lowerRoman"):
                    # Roman numerals are kept simple but correct for usual list lengths.
                    n = max(1, count); vals = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
                    roman = ""
                    for number, symbol in vals:
                        while n >= number: roman += symbol; n -= number
                    return roman if fmt == "upperRoman" else roman.lower()
                if fmt in ("upperLetter", "lowerLetter"):
                    n = max(1, count); letters = ""
                    while n:
                        n, rem = divmod(n - 1, 26); letters = chr(65 + rem) + letters
                    return letters if fmt == "upperLetter" else letters.lower()
                return str(count)
            template = re.sub(r"%(\d+)", replace_level, template)
            return template + " "
        except Exception:
            return ""

    def _insert_docx_run(self, text: str, style: dict):
        """Inserta runs DOCX conservando los saltos manuales dentro del mismo párrafo."""
        pieces = text.split("\n")
        for index, piece in enumerate(pieces):
            if piece:
                self.insert_styled(piece, style)
            if index < len(pieces) - 1:
                start = self.editor.index("end-1c")
                self.editor.insert("end-1c", "\n")
                end = self.editor.index("end-1c")
                self.editor.tag_add(self.soft_break_tag, start, end)

    def _open_docx(self, path: str):
        # Importación diferida: python-docx puede añadir tiempo de arranque y no
        # hace falta para TXT, HTML ni para el modo básico de escritura.
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError(
                "Para abrir archivos DOCX instala la dependencia opcional ejecutando "
                "instalar_dependencias.bat y reinicia la aplicación."
            ) from exc
        document = Document(path)
        self.imported_page_setup = self._extract_page_setup(document)
        self.page_setup = dict(self.imported_page_setup) if self.imported_page_setup else None
        self._active_theme_fonts = self._docx_theme_fonts(document)
        list_counters: dict[tuple[int, int], int] = {}
        fallback_number = 0
        for paragraph in document.paragraphs:
            pstart = self.editor.index("end-1c")
            prefix = self._docx_list_prefix(document, paragraph, list_counters)
            pstyle_name = (paragraph.style.name or "").lower()
            if not prefix:
                if "bullet" in pstyle_name or "viñeta" in pstyle_name:
                    prefix = "• "
                    fallback_number = 0
                elif "number" in pstyle_name or "numerada" in pstyle_name:
                    fallback_number += 1
                    prefix = f"{fallback_number}. "
                else:
                    fallback_number = 0
            if prefix:
                self.editor.insert("end-1c", prefix)
            for run in paragraph.runs:
                self._insert_docx_run(run.text, self._effective_docx_run_style(run, paragraph, document))
            self.editor.insert("end-1c", "\n")
            pend = self.editor.index("end-1c")
            self._set_paragraph_meta_range(pstart, pend, self._docx_paragraph_meta(paragraph), remove_overlap=False)

    def _char_style_html(self, index: str) -> dict:
        style = {"family": "Arial", "size": 11}
        for name in self.editor.tag_names(index):
            if name in self.format_tags: style.update(self.format_tags[name])
        return style

    @staticmethod
    def _css_from_style(style: dict) -> str:
        css = []
        if style.get("family"): css.append("font-family:'" + str(style["family"]).replace("'", "") + "'")
        if style.get("size"): css.append(f"font-size:{float(style['size']):g}pt")
        if style.get("bold"): css.append("font-weight:bold")
        if style.get("italic"): css.append("font-style:italic")
        decorations = []
        if style.get("underline"): decorations.append("underline")
        if style.get("strike"): decorations.append("line-through")
        if decorations: css.append("text-decoration:" + " ".join(decorations))
        if style.get("color"): css.append("color:" + str(style["color"]))
        return ";".join(css)

    @staticmethod
    def _css_from_paragraph_meta(meta: dict) -> str:
        css: list[str] = []
        if meta.get("alignment") in ("left", "center", "right", "justify"):
            css.append(f"text-align:{meta['alignment']}")
        point_map = (("left_indent_pt", "margin-left"), ("right_indent_pt", "margin-right"),
                     ("first_line_indent_pt", "text-indent"), ("space_before_pt", "margin-top"),
                     ("space_after_pt", "margin-bottom"))
        for key, css_name in point_map:
            if meta.get(key) is not None:
                css.append(f"{css_name}:{float(meta[key]):g}pt")
        spacing_type = meta.get("line_spacing_type")
        spacing_value = meta.get("line_spacing_value")
        if spacing_type == "single":
            css.append("line-height:1")
        elif spacing_type == "one_point_five":
            css.append("line-height:1.5")
        elif spacing_type == "double":
            css.append("line-height:2")
        elif spacing_type == "multiple" and spacing_value is not None:
            css.append(f"line-height:{float(spacing_value):g}")
        elif spacing_type in ("exactly", "at_least") and spacing_value is not None:
            css.append(f"line-height:{float(spacing_value):g}pt")
        return ";".join(css)

    def build_html_fragment(self, include_page_setup: bool = False) -> str:
        text = self.editor.get("1.0", "end-1c")
        lines = text.split("\n")
        style_runs = self._collect_style_runs()
        run_index = 0
        out = []
        base_css = "font-family:Arial;font-size:11pt;white-space:pre-wrap"

        # Construye grupos por identidad de etiqueta de párrafo, no solo por los
        # valores de formato. Así, los saltos manuales internos de un párrafo DOCX
        # se exportan como <br>, mientras que los párrafos distintos siguen separados.
        line_info = []
        absolute_offset = 0
        for line_num, line in enumerate(lines, start=1):
            paragraph_tag = self._paragraph_tag_at(f"{line_num}.0")
            line_info.append((line, absolute_offset, paragraph_tag,
                              self._paragraph_meta_at(f"{line_num}.0")))
            absolute_offset += len(line) + 1
        groups: list[list[tuple[str, int, str | None, dict]]] = []
        for info in line_info:
            if info[2] is not None and groups and groups[-1][-1][2] == info[2]:
                groups[-1].append(info)
            else:
                groups.append([info])

        def render_line(line: str, start_offset: int) -> str:
            nonlocal run_index
            parts = []
            cursor = start_offset
            line_end = start_offset + len(line)
            while run_index < len(style_runs) and style_runs[run_index][1] <= cursor:
                run_index += 1
            while cursor < line_end:
                while run_index < len(style_runs) and style_runs[run_index][1] <= cursor:
                    run_index += 1
                if run_index >= len(style_runs):
                    run_end, style = line_end, {"family": "Arial", "size": 11}
                else:
                    _run_start, run_end, style = style_runs[run_index]
                    run_end = min(run_end, line_end)
                if run_end <= cursor:
                    run_end = line_end
                start_col = cursor - start_offset
                end_col = run_end - start_offset
                txt = html.escape(line[start_col:end_col], quote=False)
                css = self._css_from_style(style)
                parts.append(f'<span style="{css}">{txt}</span>' if css else txt)
                cursor = run_end
            return "".join(parts) or "&nbsp;"

        for group in groups:
            first_line, _first_offset, _tag, paragraph_meta = group[0]
            body = "<br>".join(render_line(line, offset) for line, offset, _ptag, _meta in group)
            paragraph_css = self._css_from_paragraph_meta(paragraph_meta)
            pstyles = [paragraph_css] if paragraph_css else []
            # CSS de párrafo (incluido el interlineado) tiene prioridad sobre los
            # valores neutros. La @page se agrega por separado al exportar/pegar.
            style_attr = ";".join([base_css, "margin-top:0", "margin-bottom:0"] + pstyles)
            data_attrs = []
            spacing_type = paragraph_meta.get("line_spacing_type")
            spacing_value = paragraph_meta.get("line_spacing_value")
            if spacing_type:
                data_attrs.append(f'data-line-spacing-type="{html.escape(str(spacing_type), quote=True)}"')
                if spacing_value is not None:
                    data_attrs.append(f'data-line-spacing-value="{float(spacing_value):g}"')
            for key, attr in (("keep_together", "data-keep-together"), ("keep_with_next", "data-keep-with-next"),
                              ("page_break_before", "data-page-break-before")):
                if key in paragraph_meta:
                    data_attrs.append(f'{attr}="{"true" if paragraph_meta[key] else "false"}"')
            attrs = f' style="{html.escape(style_attr, quote=True)}"' + (" " + " ".join(data_attrs) if data_attrs else "")
            out.append(f"<p{attrs}>{body}</p>")
        fragment = "\n".join(out)
        page_css = self._page_css()
        if include_page_setup and page_css:
            fragment = f"<style>{page_css}</style>" + fragment
        return fragment

    def save_html(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Guardar formato HTML", defaultextension=".html", initialfile="documento.html", filetypes=[("Página HTML", "*.html")])
        if not path: return
        fragment = self.build_html_fragment()
        page_css = self._page_css()
        style_tag = f"<style>{page_css}</style>" if page_css else ""
        doc = '<!DOCTYPE html><html><head><meta charset="utf-8">' + style_tag + '</head><body>' + fragment + '</body></html>'
        try:
            Path(path).write_text(doc, encoding="utf-8")
            self.status.set(f"Guardado: {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self.root)

    def _start_hotkeys(self):
        if IS_WINDOWS:
            def watch():
                user32 = ctypes.windll.user32
                prev8 = prev9 = False
                while not self.closing:
                    state8 = bool(user32.GetAsyncKeyState(0x77) & 0x8000)
                    state9 = bool(user32.GetAsyncKeyState(0x78) & 0x8000)
                    if state8 and not prev8: self.root.after(0, self.stop)
                    if state9 and not prev9: self.root.after(0, self.pause_toggle)
                    prev8, prev9 = state8, state9
                    time.sleep(0.04)
            self.hotkey_thread = threading.Thread(target=watch, daemon=True, name="hotkeys")
            self.hotkey_thread.start()
        elif IS_LINUX:
            try:
                pynput_keyboard = importlib.import_module("pynput.keyboard")
                def on_press(key):
                    if key == pynput_keyboard.Key.f8:
                        self.root.after(0, self.stop)
                    elif key == pynput_keyboard.Key.f9:
                        self.root.after(0, self.pause_toggle)
                self.hotkey_listener = pynput_keyboard.Listener(on_press=on_press, suppress=False)
                self.hotkey_listener.daemon = True
                self.hotkey_listener.start()
                self._pynput_keyboard_module = pynput_keyboard
            except Exception as exc:
                if hasattr(self, "status"):
                    self.status.set(f"Atajos globales F8/F9 no disponibles: {exc}. También puedes usar los botones de la aplicación.")

    def _character_style_runs(self, text: str) -> list[tuple[int, int, dict]]:
        """Obtiene formato por segmentos; evita guardar un diccionario por carácter."""
        # _collect_style_runs usa el texto del editor, que es la fuente de los
        # estilos. El parámetro se mantiene para documentar/validar el texto que
        # se va a enviar y facilitar futuras extensiones.
        if self.editor.get("1.0", "end-1c") != text:
            return []
        return self._collect_style_runs()

    def start(self):
        if not IS_SUPPORTED_OS:
            messagebox.showerror("Sistema no compatible", f"La escritura está habilitada en Windows y Linux; este equipo usa {SYSTEM_NAME or sys.platform}.", parent=self.root)
            return
        if (self.worker and self.worker.is_alive()) or self.web_job_id:
            messagebox.showinfo("En ejecución", "Ya hay una operación activa. Deténla antes de iniciar otra.", parent=self.root)
            return
        text = self.editor.get("1.0", "end-1c")
        if not text:
            messagebox.showwarning("Texto vacío", "Escribe o carga algún texto antes de iniciar.", parent=self.root)
            return
        try:
            speed = max(1, min(240, int(self.speed.get())))
            count = max(1, min(30, int(self.countdown.get())))
        except (ValueError, tk.TclError):
            messagebox.showerror("Configuración incorrecta", "Revisa la velocidad y la cuenta regresiva.", parent=self.root)
            return

        mode = self.mode.get()
        if IS_LINUX and mode in ("rich", "paste", "background"):
            messagebox.showerror(
                "Función no disponible en Linux",
                "En Linux están disponibles 'Ventana activa' y 'Página web'. "
                "La automatización de Microsoft Word mediante COM, el portapapeles HTML de Windows "
                "y los mensajes Win32 en segundo plano son exclusivos de Windows.",
                parent=self.root,
            )
            return
        target_title = ""
        character_style_runs = None
        paragraph_format_runs = None
        soft_break_offsets = None
        page_setup = dict(self.page_setup) if self.page_setup else None
        web_target = None
        web_job_id = None
        google_docs_fallback = False
        try:
            if mode == "web":
                if self.web_bridge is None or self.web_bridge.client_count() == 0:
                    self.refresh_web_pages()
                    if self.web_bridge is None or self.web_bridge.client_count() == 0:
                        return
                tab = self.web_tab_map.get(self.web_tab_var.get())
                if not tab:
                    messagebox.showwarning("Selecciona una página", "Pulsa 'Actualizar páginas' y elige una pestaña web.", parent=self.root)
                    return
                tab_url = str(tab.get("url") or "")
                parsed_url = urlsplit(tab_url)
                is_google_docs = parsed_url.netloc.lower().endswith("docs.google.com") and "/document/" in parsed_url.path
                tab_title = str(tab.get("title") or "Página web")
                browser = str(tab.get("browser") or "Chromium")
                if is_google_docs:
                    # Google Docs uses an editor surface that is not a standard editable DOM field.
                    # Send genuine OS-level keyboard input to the active window instead.
                    mode = "type"
                    google_docs_fallback = True
                    target_title = f"{browser}: {tab_title} (Google Docs)"
                    backend = create_keyboard_backend()
                else:
                    field = self.web_field_map.get(self.web_field_var.get())
                    if not field:
                        messagebox.showwarning("Selecciona un campo", "La página seleccionada no tiene un campo de texto compatible. Elige otra página o vuelve a escanearla.", parent=self.root)
                        return
                    web_target = {
                        "client_id": tab.get("client_id"),
                        "tab_id": int(tab.get("tabId")),
                        "frame_id": int(field.get("frameId", 0)),
                        "field_id": str(field.get("fieldId")),
                        "tab_title": tab_title,
                        "url": tab_url,
                        "browser": browser,
                        "field_label": str(field.get("label") or field.get("placeholder") or field.get("name") or field.get("kind") or "campo editable"),
                    }
                    if not web_target["client_id"] or not web_target["field_id"]:
                        messagebox.showerror("Destino web inválido", "Actualiza la lista de páginas y vuelve a seleccionar el campo.", parent=self.root)
                        return
                    target_title = f"{web_target['browser']}: {web_target['tab_title']}"
                    web_job_id = uuid.uuid4().hex
                    backend = None
            elif mode == "background":
                target_title = self.target_window.get()
                target_hwnd = self.window_map.get(target_title)
                if not target_hwnd:
                    messagebox.showwarning("Selecciona una ventana", "Pulsa 'Actualizar ventanas' y selecciona la ventana de destino.", parent=self.root)
                    return
                backend = BackgroundWindowWriter(target_hwnd)
                if not backend.user32.IsWindow(target_hwnd):
                    messagebox.showerror("Ventana no disponible", "La ventana elegida ya no existe. Actualiza la lista.", parent=self.root)
                    return
            elif mode in ("word", "rich"):
                try:
                    import pythoncom  # noqa: F401
                    import win32com.client  # noqa: F401
                except ImportError as exc:
                    raise RuntimeError("Para el modo Word instala las dependencias con instalar_dependencias.bat y vuelve a abrir el programa.") from exc
                character_style_runs = self._character_style_runs(text)
                paragraph_format_runs = self._paragraph_runs(text)
                soft_break_offsets = self._soft_break_offsets(text)
                backend = WordAutomationWriter()
            else:
                backend = create_keyboard_backend()
                if mode == "paste":
                    set_windows_clipboard_html(self.build_html_fragment(include_page_setup=True), text)
        except Exception as exc:
            messagebox.showerror("No se pudo preparar la escritura", str(exc), parent=self.root)
            return

        self.stop_event.clear()
        self.pause_event.set()
        if google_docs_fallback:
            self.web_active_target = None
            self.web_job_id = None
            self.web_job_dispatched = False
            self.status.set(f"Google Docs detectado. Durante la cuenta regresiva, cambia al navegador y haz clic dentro del documento. Escritura por teclado del sistema en {count} segundos; F8 cancela.")
        elif mode == "web":
            self.web_active_target = web_target
            self.web_job_id = web_job_id
            self.web_job_dispatched = False
            self.status.set(f"Destino web: {target_title}. Campo: {web_target['field_label']}. Inicio en {count} segundos… F8 cancela.")
        elif mode == "background":
            self.status.set("Modo experimental: durante la cuenta regresiva, cambia a la ventana seleccionada y coloca el cursor en su campo de texto.")
        elif mode in ("word", "rich"):
            self.status.set(f"Modo Word con formato: se escribirá letra por letra. Abre el documento, coloca el cursor y el inicio será en {count} segundos; F8 cancela.")
        else:
            self.status.set(f"Cambia al programa de destino. Inicio en {count} segundos. F8 cancela.")
        self.worker = threading.Thread(
            target=self._typing_worker,
            args=(backend, text, speed, count, mode, self.tabs_as_spaces.get(), target_title,
                  character_style_runs, paragraph_format_runs, page_setup, soft_break_offsets,
                  web_target, web_job_id, google_docs_fallback),
            daemon=True,
            name="typing-worker",
        )
        self.worker.start()

    def _typing_worker(self, backend, text: str, speed: int, count: int, mode: str, tabs: bool,
                       target_title: str = "", character_style_runs: list[tuple[int, int, dict]] | None = None,
                       paragraph_format_runs: list[tuple[int, int, dict]] | None = None,
                       page_setup: dict | None = None, soft_break_offsets: set[int] | None = None,
                       web_target: dict | None = None, web_job_id: str | None = None,
                       google_docs_fallback: bool = False):
        try:
            for sec in range(count, 0, -1):
                if self.stop_event.is_set():
                    return
                if google_docs_fallback:
                    message = f"Google Docs: cambia al navegador y haz clic dentro del documento. Inicio en {sec} s… (F8 cancela)"
                elif mode == "web":
                    field_label = (web_target or {}).get("field_label", "campo editable")
                    message = f"Página web: {target_title} · {field_label}. Inicio en {sec} s… (F8 cancela)"
                elif mode == "background":
                    message = f"Destino: {target_title}. Cambia a esa ventana y coloca el cursor; inicio en {sec} s… (F8 cancela)"
                elif mode in ("word", "rich"):
                    message = f"Word: coloca el cursor en el documento; la escritura conservará los estilos y comenzará en {sec} s… (F8 cancela)"
                else:
                    message = f"Cambia a la ventana de destino. Empezará en {sec} s… (F8 para cancelar)"
                self.root.after(0, lambda m=message: self.status.set(m))
                if self.stop_event.wait(1):
                    return

            if mode == "web":
                if not self.web_bridge or not web_target or not web_job_id:
                    raise RuntimeError("No hay un puente web conectado o el destino ya no está seleccionado.")
                if len(text.encode("utf-8")) > 6 * 1024 * 1024:
                    raise RuntimeError("El texto del modo web supera el límite de seguridad de 6 MiB. Divide el contenido en partes más pequeñas.")
                payload = {
                    "type": "start_job",
                    "job_id": web_job_id,
                    "tab_id": web_target["tab_id"],
                    "frame_id": web_target["frame_id"],
                    "field_id": web_target["field_id"],
                    "text": text,
                    "speed": speed,
                    "tabs_as_spaces": tabs,
                    "start_paused": not self.pause_event.is_set(),
                }
                self.web_job_dispatched = True
                if not self.web_bridge.send(web_target["client_id"], payload):
                    self.web_job_dispatched = False
                    raise RuntimeError("La extensión se desconectó. Vuelve a pulsar 'Actualizar páginas'.")
                self.root.after(0, lambda: self.status.set("Solicitud enviada a la página web. Escribiendo letra por letra en segundo plano… F8 detiene · F9 pausa."))
                return
            if mode == "background":
                backend.resolve_control()
                self.root.after(0, lambda: self.status.set("Enviando caracteres en segundo plano. Si no aparecen, la aplicación de destino puede bloquear este método. F8 detiene; F9 pausa."))
            elif mode in ("word", "rich"):
                backend.initialize(page_setup)
                self.root.after(0, lambda: self.status.set("Escribiendo carácter por carácter en Microsoft Word. Se aplican estilos de letra y párrafo; F8 detiene y F9 pausa."))
            elif mode == "paste":
                backend.paste()
                self.root.after(0, lambda: self.status.set("Pegado enviado. El formato depende de que el destino admita HTML enriquecido."))
                return

            total = len(text)
            interval = 1.0 / speed
            # El plazo se calcula contra el reloj monotónico. Antes se esperaba
            # 1/velocidad DESPUÉS de cada envío, sumando el tiempo de Windows/COM
            # y haciendo que la velocidad real fuese mucho menor que la elegida.
            next_deadline = time.perf_counter()
            style_run_index = 0
            paragraph_run_index = 0
            last_status_time = time.perf_counter()
            for i, char in enumerate(text, 1):
                if self.stop_event.is_set():
                    return
                was_paused = False
                while not self.pause_event.wait(0.05):
                    if self.stop_event.is_set():
                        return
                    was_paused = True
                if was_paused:
                    # No intentes recuperar el tiempo transcurrido durante una
                    # pausa enviando caracteres en ráfaga al reanudar.
                    next_deadline = time.perf_counter()
                if mode in ("word", "rich"):
                    position = i - 1
                    while (character_style_runs and style_run_index < len(character_style_runs)
                           and position >= character_style_runs[style_run_index][1]):
                        style_run_index += 1
                    style = None
                    if character_style_runs and style_run_index < len(character_style_runs):
                        run_start, run_end, run_style = character_style_runs[style_run_index]
                        if run_start <= position < run_end:
                            style = run_style
                    # El formato de párrafo se aplica una vez al comienzo de cada
                    # párrafo; no se confunde con el formato de cada carácter.
                    while (paragraph_format_runs and paragraph_run_index < len(paragraph_format_runs)
                           and position >= paragraph_format_runs[paragraph_run_index][1]
                           and paragraph_format_runs[paragraph_run_index][1] > paragraph_format_runs[paragraph_run_index][0]):
                        paragraph_run_index += 1
                    if paragraph_format_runs and paragraph_run_index < len(paragraph_format_runs):
                        para_start, para_end, para_meta = paragraph_format_runs[paragraph_run_index]
                        if position == para_start and para_start < para_end and para_meta:
                            backend.apply_paragraph_format(para_meta)
                    if char == "\n" and soft_break_offsets and position in soft_break_offsets:
                        backend.type_soft_break()
                    else:
                        backend.type_char(char, tabs, style)
                else:
                    backend.type_char(char, tabs)
                now = time.perf_counter()
                if i == total or now - last_status_time >= 0.15:
                    self.root.after(0, lambda x=i, n=total: self.status.set(f"Escribiendo… {x}/{n} caracteres"))
                    last_status_time = now

                next_deadline += interval
                delay = next_deadline - time.perf_counter()
                if delay > 0:
                    if self.stop_event.wait(delay):
                        return
                else:
                    # Si el backend es más lento que el ritmo solicitado, no
                    # acumules deuda de tiempo ni produzcas una ráfaga posterior.
                    next_deadline = time.perf_counter()
            self.root.after(0, lambda: self.status.set("Texto escrito completamente."))
        except Exception as exc:
            error_text = str(exc)
            if mode == "web":
                self.root.after(0, lambda e=error_text, j=web_job_id: self._finish_web_job_error(j, e))
            else:
                self.root.after(0, lambda e=error_text: self.status.set(f"Error al escribir: {e}"))
        finally:
            if mode in ("word", "rich") and backend is not None:
                try:
                    backend.cleanup()
                except Exception:
                    pass

    def _send_web_control(self, action: str) -> bool:
        if not self.web_bridge or not self.web_active_target or not self.web_job_id or not self.web_job_dispatched:
            return False
        return self.web_bridge.send(self.web_active_target.get("client_id", ""), {
            "type": "control_job", "action": action, "job_id": self.web_job_id,
            "tab_id": self.web_active_target.get("tab_id"),
            "frame_id": self.web_active_target.get("frame_id", 0),
        })

    def _finish_web_job_error(self, job_id: str | None, error: str):
        if job_id and self.web_job_id == job_id:
            self.web_job_id = None
            self.web_active_target = None
            self.web_job_dispatched = False
        self.status.set(f"No se pudo completar la escritura web: {error}")

    def stop(self):
        self.stop_event.set(); self.pause_event.set()
        if self.web_job_id:
            if self.web_job_dispatched:
                sent = self._send_web_control("stop")
                if sent:
                    self.status.set("Deteniendo la escritura en la página web…")
                else:
                    self.web_job_id = None
                    self.web_active_target = None
                    self.web_job_dispatched = False
                    self.status.set("La conexión web se perdió; se canceló la operación local.")
            else:
                self.web_job_id = None
                self.web_active_target = None
                self.web_job_dispatched = False
                self.status.set("Cuenta regresiva cancelada.")
        else:
            self.status.set("Deteniendo la operación…")

    def pause_toggle(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self._send_web_control("pause")
            self.status.set("Pausado. F9 reanuda y F8 detiene.")
        else:
            self.pause_event.set()
            self._send_web_control("resume")
            self.status.set("Escritura reanudada.")

    def close(self):
        self.closing = True
        self.stop_event.set(); self.pause_event.set()
        if self.hotkey_listener is not None:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        if self._count_update_id is not None:
            try:
                self.root.after_cancel(self._count_update_id)
            except tk.TclError:
                pass
            self._count_update_id = None
        if self.web_bridge:
            if self.web_job_id and self.web_job_dispatched:
                self._send_web_control("stop")
                time.sleep(0.05)
            self.web_bridge.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = EscritorAutomatico(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log_path = Path(__file__).with_name("error_inicio.txt")
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
