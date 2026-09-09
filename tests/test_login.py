from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from perplexity.perplexity import Perplexity


class FakeCookies:
    def get_dict(self):
        return {"session": "cookie"}


class FakeSession:
    def __init__(self):
        self.cookies = FakeCookies()
        self.get_urls = []

    def post(self, url, data):
        self.post_url = url
        self.post_data = data

    def get(self, url):
        self.get_urls.append(url)


class LoginFallbackTest(unittest.TestCase):
    def test_mail_failure_falls_back_to_manual_token(self):
        with TemporaryDirectory() as tmp:
            perplexity = Perplexity.__new__(Perplexity)
            perplexity.session = FakeSession()

            with patch("perplexity.perplexity.config_dir", return_value=Path(tmp)):
                with patch("perplexity.perplexity.mail_config_for", return_value={"address": "mailbox@example.com"}):
                    with patch(
                        "perplexity.perplexity.retrieve_login_url_from_mail",
                        side_effect=RuntimeError("imap failed"),
                    ):
                        with patch("sys.stdin", StringIO("543116\n")):
                            with patch("sys.stderr", StringIO()) as stderr:
                                perplexity._login("login@example.com")

            self.assertIn("Failed to retrieve token from email: imap failed", stderr.getvalue())
            self.assertEqual(
                perplexity.session.get_urls[-1],
                "https://www.perplexity.ai/api/auth/callback/email?callbackUrl=defaultMobileSignIn&email=login%40example.com&token=543116",
            )


if __name__ == "__main__":
    unittest.main()
