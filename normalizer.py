"""Chuẩn hóa tin đăng thành 'khóa sản phẩm' để so giá cùng loại.

Thứ tự ưu tiên: tiêu đề (người bán tự ghi) trước, rồi tới trường cấu trúc của Chợ Tốt
(mã dung lượng, xuất xứ, lock, tình trạng), cuối cùng là phần mô tả tin (chỉ có khi xác minh).
Bảng mã và các dấu hiệu học từ tin thật ngày 26/10/2026.

Hai bộ luật, chọn theo từng từ khóa trong watchlist.json (normalize_watch):
- "iphone": tách đời máy, dung lượng, xách tay / VN/A / lock (normalize).
- "keyword": mọi sản phẩm khác — nhóm theo từ khóa + danh mục Chợ Tốt + mới/đã dùng (+ năm với xe)
  (normalize_keyword).
"""
import re
import unicodedata

SKIP_WORDS = (
    "thu mua", "cần mua", "can mua", "linh kiện", "linh kien",
    "xác máy", "xac may", "mô hình", "mo hinh", "dummy", "giao lưu",
)
SKIP_BUY = ("thu mua", "cần mua", "can mua", "giao lưu")  # nhóm "không phải tin bán" trong SKIP_WORDS

# Lý do 1 tin bị loại (hiện ở tab "Tin bỏ qua" của dashboard và sheet "Tin bỏ qua" của Excel)
SKIP_LABEL = {
    "mua": "Tin thu mua / cần mua / giao lưu",
    "linh-kien": "Linh kiện, xác máy, mô hình",
    "hong": "Máy hỏng/bể ghi ngay ở tiêu đề",
    "khong-khop": "Tiêu đề thiếu chữ của từ khóa",
    "loai-tru": "Có chữ loại trừ",
    "thieu-doi": "Không nhận ra đời máy",
    "thieu-dung-luong": "Thiếu dung lượng (không so giá được)",
    "ngoai-gia": "Giá ngoài khoảng đã đặt",
    "gia-0": "Không ghi giá (thỏa thuận)",
    "khong-phai-ban": "Không phải tin bán",
    "khac": "Lý do khác",
}

# Mã Chợ Tốt -> giá trị (mobile_capacity, elt_origin, elt_lock, elt_condition)
# Mã 10 = 1TB (20/20 tin thật có "1TB" ở tiêu đề), mã 11 = 2TB ("iPhone 17 Pro Max 2T"); đối chiếu 26/10/2026
CAPACITY_CODES = {5: 64, 6: 128, 7: 256, 9: 512, 10: 1024, 11: 2048}
STORAGE_SIZES = (64, 128, 256, 512, 1024, 2048)
ORIGIN_VN = 1
LOCK_CODE = 2           # elt_lock: 1 = Quốc tế, 2 = Lock
CONDITION_NEW = 1       # elt_condition: 1 = mới, 2 = đã dùng (chưa sửa), 3 = đã qua sửa chữa
CONDITION_REPAIRED = 3

_MODEL = re.compile(
    r"(?:iphone|ip)\s*(\d{1,2})\s*(pro\s*max|promax|pm|pro|plus|mini|air)?\b", re.I
)
_STORAGE = re.compile(r"(?<!\d)(\d{1,4})\s*(gb|g|tb|t)\b", re.I)
_GREY = re.compile(
    r"xách tay|xach tay|quốc tế|quoc te|\bqte\b|\b(?:ll|zp|za|jp|j|kh|ch)/a\b|\bmỹ\b", re.I
)
_VNA = re.compile(r"\bvn/a\b|chính hãng|chinh hang|\bfpt\b|\btgdd\b|thế giới di động", re.I)
# Máy lock (ghép sim) rẻ hơn hẳn quốc tế: để chung nhóm sẽ sinh "deal" giả.
_LOCK = re.compile(r"\block\b|sim ghép|ghép sim", re.I)

# Tiêu đề ghi rõ máy hỏng: bỏ qua hẳn như thiết kế gốc.
_DEFECT_WORDS = (r"(?:bể|vỡ|nứt|hư|lỗi|sọc màn|màn sọc|ám màn|thay màn|treo táo|mất face"
                 r"|mất vân tay|dính icloud|khóa icloud|ẩn icloud|icloud ẩn|ẩn id)")
