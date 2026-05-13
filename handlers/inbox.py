"""Microsoft 365 inbox handler — reads newsletters from a dedicated mailbox via IMAP."""
import email
import imaplib
import logging
import os
import re
import socket
from datetime import datetime, timezone
from email.header import decode_header, make_header

from handlers.base import BaseHandler, NormalisedItem

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_DEFAULT_SERVER = "outlook.office365.com"
_DEFAULT_PORT = 993
_CONNECT_TIMEOUT = 20  # seconds


def _decode_header_value(raw) -> str:
    """Safely decode a potentially encoded email header."""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def _extract_text_and_urls(msg: email.message.Message) -> tuple[str, str]:
    """Return (plain_text_body, first_url_found)."""
    plain_parts: list[str] = []
    first_url = ""

    for part in msg.walk():
        ct = part.get_content_type()
        cd = part.get("Content-Disposition", "")
        if "attachment" in cd:
            continue

        if ct == "text/plain":
            charset = part.get_content_charset() or "utf-8"
            try:
                text = part.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                text = ""
            plain_parts.append(text)

        elif ct == "text/html" and not plain_parts:
            # Fallback: strip tags to get rough text and extract URLs
            charset = part.get_content_charset() or "utf-8"
            try:
                html = part.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                html = ""
            urls = _URL_RE.findall(html)
            if urls and not first_url:
                # Pick the first non-tracking URL
                for u in urls:
                    if "unsubscribe" not in u.lower() and "track" not in u.lower():
                        first_url = u
                        break
            # Very rough HTML-to-text
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            plain_parts.append(text[:2000])

    body = " ".join(plain_parts)[:2000]
    urls = _URL_RE.findall(body)
    for u in urls:
        if "unsubscribe" not in u.lower() and "track" not in u.lower():
            first_url = u
            break

    return body.strip(), first_url


def _parse_date(msg: email.message.Message) -> datetime:
    raw = msg.get("Date", "")
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw)
    except Exception:
        return datetime.now(timezone.utc)


class InboxHandler(BaseHandler):
    """Reads unread newsletters from an M365 mailbox via IMAP."""

    name = "inbox"

    def fetch(self) -> list[NormalisedItem]:
        user = os.environ.get("IMAP_USER", "")
        password = os.environ.get("IMAP_PASS", "")
        server = os.environ.get("IMAP_SERVER", _DEFAULT_SERVER)
        port = int(os.environ.get("IMAP_PORT", _DEFAULT_PORT))

        if not user or not password:
            logger.warning("IMAP_USER or IMAP_PASS not set — skipping inbox handler")
            return []

        allowed_senders = {
            s.lower() for s in self.config.get("newsletter_senders", [])
        }

        try:
            return self._read_inbox(server, port, user, password, allowed_senders)
        except Exception as exc:
            logger.error("Inbox handler error: %s", exc)
            return []

    def _read_inbox(
        self,
        server: str,
        port: int,
        user: str,
        password: str,
        allowed_senders: set[str],
    ) -> list[NormalisedItem]:
        logger.info("Connecting to IMAP server %s as %s", server, user)
        socket.setdefaulttimeout(_CONNECT_TIMEOUT)
        imap = imaplib.IMAP4_SSL(server, port)
        try:
            imap.login(user, password)
            imap.select("INBOX")

            _, data = imap.search(None, "UNSEEN")
            uid_list = data[0].split() if data[0] else []
            logger.info("Found %d unread messages", len(uid_list))

            items: list[NormalisedItem] = []
            for uid in uid_list:
                item = self._process_message(imap, uid, allowed_senders)
                if item:
                    items.append(item)

            return items
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    def _process_message(
        self,
        imap: imaplib.IMAP4_SSL,
        uid: bytes,
        allowed_senders: set[str],
    ) -> NormalisedItem | None:
        _, msg_data = imap.fetch(uid, "(RFC822)")
        if not msg_data or not msg_data[0]:
            return None

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        from_header = _decode_header_value(msg.get("From", ""))
        sender_email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", from_header)
        sender = sender_email.group(0).lower() if sender_email else ""

        if allowed_senders and sender not in allowed_senders:
            logger.debug("Skipping message from non-whitelisted sender: %s", sender)
            # Still mark as read so we don't re-check each run
            imap.store(uid, "+FLAGS", "\\Seen")
            return None

        subject = _decode_header_value(msg.get("Subject", "(no subject)"))
        body, url = _extract_text_and_urls(msg)
        published = _parse_date(msg)

        # Mark as read
        imap.store(uid, "+FLAGS", "\\Seen")
        logger.info("Processed email: %s from %s", subject, sender)

        # Deduplication fallback: if no URL found, we hash by subject+date in dedup module
        item_url = url or f"inbox://{sender}/{subject}/{published.date()}"

        return NormalisedItem(
            title=subject,
            url=item_url,
            summary=body[:500],
            source=self.name,
            published_at=published,
        )
