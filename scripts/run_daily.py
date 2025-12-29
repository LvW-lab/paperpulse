import os
import sqlite3
from datetime import datetime, timedelta, timezone

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
    # TODO: implement SMTP send using secrets in env vars
    # SMTP_HOST/PORT/USER/PASS/MAIL_FROM/MAIL_TO
    print(subject)
    print(html_body)

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

    subject = f"GBM invasion & integrins — new papers ({datetime.now().date().isoformat()})"
    html = "<h2>New papers</h2>" + "".join(
        f"<p><a href='{p.get('url','')}'>{p.get('title','(no title)')}</a></p>" for p in new_items
    )
    send_email_stub(subject, html)

if __name__ == "__main__":
    main()