_NEGATED = re.compile(r"\b(?:không|ko|chưa)\s+(?:bị\s+)?" + _DEFECT_WORDS, re.I)
_DEFECT = re.compile(r"\b" + _DEFECT_WORDS, re.I)

# Dấu hiệu làm giá KHÔNG so được với máy zin bình thường. Học từ mô tả các tin rẻ bất thường
# trên Chợ Tốt (26/10/2026): phần lớn là máy bypass, giá "đưa trước" trả góp, màn/vỏ đã thay.
# Tin có dấu hiệu được xếp nhóm riêng (…|bypass, …|tra-truoc…) và không bao giờ bị báo deal.
FLAGS = {
    "bypass": re.compile(
        r"bypa?s|by\.?\s?ba\.?\s?ss|bybass|\bbb\b|chỉ (?:dùng|xài|sài) wifi"
        r"|\b(?:không|khong|ko|k|hok)\s+(?:(?:dùng|xài|sài|dung|nghe gọi|nhận)\s+(?:được\s+)?)?sim\b"
        r"|ẩn (?:id|icloud|icl|tk)|icloud ẩn|dính icloud|khóa icloud|x[oó][áa] icloud|dính face"
        r"|\bmdm\b", re.I),
    "tra-truoc": re.compile(r"đưa\s*tr(?:ước|c)\b|g\s?ó\s?p tay đôi|bao nậu|nậu s[ớở]", re.I),
    "thay-linh-kien": re.compile(
        r"màn\s+(?:đã\s+)?(?:thay|oled|gx|hx|soft|1:1|ép|lô|linh kiện)|màn\s+hình\s+(?:đã\s+)?thay"
        r"|(?:đã\s+)?thay màn"
        r"|màn\s+(?:zin\s+)?fix|ép kính|(?:vỏ|võ) thay|thay (?:vỏ|võ|main|lưng)|(?:main|lưng)\s+(?:đã\s+)?thay"
        r"|báo (?:màn|linh kiện)", re.I),
    "loi": re.compile(
        r"\b(?:bể|vỡ|nứt|sọc|mực|ám|treo táo|bi bát|mất vân tay)\b|mất\s*face|màn\s+(?:zin\s+)?đốm|đốm\s+màn"
        r"|lỗi\s+(?:face|cam|loa|mic|wifi|sóng|cảm ứng|màn|main|nguồn|vân tay)"
        r"|cam(?:era)?\s+(?:sau\s+|trước\s+)?mờ|\b(?:không|k|ko)\s+(?:dùng|dung|xài)\s+được\s+face", re.I),
}
# Chỉ xét trong tiêu đề: người bán ghi "oled" ở tiêu đề là màn thay (trong mô tả có thể chỉ là thông số máy)
_TITLE_REPLACED = re.compile(r"\boled\b", re.I)
FLAG_LABEL = {"bypass": "bypass/không sim", "tra-truoc": "giá trả trước",
              "thay-linh-kien": "đã thay linh kiện", "loi": "có lỗi"}
NO_ALERT = set(FLAGS)
# bỏ các cụm phủ định / câu bảo hành trước khi dò lỗi ("không lỗi", "lỗi 1 đổi 1", "chưa thay màn")
_FLAG_NEGATION = re.compile(
    r"\b(?:không|ko|k|kg|chưa|hok|hông)\s+(?:bị\s+|có\s+)?"
    r"(?:lỗi|bể|vỡ|nứt|hư|sọc|mực|đốm|ám|thay màn|thay vỏ|thay main|thay lưng|fix)"
    r"|lỗi\s*(?:1|một)\s*đổi\s*(?:1|một)", re.I)

