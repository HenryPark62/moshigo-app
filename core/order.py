"""주문 카드: 직원에게 보여 줄 현지어 문장. 알레르기와 못 먹는 것을 맨 위에.

메뉴판 언어(language_code)에 맞춰 11개 언어 문장을 미리 넣어 두었다. 없는 언어는 영어로 보여 준다.
문장은 원어민 검토가 필요하다.
"""
from . import menu2

ALLERGENS = ["견과류", "우유", "달걀", "밀가루", "갑각류", "조개류", "생선"]
CANNOT = ["조개류", "돼지고기", "소고기", "생선", "날것", "술", "버섯", "양파", "갑각류"]
REQUEST_KEYS = ["소스는 따로", "잘 익혀 주세요", "덜 짜게", "양파 빼고", "버섯 빼고", "앞접시 하나 더", "물 한 병",
                "빨리 나오는 걸로", "계산서도 같이", "맵지 않게", "아이용 작은 접시"]

# who: 나, 엄마, 아빠, 아이, 부모님, 가족 / allergy·cannot: {who}, {what} / *_me: 나일 때
LANG = {
    "fr": {
        "name": "프랑스어", "voice": "fr-FR",
        "hello": "Bonjour ! Nous voudrions commander, s'il vous plaît.", "thanks": "Merci beaucoup !",
        "who": {"엄마": "Ma mère", "아빠": "Mon père", "아이": "Mon enfant", "부모님": "Un de mes parents", "가족": "Un membre de ma famille"},
        "allergy": "{who} est allergique {what}. Pouvez-vous vérifier, s'il vous plaît ?",
        "allergy_me": "Je suis allergique {what}. Pouvez-vous vérifier, s'il vous plaît ?",
        "cannot": "{who} ne mange pas {what}.", "cannot_me": "Je ne mange pas {what}.",
        "what": {"견과류": "aux fruits à coque (noix, noisettes, amandes)", "우유": "au lait", "달걀": "aux œufs", "밀가루": "au gluten",
                 "갑각류": "aux crustacés", "조개류": "aux coquillages", "생선": "au poisson"},
        "what_not": {"조개류": "de coquillages (moules, huîtres, palourdes)", "돼지고기": "de porc", "소고기": "de bœuf", "생선": "de poisson",
                     "날것": "de plats crus", "술": "d'alcool", "버섯": "de champignons", "양파": "d'oignon", "갑각류": "de crustacés"},
        "req": ["La sauce à part, s'il vous plaît.", "Bien cuit, s'il vous plaît.", "Peu salé, s'il vous plaît.", "Sans oignon, s'il vous plaît.",
                "Sans champignons, s'il vous plaît.", "Une assiette en plus, s'il vous plaît.", "Une carafe d'eau, s'il vous plaît.", "Nous sommes pressés, quelque chose de rapide, s'il vous plaît.", "L'addition en même temps, s'il vous plaît.", "Pas épicé, s'il vous plaît.", "Une petite assiette pour l'enfant, s'il vous plaît."],
    },
    "en": {
        "name": "영어", "voice": "en-US",
        "hello": "Hello! We would like to order, please.", "thanks": "Thank you very much!",
        "who": {"엄마": "My mother", "아빠": "My father", "아이": "My child", "부모님": "My parent", "가족": "A family member"},
        "allergy": "{who} is allergic to {what}. Could you please check?", "allergy_me": "I am allergic to {what}. Could you please check?",
        "cannot": "{who} does not eat {what}.", "cannot_me": "I do not eat {what}.",
        "what": {"견과류": "tree nuts (walnuts, hazelnuts, almonds)", "우유": "milk", "달걀": "eggs", "밀가루": "gluten",
                 "갑각류": "shellfish (shrimp, crab)", "조개류": "shellfish (mussels, clams, oysters)", "생선": "fish"},
        "what_not": {"조개류": "shellfish (mussels, clams)", "돼지고기": "pork", "소고기": "beef", "생선": "fish", "날것": "raw food",
                     "술": "alcohol", "버섯": "mushrooms", "양파": "onion", "갑각류": "shellfish"},
        "req": ["Sauce on the side, please.", "Well done, please.", "Less salt, please.", "No onion, please.", "No mushrooms, please.",
                "One extra plate, please.", "A jug of tap water, please.", "We're in a hurry. Something quick, please.", "Could we have the bill with the food, please?", "Not spicy, please.", "A small plate for the child, please."],
    },
    "ja": {
        "name": "일본어", "voice": "ja-JP",
        "hello": "すみません、注文をお願いします。", "thanks": "ありがとうございます。",
        "who": {"엄마": "母", "아빠": "父", "아이": "子ども", "부모님": "親", "가족": "家族"},
        "allergy": "{who}は{what}アレルギーがあります。確認していただけますか？", "allergy_me": "私は{what}アレルギーがあります。確認していただけますか？",
        "cannot": "{who}は{what}が食べられません。", "cannot_me": "私は{what}が食べられません。",
        "what": {"견과류": "ナッツ類", "우유": "乳製品", "달걀": "卵", "밀가루": "小麦", "갑각류": "甲殻類（エビ・カニ）", "조개류": "貝類", "생선": "魚"},
        "what_not": {"조개류": "貝類", "돼지고기": "豚肉", "소고기": "牛肉", "생선": "魚", "날것": "生もの", "술": "お酒", "버섯": "きのこ",
                     "양파": "玉ねぎ", "갑각류": "エビ・カニ"},
        "req": ["ソースは別にしてください。", "よく焼いてください。", "塩分控えめでお願いします。", "玉ねぎ抜きでお願いします。",
                "きのこ抜きでお願いします。", "取り皿をもう一枚ください。", "お水をください。", "急いでいるので、早く出せるものをお願いします。", "お会計も一緒にお願いします。", "辛くしないでください。", "子ども用の小皿をお願いします。"],
    },
    "zh-Hans": {
        "name": "중국어", "voice": "zh-CN",
        "hello": "您好，我们想点餐。", "thanks": "谢谢！",
        "who": {"엄마": "我妈妈", "아빠": "我爸爸", "아이": "我的孩子", "부모님": "我的父母", "가족": "我的家人"},
        "allergy": "{who}对{what}过敏，请帮忙确认一下。", "allergy_me": "我对{what}过敏，请帮忙确认一下。",
        "cannot": "{who}不能吃{what}。", "cannot_me": "我不能吃{what}。",
        "what": {"견과류": "坚果", "우유": "牛奶", "달걀": "鸡蛋", "밀가루": "小麦", "갑각류": "虾蟹类", "조개류": "贝类", "생선": "鱼"},
        "what_not": {"조개류": "贝类", "돼지고기": "猪肉", "소고기": "牛肉", "생선": "鱼", "날것": "生的食物", "술": "酒", "버섯": "蘑菇",
                     "양파": "洋葱", "갑각류": "虾蟹"},
        "req": ["酱汁请分开放。", "请做全熟。", "请少放盐。", "请不要放洋葱。", "请不要放蘑菇。", "请再给一个小碟子。", "请给一壶水。", "我们赶时间，请上快一点的菜。", "请把账单一起拿来。", "请不要辣。", "请给孩子一个小盘子。"],
    },
    "zh-Hant": {
        "name": "중국어(번체)", "voice": "zh-TW",
        "hello": "你好，我們想點餐。", "thanks": "謝謝！",
        "who": {"엄마": "我媽媽", "아빠": "我爸爸", "아이": "我的孩子", "부모님": "我的父母", "가족": "我的家人"},
        "allergy": "{who}對{what}過敏，請幫忙確認一下。", "allergy_me": "我對{what}過敏，請幫忙確認一下。",
        "cannot": "{who}不能吃{what}。", "cannot_me": "我不能吃{what}。",
        "what": {"견과류": "堅果", "우유": "牛奶", "달걀": "雞蛋", "밀가루": "小麥", "갑각류": "蝦蟹類", "조개류": "貝類", "생선": "魚"},
        "what_not": {"조개류": "貝類", "돼지고기": "豬肉", "소고기": "牛肉", "생선": "魚", "날것": "生的食物", "술": "酒", "버섯": "蘑菇",
                     "양파": "洋蔥", "갑각류": "蝦蟹"},
        "req": ["醬汁請分開放。", "請做全熟。", "請少放鹽。", "請不要放洋蔥。", "請不要放蘑菇。", "請再給一個小碟子。", "請給一壺水。", "我們趕時間，請上快一點的菜。", "請把帳單一起拿來。", "請不要辣。", "請給孩子一個小盤子。"],
    },
    "th": {
        "name": "태국어", "voice": "th-TH",
        "hello": "สวัสดีครับ/ค่ะ ขอสั่งอาหารครับ/ค่ะ", "thanks": "ขอบคุณครับ/ค่ะ",
        "who": {"엄마": "แม่ของฉัน", "아빠": "พ่อของฉัน", "아이": "ลูกของฉัน", "부모님": "พ่อแม่ของฉัน", "가족": "คนในครอบครัวของฉัน"},
        "allergy": "{who}แพ้{what} ช่วยตรวจสอบให้ด้วยครับ/ค่ะ", "allergy_me": "ฉันแพ้{what} ช่วยตรวจสอบให้ด้วยครับ/ค่ะ",
        "cannot": "{who}ทาน{what}ไม่ได้ครับ/ค่ะ", "cannot_me": "ฉันทาน{what}ไม่ได้ครับ/ค่ะ",
        "what": {"견과류": "ถั่ว", "우유": "นม", "달걀": "ไข่", "밀가루": "แป้งสาลี", "갑각류": "กุ้งและปู", "조개류": "หอย", "생선": "ปลา"},
        "what_not": {"조개류": "หอย", "돼지고기": "หมู", "소고기": "เนื้อวัว", "생선": "ปลา", "날것": "อาหารดิบ", "술": "แอลกอฮอล์",
                     "버섯": "เห็ด", "양파": "หัวหอม", "갑각류": "กุ้งและปู"},
        "req": ["ขอซอสแยกครับ/ค่ะ", "ขอสุกมากๆ ครับ/ค่ะ", "ขอไม่เค็มมากครับ/ค่ะ", "ไม่ใส่หัวหอมครับ/ค่ะ", "ไม่ใส่เห็ดครับ/ค่ะ",
                "ขอจานเล็กเพิ่มอีกใบครับ/ค่ะ", "ขอน้ำเปล่าครับ/ค่ะ", "รีบนิดหน่อย ขอเมนูที่ได้เร็วครับ/ค่ะ", "ขอเช็คบิลพร้อมอาหารเลยครับ/ค่ะ", "ไม่เผ็ดครับ/ค่ะ", "ขอจานเล็กสำหรับเด็กครับ/ค่ะ"],
    },
    "de": {
        "name": "독일어", "voice": "de-DE",
        "hello": "Hallo! Wir möchten bitte bestellen.", "thanks": "Vielen Dank!",
        "who": {"엄마": "Meine Mutter", "아빠": "Mein Vater", "아이": "Mein Kind", "부모님": "Ein Elternteil von mir", "가족": "Ein Familienmitglied"},
        "allergy": "{who} hat eine Allergie gegen {what}. Können Sie das bitte prüfen?", "allergy_me": "Ich habe eine Allergie gegen {what}. Können Sie das bitte prüfen?",
        "cannot": "{who} isst {what}.", "cannot_me": "Ich esse {what}.",
        "what": {"견과류": "Nüsse", "우유": "Milch", "달걀": "Eier", "밀가루": "Gluten (Weizen)", "갑각류": "Krebstiere (Garnelen, Krabben)",
                 "조개류": "Muscheln", "생선": "Fisch"},
        "what_not": {"조개류": "keine Muscheln", "돼지고기": "kein Schweinefleisch", "소고기": "kein Rindfleisch", "생선": "keinen Fisch",
                     "날것": "nichts Rohes", "술": "keinen Alkohol", "버섯": "keine Pilze", "양파": "keine Zwiebeln", "갑각류": "keine Krebstiere"},
        "req": ["Die Soße bitte separat.", "Bitte gut durchgebraten.", "Bitte wenig Salz.", "Bitte ohne Zwiebeln.", "Bitte ohne Pilze.",
                "Bitte einen extra Teller.", "Eine Karaffe Leitungswasser, bitte.", "Wir haben es eilig, bitte etwas Schnelles.", "Bitte die Rechnung gleich mit.", "Bitte nicht scharf.", "Einen kleinen Teller für das Kind, bitte."],
    },
    "it": {
        "name": "이탈리아어", "voice": "it-IT",
        "hello": "Buongiorno! Vorremmo ordinare, per favore.", "thanks": "Grazie mille!",
        "who": {"엄마": "Mia madre", "아빠": "Mio padre", "아이": "Il mio bambino", "부모님": "Un mio genitore", "가족": "Un mio familiare"},
        "allergy": "{who} ha un'allergia {what}. Potete controllare, per favore?", "allergy_me": "Ho un'allergia {what}. Potete controllare, per favore?",
        "cannot": "{who} non mangia {what}.", "cannot_me": "Non mangio {what}.",
        "what": {"견과류": "alla frutta a guscio", "우유": "al latte", "달걀": "alle uova", "밀가루": "al glutine", "갑각류": "ai crostacei",
                 "조개류": "ai molluschi", "생선": "al pesce"},
        "what_not": {"조개류": "molluschi (cozze, vongole)", "돼지고기": "carne di maiale", "소고기": "manzo", "생선": "pesce", "날것": "cibi crudi",
                     "술": "alcol", "버섯": "funghi", "양파": "cipolla", "갑각류": "crostacei"},
        "req": ["La salsa a parte, per favore.", "Ben cotto, per favore.", "Poco sale, per favore.", "Senza cipolla, per favore.",
                "Senza funghi, per favore.", "Un piatto in più, per favore.", "Una caraffa d'acqua, per favore.", "Abbiamo fretta, qualcosa di veloce, per favore.", "Il conto insieme, per favore.", "Non piccante, per favore.", "Un piattino per il bambino, per favore."],
    },
    "es": {
        "name": "스페인어", "voice": "es-ES",
        "hello": "¡Hola! Queremos pedir, por favor.", "thanks": "¡Muchas gracias!",
        "who": {"엄마": "Mi madre", "아빠": "Mi padre", "아이": "Mi hijo", "부모님": "Uno de mis padres", "가족": "Un familiar"},
        "allergy": "{who} tiene alergia {what}. ¿Pueden comprobarlo, por favor?", "allergy_me": "Tengo alergia {what}. ¿Pueden comprobarlo, por favor?",
        "cannot": "{who} no come {what}.", "cannot_me": "No como {what}.",
        "what": {"견과류": "a los frutos secos", "우유": "a la leche", "달걀": "al huevo", "밀가루": "al gluten", "갑각류": "al marisco (gambas, cangrejo)",
                 "조개류": "a los moluscos", "생선": "al pescado"},
        "what_not": {"조개류": "moluscos (mejillones, almejas)", "돼지고기": "cerdo", "소고기": "ternera", "생선": "pescado", "날것": "comida cruda",
                     "술": "alcohol", "버섯": "setas", "양파": "cebolla", "갑각류": "marisco"},
        "req": ["La salsa aparte, por favor.", "Bien hecho, por favor.", "Con poca sal, por favor.", "Sin cebolla, por favor.",
                "Sin setas, por favor.", "Un plato más, por favor.", "Una jarra de agua, por favor.", "Tenemos prisa, algo rápido, por favor.", "La cuenta junto con la comida, por favor.", "Sin picante, por favor.", "Un plato pequeño para el niño, por favor."],
    },
    "vi": {
        "name": "베트남어", "voice": "vi-VN",
        "hello": "Xin chào! Cho chúng tôi gọi món.", "thanks": "Cảm ơn nhiều!",
        "who": {"엄마": "Mẹ tôi", "아빠": "Bố tôi", "아이": "Con tôi", "부모님": "Bố mẹ tôi", "가족": "Người nhà tôi"},
        "allergy": "{who} bị dị ứng {what}. Xin kiểm tra giúp.", "allergy_me": "Tôi bị dị ứng {what}. Xin kiểm tra giúp.",
        "cannot": "{who} không ăn được {what}.", "cannot_me": "Tôi không ăn được {what}.",
        "what": {"견과류": "các loại hạt", "우유": "sữa", "달걀": "trứng", "밀가루": "bột mì", "갑각류": "tôm cua", "조개류": "nghêu sò", "생선": "cá"},
        "what_not": {"조개류": "nghêu sò", "돼지고기": "thịt heo", "소고기": "thịt bò", "생선": "cá", "날것": "đồ sống", "술": "rượu bia",
                     "버섯": "nấm", "양파": "hành tây", "갑각류": "tôm cua"},
        "req": ["Cho nước sốt để riêng.", "Làm chín kỹ giúp tôi.", "Nêm nhạt giúp tôi.", "Không cho hành tây.", "Không cho nấm.",
                "Cho thêm một cái đĩa nhỏ.", "Cho một bình nước lọc.", "Chúng tôi đang vội, cho món nào ra nhanh.", "Cho xin hóa đơn luôn nhé.", "Đừng cay nhé.", "Cho một đĩa nhỏ cho bé."],
    },
    "ko": {
        "name": "한국어", "voice": "ko-KR",
        "hello": "안녕하세요, 주문할게요.", "thanks": "감사합니다.",
        "who": {"엄마": "어머니", "아빠": "아버지", "아이": "아이", "부모님": "부모님", "가족": "일행"},
        "allergy": "{who}가 {what} 알레르기가 있어요. 확인 부탁드려요.", "allergy_me": "제가 {what} 알레르기가 있어요. 확인 부탁드려요.",
        "cannot": "{who}는 {what}를 못 드세요.", "cannot_me": "저는 {what}를 못 먹어요.",
        "what": {k: k for k in ALLERGENS}, "what_not": {k: k for k in CANNOT},
        "req": ["소스는 따로 주세요.", "잘 익혀 주세요.", "덜 짜게 해 주세요.", "양파는 빼 주세요.", "버섯은 빼 주세요.", "앞접시 하나 더 주세요.", "물 좀 주세요.", "시간이 없어서 빨리 나오는 걸로 주세요.", "계산서도 같이 주세요.", "맵지 않게 해 주세요.", "아이용 작은 접시 하나 주세요."],
    },
}
# 술은 '먹다'가 아니라 '마시다'
DRINK = {'fr': ("{who} ne boit pas d'alcool.", "Je ne bois pas d'alcool."), 'en': ('{who} does not drink alcohol.', 'I do not drink alcohol.'), 'ja': ('{who}はお酒が飲めません。', '私はお酒が飲めません。'), 'zh-Hans': ('{who}不能喝酒。', '我不能喝酒。'), 'zh-Hant': ('{who}不能喝酒。', '我不能喝酒。'), 'th': ('{who}ดื่มแอลกอฮอล์ไม่ได้ครับ/ค่ะ', 'ฉันดื่มแอลกอฮอล์ไม่ได้ครับ/ค่ะ'), 'de': ('{who} trinkt keinen Alkohol.', 'Ich trinke keinen Alkohol.'), 'it': ('{who} non beve alcolici.', 'Non bevo alcolici.'), 'es': ('{who} no bebe alcohol.', 'No bebo alcohol.'), 'vi': ('{who} không uống được rượu bia.', 'Tôi không uống được rượu bia.'), 'ko': ('{who}는 술을 못 드세요.', '저는 술을 못 마셔요.')}
REQUESTS = {k: k for k in REQUEST_KEYS}  # 화면의 '부탁할 것' 목록 (한국어)


