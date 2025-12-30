import os
import sqlite3
from datetime import datetime, timedelta, timezone
import smtplib
from email.message import EmailMessage
import time
import requests
import xml.etree.ElementTree as ET


DB_PATH = "paperpulse.db"
PUBMED_QUERY = r"""
(
  glioblastoma[Title/Abstract] OR GBM[Title/Abstract] OR glioma[Title/Abstract]
  OR "high-grade glioma"[Title/Abstract] OR "diffuse glioma"[Title/Abstract]
)
AND
(
  invasion[Title/Abstract] OR invasive[Title/Abstract] OR migration[Title/Abstract]
  OR infiltrat*[Title/Abstract] OR "cell motility"[Title/Abstract]
)
AND
(
  integrin*[Title/Abstract] OR "focal adhesion"[Title/Abstract]
  OR "extracellular matrix"[Title/Abstract] OR ECM[Title/Abstract]
  OR laminin[Title/Abstract] OR fibronectin[Title/Abstract] OR collagen[Title/Abstract]
  OR talin[Title/Abstract] OR kindlin[Title/Abstract] OR paxillin[Title/Abstract]
  OR vinculin[Title/Abstract] OR FAK[Title/Abstract] OR PTK2[Title/Abstract]
  OR SRC[Title/Abstract] OR ILK[Title/Abstract]
)
NOT ( "case report"[Publication Type] OR editorial[Publication Type] OR comment[Publication Type] )
""".strip()


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

def _fmt_date_utc(dt: datetime) -> str:
    # NCBI mindate/maxdate accept YYYY/MM/DD
    return dt.astimezone(timezone.utc).strftime("%Y/%m/%d")

def fetch_new_papers_pubmed(since_utc: datetime) -> list[dict]:
    """
    Returns list of dicts: {id, source, title, journal, published_date, url}
    id is PMID.
    """
    api_key = os.environ.get("NCBI_API_KEY")
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Be polite with rate limits
    sleep_s = 0.12 if api_key else 0.4  # ~8 rps vs ~2.5 rps

    # 1) ESearch: find PMIDs in date range (publication date)
    params = {
        "db": "pubmed",
        "term": PUBMED_QUERY,
        "retmode": "json",
        "datetype": "pdat",
        "mindate": _fmt_date_utc(since_utc),
        "maxdate": _fmt_date_utc(datetime.now(timezone.utc)),
        "retmax": "200",
        "sort": "pub+date",
    }
    if api_key:
        params["api_key"] = api_key

    r = requests.get(f"{base}/esearch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    time.sleep(sleep_s)

    data = r.json()
    id_list = data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []

    # 2) ESummary: get title/journal/date quickly
    sparams = {"db": "pubmed", "id": ",".join(id_list), "retmode": "json"}
    if api_key:
        sparams["api_key"] = api_key

    r = requests.get(f"{base}/esummary.fcgi", params=sparams, timeout=30)
    r.raise_for_status()
    time.sleep(sleep_s)
    summ = r.json().get("result", {})

    papers = []
    for pmid in id_list:
        item = summ.get(pmid, {})
        title = (item.get("title") or "").rstrip(".")
        journal = item.get("fulljournalname") or item.get("source") or ""
        pubdate = item.get("pubdate") or ""  # format varies (e.g., "2025 Dec 29")
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        papers.append({
            "id": pmid,
            "source": "pubmed",
            "title": title if title else "(no title)",
            "journal": journal,
            "published_date": pubdate,
            "url": url,
        })

    return papers

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

        papers = fetch_new_papers_pubmed(since)
        new_items = []
        for p in papers:
            if not already_seen(conn, p["id"]):
                store(conn, p)
                new_items.append(p)

    subject = f"PaperPulse Daily Report — {datetime.now(timezone.utc).isoformat()}"
    if not new_items:
        html = "<h2>No new PubMed papers in the last 24h for your query.</h2>"
    else:
        html = "<h2>New PubMed papers</h2><ol>" + "".join(
            f"<li><a href='{p['url']}'>{p['title']}</a><br>"
            f"<i>{p.get('journal','')}</i> — {p.get('published_date','')}</li>"
            for p in new_items
        ) + "</ol>"

    send_email_stub(subject, html)
    return


if __name__ == "__main__":
    main()