# Tình trạng máy: % pin và % ngoại hình. Cách ghi học từ 100 mô tả thật (26/10/2026):
# "Pin 86%", "pin zin 85", "pin còn 72%", "pin 7x", "pin new 100%", "thay pin";
# "Ngoại hình 95%", "hình thức máy 95%", "đẹp 99", "keng 99%", "trầy xước nhiều", "ko trầy xước cấn móp".
_PIN_WORDS = r"(?:zin|còn|thay|mới|new|chính hãng|ip|hiện tại|sức khỏe|dung lượng)"
_BATTERY_NUM = re.compile(
    r"\bpin(?:\s+" + _PIN_WORDS + r")*\s*[:\-=]?\s*(\d{2,3})(?:[.,]\d+)?(?!\d)\s*(?:%|\b)", re.I)
_BATTERY_X = re.compile(r"\bpin(?:\s+" + _PIN_WORDS + r")*\s*[:\-=]?\s*(\d)x\b", re.I)
_BATTERY_LOW = re.compile(r"\bpin\s+(?:kém|thấp|yếu|chai|tụt)", re.I)
_BATTERY_NEW = re.compile(r"thay pin|\bpin\s+(?:thay|mới thay|vừa thay|new|mới)\b", re.I)
_COSMETIC_NUM = re.compile(
    r"(?:ngoại hình|ngoại hinh|hình thức|đẹp|keng|còn mới|(?<!pin )(?<!thay )\bmới|like ?new)"
    r"(?:\s+(?!pin\b)[^\s\d/|,.;:]+){0,3}\s*[:\-]?\s*"
    r"(\d{2,3})(?:[.,]\d+)?(?:\s*-\s*\d{2})?(?!\d)\s*(?:%|\b)", re.I)
_BARE_PERCENT = re.compile(r"(?<![\d.,])(\d{2,3})(?:[.,]\d+)?(?:\s*-\s*\d{2})?\s*%")
_COSMETIC_NEGATED = re.compile(
    r"\b(?:không|ko|k|kg|kho|chưa)\s+(?:bị\s+|có\s+)?(?:trầy|xước|cấn|móp)(?:[\s,]*(?:và|hay|trầy|xước|cấn|móp))*",
    re.I)
_COSMETIC_WORDS = [(re.compile(r"\b(?:cấn|móp|xấu|tróc|bong sơn)\b", re.I), 88),
                   (re.compile(r"\b(?:trầy|xước|nhăm|nhâm)\b", re.I), 93),
                   (re.compile(r"\bkeng\b|like ?new|như mới", re.I), 99)]


def _first_number(pattern, text, lo, hi):
    for m in pattern.finditer(text):
        v = int(m.group(1))
        if lo <= v <= hi:
            return v
    return None


def condition_info(title, body=""):
    """(pin %, ngoại hình %) người bán tự ghi; None nếu không ghi. Ưu tiên số có từ khóa đi kèm,
    sau đó tới "% trơn" trong tiêu đề: dưới 95% thường là pin ("Xanh 72%"), từ 95% là ngoại hình ("98%")."""
    text = f"{title} / {body or ''}"
    battery = _first_number(_BATTERY_NUM, text, 50, 100)
    if battery is None:
        x = _BATTERY_X.search(text)
        battery = int(x.group(1)) * 10 + 5 if x else None
    cosmetic = _first_number(_COSMETIC_NUM, text, 70, 100)
    for m in _BARE_PERCENT.finditer(title):
        v = int(m.group(1))
        if 95 <= v <= 100 and cosmetic is None:
            cosmetic = v
        elif 50 <= v < 95 and battery is None:
            battery = v
    if battery is None:  # chỉ có lời tả, không có số
        battery = 75 if _BATTERY_LOW.search(text) else 100 if _BATTERY_NEW.search(text) else None
    if cosmetic is None:
        clean = _COSMETIC_NEGATED.sub(" ", text)
        hits = [v for p, v in _COSMETIC_WORDS if p.search(clean)]
        cosmetic = min(hits) if hits else (99 if clean != text else None)
    return battery, cosmetic


def read_body(title, body):
    """Mọi thứ cần từ phần mô tả, gói thành dict để lưu vào attrs (không lưu nguyên văn mô tả
    vì có thể chứa số điện thoại người bán)."""
    battery, cosmetic = condition_info(title, body)
    return {"flag": text_flag(body), "lock_text": mentions_lock(body),
            "battery": battery, "cosmetic": cosmetic, "storage": body_storage(body)}