def lang_key(scan):
    """메뉴판 언어 -> 문장 언어. 중국어는 간체/번체를 나눈다. 없으면 영어."""
    code = (scan.get("language_code") or "").replace("_", "-")
    base = code.split("-")[0].lower()
    if base == "zh":
        hant = any(t in code for t in ("Hant", "TW", "HK", "MO")) or "번체" in (scan.get("menu_language") or "")
        return "zh-Hant" if hant else "zh-Hans"
    return base if base in LANG else "en"


def voice(scan):
    k = lang_key(scan)
    code = scan.get("language_code") or ""
    if k == "zh-Hant" and "HK" in code:
        return "zh-HK"
    return LANG[k]["voice"]


def request_text(key, ko):
    L = LANG[key]
    return L["req"][REQUEST_KEYS.index(ko)] if ko in REQUEST_KEYS else ko


def speakable(text, key):
    """읽어 줄 때만: 태국어 '크랍/카' 두 가지를 하나로."""
    return text.replace("ครับ/ค่ะ", "ค่ะ") if key == "th" else text


def _who(p, L):
    if p.get("id") == "me" or p.get("relation") == "나":
        return None
    if p["name"] in L["who"]:
        return L["who"][p["name"]]
    return L["who"]["아이" if p.get("child") else "부모님" if p.get("relation") == "부모님" else "가족"]


