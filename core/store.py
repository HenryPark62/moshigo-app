"""사람별 입맛 저장 (SQLite). 로그인 없이 기기마다 '내 코드'로 구분한다.

코드는 주소창(?me=...)에 붙어 있어서 새로고침하거나 즐겨찾기로 다시 열어도 그대로 불러온다.
다른 기기에서는 코드를 입력하면 같은 입맛 목록을 불러온다.
"""
import copy
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

DB = Path(os.environ.get("MOSHIGO_DB", Path(__file__).parent / "data" / "moshigo.db"))
ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"  # 헷갈리는 글자(0, o, 1, l, i) 빼기


def _db():
    con = sqlite3.connect(DB)
    con.execute("create table if not exists people (code text primary key, data text, updated real)")
    return con


def new_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def load(code):
    with _db() as con:
        row = con.execute("select data from people where code = ?", (code,)).fetchone()
    return json.loads(row[0]) if row else None


def save(code, people):
    with _db() as con:
        con.execute("insert into people (code, data, updated) values (?, ?, ?) on conflict(code) do update set data = excluded.data, updated = excluded.updated",
                    (code, json.dumps(people, ensure_ascii=False), time.time()))


def load_or_default(code, default):
    got = load(code) if code else None
    return got if got is not None else copy.deepcopy(default)


DAILY_LIMIT = int(os.environ.get("MOSHIGO_DAILY_SCANS", "150"))  # 공개 주소에서 API 비용이 끝없이 나가지 않게


def take_scan():
    """오늘 사진 읽기 횟수를 하나 쓴다. 한도를 넘으면 False."""
    day = time.strftime("%Y-%m-%d")
    with _db() as con:
        con.execute("create table if not exists usage (day text primary key, scans int)")
        row = con.execute("select scans from usage where day = ?", (day,)).fetchone()
        n = row[0] if row else 0
        if n >= DAILY_LIMIT:
            return False
        con.execute("insert into usage (day, scans) values (?, 1) on conflict(day) do update set scans = scans + 1", (day,))
    return True