_VARIANT = {"pm": "pro-max", "promax": "pro-max", "pro": "pro",
            "plus": "plus", "mini": "mini", "air": "air"}
_VARIANT_LABEL = {"pro-max": "Pro Max", "pro": "Pro", "plus": "Plus", "mini": "Mini", "air": "Air"}
MARKET_VN = {"grey": "xách tay", "vna": "chính hãng VN/A", "lock": "bản lock", "unk": "chưa rõ nguồn gốc",
             # từ khóa chung: ô này là tình trạng mới / đã dùng theo mã của Chợ Tốt
             "new": "mới", "used": "đã dùng", "na": "không ghi tình trạng"}
CONDITION_LABEL = {"used": "", "new": " (mới)", "repaired": " (đã sửa)",
                   **{k: f" ({v})" for k, v in FLAG_LABEL.items()}}


def _storage_value(num, unit):
    """GB của 1 cặp (số, đơn vị) như '256 gb', '1 tb', '2t'; None nếu không phải dung lượng iPhone."""
    if unit.lower().startswith("t"):
        return num * 1024 if num in (1, 2) else None
    return num if num in STORAGE_SIZES else None


def _storage(text):
    for m in _STORAGE.finditer(text):
        v = _storage_value(int(m.group(1)), m.group(2))
        if v:
            return v
    return None


# Dung lượng trong MÔ TẢ (chỉ dùng khi tiêu đề và mã Chợ Tốt không có). Đo trên 721 tin iPhone thật (26/10/2026):
# mô tả ghi 1 dung lượng thì đúng 99,6% (505/507); 2 chỗ sai là mô tả liệt kê nhiều bản ("128 và 256gb",
# "256-512-1Tb"). Nên chỉ nhận khi chỉ có ĐÚNG 1 dung lượng và không còn số 64/128/256/512 nào khác đứng riêng.
_PHONE_VARIANT = r"(?:pro\s*max|promax|prm|pm|pro|plus|mini|air)"
_BODY_BARE = re.compile(
    r"(?:(?:iphone|ip)\s*\d{1,2}\s*" + _PHONE_VARIANT + r"?|\b\d{2}\s*" + _PHONE_VARIANT + r")\s*[-:,.]?\s*"
    r"(64|128|256|512)(?!\d|[.,]\d|\s*(?:%|tr\b|k\b|triệu|đ|gb|g\b|tb|t\b))", re.I)
_BARE_NUMBER = re.compile(r"(?<![\d.,/])(64|128|256|512)(?![\d.,]|\s*(?:%|tr\b|k\b|triệu|đ|hz|mah|mp|w\b))", re.I)


def body_storage(body):
    """Dung lượng (GB) ghi trong mô tả tin, hoặc None nếu không có / mơ hồ."""
    body = body or ""
    found = {v for m in _STORAGE.finditer(body) if (v := _storage_value(int(m.group(1)), m.group(2)))}
    found |= {int(m.group(1)) for m in _BODY_BARE.finditer(body)}
    if len(found) != 1:
        return None
    (value,) = found
    others = {int(m.group(1)) for m in _BARE_NUMBER.finditer(body)} - {value}
    return None if others else value


def _market(text):
    if _LOCK.search(text):
        return "lock"
    grey, vna = bool(_GREY.search(text)), bool(_VNA.search(text))
    if grey and not vna:
        return "grey"
    if vna and not grey:
        return "vna"
    return "unk"


def _market_from_code(origin):
    if origin is None:
        return "unk"
    return "vna" if origin == ORIGIN_VN else "grey"


def is_defect(text):
    """Máy bể/lỗi/dính iCloud không so giá với máy lành được. 'không lỗi' thì không tính."""
    return bool(_DEFECT.search(_NEGATED.sub(" ", text)))


def mentions_lock(text):
    return bool(_LOCK.search(text or ""))


def text_flag(text):
    """Dấu hiệu đầu tiên tìm thấy trong tiêu đề/mô tả (bypass, tra-truoc, thay-linh-kien, loi) hoặc None."""
    clean = _FLAG_NEGATION.sub(" ", text or "")
    for name, pattern in FLAGS.items():
        if pattern.search(clean):
            return name
    return None


