from datetime import datetime, timezone
from email.message import EmailMessage
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from perplexity.config import (
    _check_mailbox,
    configure_mail,
    extract_perplexity_login_url,
    is_valid_security,
    is_valid_yes_no,
    load_config,
    mail_config_for,
    mail_security,
    parse_yes_no,
    save_config,
    validate_mail_config,
)


class FakeMailbox:
    instances = []

    def __init__(self, hostname, port):
        self.hostname = hostname
        self.port = port
        self.started_tls = False
        self.logged_out = False
        FakeMailbox.instances.append(self)

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.username = username
        self.password = password
        return ("OK", [])

    def select(self, mailbox):
        self.selected_mailbox = mailbox
        return ("OK", [])

    def logout(self):
        self.logged_out = True


class FailingMailbox(FakeMailbox):
    def login(self, username, password):
        return ("NO", [])


class EmptyMailbox(FakeMailbox):
    def search(self, charset, criterion):
        self.search_charset = charset
        self.search_criterion = criterion
        return ("OK", [b""])


class LoginMessageMailbox(FakeMailbox):
    def search(self, charset, criterion):
        return ("OK", [b"123"])

    def fetch(self, message_id, spec):
        self.fetched_message_id = message_id
        msg = EmailMessage()
        msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
        msg["From"] = "Perplexity <team@mail.perplexity.ai>"
        msg["To"] = "login@example.com"
        msg["Subject"] = "Sign in to Perplexity"
        msg.set_content(
            "https://www.perplexity.ai/api/auth/callback/email?"
            "callbackUrl=defaultMobileSignIn&email=login%40example.com&token=543116"
        )
        return ("OK", [(message_id, msg.as_bytes())])

    def store(self, message_id, command, flags):
        self.stored_message_id = message_id
        self.store_command = command
        self.store_flags = flags
        return ("OK", [])

    def expunge(self):
        self.expunged = True
        return ("OK", [])


