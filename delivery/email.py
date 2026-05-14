"""
Email delivery via SMTP (plain text + HTML multipart).
"""

from __future__ import annotations

import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
from delivery.base import AlertItem, DigestBundle


def _truncate(text: str, max_len: int = 200) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _item_html(item: AlertItem) -> str:
    flags = []
    if item.is_priority:
        flags.append('<span style="color:#c00;font-weight:bold;">URGENT</span>')
    if item.is_update:
        flags.append('<em>Update to previously seen article</em>')
    flag_html = (" &nbsp;·&nbsp; ".join(flags) + "<br>") if flags else ""
    return f"""
    <div style="border-left:3px solid #0066cc;padding:8px 12px;margin:12px 0;">
      <div style="font-weight:bold;color:#0066cc;">{item.client_name}</div>
      {flag_html}
      <div><a href="{item.url}">{_truncate(item.headline, 160)}</a></div>
      <div style="color:#666;font-size:0.9em;">{item.source_name or ''}</div>
      {"<div style='color:#444;font-size:0.9em;margin-top:4px;'>" + _truncate(item.summary, 200) + "</div>" if item.summary else ""}
    </div>"""


def _item_text(item: AlertItem) -> str:
    flags = []
    if item.is_priority:
        flags.append("[URGENT]")
    if item.is_update:
        flags.append("[UPDATE]")
    flag_str = " ".join(flags) + " " if flags else ""
    return (
        f"{flag_str}{item.client_name}\n"
        f"{item.headline}\n"
        f"Source: {item.source_name or 'Unknown'} | Matched: {item.keyword_matched}\n"
        f"{item.url}\n"
    )


def _build_immediate_message(item: AlertItem, to_email: str) -> MIMEMultipart:
    flags = []
    if item.is_priority:
        flags.append("URGENT")
    if item.is_update:
        flags.append("UPDATE")
    prefix = f"[{', '.join(flags)}] " if flags else ""
    subject = f"{prefix}Coverage: {item.client_name} — {_truncate(item.headline, 80)}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = to_email

    text_body = f"Montfort Coverage Alert\n\n{_item_text(item)}"
    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
    <h2 style="color:#0066cc;">Montfort Coverage Alert</h2>
    {_item_html(item)}
    <p style="color:#999;font-size:0.8em;margin-top:24px;">
      Delivered by Montfort Coverage Agent
    </p>
    </body></html>"""

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


def _build_digest_message(bundle: DigestBundle) -> MIMEMultipart:
    to_email = bundle.user_email or ""
    now = datetime.now(timezone.utc).strftime("%d %b %Y")
    subject = f"Coverage digest — {bundle.brief_title} ({now})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = to_email

    text_parts = [f"Coverage digest — {bundle.brief_title}\n{now}\n{len(bundle.items)} item(s)\n\n"]
    for item in bundle.items:
        text_parts.append(_item_text(item) + "\n")

    html_items = "".join(_item_html(item) for item in bundle.items)
    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
    <h2 style="color:#0066cc;">{bundle.brief_title}</h2>
    <p style="color:#666;">{now} · {len(bundle.items)} item{'s' if len(bundle.items) != 1 else ''} {bundle.period_label}</p>
    {html_items}
    <p style="color:#999;font-size:0.8em;margin-top:24px;">
      Delivered by Montfort Coverage Agent
    </p>
    </body></html>"""

    msg.attach(MIMEText("".join(text_parts), "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


async def deliver_email(
    to_email: str,
    items: list[AlertItem] | None = None,
    bundle: DigestBundle | None = None,
) -> bool:
    """
    Send coverage to the given email address.
    Pass `items` for immediate per-item delivery, or `bundle` for a digest.
    Returns True on success.
    """
    if not all([config.SMTP_HOST, config.SMTP_USER, config.SMTP_PASS]):
        print("[Email] SMTP not configured — skipping delivery")
        return False

    messages: list[MIMEMultipart] = []

    if bundle is not None:
        messages.append(_build_digest_message(bundle))
    elif items:
        for item in items:
            messages.append(_build_immediate_message(item, to_email))

    if not messages:
        return False

    return _send_all(messages, to_email)


def _send_all(messages: list[MIMEMultipart], to_email: str) -> bool:
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(config.SMTP_USER, config.SMTP_PASS)
            for msg in messages:
                server.sendmail(config.SMTP_USER, to_email, msg.as_string())
        return True
    except Exception as exc:
        print(f"[Email] Delivery failed: {exc}")
        return False