def normalize(title, attrs=None, body=""):
    """attrs (tùy chọn): {"capacity", "origin", "lock", "condition"} = mã thô từ Chợ Tốt,
    cộng {"flag", "lock_text"} = kết quả đã đọc mô tả trước đó (lưu trong DB).
    body (tùy chọn): mô tả tin — chỉ dùng để nhận ra máy lock và các dấu hiệu bất thường."""
    attrs = attrs or {}
    low = title.lower()
    if any(w in low for w in SKIP_WORDS) or is_defect(low):
        return None
    m = _MODEL.search(title)
    if not m:
        return None
    # thứ tự tin cậy: tiêu đề > mã Chợ Tốt > mô tả (attrs["storage"] đã đọc sẵn từ mô tả, hoặc đọc từ body)
    storage = _storage(title) or CAPACITY_CODES.get(attrs.get("capacity")) or attrs.get("storage") \
        or body_storage(body)
    if not storage:
        return None  # thiếu dung lượng thì không so sánh được
    gen = m.group(1)
    raw_variant = re.sub(r"\s+", "", (m.group(2) or "")).lower()
    variant = "pro-max" if raw_variant in ("promax", "pm") else _VARIANT.get(raw_variant, "")
    market = _market(title)
    if attrs.get("lock") == LOCK_CODE or attrs.get("lock_text") or mentions_lock(body):
        market = "lock"
    elif market == "unk":
        market = _market_from_code(attrs.get("origin"))
    condition = text_flag(title) or ("thay-linh-kien" if _TITLE_REPLACED.search(title) else None) or \
        text_flag(body) or attrs.get("flag") or \
        {CONDITION_NEW: "new", CONDITION_REPAIRED: "repaired"}.get(attrs.get("condition"), "used")

    parts = ["iphone", gen] + ([variant] if variant else []) + [f"{storage}gb"]
    label = " ".join(
        ["iPhone", gen] + ([_VARIANT_LABEL[variant]] if variant else []) + [f"{storage}GB"]
    )
    return {
        "key": "-".join(parts) + "|" + market + ("" if condition == "used" else "|" + condition),
        "label": label + CONDITION_LABEL[condition],
        "market": market,
        "condition": condition,
    }


# ---------------------------------------------------------------- từ khóa bất kỳ (mọi loại sản phẩm)
# Kiểm chứng 26/10/2026 trên tin thật (MacBook, xe máy, máy lạnh, máy ảnh, iPad): Chợ Tốt đã lọc đúng
# từ khóa và trả kèm danh mục; condition_ad: 1 = đã sử dụng, 2 = mới (xe, đồ gia dụng…);
# máy tính/điện thoại dùng elt_condition: 1 = mới, 2 = đã dùng, 3 = đã sửa; xe có regdate (năm).
CONDITION_AD_USED, CONDITION_AD_NEW = 1, 2
GENERIC_SKIP = ("thu mua", "can mua", "can tim", "tim mua", "giao luu")  # so trên chữ đã bỏ dấu
# Chỉ xét tiêu đề: mô tả của shop hay có câu bảo hành ("lỗi 1 đổi 1") hoặc quảng cáo trả góp.
_GENERIC_FLAGS = {
    "tra-truoc": re.compile(r"(?:đưa|trả)\s*tr(?:ước|c)\b|góp tay đôi|bao nậu", re.I),
    "loi": re.compile(
        r"\b(?:hư|hỏng|lỗi|bể|vỡ|nứt|liệt|chết nguồn|không lên nguồn|không hoạt động|cần sửa|dính icloud"
        r"|khóa icloud|xác máy|xác xe|bán xác|rã xác|để lại linh kiện)\b", re.I),
}
_NEW_TEXT = re.compile(r"nguyên seal|new seal|mới 100\s*%|chưa (?:kích hoạt|active|sử dụng|qua sử dụng)"
                       r"|hàng mới|mới tinh|brand new", re.I)
_YEAR = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def fold(text):
    """Chữ thường, bỏ dấu, chỉ giữ chữ-số: 'Máy lạnh Daikin 1.5HP' -> 'may lanh daikin 1 5hp'."""
    s = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def slug(text):
    return fold(text).replace(" ", "-")


