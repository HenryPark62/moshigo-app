"""부모님께 보내는 링크와 간단 모드: 한 사람 기준으로 메뉴를 묶는다."""
from urllib.parse import urlencode, urlsplit

VERDICTS = ["편히", "조심", "피하기"]
COURSE_ORDER = {"main": 0, "starter": 1, "dessert": 3}


def base_url(url=None, host=None):
    """앱 주소 (끝 / 없이). 브라우저 주소가 있으면 그것을, 없으면 Host 헤더로 만든다."""
    if url:
        u = urlsplit(url)
        if u.scheme and u.netloc:
            return f"{u.scheme}://{u.netloc}{u.path.rstrip('/')}"
    if host:
        local = host.split(":")[0] in ("localhost", "127.0.0.1", "0.0.0.0")
        return f"{'http' if local else 'https'}://{host}"
    return ""


def link(base, code, pid):
    """이 사람 입맛으로 바로 여는 주소."""
    return f"{base}/?{urlencode({'me': code, 'for': pid})}"


def groups(scan, pid):
    """한 사람 기준 판정별 메뉴 목록. {'편히': [(item, x)], '조심': [...], '피하기': [...]}.
    음료와 못 읽은 메뉴는 빼고, 닮은꼴이 가까운 메뉴와 메인 요리를 앞에 둔다."""
    out = {v: [] for v in VERDICTS}
    for it in scan["items"]:
        if it["course"] == "drink" or it.get("unreadable"):
            continue
        x = next((x for x in it.get("per") or [] if x["id"] == pid), None)
        if x and x["verdict"] in out:
            out[x["verdict"]].append((it, x))
    for v in out:
        out[v].sort(key=lambda t: (-((t[1]["match"] or {}).get("score") or 0) - 0.05 * t[0].get("boost", 0),
                                   COURSE_ORDER.get(t[0]["course"], 2)))
    return out
