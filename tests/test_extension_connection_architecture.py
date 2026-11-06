from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExtensionConnectionArchitectureTests(unittest.TestCase):
    def test_websocket_is_owned_by_persistent_extension_page(self):
        worker = (ROOT / "web_extension/service_worker.js").read_text(encoding="utf-8")
        connection = (ROOT / "web_extension/connection.js").read_text(encoding="utf-8")
        html = (ROOT / "web_extension/connection.html").read_text(encoding="utf-8")
        self.assertNotIn("new WebSocket(", worker)
        self.assertIn('"bridge_incoming"', worker)
        self.assertIn('"bridge_outgoing"', worker)
        self.assertIn('new WebSocket(BRIDGE_URL)', connection)
        self.assertIn("ws://127.0.0.1:8765", connection)
        self.assertIn('src="connection.js"', html)

    def test_application_diagnostic_round_trip_is_handled_by_service_worker(self):
        worker = (ROOT / "web_extension/service_worker.js").read_text(encoding="utf-8")
        app = (ROOT / "escritor_automatico.py").read_text(encoding="utf-8")
        self.assertIn('message.type === "diagnostic_ping"', worker)
        self.assertIn('type: "diagnostic_pong"', worker)
        self.assertIn('"diagnostic_pong"', app)
        self.assertIn('"type": "diagnostic_ping"', app)
        self.assertIn("_web_diagnostic_timeout", app)

    def test_connection_page_retains_mutual_hmac_authentication(self):
        connection = (ROOT / "web_extension/connection.js").read_text(encoding="utf-8")
        self.assertIn('"Client"', connection)
        self.assertIn('"Server"', connection)
        self.assertIn("auth_challenge", connection)
        self.assertIn("auth_ok", connection)


if __name__ == "__main__":
    unittest.main()
