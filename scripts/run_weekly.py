import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = "paperpulse.db"

def main() -> None:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT title, journal, published_date, url FROM papers WHERE created_at >= ? ORDER BY published_date DESC",
            (since.isoformat(),)
        ).fetchall()

    subject = f"Weekly highlights — GBM invasion & integrins (week of {datetime.now().date().isoformat()})"
    html = "<h2>Weekly overview</h2>" + "".join(
        f"<p><b>{t}</b><br>{j or ''} — {d or ''}<br><a href='{u or ''}'>link</a></p>"
        for (t, j, d, u) in rows
    )
    print(subject)
    print(html)

if __name__ == "__main__":
    main()
