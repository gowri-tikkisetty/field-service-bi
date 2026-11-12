"""Every practice query in sql/04_report_queries.sql must run and return sensible rows."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def statements():
    text = (ROOT / "sql" / "04_report_queries.sql").read_text()
    # split on ';' at statement ends, ignore comment-only chunks
    for chunk in text.split(";\n"):
        body = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--")).strip()
        if body:
            yield body


def test_all_example_queries_run(db):
    n = 0
    for sql in statements():
        db.execute(sql).fetchall()
        n += 1
    assert n == 9


def test_duplicate_check_finds_nothing(db):
    sql = [s for s in statements() if "HAVING COUNT(*) > 1" in s][0]
    assert db.execute(sql).fetchall() == []


def test_mom_first_row_is_null(db):
    sql = next(statements())
    rows = db.execute(sql).fetchall()
    assert rows[0][2] is None and rows[1][2] is not None
