# scripts/run_monthly.py
import os
import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Set
import csv

DB_PATH = "paperpulse.db"
TQCC_PATH = os.path.join("journal-ranking", "tqcc.csv")
WHITELIST_PATH = os.path.join("journal-ranking", "whitelist.txt")


def normalize_journal(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def load_whitelist(path: str) -> Set[str]:
    if not os.path.exists(path):
        print(f"[WHITELIST] File not found: {path} (no whitelist will be applied)")
        return set()

    wl: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            wl.add(normalize_journal(line))

    print(f"[WHITELIST] Loaded {len(wl)} journals from {path}")
    return wl


def load_tqcc_map(path: str) -> Dict[str, int]:
    tqcc: Dict[str, int] = {}
    if not os.path.exists(path):
        print(f"[TQCC] File not found: {path} (no filtering will be applied)")
        return tqcc

    last_err: Exception | None = None
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    j = normalize_journal(row.get("Journal", ""))
                    v_raw = (row.get("Value") or "").strip()
                    if not j or v_raw == "":
                        continue
                    try:
                        tqcc[j] = int(float(v_raw))  # allows "0"
                    except ValueError:
                        continue
            print(f"[TQCC] Loaded {len(tqcc)} journal scores from {path} (encoding={enc})")
            return tqcc
        except UnicodeDecodeError as e:
            last_err = e
            continue

    raise last_err  # type: ignore[misc]


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS papers (
      id TEXT PRIMARY KEY,
      source TEXT,
      title TEXT,
      journal TEXT,
      published_date TEXT,
      published_date_iso TEXT,
      url TEXT,
      created_at TEXT
    )
    """)
    conn.commit()


def db_stats(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'")
    has_table = cur.fetchone() is not None
    print(f"[DB] papers table exists: {has_table}")

    if has_table:
        total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        newest = conn.execute("SELECT MAX(created_at) FROM papers").fetchone()[0]
        missing_iso = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE published_date_iso IS NULL OR published_date_iso = ''"
        ).fetchone()[0]
        print(f"[DB] total rows in papers: {total}")
        print(f"[DB] newest created_at: {newest}")
        print(f"[DB] rows missing published_date_iso: {missing_iso}")


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
    raw = os.environ.get("DAYS_OVERRIDE", "").strip()
    if raw.isdigit():
        days = int(raw)
        if 1 <= days <= max_days:
            return days
    return default_days


def get_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw.isdigit():
        return int(raw)
    return default


def fetch_rows(conn: sqlite3.Connection, since_date_iso: str) -> List[Tuple[str, str, str, str, str, str]]:
    return conn.execute(
        """
        SELECT id, source, title, journal, published_date, url
        FROM papers
        WHERE published_date_iso >= ?
        ORDER BY published_date_iso DESC
        """,
        (since_date_iso,),
    ).fetchall()


def filter_by_tqcc(
    rows: List[Tuple[str, str, str, str, str, str]],
    tqcc_map: Dict[str, int],
    tqcc_min: int,
    include_unranked: bool,
    whitelist: Set[str],
) -> List[Tuple[str, str, str, str, str, str]]:
    kept = []
    whitelisted = 0
    unranked = 0
    below = 0

    for r in rows:
        (_pid, _source, _title, journal, _pubdate, _url) = r
        j_norm = normalize_journal(journal)

        if j_norm in whitelist:
            kept.append(r)
            whitelisted += 1
            continue

        score = tqcc_map.get(j_norm)

        if score is None:
            unranked += 1
            if include_unranked:
                kept.append(r)
            continue

        if score >= tqcc_min:
            kept.append(r)
        else:
            below += 1

    print(
        f"[TQCC] cutoff >= {tqcc_min} | kept={len(kept)} | "
        f"whitelisted={whitelisted} | below={below} | unranked={unranked} "
        f"(include_unranked={include_unranked})"
    )
    return kept


def build_html(
    rows: List[Tuple[str, str, str, str, str, str]],
    window_days: int,
    tqcc_min: int,
    include_unranked: bool,
    whitelist_count: int,
) -> str:
    header = (
        f"<h2>Monthly overview</h2>"
        f"<p>Papers published in the last {window_days} days: <b>{len(rows)}</b></p>"
        f"<p>Filter: <b>TQCC ≥ {tqcc_min}</b> "
        f"({'including' if include_unranked else 'excluding'} unranked journals)"
        f"{' + whitelist' if whitelist_count > 0 else ''}</p>"
    )

    if not rows:
        return header + "<p>No papers matched the filter in this window.</p>"

    items = []
    for (_pid, source, title, journal, pubdate, url) in rows:
        title = (title or "(no title)").strip()
        source = (source or "").strip()
        journal = (journal or "").strip()
        pubdate = (pubdate or "").strip()
        url = (url or "").strip()

        meta_parts = [p for p in [source, journal, pubdate] if p]
        meta = " — ".join(meta_parts)
        meta_html = f"<br><i>{meta}</i>" if meta else ""
        link_html = f"<br><a href='{url}'>Open</a>" if url else ""

        items.append(f"<li><b>{title}</b>{meta_html}{link_html}</li>")

    return header + f"<ol>{''.join(items)}</ol>"


def main() -> None:
    window_days = get_window_days(default_days=30)
    tqcc_min = get_int_env("TQCC_MIN", 15)
    include_unranked = os.environ.get("INCLUDE_UNRANKED_JOURNALS", "0").strip() == "1"

    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    since_date_iso = since.date().isoformat()

    tqcc_map = load_tqcc_map(TQCC_PATH)
    whitelist = load_whitelist(WHITELIST_PATH)

    with sqlite3.connect(DB_PATH) as conn:
        init_db(conn)
        db_stats(conn)
        rows = fetch_rows(conn, since_date_iso)

    if tqcc_map:
        rows = filter_by_tqcc(rows, tqcc_map, tqcc_min, include_unranked, whitelist)

    today_utc = datetime.now(timezone.utc).date().isoformat()
    subject = f"Monthly overview — GBM invasion & integrins ({window_days}d window, as of {today_utc})"
    html = build_html(rows, window_days, tqcc_min, include_unranked, whitelist_count=len(whitelist))

    send_email(subject, html)


if __name__ == "__main__":
    main()
