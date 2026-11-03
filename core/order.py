"""주문 카드: 직원에게 보여 줄 현지어 문장. 알레르기와 못 먹는 것을 맨 위에.

시연용으로 프랑스어와 영어 문장을 미리 넣어 두었다. 원어민 검토가 필요하다.
"""
from . import menu2

LANG = {
    "fr": {
        "hello": "Bonjour ! Nous voudrions commander, s'il vous plaît.",
        "allergy": "{who} est allergique {what}. Pouvez-vous vérifier, s'il vous plaît ?",
        "cannot": "{who} ne mange pas {what}.",
        "thanks": "Merci beaucoup !",
        "who": {"나": "Je", "엄마": "Ma mère", "아빠": "Mon père", "아이": "Mon enfant", "부모님": "Mon parent"},
        "what": {"견과류": "aux fruits à coque (noix, noisettes, amandes)", "우유": "au lait", "달걀": "aux œufs", "밀가루": "au gluten",
                 "갑각류": "aux crustacés", "조개류": "aux coquillages", "생선": "au poisson"},
        "what_not": {"조개류": "de coquillages (moules, huîtres, palourdes)", "돼지고기": "de porc", "소고기": "de bœuf", "생선": "de poisson",
                     "날것": "de plats crus", "술": "d'alcool", "버섯": "de champignons", "양파": "d'oignon", "갑각류": "de crustacés"},
    },
    "en": {
        "hello": "Hello! We would like to order, please.",
        "allergy": "{who} is allergic to {what}. Could you please check?",
        "cannot": "{who} does not eat {what}.",
        "thanks": "Thank you very much!",
        "who": {"나": "I", "엄마": "My mother", "아빠": "My father", "아이": "My child", "부모님": "My parent"},
        "what": {"견과류": "tree nuts (walnuts, hazelnuts, almonds)", "우유": "milk", "달걀": "eggs", "밀가루": "gluten",
                 "갑각류": "shellfish (shrimp, crab)", "조개류": "shellfish (mussels, clams, oysters)", "생선": "fish"},
        "what_not": {"조개류": "shellfish (mussels, clams)", "돼지고기": "pork", "소고기": "beef", "생선": "fish", "날것": "raw food",
                     "술": "alcohol", "버섯": "mushrooms", "양파": "onion", "갑각류": "shellfish"},
    },
}
REQUESTS = {  # 한국어: (fr, en)
    "소스는 따로": ("La sauce à part, s'il vous plaît.", "Sauce on the side, please."),
    "잘 익혀 주세요": ("Bien cuit, s'il vous plaît.", "Well done, please."),
    "덜 짜게": ("Peu salé, s'il vous plaît.", "Less salt, please."),
    "양파 빼고": ("Sans oignon, s'il vous plaît.", "No onion, please."),
    "버섯 빼고": ("Sans champignons, s'il vous plaît.", "No mushrooms, please."),
    "앞접시 하나 더": ("Une assiette en plus, s'il vous plaît.", "One extra plate, please."),
    "물 한 병": ("Une carafe d'eau, s'il vous plaît.", "A jug of tap water, please."),
}


def _who(p, L):
    key = p["name"] if p["name"] in L["who"] else ("아이" if p.get("child") else "부모님" if p.get("relation") == "부모님" else "나")
    return L["who"][key]


def _verb_fix(sentence, who):
    if who == "Je":  # 1인칭 활용
        return sentence.replace("Je est", "Je suis").replace("Je ne mange", "Je ne mange")
    if who == "I":
        return sentence.replace("I is", "I am").replace("I does", "I do")
    return sentence


def card(scan, people, lines, requests):
    """lines: [{item_id, count}], requests: [한국어 요청]."""
    code = (scan.get("language_code") or "fr").split("-")[0]
    lang = code if code in LANG else "en"
    L = LANG[lang]
    items = {i["id"]: i for i in scan["items"]}
    top, top_ko = [], []
    for p in people:  # 알레르기를 먼저
        for a in p.get("allergies") or []:
            if a in L["what"]:
                w = _who(p, L)
                top.append(_verb_fix(L["allergy"].format(who=w, what=L["what"][a]), w))
                top_ko.append(f"{p['name']}: {a} 알레르기가 있어요. 확인해 주세요.")
    for p in people:
        for c in p.get("cannot") or []:
            if c in L["what_not"]:
                w = _who(p, L)
                top.append(_verb_fix(L["cannot"].format(who=w, what=L["what_not"][c]), w))
                top_ko.append(f"{p['name']}: {c}{menu2.josa(c, '을', '를')} 못 먹어요.")
    order = []
    for ln in lines:
        it = items.get(ln["item_id"])
        if it:
            order.append({"count": ln.get("count", 1), "orig": it["name_orig"], "ko": it["name_ko"], "price": it["price"]})
    reqs = [{"ko": r, "orig": REQUESTS[r][0 if lang == "fr" else 1]} for r in requests if r in REQUESTS]
    text = "\n".join([*top, L["hello"], *[f"{o['count']} × {o['orig']}" for o in order], *[r["orig"] for r in reqs], L["thanks"]])
    return {"lang": lang, "voice": "fr-FR" if lang == "fr" else "en-US", "first": top, "first_ko": top_ko, "hello": L["hello"],
            "order": order, "requests": reqs, "thanks": L["thanks"], "text": text,
            "note": None if code in LANG else "이 나라 말 문장이 아직 없어 영어로 보여 드려요.",
            "request_choices": list(REQUESTS)}
