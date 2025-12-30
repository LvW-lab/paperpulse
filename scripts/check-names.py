import os
import re
import csv
import sqlite3
from collections import Counter

DB_PATH = r"C:\Users\l.v.winden\paperpulse\db\paperpulse.db"
TQCC_PATH = r"C:\Users\l.v.winden\paperpulse\journal-ranking\tqcc.csv"


def normalize_journal(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"&", "and", s)
    s = re.sub(r"[^a-z0-9\s\-]", "", s)   # drop punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_tqcc(path: str) -> dict[str, int]:
    tqcc = {}
    with open(path, "r", encoding="cp1252") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            j = normalize_journal(row.get("Journal", ""))
            v = (row.get("Value") or "").strip()
            if not j or v == "":
                continue
            try:
                tqcc[j] = int(float(v))  # allows "0" too
            except ValueError:
                continue
    return tqcc


def load_pubmed_journals(db_path: str) -> tuple[Counter, int]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT journal FROM papers WHERE journal IS NOT NULL AND journal != ''").fetchall()
    journals = [normalize_journal(r[0]) for r in rows if r and r[0]]
    return Counter(journals), len(rows)


def main() -> None:
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"DB not found: {DB_PATH}")
    if not os.path.exists(TQCC_PATH):
        raise SystemExit(f"TQCC file not found: {TQCC_PATH}")

    tqcc = load_tqcc(TQCC_PATH)
    pub_counter, n_rows = load_pubmed_journals(DB_PATH)

    pub_set = set(pub_counter.keys())
    tqcc_set = set(tqcc.keys())

    matched = pub_set & tqcc_set
    pub_unmatched = pub_set - tqcc_set
    tqcc_unused = tqcc_set - pub_set

    print("=== Sanity check: journal name matching ===")
    print(f"DB rows with non-empty journal: {n_rows}")
    print(f"Unique journals in DB:          {len(pub_set)}")
    print(f"Unique journals in TQCC list:   {len(tqcc_set)}")
    print()
    print(f"Exact normalized matches:       {len(matched)}")
    if len(pub_set) > 0:
        print(f"Match rate (unique):            {len(matched)/len(pub_set):.1%}")
    print()

    # Show top unmatched journals (by frequency in DB)
    print("Top unmatched journals in DB (normalized) — by frequency:")
    for j, c in pub_counter.most_common(30):
        if j in pub_unmatched:
            print(f"  {c:4d}  {j}")
    print()

    # Show some examples of matched journals with their tqcc score
    print("Examples of matched journals + TQCC value:")
    shown = 0
    for j in sorted(matched):
        print(f"  {j}  ->  {tqcc.get(j)}")
        shown += 1
        if shown >= 20:
            break

    # Optional: how many matched journals have score 0?
    zeros = sum(1 for j in matched if tqcc.get(j) == 0)
    print()
    print(f"Matched journals with TQCC=0:   {zeros}")

    # Write a CSV report (useful to inspect)
    out = "journal_match_report.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["journal_normalized", "in_db", "db_count", "in_tqcc", "tqcc_value"])
        all_j = sorted(pub_set | tqcc_set)
        for j in all_j:
            w.writerow([
                j,
                1 if j in pub_set else 0,
                pub_counter.get(j, 0),
                1 if j in tqcc_set else 0,
                tqcc.get(j, "")
            ])
    print(f"\nWrote: {out}")


if __name__ == "__main__":
    main()
