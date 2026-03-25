"""
Email alert sender via Gmail.
Uses Python's built-in smtplib — no extra packages needed.
Loads credentials from .env — never hardcode them here.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def send_alert(subject: str, body: str) -> None:
    """
    Send an email alert via Gmail.
    Splits long bodies into readable plain-text email.
    """
    gmail_user = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    to_address = os.getenv("ALERT_TO_EMAIL")

    if not all([gmail_user, gmail_password, to_address]):
        raise EnvironmentError(
            "GMAIL_ADDRESS, GMAIL_APP_PASSWORD, and ALERT_TO_EMAIL must be set in .env"
        )

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to_address, msg.as_string())

    print(f"Email sent to {to_address} — Subject: {subject}")
