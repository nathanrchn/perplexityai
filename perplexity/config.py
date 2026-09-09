import re
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from getpass import getpass
from html import unescape
from imaplib import IMAP4, IMAP4_SSL
from json import JSONDecodeError, dumps, loads
from pathlib import Path
from re import DOTALL, IGNORECASE, search, sub
from sys import stderr
from time import sleep, time
from typing import Callable, Optional


def config_dir() -> Path:
    path = Path.home() / ".cache" / "perplexity-cli"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    try:
        return loads(config_path().read_text())
    except (OSError, JSONDecodeError):
        return {}


def save_config(config: dict) -> None:
    path = config_path()
    path.write_text(dumps(config, indent=2) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def mail_config_for(account: str) -> Optional[dict]:
    accounts = load_config().get("mail", {}).get("accounts", {})
    if account in accounts:
        return accounts[account]
    for configured_account, mail_config in accounts.items():
        if configured_account.lower() == account.lower():
            return mail_config
    return None

MAIL_SECURITY_CHOICES = ("ssl", "starttls", "none")
DEFAULT_PORTS = {"ssl": 993, "starttls": 143, "none": 143}


def mail_security(mail_config: dict) -> str:
    """Return the transport security for a mail config.

    Configs written before the setting existed only carry a port, so the
    historic mapping (993 means implicit TLS, anything else STARTTLS) is used
    as the fallback.
    """
    security = str(mail_config.get("security", "")).strip().lower()
    if security in MAIL_SECURITY_CHOICES:
        return security
    return "ssl" if int(mail_config["port"]) == 993 else "starttls"


def connect_mailbox(mail_config: dict):
    security = mail_security(mail_config)
    hostname = mail_config["imap_hostname"]
    port = int(mail_config["port"])
    if security == "ssl":
        return IMAP4_SSL(hostname, port)
    mailbox = IMAP4(hostname, port)
    if security == "starttls":
        mailbox.starttls()
    return mailbox


def loop_input(prompt: str, default: Optional[str] = None, validator: Optional[Callable[[str], bool]] = None) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            if validator and not validator(value):
                continue
            return value
        if default is not None:
            return default

def loop_password(prompt: str, default: Optional[str] = None) -> str:
    while True:
        value = getpass(prompt)
        if value:
            return value
        if default is not None:
            return default

def is_valid_port(value: str) -> bool:
    if not value.isdigit():
        return False
    port = int(value)
    is_valid = 1 <= port <= 65535
    if not is_valid:
        stderr.write("ERROR: Port number must be between 1 and 65535.\n\n")
    return is_valid

def is_valid_security(value: str) -> bool:
    is_valid = value.lower() in MAIL_SECURITY_CHOICES
    if not is_valid:
        stderr.write(f"ERROR: Security must be one of {', '.join(MAIL_SECURITY_CHOICES)}.\n\n")
    return is_valid

def is_valid_email(value: str) -> bool:
    is_valid = True
    if " " in value:
        is_valid = False

    if is_valid:
        m = re.fullmatch(r"([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)", value)
        if not m:
            is_valid = False
        else:
            domain = m.group(2)
            labels = domain.split(".")
            is_valid = all(label and not label.startswith("-") and not label.endswith("-") for label in labels)

    if not is_valid:
        stderr.write("ERROR: Invalid email address.\n\n")
    return is_valid

def is_valid_yes_no(value: str) -> bool:
    is_valid = bool(re.fullmatch(r"[yY](es)?|[nN]o?", value))
    if not is_valid:
        stderr.write("ERROR: Enter yes or no.\n\n")
    return is_valid

def parse_yes_no(value: str) -> bool:
    return bool(re.fullmatch(r"[yY](es)?", value))

def configure_mail() -> None:
    stderr.write("Configure the IMAP mail account which receives Perplexity Sign-in emails...\n\n")
    accounts = load_config().get("mail", {}).get("accounts", {})
    if accounts:
        stderr.write("Configured accounts:\n")
        for configured_account in sorted(accounts):
            stderr.write(f"  - {configured_account}\n")
        stderr.write("\n")
    account = loop_input("Perplexity Account: ", validator=is_valid_email)
    existing_mail_config = mail_config_for(account) or {}
    stderr.write("\nYou can forward the Perplexity Sign-in emails to a different address,\nif so, enter it here. Otherwise, just press enter.\n\n")
    address_default = existing_mail_config.get("address", account)
    address = loop_input(f"Email Address [{address_default}]: ", address_default, is_valid_email)
    stderr.write("\nEnter the IMAP login details.\n")
    username_default = existing_mail_config.get("username")
    username_prompt = f"Username [{username_default}]: " if username_default else "Username: "
    username = loop_input(username_prompt, username_default)
    password_default = existing_mail_config.get("password")
    password_prompt = "Password [configured]: " if password_default else "Password: "
    password = loop_password(password_prompt, password_default)
    imap_hostname_default = existing_mail_config.get("imap_hostname")
    imap_hostname_prompt = f"IMAP Server [{imap_hostname_default}]: " if imap_hostname_default else "IMAP Server: "
    imap_hostname = loop_input(imap_hostname_prompt, imap_hostname_default)
    security_default = mail_security(existing_mail_config) if existing_mail_config else "ssl"
    stderr.write("\nTransport security: ssl (implicit TLS), starttls or none (unencrypted).\n")
    security = loop_input(f"Security [{security_default}]: ", security_default, is_valid_security).lower()
    if security == "none":
        stderr.write("WARNING: Without encryption the IMAP username, password and mail\n"
                     "         contents travel over the network in plain text.\n")
    existing_port = existing_mail_config.get("port")
    if existing_port and security == security_default:
        port_default = str(existing_port)
    else:
        port_default = str(DEFAULT_PORTS[security])
    port_text = loop_input(f"Port [{port_default}]: ", port_default, is_valid_port)
    port = int(port_text)
    folder_default = existing_mail_config.get("folder", "INBOX")
    folder = loop_input(f"Folder [{folder_default}]: ", folder_default)
    delete_default = existing_mail_config.get("delete_signin_messages", False if existing_mail_config else True)
    delete_prompt = "Delete Sign-in Messages [Y/n]? " if delete_default else "Delete Sign-in Messages [y/N]? "
    delete_signin_messages_text = loop_input(delete_prompt, "yes" if delete_default else "no", is_valid_yes_no)
    delete_signin_messages = parse_yes_no(delete_signin_messages_text)

    mail_config = {
        "address": address,
        "username": username,
        "password": password,
        "imap_hostname": imap_hostname,
        "security": security,
        "port": port,
        "folder": folder,
        "delete_signin_messages": delete_signin_messages,
    }
    stderr.write("\nValidating IMAP login details...\n")
    validate_mail_config(mail_config)
    stderr.write("IMAP login details validated.\n")

    config = load_config()
    config.setdefault("mail", {}).setdefault("accounts", {})[account] = mail_config
    save_config(config)
    stderr.write(f"\nMail login configured for {account}.\n")


def validate_mail_config(mail_config: dict) -> None:
    mailbox = connect_mailbox(mail_config)
    try:
        status, _ = mailbox.login(mail_config["username"], mail_config["password"])
        if status != "OK":
            raise RuntimeError("IMAP login failed")
        folder = mail_config.get("folder", "INBOX")
        status, _ = mailbox.select(folder)
        if status != "OK":
            raise RuntimeError(f"IMAP folder selection failed: {folder}")
    finally:
        try:
            mailbox.logout()
        except OSError:
            pass


def extract_perplexity_login_url(raw_message: bytes, account: str, now: Optional[datetime] = None) -> Optional[str]:
    msg = message_from_bytes(raw_message)
    subject = str(msg.get("Subject", ""))
    sender = str(msg.get("From", ""))
    recipient = str(msg.get("To", ""))
    if subject != "Sign in to Perplexity":
        return None
    if "perplexity" not in sender.lower():
        return None
    if account.lower() not in recipient.lower():
        return None

    try:
        date = parsedate_to_datetime(msg.get("Date"))
    except (TypeError, ValueError):
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if (current - date).total_seconds() > 60:
        return None

    for body in _message_bodies(msg):
        url = _extract_url_from_body(body)
        if url:
            return url
    return None


def retrieve_login_url_from_mail(account: str, mail_config: dict, timeout: float = 60) -> str:
    deadline = time() + timeout
    last_error = None
    while time() < deadline:
        try:
            url = _check_mailbox(account, mail_config)
            if url:
                return url
        except Exception as exc:
            last_error = exc
        sleep(5)
    if last_error:
        raise RuntimeError(f"mail lookup failed: {last_error}")
    raise RuntimeError("mail lookup timed out")


def _check_mailbox(account: str, mail_config: dict) -> Optional[str]:
    mailbox = connect_mailbox(mail_config)
    try:
        mailbox.login(mail_config["username"], mail_config["password"])
        mailbox.select(mail_config.get("folder", "INBOX"))
        status, data = mailbox.search(None, 'FROM "perplexity" SUBJECT "Sign in to Perplexity"')
        if status != "OK" or not data or not data[0]:
            return None
        for message_id in reversed(data[0].split()):
            status, message_data = mailbox.fetch(message_id, "(RFC822)")
            if status != "OK":
                continue
            for part in message_data:
                if not isinstance(part, tuple):
                    continue
                url = extract_perplexity_login_url(part[1], account)
                if url:
                    if mail_config.get("delete_signin_messages", False):
                        mailbox.store(message_id, "+FLAGS", "\\Deleted")
                        mailbox.expunge()
                    return url
        return None
    finally:
        try:
            mailbox.logout()
        except OSError:
            pass


def _message_bodies(msg) -> list[str]:
    bodies = []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        bodies.append(payload.decode(charset, errors="replace"))
    return bodies


def _extract_url_from_body(body: str) -> Optional[str]:
    text = unescape(body)
    text = sub(r"=\r?\n", "", text)
    text = text.replace("=3D", "=")
    match = search(
        r"https://www\.perplexity\.ai/api/auth/callback/email\?[^<>\s\"']+",
        text,
        IGNORECASE | DOTALL,
    )
    if not match:
        return None
    url = match.group(0)
    url = sub(r"\s+", "", url)
    url = url.replace("&amp;", "&")
    return url
