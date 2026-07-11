"""
app/email/sender.py — Email delivery via Resend.

Sends the HTML digest to the configured recipient.
Uses the Resend Python SDK (not SMTP).

Usage:
    from app.email.sender import send_digest
    sent = send_digest(html_content, digest_date, status_footer)
"""

import logging
from datetime import date

import resend

from app.config import settings

log = logging.getLogger(__name__)

# Sender address — must be verified in your Resend dashboard.
# Resend provides onboarding@resend.dev for testing with verified domain accounts.
SENDER_ADDRESS = "DailyDigest <onboarding@resend.dev>"


def send_digest(
    html_content: str,
    digest_date: date,
    status_footer: str,
    recipient_email: str | None = None,
) -> bool:
    """
    Sends the daily digest email via Resend.

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
    resend.api_key = settings.resend_api_key
    to_address = recipient_email.strip() if recipient_email and recipient_email.strip() \
        else settings.digest_recipient_email.strip()

    subject = f"Your AI Digest — {digest_date.strftime('%B %d, %Y')}"

    # Wrap digest HTML with a minimal outer shell and append the status footer
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

    try:
        response = resend.Emails.send({
            "from": SENDER_ADDRESS,
            "to": [to_address],
            "subject": subject,
            "html": full_html,
        })
        log.info(
            "Digest email sent to %s (id=%s)",
            to_address,
            response.get("id"),
        )
        return True

    except Exception as exc:
        # Email failure never crashes the pipeline — log and move on.
        log.error("Failed to send digest email: %s", exc)
        return False
