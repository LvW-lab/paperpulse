import os
import sqlite3
from datetime import datetime, timedelta, timezone
import smtplib
from email.message import EmailMessage

DB_PATH = "paperpulse.db"

def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS papers (
      id TEXT PRIMARY KEY,
      source TEXT,
      title TEXT,
      journal TEXT,
      published_date TEXT,
      url TEXT,
      created_at TEXT
    )
    """)
    conn.commit()

def already_seen(conn: sqlite3.Connection, paper_id: str) -> bool:
    cur = conn.execute("SELECT 1 FROM papers WHERE id = ? LIMIT 1", (paper_id,))
    return cur.fetchone() is not None

def store(conn: sqlite3.Connection, p: dict) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO papers (id, source, title, journal, published_date, url, created_at) VALUES (?,?,?,?,?,?,?)",
        (p["id"], p["source"], p["title"], p.get("journal"), p.get("published_date"), p.get("url"),
         datetime.now(timezone.utc).isoformat())
    )
    conn.commit()

def fetch_new_papers_stub(since_utc: datetime) -> list[dict]:
    # TODO: replace with PubMed/bioRxiv/medRxiv fetching
    # Return list of dicts with stable IDs (DOI/PMID/arXiv ID)
    return []

def send_email_stub(subject: str, html_body: str) -> None:
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

    with smtplib.SMTP(host, port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(msg)

def main() -> None:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    with sqlite3.connect(DB_PATH) as conn:
        init_db(conn)

        papers = fetch_new_papers_stub(since)
        new_items = []
        for p in papers:
            if not already_seen(conn, p["id"]):
                store(conn, p)
                new_items.append(p)

    subject = f"[TEST] PaperPulse SMTP works — {datetime.now(timezone.utc).isoformat()}"
    html = "<h2>✅ PaperPulse test</h2><p>Als je dit ontvangt, werken GitHub Secrets + SMTP + Actions.</p>"
    send_email_stub(subject, html)
    return


if __name__ == "__main__":
    main()
