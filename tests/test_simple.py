import os

os.environ.setdefault("MOSHIGO_DB", "/tmp/moshigo-test.db")

from core import menu2, simple  # noqa: E402


def test_share_link_base_and_params():
    assert simple.base_url("https://moshigo.onrender.com/?me=abc123", "x") == "https://moshigo.onrender.com"
    assert simple.base_url(None, "localhost:8502") == "http://localhost:8502"
    assert simple.base_url("", "moshigo.onrender.com") == "https://moshigo.onrender.com"
    assert simple.link("https://moshigo.onrender.com", "abc123", "pk3h4j2") == "https://moshigo.onrender.com/?me=abc123&for=pk3h4j2"


def test_one_person_groups():
    mom = next(p for p in menu2.DEFAULT_PEOPLE if p["id"] == "mom")
    scan = menu2.demo([mom])
    g = simple.groups(scan, "mom")
    names = [it["name_orig"] for v in g.values() for it, _ in v]
    assert "Bœuf bourguignon" in [it["name_orig"] for it, _ in g["편히"]]
    assert not any(it["course"] == "drink" or it["unreadable"] for v in g.values() for it, _ in v)
    assert len(names) == len(set(names))
    # 편히 안에서는 닮은꼴이 가까운 메뉴가 앞에
    scores = [(x["match"] or {}).get("score") or 0 for _, x in g["편히"]]
    assert scores == sorted(scores, reverse=True)
    dad = next(p for p in menu2.DEFAULT_PEOPLE if p["id"] == "dad")
    g2 = simple.groups(menu2.demo([dad]), "dad")
    assert any(it["name_orig"].startswith("Moules") for it, _ in g2["피하기"])
