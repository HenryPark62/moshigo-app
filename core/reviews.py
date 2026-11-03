"""후기와 먹은 뒤 설문.

후기는 이 식당의 같은 메뉴를 먼저, 없으면 다른 식당의 같은 메뉴로 넓힌다.
설문(실제로 시켰는지, 설명이 맛을 잘 그려 줬는지, 예상보다 강했던 맛, 다시 추천받고 싶은지)은 SQLite에 쌓고,
'예상보다 강했다'는 응답이 많으면 그 메뉴 설명에 미리 알려 준다.
"""
import os
import sqlite3
import time
from pathlib import Path

DATA = Path(__file__).parent / "data"
DB = Path(os.environ.get("MOSHIGO_DB", DATA / "moshigo.db"))
STRONG = ["짠맛", "단맛", "매운맛", "신맛", "느끼함", "향", "없음"]
STRONG_KW = {"짠맛": "생각보다 짤 수 있어요", "단맛": "생각보다 달 수 있어요", "매운맛": "생각보다 매울 수 있어요",
             "신맛": "생각보다 새콤할 수 있어요", "느끼함": "생각보다 느끼할 수 있어요", "향": "향이 생각보다 셀 수 있어요"}


def _db():
    con = sqlite3.connect(DB)
    con.execute("""create table if not exists survey (
        id integer primary key, ts real, restaurant text, menu text, ordered int, imagine int,
        stronger text, again int, comment text, who text)""")
    return con


def save(restaurant, menu, ordered, imagine, stronger, again, comment="", who=""):
    with _db() as con:
        con.execute("insert into survey (ts, restaurant, menu, ordered, imagine, stronger, again, comment, who) values (?,?,?,?,?,?,?,?,?)",
                    (time.time(), restaurant, menu, int(ordered), int(imagine), ",".join(stronger), int(again), comment.strip()[:200], who))


def stats(menu):
    """메뉴 하나에 쌓인 설문 요약."""
    with _db() as con:
        rows = con.execute("select ordered, imagine, stronger, again from survey where menu = ?", (menu,)).fetchall()
    n = len(rows)
    if not n:
        return {"n": 0}
    strong = {}
    for _, _, s, _ in rows:
        for k in filter(None, s.split(",")):
            if k != "없음":
                strong[k] = strong.get(k, 0) + 1
    top = max(strong.items(), key=lambda kv: kv[1]) if strong else None
    return {"n": n, "ordered": round(100 * sum(r[0] for r in rows) / n), "imagine": round(sum(r[1] for r in rows) / n, 1),
            "again": round(100 * sum(r[3] for r in rows) / n),
            "strong": top and {"taste": top[0], "pct": round(100 * top[1] / n)}}


def caution(menu):
    """설문에서 '예상보다 강했다'가 40% 넘게 나온 맛을 미리 알려 준다 (응답 3개 이상일 때)."""
    s = stats(menu)
    if s["n"] >= 3 and s.get("strong") and s["strong"]["pct"] >= 40:
        return f"먹어 본 사람 {s['strong']['pct']}%가 {s['strong']['taste']}이 예상보다 강했다고 했어요. {STRONG_KW[s['strong']['taste']]}"
    return None


def user_reviews(menu, restaurant):
    with _db() as con:
        rows = con.execute("select ts, restaurant, imagine, stronger, comment from survey where menu = ? and comment != '' order by ts desc limit 20",
                           (menu,)).fetchall()
    return [{"source": "here" if r[1] == restaurant else "same_menu", "kind": "user", "stars": r[2], "text": r[4],
             "date": time.strftime("%Y.%m.%d", time.localtime(r[0]))} for r in rows]


def reviews(menu, restaurant):
    """1순위 이 식당의 이 메뉴, 2순위 다른 식당의 같은 메뉴. 실제 이용자가 남긴 후기만."""
    allr = user_reviews(menu, restaurant)
    here = [r for r in allr if r["source"] == "here"]
    other = [r for r in allr if r["source"] != "here"]
    stars = [r["stars"] for r in allr]
    return {"here": here, "other": other, "count": len(allr), "avg": round(sum(stars) / len(stars), 1) if stars else None}
