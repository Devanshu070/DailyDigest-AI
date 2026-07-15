"""
app/email/sender.py — Email delivery via Gmail SMTP.

Sends the HTML digest to the configured recipient using Python's
built-in smtplib with Gmail's SMTP relay (smtp.gmail.com:587 + STARTTLS).

Requires a Gmail App Password (not your account password):
  Google Account → Security → 2-Step Verification → App passwords

Usage:
    from app.email.sender import send_digest
    sent = send_digest(html_content, digest_date, status_footer)
"""

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

log = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_digest(
    html_content: str,
    digest_date: date,
    status_footer: str,
    recipient_email: str | None = None,
) -> bool:
    """
    Sends the daily digest email via Gmail SMTP.

    Args:
        html_content:     The full HTML body of the digest.
        digest_date:      The date of the digest run (used in the subject line).
        status_footer:    Plain-text summary of source success/failure counts,
                          appended below the digest as a <footer> block.
        recipient_email:  Who to send the email to. Defaults to
                          settings.digest_recipient_email if not provided.

    Returns:
        True if the email was sent successfully, False otherwise.
        Never raises — failures are logged and the pipeline continues.
    """
    to_address = (
        recipient_email.strip()
        if recipient_email and recipient_email.strip()
        else settings.digest_recipient_email.strip()
    )

    subject = f"Your AI Digest — {digest_date.strftime('%B %d, %Y')}"

    # Build the full HTML email body
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 680px; margin: 40px auto; padding: 0 20px;
           color: #1a1a1a; line-height: 1.6; }}
    h1, h2, h3 {{ color: #111; }}
    a {{ color: #0066cc; }}
    hr {{ border: none; border-top: 1px solid #e5e5e5; margin: 32px 0; }}
    footer {{ font-size: 12px; color: #888; margin-top: 40px; }}
  </style>
</head>
<body>
  {html_content}
  <hr>
  <footer>{status_footer}</footer>
</body>
</html>"""

    # Compose the MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.gmail_sender
    msg["To"]      = to_address
    msg.attach(MIMEText(full_html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.gmail_sender, settings.gmail_app_password)
            server.sendmail(settings.gmail_sender, [to_address], msg.as_string())

        log.info("Digest email sent to %s via Gmail SMTP", to_address)
        return True

    except Exception as exc:
        # Email failure never crashes the pipeline — log and move on.
        log.error("Failed to send digest email: %s", exc)
        return False
