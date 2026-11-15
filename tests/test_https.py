"""不访问外网：缺少开发机证书时仍加载随包 CA，校验失败不能绕过。"""
import os
import ssl
import unittest
import urllib.error
import urllib.request
from unittest import mock

from widget import https


class HttpsTests(unittest.TestCase):
    def test_missing_system_ca_still_uses_bundled_trust_and_verifies_hostname(self):
        request = urllib.request.Request("https://api.github.com/repos/example/deskmate/releases")
        env = {"SSL_CERT_FILE": "/nonexistent-deskmate-ca/cert.pem", "SSL_CERT_DIR": "/nonexistent-deskmate-ca/certs"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(ssl.SSLContext, "load_default_certs", side_effect=AssertionError("must not use host CA")), \
                mock.patch.object(urllib.request, "urlopen") as urlopen:
            result = https.open_url(request, timeout=10)
        self.assertIs(result, urlopen.return_value)
        args, kwargs = urlopen.call_args
        self.assertIs(args[0], request)
        self.assertEqual(kwargs["timeout"], 10)
        context = kwargs["context"]
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_missing_bundle_ca_fails_before_request_without_system_fallback(self):
        with mock.patch.object(https.certifi, "where", return_value="/nonexistent-deskmate-ca/cert.pem"), \
                mock.patch.object(urllib.request, "urlopen") as urlopen:
            with self.assertRaises(FileNotFoundError):
                https.open_url(urllib.request.Request("https://example.invalid"), timeout=30)
        urlopen.assert_not_called()

    def test_invalid_server_certificate_is_not_retried_without_verification(self):
        error = urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))
        with mock.patch.object(urllib.request, "urlopen", side_effect=error) as urlopen:
            with self.assertRaises(urllib.error.URLError) as caught:
                https.open_url(urllib.request.Request("https://example.invalid"), timeout=30)
        self.assertIs(caught.exception, error)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)


if __name__ == "__main__":
    unittest.main()
