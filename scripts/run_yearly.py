# scripts/run_yearly.py
import os
import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

DB_PATH = "paperpulse.db"


def send_email(subject: str, html_body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    mail_from = os.environ["MAIL_FROM"]
    mail_to = os.environ["MAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content("This email requires HTML support.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(msg)


def get_window_days(default_days: int, max_days: int = 1825) -> int:
    """
    Allow overriding the window via DAYS_OVERRIDE env var (workflow_dispatch input).
    Safety cap defaults to 5 years (1825 days).
    """
    raw = os.environ.get("DAYS_OVERRIDE", "").strip()
    if raw.isdigit():
        days = int(raw)
        if 1 <= days <= max_days:
            return days
    return default_days


def fetch_rows(conn: sqlite3.Connection, since_iso: str) -> List[Tuple[str, str, str, str, str]]:
    return conn.execute(
        """
        SELECT id, title, journal, published_date, url
        FROM papers
        WHERE created_at >= ?
        ORDER BY published_date DESC
        """,
        (since_iso,),
    ).fetchall()


def build_html(rows: List[Tuple[str, str, str, str, str]], window_days: int) -> str:
    header = f"<h2>Yearly overview</h2><p>Items added in the last {window_days} days: <b>{len(rows)}</b></p>"
    if not rows:
        return header + "<p>No papers were added to the database in this window.</p>"

    items = []
    for (_pid, title, journal, pubdate, url) in rows:
        title = (title or "(no title)").strip()
        journal = (journal or "").strip()
        pubdate = (pubdate or "").strip()
        url = (url or "").strip()

        meta = " — ".join([x for x in [journal, pubdate] if x])
        meta_html = f"<br><i>{meta}</i>" if meta else ""
        link_html = f"<br><a href='{url}'>Open</a>" if url else ""

        items.append(f"<li><b>{title}</b>{meta_html}{link_html}</li>")

    return header + f"<ol>{''.join(items)}</ol>"


def main() -> None:
    # Default to 365 days, but allow override (e.g., 30/90/365/730)
    window_days = get_window_days(default_days=365)
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    with sqlite3.connect(DB_PATH) as conn:
        rows = fetch_rows(conn, since.isoformat())

    today_utc = datetime.now(timezone.utc).date().isoformat()
    subject = f"Yearly overview — GBM invasion & integrins ({window_days}d window, as of {today_utc})"
    html = build_html(rows, window_days)

    send_email(subject, html)


if __name__ == "__main__":
    main()
