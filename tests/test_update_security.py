import base64
import unittest

from update_security import verify_release_manifest, public_key_raw


class ReleaseSignatureTests(unittest.TestCase):
    # Public test vector signed by the project's Ed25519 release key.
    MANIFEST = b"EscritorAutomatico release manifest test\n"
    SIGNATURE_B64 = "76EIdmXxXDlBFt8XfFi8LSqVN/YsjJt2SQGO+NjIgUqep6GnhQRJ4+JLsw4tBpcdW6NgFYHQMd2XLb69yQAVBg=="

    def test_valid_ed25519_signature_is_accepted(self):
        signature = base64.b64decode(self.SIGNATURE_B64)
        self.assertEqual(len(public_key_raw()), 32)
        self.assertTrue(verify_release_manifest(self.MANIFEST, signature))

    def test_modified_manifest_is_rejected(self):
        signature = base64.b64decode(self.SIGNATURE_B64)
        self.assertFalse(verify_release_manifest(self.MANIFEST + b"changed", signature))

    def test_malformed_signature_is_rejected(self):
        self.assertFalse(verify_release_manifest(self.MANIFEST, b"short"))


if __name__ == "__main__":
    unittest.main()
