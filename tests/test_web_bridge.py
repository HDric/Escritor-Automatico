import json
import os
import queue
import secrets
import threading
import time
import unittest
from unittest.mock import patch

from websockets.sync.client import connect

from bridge_security import (
    encode_nonce,
    make_client_proof,
    make_server_proof,
    decode_pairing_code,
)
from escritor_automatico import WebPageBridge, WEB_EXTENSION_ID


class FakeAuthenticatedSocket:
    def __init__(self, secret, invalid=False):
        self.secret = secret
        self.invalid = invalid
        self.sent = []
        self.server_nonce = None
        self.client_nonce = secrets.token_bytes(32)

    def send(self, message):
        data = json.loads(message)
        self.sent.append(data)
        if data.get("type") == "auth_challenge":
            self.server_nonce = decode_pairing_code(data["nonce"])

    def recv(self, timeout=None):
        proof_secret = os.urandom(32) if self.invalid else self.secret
        proof = make_client_proof(proof_secret, self.server_nonce, self.client_nonce)
        return json.dumps({
            "type": "auth_response",
            "client_nonce": encode_nonce(self.client_nonce),
            "proof": encode_nonce(proof),
        })


class WebBridgeSecurityTests(unittest.TestCase):
    def test_server_authenticates_extension_before_accepting_it(self):
        secret = secrets.token_bytes(32)
        bridge = WebPageBridge.__new__(WebPageBridge)
        bridge.pairing_code = encode_nonce(secret)
        socket = FakeAuthenticatedSocket(secret)
        self.assertTrue(bridge._authenticate_client(socket))
        self.assertEqual(socket.sent[0]["type"], "auth_challenge")
        self.assertEqual(socket.sent[1]["type"], "auth_ok")
        expected = make_server_proof(secret, socket.server_nonce, socket.client_nonce)
        self.assertEqual(decode_pairing_code(socket.sent[1]["proof"]), expected)

    def test_server_rejects_an_invalid_pairing_secret(self):
        bridge = WebPageBridge.__new__(WebPageBridge)
        bridge.pairing_code = encode_nonce(secrets.token_bytes(32))
        socket = FakeAuthenticatedSocket(secrets.token_bytes(32))
        self.assertFalse(bridge._authenticate_client(socket))

    def test_event_queue_is_bounded_and_accounting_is_reduced_on_read(self):
        bridge = WebPageBridge.__new__(WebPageBridge)
        bridge.events = queue.Queue(maxsize=6)
        bridge._event_lock = threading.Lock()
        bridge._queued_event_bytes = 0
        bridge._event_sizes = {}
        for index in range(20):
            bridge._emit({"event": "test", "value": index})
        self.assertEqual(bridge.events.qsize(), 6)
        self.assertGreater(bridge._queued_event_bytes, 0)
        bridge.get_event_nowait()
        self.assertEqual(bridge.events.qsize(), 5)
        self.assertGreaterEqual(bridge._queued_event_bytes, 0)

    def test_real_loopback_server_listens_and_authenticates_extension_origin(self):
        bridge = WebPageBridge()
        bridge.PORT = 0  # Let the OS select an available port for an isolated test.
        try:
            bridge.start()
            self.assertIsNotNone(bridge.bound_port)
            with connect(
                f"ws://{bridge.HOST}:{bridge.bound_port}",
                origin=f"chrome-extension://{WEB_EXTENSION_ID}",
                open_timeout=3,
            ) as websocket:
                challenge = json.loads(websocket.recv(timeout=3))
                self.assertEqual(challenge.get("type"), "auth_challenge")
                server_nonce = decode_pairing_code(challenge["nonce"])
                client_nonce = secrets.token_bytes(32)
                secret = decode_pairing_code(bridge.pairing_code)
                proof = make_client_proof(secret, server_nonce, client_nonce)
                websocket.send(json.dumps({
                    "type": "auth_response",
                    "client_nonce": encode_nonce(client_nonce),
                    "proof": encode_nonce(proof),
                }))
                auth_ok = json.loads(websocket.recv(timeout=3))
                self.assertEqual(auth_ok.get("type"), "auth_ok")
                expected = make_server_proof(secret, server_nonce, client_nonce)
                self.assertEqual(decode_pairing_code(auth_ok["proof"]), expected)

                client_id = None
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not client_id:
                    try:
                        event = bridge.get_event_nowait()
                        if event.get("event") == "connected":
                            client_id = event.get("client_id")
                    except queue.Empty:
                        time.sleep(0.02)
                self.assertTrue(client_id, "El cliente autenticado no se registró en la aplicación")

                diagnostic_id = "0123456789abcdef0123456789abcdef"
                self.assertTrue(bridge.send(client_id, {
                    "type": "diagnostic_ping", "diagnostic_id": diagnostic_id
                }))
                ping = json.loads(websocket.recv(timeout=3))
                self.assertEqual(ping.get("type"), "diagnostic_ping")
                self.assertEqual(ping.get("diagnostic_id"), diagnostic_id)
                websocket.send(json.dumps({
                    "type": "diagnostic_pong",
                    "diagnostic_id": diagnostic_id,
                    "extension_version": "1.3.2",
                    "timestamp": int(time.time() * 1000),
                }))

                pong_received = False
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not pong_received:
                    try:
                        event = bridge.get_event_nowait()
                        data = event.get("data", {})
                        if event.get("event") == "message" and data.get("type") == "diagnostic_pong":
                            pong_received = data.get("diagnostic_id") == diagnostic_id
                    except queue.Empty:
                        time.sleep(0.02)
                self.assertTrue(pong_received, "La respuesta de diagnóstico no volvió a la aplicación")
        finally:
            bridge.close()

    def test_diagnostic_pong_requires_matching_shape_and_bounded_values(self):
        valid = {
            "type": "diagnostic_pong",
            "diagnostic_id": "a" * 32,
            "extension_version": "1.0.3",
            "timestamp": 1762370000000,
        }
        self.assertTrue(WebPageBridge._valid_inbound_message(valid))
        invalid = dict(valid, diagnostic_id="")
        self.assertFalse(WebPageBridge._valid_inbound_message(invalid))
        invalid = dict(valid, timestamp=float("inf"))
        self.assertFalse(WebPageBridge._valid_inbound_message(invalid))

    def test_oversized_event_is_discarded(self):
        bridge = WebPageBridge.__new__(WebPageBridge)
        bridge.events = queue.Queue(maxsize=6)
        bridge._event_lock = threading.Lock()
        bridge._queued_event_bytes = 0
        bridge._event_sizes = {}
        bridge._emit({"event": "test", "data": "x" * (bridge.MAX_EVENT_BYTES + 1)})
        self.assertEqual(bridge.events.qsize(), 0)
        self.assertEqual(bridge._queued_event_bytes, 0)


if __name__ == "__main__":
    unittest.main()