def _sentence(L, kind, p, word, key=None, drink=False):
    who = _who(p, L)
    if drink:
        t = DRINK[key]
        s = t[1] if who is None else t[0].format(who=who)
    elif who is None:
        s = L[f"{kind}_me"].format(what=word)
    else:
        s = L[kind].format(who=who, what=word)
    if L is LANG["ko"]:  # 받침에 맞는 조사
        if who:
            s = s.replace(f"{who}가 ", f"{who}{menu2.josa(who, '이', '가')} ").replace(f"{who}는 ", f"{who}{menu2.josa(who, '은', '는')} ")
        s = s.replace(f"{word}를", f"{word}{menu2.josa(word, '을', '를')}")
    return s


def card(scan, people, lines, requests):
    """lines: [{item_id, count}], requests: [한국어 요청]."""
    key = lang_key(scan)
    L = LANG[key]
    items = {i["id"]: i for i in scan["items"]}
    top, top_ko = [], []
    for p in people:  # 알레르기를 먼저
        for a in p.get("allergies") or []:
            if a in L["what"]:
                top.append(_sentence(L, "allergy", p, L["what"][a]))
                top_ko.append(f"{p['name']}: {a} 알레르기가 있어요. 확인해 주세요.")
    for p in people:
        for c in p.get("cannot") or []:
            if c in L["what_not"]:
                top.append(_sentence(L, "cannot", p, L["what_not"][c], key, drink=c == "술"))
                top_ko.append(f"{p['name']}: {c}{menu2.josa(c, '을', '를')} 못 먹어요.")
    order = []
    for ln in lines:
        it = items.get(ln["item_id"])
        if it:
            order.append({"count": ln.get("count", 1), "orig": it["name_orig"], "ko": it["name_ko"], "price": it["price"]})
    reqs = [{"ko": r, "orig": request_text(key, r)} for r in requests if r in REQUEST_KEYS]
    text = "\n".join([*top, L["hello"], *[f"{o['count']} × {o['orig']}" for o in order], *[r["orig"] for r in reqs], L["thanks"]])
    code = (scan.get("language_code") or "").split("-")[0].lower()
    return {"lang": key, "lang_name": L["name"], "voice": voice(scan), "first": top, "first_ko": top_ko, "hello": L["hello"],
            "order": order, "requests": reqs, "thanks": L["thanks"], "text": text,
            "note": None if (code == "zh" or code in LANG) else "이 나라 말 문장이 아직 없어 영어로 보여 드려요.",
            "request_choices": list(REQUEST_KEYS)}