def watch_type(watch):
    """'iphone' hoặc 'keyword'. Không ghi "type" thì từ khóa có chữ iphone dùng luật iPhone."""
    t = (watch.get("type") or "auto").lower()
    if t in ("iphone", "keyword"):
        return t
    return "iphone" if "iphone" in fold(watch.get("keywords") or watch.get("name")) else "keyword"


def _exclude_reason(watch, title):
    """("loai-tru", chữ) nếu tiêu đề chứa 1 chữ trong "exclude" của từ khóa, ngược lại None."""
    t = f" {fold(title)} "
    for x in watch.get("exclude") or []:
        if fold(x) and f" {fold(x)} " in t:
            return "loai-tru", x
    return None


def _match_reason(watch, title):
    """None nếu tiêu đề đủ mọi chữ của từ khóa (bỏ dấu, không phân biệt dính liền: 'SH150i' khớp 'sh 150i')
    và không chứa chữ loại trừ; ngược lại (mã lý do, chi tiết)."""
    compact = fold(title).replace(" ", "")
    if watch.get("match", True):
        missing = [w for w in fold(watch.get("keywords")).split() if w not in compact]
        if missing:
            return "khong-khop", "thiếu: " + ", ".join(missing)
    return _exclude_reason(watch, title)


def matches(watch, title):
    return _match_reason(watch, title) is None


def _generic_skip_word(title):
    t = f" {fold(title)} "
    return next((x for x in GENERIC_SKIP if f" {x} " in t), None)


def _generic_flag(title):
    clean = _FLAG_NEGATION.sub(" ", title)
    for name, pattern in _GENERIC_FLAGS.items():
        if pattern.search(clean):
            return name
    return None


def _generic_condition(attrs, title):
    """(mới/đã dùng/không ghi, có phải máy đã sửa)."""
    ca, ec = attrs.get("condition_ad"), attrs.get("condition")
    if ca == CONDITION_AD_NEW or ec == CONDITION_NEW:
        return "new", False
    if ca == CONDITION_AD_USED or ec in (2, CONDITION_REPAIRED):
        return "used", ec == CONDITION_REPAIRED
    return ("new" if _NEW_TEXT.search(title) else "na"), False


def _year(watch, attrs, title):
    """Tách nhóm theo năm: mặc định chỉ khi Chợ Tốt có trường năm (xe); "group_by" có "year" thì lấy
    cả năm ghi trong tiêu đề; "group_by" không có "year" (vd. [] hoặc ["spec"]) thì không tách."""
    group_by = watch.get("group_by")
    if group_by is not None and "year" not in group_by:
        return None
    y = attrs.get("year")
    if y:
        return int(y)
    if group_by is not None:
        m = _YEAR.search(title)
        return int(m.group(1)) if m else None
    return None


# Điện thoại, laptop, máy tính bảng (mã danh mục kiểm chứng 26/10/2026): giá theo RAM/bộ nhớ chênh nhiều.
# Đo trên 97 tin MacBook Air M2 thật: gộp chung độ phân tán 18,4% (ngưỡng deal 37%); tách theo cấu hình
# 16/256, 8/256, 16/512 còn 7–10% (ngưỡng 15–21%).
SPEC_CATEGORIES = {5010, 5030, 5040}
_SPEC_SIZES = {4, 6, 8, 12, 16, 18, 24, 32, 36, 48, 64, 96, 128, 256, 512, 1024, 2048, 4096}


# "8/256", "16G/512", "12/256GB": RAM/bộ nhớ viết tắt không kèm đơn vị
_SPEC_PAIR = re.compile(r"(?<![\d.,])(\d{1,2})\s*(?:gb|g)?\s*/\s*(\d{1,4})\s*(gb|g|tb|t)?\b", re.I)


