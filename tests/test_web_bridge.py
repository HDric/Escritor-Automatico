import json
import os
import queue
import secrets
import threading
import unittest
from unittest.mock import patch

from bridge_security import (
    encode_nonce,
    make_client_proof,
    make_server_proof,
    decode_pairing_code,
)
from escritor_automatico import WebPageBridge


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