class MailLoginExtractionTest(unittest.TestCase):
    def _message(self, body, date=None):
        msg = EmailMessage()
        msg["Date"] = (date or datetime(2026, 5, 6, 6, 3, 8, tzinfo=timezone.utc)).strftime(
            "%a, %d %b %Y %H:%M:%S %z"
        )
        msg["From"] = "Perplexity <team@mail.perplexity.ai>"
        msg["To"] = "d.grieser@mittwald.de"
        msg["Subject"] = "Sign in to Perplexity"
        msg.set_content(body, cte="quoted-printable")
        return msg.as_bytes()

    def test_extracts_wrapped_quoted_printable_url(self):
        body = (
            "https://www.perplexity.ai/api/auth/callback/email?=\n"
            "callbackUrl=3DdefaultMobileSignIn&email=3Dd.grieser%40mittwald.=\n"
            "de&token=3D543116"
        )
        url = extract_perplexity_login_url(
            self._message(body),
            "d.grieser@mittwald.de",
            now=datetime(2026, 5, 6, 6, 3, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(
            url,
            "https://www.perplexity.ai/api/auth/callback/email?callbackUrl=defaultMobileSignIn&email=d.grieser%40mittwald.de&token=543116",
        )

    def test_extracts_html_entity_url(self):
        body = (
            '<a href="https://www.perplexity.ai/api/auth/callback/email?'
            'callbackUrl=defaultMobileSignIn&amp;email=d.grieser%40mittwald.de&amp;token=543116">'
        )
        url = extract_perplexity_login_url(
            self._message(body),
            "d.grieser@mittwald.de",
            now=datetime(2026, 5, 6, 6, 3, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(
            url,
            "https://www.perplexity.ai/api/auth/callback/email?callbackUrl=defaultMobileSignIn&email=d.grieser%40mittwald.de&token=543116",
        )

    def test_rejects_stale_message(self):
        raw = self._message(
            "https://www.perplexity.ai/api/auth/callback/email?callbackUrl=defaultMobileSignIn&email=d.grieser%40mittwald.de&token=543116",
            date=datetime(2026, 5, 6, 6, 1, 0, tzinfo=timezone.utc),
        )
        url = extract_perplexity_login_url(
            raw,
            "d.grieser@mittwald.de",
            now=datetime(2026, 5, 6, 6, 3, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(url)


class ConfigStorageTest(unittest.TestCase):
    def test_saves_and_loads_mail_account(self):
        with TemporaryDirectory() as tmp:
            with patch("perplexity.config.Path.home", return_value=Path(tmp)):
                save_config(
                    {
                        "mail": {
                            "accounts": {
                                "login@example.com": {
                                    "address": "mailbox@example.com",
                                    "username": "imap-user",
                                    "password": "secret",
                                    "imap_hostname": "imap.example.com",
                                    "port": 993,
                                    "folder": "Archive/Perplexity",
                                }
                            }
                        }
                    }
                )

                self.assertEqual(load_config()["mail"]["accounts"]["login@example.com"]["port"], 993)
                self.assertEqual(
                    load_config()["mail"]["accounts"]["login@example.com"]["folder"],
                    "Archive/Perplexity",
                )
                self.assertEqual(mail_config_for("login@example.com")["address"], "mailbox@example.com")
                self.assertEqual(mail_config_for("LOGIN@example.com")["username"], "imap-user")


class MailConfigValidationTest(unittest.TestCase):
    def setUp(self):
        FakeMailbox.instances = []

    def test_validates_ssl_mail_config(self):
        with patch("perplexity.config.IMAP4_SSL", FakeMailbox):
            validate_mail_config(
                {
                    "username": "imap-user",
                    "password": "secret",
                    "imap_hostname": "imap.example.com",
                    "port": 993,
                }
            )

        mailbox = FakeMailbox.instances[0]
        self.assertEqual(mailbox.hostname, "imap.example.com")
        self.assertEqual(mailbox.port, 993)
        self.assertEqual(mailbox.username, "imap-user")
        self.assertEqual(mailbox.password, "secret")
        self.assertEqual(mailbox.selected_mailbox, "INBOX")
        self.assertFalse(mailbox.started_tls)
        self.assertTrue(mailbox.logged_out)

    def test_validates_starttls_mail_config(self):
        with patch("perplexity.config.IMAP4", FakeMailbox):
            validate_mail_config(
                {
                    "username": "imap-user",
                    "password": "secret",
                    "imap_hostname": "imap.example.com",
                    "port": 143,
                }
            )

        self.assertTrue(FakeMailbox.instances[0].started_tls)

    def test_validates_plain_mail_config(self):
        with patch("perplexity.config.IMAP4", FakeMailbox):
            validate_mail_config(
                {
                    "username": "imap-user",
                    "password": "secret",
                    "imap_hostname": "imap.example.com",
                    "security": "none",
                    "port": 143,
                }
            )

        mailbox = FakeMailbox.instances[0]
        self.assertEqual(mailbox.port, 143)
        self.assertFalse(mailbox.started_tls)
        self.assertTrue(mailbox.logged_out)

    def test_security_setting_overrides_port_defaults(self):
        self.assertEqual(mail_security({"port": 993}), "ssl")
        self.assertEqual(mail_security({"port": 143}), "starttls")
        self.assertEqual(mail_security({"port": 993, "security": "none"}), "none")
        self.assertEqual(mail_security({"port": 143, "security": "SSL"}), "ssl")
        self.assertEqual(mail_security({"port": 143, "security": "bogus"}), "starttls")

    def test_accepts_security_values(self):
        for value in ["ssl", "STARTTLS", "none"]:
            self.assertTrue(is_valid_security(value))

        with patch("perplexity.config.stderr", StringIO()):
            self.assertFalse(is_valid_security("plain"))

    def test_configure_mail_saves_plain_security_with_default_port(self):
        answers = iter(["login@example.com", "", "imap-user", "imap.example.com", "none", "", "", ""])

        with TemporaryDirectory() as tmp:
            with patch("perplexity.config.Path.home", return_value=Path(tmp)):
                with patch("perplexity.config.input", side_effect=lambda _prompt: next(answers)):
                    with patch("perplexity.config.getpass", return_value="secret"):
                        with patch("perplexity.config.IMAP4", FakeMailbox):
                            with patch("perplexity.config.stderr", StringIO()):
                                configure_mail()

                mail_config = load_config()["mail"]["accounts"]["login@example.com"]
                self.assertEqual(mail_config["security"], "none")
                self.assertEqual(mail_config["port"], 143)
                self.assertFalse(FakeMailbox.instances[0].started_tls)

    def test_validates_configured_folder(self):
        with patch("perplexity.config.IMAP4_SSL", FakeMailbox):
            validate_mail_config(
                {
                    "username": "imap-user",
                    "password": "secret",
                    "imap_hostname": "imap.example.com",
                    "port": 993,
                    "folder": "Archive/Perplexity",
                }
            )

        self.assertEqual(FakeMailbox.instances[0].selected_mailbox, "Archive/Perplexity")

    def test_accepts_yes_no_delete_message_values(self):
        for value in ["y", "Y", "yes", "Yes"]:
            self.assertTrue(is_valid_yes_no(value))
            self.assertTrue(parse_yes_no(value))
        for value in ["n", "N", "no", "No"]:
            self.assertTrue(is_valid_yes_no(value))
            self.assertFalse(parse_yes_no(value))

        with patch("perplexity.config.stderr", StringIO()):
            self.assertFalse(is_valid_yes_no("sure"))

    def test_configure_mail_does_not_save_invalid_mail_config(self):
        answers = iter(["login@example.com", "", "imap-user", "imap.example.com", "ssl", "993", "INBOX", ""])

        with TemporaryDirectory() as tmp:
            with patch("perplexity.config.Path.home", return_value=Path(tmp)):
                with patch("perplexity.config.input", side_effect=lambda _prompt: next(answers)):
                    with patch("perplexity.config.getpass", return_value="secret"):
                        with patch("perplexity.config.IMAP4_SSL", FailingMailbox):
                            with patch("perplexity.config.stderr", StringIO()):
                                with self.assertRaises(RuntimeError):
                                    configure_mail()

                self.assertEqual(load_config(), {})

    def test_configure_mail_saves_default_folder(self):
        answers = iter(["login@example.com", "", "imap-user", "imap.example.com", "ssl", "993", "", ""])

        with TemporaryDirectory() as tmp:
            with patch("perplexity.config.Path.home", return_value=Path(tmp)):
                with patch("perplexity.config.input", side_effect=lambda _prompt: next(answers)):
                    with patch("perplexity.config.getpass", return_value="secret"):
                        with patch("perplexity.config.IMAP4_SSL", FakeMailbox):
                            with patch("perplexity.config.stderr", StringIO()):
                                configure_mail()

                mail_config = load_config()["mail"]["accounts"]["login@example.com"]
                self.assertEqual(mail_config["folder"], "INBOX")
                self.assertTrue(mail_config["delete_signin_messages"])
                self.assertEqual(FakeMailbox.instances[0].selected_mailbox, "INBOX")

    def test_configure_mail_saves_no_delete_signin_messages(self):
        answers = iter(["login@example.com", "", "imap-user", "imap.example.com", "ssl", "993", "", "No"])

        with TemporaryDirectory() as tmp:
            with patch("perplexity.config.Path.home", return_value=Path(tmp)):
                with patch("perplexity.config.input", side_effect=lambda _prompt: next(answers)):
                    with patch("perplexity.config.getpass", return_value="secret"):
                        with patch("perplexity.config.IMAP4_SSL", FakeMailbox):
                            with patch("perplexity.config.stderr", StringIO()):
                                configure_mail()

                mail_config = load_config()["mail"]["accounts"]["login@example.com"]
                self.assertFalse(mail_config["delete_signin_messages"])

    def test_configure_mail_uses_existing_account_values_as_defaults(self):
        answers = iter(["login@example.com", "", "", "", "", "", "", ""])
        prompts = []
        password_prompts = []
        stderr = StringIO()

        def input_answer(prompt):
            prompts.append(prompt)
            return next(answers)

        def password_answer(prompt):
            password_prompts.append(prompt)
            return ""

        with TemporaryDirectory() as tmp:
            with patch("perplexity.config.Path.home", return_value=Path(tmp)):
                save_config(
                    {
                        "mail": {
                            "accounts": {
                                "login@example.com": {
                                    "address": "mailbox@example.com",
                                    "username": "imap-user",
                                    "password": "secret",
                                    "imap_hostname": "imap.example.com",
                                    "port": 143,
                                    "folder": "Archive/Perplexity",
                                    "delete_signin_messages": False,
                                }
                            }
                        }
                    }
                )

                with patch("perplexity.config.input", side_effect=input_answer):
                    with patch("perplexity.config.getpass", side_effect=password_answer):
                        with patch("perplexity.config.IMAP4", FakeMailbox):
                            with patch("perplexity.config.stderr", stderr):
                                configure_mail()

                mail_config = load_config()["mail"]["accounts"]["login@example.com"]
                self.assertEqual(mail_config["address"], "mailbox@example.com")
                self.assertEqual(mail_config["username"], "imap-user")
                self.assertEqual(mail_config["password"], "secret")
                self.assertEqual(mail_config["imap_hostname"], "imap.example.com")
                self.assertEqual(mail_config["security"], "starttls")
                self.assertEqual(mail_config["port"], 143)
                self.assertEqual(mail_config["folder"], "Archive/Perplexity")
                self.assertFalse(mail_config["delete_signin_messages"])

        self.assertIn("Email Address [mailbox@example.com]: ", prompts)
        self.assertIn("Username [imap-user]: ", prompts)
        self.assertIn("IMAP Server [imap.example.com]: ", prompts)
        self.assertIn("Security [starttls]: ", prompts)
        self.assertIn("Port [143]: ", prompts)
        self.assertIn("Folder [Archive/Perplexity]: ", prompts)
        self.assertIn("Delete Sign-in Messages [y/N]? ", prompts)
        self.assertEqual(password_prompts, ["Password [configured]: "])
        self.assertNotIn("secret", "".join(prompts + password_prompts))
        self.assertIn("Configured accounts:\n  - login@example.com\n\n", stderr.getvalue())
        self.assertIn("Validating IMAP login details...\nIMAP login details validated.\n", stderr.getvalue())

    def test_configure_mail_lists_existing_accounts(self):
        answers = iter(["new@example.com", "", "imap-user", "imap.example.com", "ssl", "993", "", ""])
        stderr = StringIO()

        with TemporaryDirectory() as tmp:
            with patch("perplexity.config.Path.home", return_value=Path(tmp)):
                save_config(
                    {
                        "mail": {
                            "accounts": {
                                "z@example.com": {"address": "z@example.com"},
                                "a@example.com": {"address": "a@example.com"},
                            }
                        }
                    }
                )

                with patch("perplexity.config.input", side_effect=lambda _prompt: next(answers)):
                    with patch("perplexity.config.getpass", return_value="secret"):
                        with patch("perplexity.config.IMAP4_SSL", FakeMailbox):
                            with patch("perplexity.config.stderr", stderr):
                                configure_mail()

        self.assertIn(
            "Configure the IMAP mail account which receives Perplexity Sign-in emails...\n\n"
            "Configured accounts:\n"
            "  - a@example.com\n"
            "  - z@example.com\n\n",
            stderr.getvalue(),
        )

    def test_mail_lookup_uses_configured_folder(self):
        with patch("perplexity.config.IMAP4_SSL", EmptyMailbox):
            self.assertIsNone(
                _check_mailbox(
                    "login@example.com",
                    {
                        "username": "imap-user",
                        "password": "secret",
                        "imap_hostname": "imap.example.com",
                        "port": 993,
                        "folder": "Archive/Perplexity",
                    },
                )
            )

        self.assertEqual(FakeMailbox.instances[0].selected_mailbox, "Archive/Perplexity")

    def test_mail_lookup_deletes_used_signin_message_when_configured(self):
        with patch("perplexity.config.IMAP4_SSL", LoginMessageMailbox):
            url = _check_mailbox(
                "login@example.com",
                {
                    "username": "imap-user",
                    "password": "secret",
                    "imap_hostname": "imap.example.com",
                    "port": 993,
                    "delete_signin_messages": True,
                },
            )

        mailbox = FakeMailbox.instances[0]
        self.assertIn("token=543116", url)
        self.assertEqual(mailbox.stored_message_id, b"123")
        self.assertEqual(mailbox.store_command, "+FLAGS")
        self.assertEqual(mailbox.store_flags, "\\Deleted")
        self.assertTrue(mailbox.expunged)

    def test_mail_lookup_leaves_used_signin_message_by_default(self):
        with patch("perplexity.config.IMAP4_SSL", LoginMessageMailbox):
            self.assertIn(
                "token=543116",
                _check_mailbox(
                    "login@example.com",
                    {
                        "username": "imap-user",
                        "password": "secret",
                        "imap_hostname": "imap.example.com",
                        "port": 993,
                    },
                ),
            )

        self.assertFalse(hasattr(FakeMailbox.instances[0], "stored_message_id"))


if __name__ == "__main__":
    unittest.main()