def _spec(title):
    """Cấu hình GB/TB ghi trong tiêu đề: 'MacBook Air M2 16G/1TB' -> '16GB/1TB', 'Air M2 8/256' ->
    '8GB/256GB' (None nếu không ghi)."""
    sizes = []

    def add(n):
        if n in _SPEC_SIZES and n not in sizes:
            sizes.append(n)

    for m in _SPEC_PAIR.finditer(title):
        ram, store = int(m.group(1)), int(m.group(2))
        store *= 1024 if (m.group(3) or "").lower().startswith("t") or store in (1, 2, 4) else 1
        if ram in _SPEC_SIZES and ram <= 96 and store in _SPEC_SIZES and store >= 64:
            add(ram)
            add(store)
    for m in _STORAGE.finditer(title):
        add(int(m.group(1)) * (1024 if m.group(2).lower().startswith("t") else 1))
    return "/".join(f"{n // 1024}TB" if n >= 1024 else f"{n}GB" for n in sorted(sizes)) or None


def _split_spec(watch, attrs):
    group_by = watch.get("group_by")
    return "spec" in group_by if group_by is not None else attrs.get("category") in SPEC_CATEGORIES


def normalize_keyword(watch, title, attrs=None, body=""):
    """Nhóm so giá của 1 tin theo từ khóa chung.
    Khóa: kw:<tên>~<danh mục>[~<năm>][~<cấu hình>]|<mới/đã dùng>[|<dấu hiệu>].
    Tin khớp nhiều từ khóa thì thuộc nhiều nhóm (bảng listing_keys)."""
    attrs = attrs or {}
    if _generic_skip_word(title) or not matches(watch, title):
        return None
    cond, repaired = _generic_condition(attrs, title)
    if watch.get("phone_rules"):  # điện thoại/máy tính bảng khác: đọc cả mô tả như luật iPhone
        flag = text_flag(title) or text_flag(body) or attrs.get("flag")
    else:
        flag = _generic_flag(title)
    flag = flag or ("repaired" if repaired else None)
    cat, year = attrs.get("category"), _year(watch, attrs, title)
    spec = (_spec(title) or "?") if _split_spec(watch, attrs) else None
    product = f"kw:{slug(watch['name'])}~{cat or 0}" + (f"~{year}" if year else "") + (f"~{spec}" if spec else "")
    spec_label = "không ghi cấu hình" if spec == "?" else spec
    label = " · ".join(str(x) for x in (watch["name"], attrs.get("category_name"), year, spec_label) if x)
    return {
        "key": f"{product}|{cond}" + (f"|{flag}" if flag else ""),
        "label": label + (CONDITION_LABEL[flag] if flag else ""),
        "market": cond,
        "condition": flag or ("new" if cond == "new" else "used"),
    }


def normalize_watch(watch, title, attrs=None, body=""):
    """Chọn bộ luật theo từ khóa: iPhone (đời máy, dung lượng, nguồn gốc) hoặc từ khóa chung.
    Chữ loại trừ ("exclude") áp dụng cho cả hai bộ luật."""
    if watch_type(watch) == "iphone":
        return None if _exclude_reason(watch, title) else normalize(title, attrs, body)
    return normalize_keyword(watch, title, attrs, body)


def skip_reason(watch, title, attrs=None):
    """(mã, chi tiết) lý do `normalize_watch` loại tin này (mã xem SKIP_LABEL). Chạy lại các phép kiểm tra
    theo đúng thứ tự của bộ luật; ("khac", "") nếu không xác định được."""
    attrs = attrs or {}
    if watch_type(watch) != "iphone":
        word = _generic_skip_word(title)
        return ("mua", word) if word else (_match_reason(watch, title) or ("khac", ""))
    hit = _exclude_reason(watch, title)
    if hit:
        return hit
    low = title.lower()
    word = next((w for w in SKIP_WORDS if w in low), None)
    if word:
        return ("mua" if word in SKIP_BUY else "linh-kien"), word
    bad = _DEFECT.search(_NEGATED.sub(" ", low))
    if bad:
        return "hong", bad.group(0)
    if not _MODEL.search(title):
        return "thieu-doi", ""
    if not (_storage(title) or CAPACITY_CODES.get(attrs.get("capacity")) or attrs.get("storage")):
        return "thieu-dung-luong", "không ghi trong tiêu đề, mã Chợ Tốt hay mô tả"
    return "khac", ""


def is_keyword_key(key):
    return (key or "").startswith("kw:")
