"""Giả lập thị trường iPhone trên Chợ Tốt, có "đáp án" để chấm điểm bộ phân tích.

Hiệu chỉnh theo dữ liệu thật lấy ngày 26/10/2026 (~1.900 tin qua nhiều lần nạp):
- Giá nền (máy cũ, xách tay): 13 Pro Max 128GB ~7,3tr | 14 Pro Max 128GB ~12,4tr | 15 Pro Max 256GB ~15,8tr
  | 16 Pro Max 256GB ~20,5tr | 17 Pro Max 256GB ~26tr. VN/A cao hơn ~8%, bản lock thấp hơn ~30%.
- Tin có vấn đề chỉ ghi trong mô tả: đã thay linh kiện 18% (giá ~85% máy zin), lỗi 5% (~81%),
  bypass 3% (~69%), có "đưa trước" 3% (nửa là giá đầy đủ kèm góp, nửa là tiền trả trước).
- Máy zin còn lại: độ phân tán giá (sigma bền) ~9%; đời 13–14 ~14–15%, đời 16–17 ~6–8%.
- Pin/ngoại hình: 47% tin ghi % pin (30% trong số đó là 100% — pin đã thay), 51% ghi ngoại hình.
  Hồi quy trên tin thật: % pin không ảnh hưởng giá rao; ngoại hình +0,6% giá mỗi 1%.
Tin giả lập có cùng cấu trúc JSON với API thật (kể cả phần mô tả) nên đi qua đúng pipeline chạy thật.
"""
import collections
import math
import random
import statistics
import time

import analyzer
import config
import db
import pipeline
from normalizer import watch_type

# (thế hệ, biến thể, {dung lượng: giá nền máy cũ xách tay}, số tin trung bình/ngày)
MODELS = [
    ("13", "pro-max", {128: 7_300_000, 256: 7_900_000, 512: 8_700_000}, 9),
    ("13", "", {128: 6_300_000, 256: 7_000_000}, 5),
    ("14", "pro-max", {128: 12_400_000, 256: 13_100_000, 512: 14_200_000}, 11),
    ("14", "pro", {128: 9_800_000, 256: 10_600_000}, 4),
    ("15", "pro-max", {256: 15_800_000, 512: 17_800_000, 1024: 19_900_000}, 12),
    ("15", "pro", {128: 13_000_000, 256: 14_000_000}, 4),
    ("16", "pro-max", {256: 20_500_000, 512: 22_900_000}, 8),
    ("16", "pro", {128: 17_300_000, 256: 18_700_000}, 3),
    ("17", "pro-max", {256: 26_000_000, 512: 29_500_000}, 6),
]
STORAGE_WEIGHTS = [0.5, 0.35, 0.15]
# độ lệch giá của máy zin bình thường (người bán, bảo hành, khu vực...) theo đời máy
NOISE_SD = {"13": 0.085, "14": 0.09, "15": 0.06, "16": 0.045, "17": 0.045}
# tình trạng máy: (giá trị, tỷ lệ) theo phân bố trên tin thật; ảnh hưởng giá theo hồi quy trên tin thật
BATTERY_DIST = [(100, 30), (97, 10), (92, 23), (87, 22), (82, 9), (77, 4), (72, 2)]
COSMETIC_DIST = [(99, 54), (98, 14), (96, 5), (93, 12), (88, 15)]
TRUE_BATTERY_K, TRUE_COSMETIC_K = 0.0, 0.006
P_SAY_BATTERY, P_SAY_COSMETIC = 0.47, 0.51
# thị trường thật: (tỷ lệ, hệ số giá, xác suất tiêu đề có ghi rõ, mã elt_origin)
MARKETS = {"grey": (0.56, 1.00, 0.55, 8), "vna": (0.36, 1.08, 0.45, 1), "lock": (0.08, 0.70, 0.85, 8)}
REGIONS = [("Tp Hồ Chí Minh", 13000, 49), ("Hà Nội", 12000, 17), ("Cần Thơ", 5027, 7),
           ("Đà Nẵng", 3017, 6), ("Đồng Nai", 2010, 5), ("Bình Dương", 2011, 4),
           ("Hải Phòng", 4019, 3), ("Khác", 9000, 9)]
CAPACITY_CODE = {64: 5, 128: 6, 256: 7, 512: 9}
# loại tin (đáp án) và tỷ lệ
KINDS = {"normal": 0.587, "deal": 0.05, "scam": 0.025, "typo": 0.005, "defect": 0.02,
         "buyer": 0.015, "accessory": 0.01, "bypass": 0.03, "installment": 0.028, "parts": 0.18,
         "hidden_defect": 0.05}
JUNK = ("defect", "buyer", "accessory", "typo")                        # lộ ngay ở tiêu đề/giá
HIDDEN = ("bypass", "installment", "parts", "hidden_defect")           # chỉ lộ trong mô tả
DEPRECIATION_PER_DAY = 0.0012   # máy cũ mất giá ~3,6%/tháng
SHOP_MARKUP = 1.02
NEW_FACTOR = 1.22
REAL_SPREAD = 0.090             # sigma bền trung vị các nhóm máy zin thật (26/10/2026), để so khi hiệu chỉnh

_VAR_TEXT = {"pro-max": ["Pro Max", "Pro Max", "ProMax", "PM", "pro max"], "pro": ["Pro", "pro"],
             "": [""]}
_MARKET_TEXT = {"grey": ["xách tay", "Quốc tế", "LL/A", "ZA/A", "quốc tế Mỹ", "JP/A"],
                "vna": ["VN/A", "chính hãng VN/A", "chính hãng TGDD", "VN/A FPT"],
                "lock": ["lock", "bản lock", "Lock Mỹ"]}
_FILLERS = ["zin all", "fullbox", "BH 6 tháng", "máy zin", "màu titan", "xanh", "đen", "trắng",
            "trả góp 0%", "không lỗi", "nguyên zin chưa thay sửa", "giá tốt"]
_DEFECTS = ["bể màn", "nứt lưng", "lỗi Face ID", "mất face", "dính iCloud", "màn sọc", "hư loa",
            "thay màn"]
_BODY_BASE = ["Máy đẹp, pin tốt, bao test 7 ngày. Lỗi 1 đổi 1 trong 15 ngày đầu.",
              "Hỗ trợ trả góp 0%, thu cũ đổi mới, ship COD toàn quốc. Full chức năng không lỗi.",
              "Máy cá nhân dùng giữ gìn, còn hộp, giao dịch trực tiếp."]
_BODY_LOCK = ["Máy lock Mỹ, dùng sim ghép ổn định.", "Bản lock, đã ghép sim, nghe gọi bình thường."]
_BODY_HIDDEN = {
    "bypass": (["Máy bypass không dùng sim, chỉ dùng wifi, full chức năng.",
                "Máy by.ba.ss ko xài sim được, dùng wifi tải app bình thường."], ["bypass", "BB", "không sim"]),
    "installment": (["Đưa trước 4tr nhận máy, góp bao nậu sớ.", "Chỉ đưa trc 3tr5 là có máy, lên hồ sơ nhanh."],
                    ["góp tay đôi"]),
    "parts": (["Màn thay OLED 120Hz, vỏ thay, còn lại zin.", "Đã thay màn soft oled, cảm ứng mượt.",
               "Zin full màn fix.", "Máy thay lưng, còn lại zin."], ["màn oled"]),
    "hidden_defect": (["Máy chỉ bị sọc màn nhẹ, còn lại dùng tốt.", "Màn zin mực góc nhỏ.",
                       "Mất faceid, còn lại full chức năng."], ["mất face"]),
}
# giá so với máy zin cùng loại (đo trên tin thật); "installment": nửa số tin ghi tiền trả trước
_HIDDEN_PRICE = {"bypass": (0.35, 0.85), "installment": (0.25, 0.50), "parts": (0.72, 0.97),
                 "hidden_defect": (0.65, 0.95)}
# elt_lock điền sẵn: (xác suất có điền, mã) theo thị trường thật
_LOCK_FIELD = {"grey": (0.4, 1), "vna": (0.3, 1), "lock": (0.5, 2)}
CODE_FIELDS = ("mobile_capacity", "elt_origin", "elt_lock", "elt_condition")


def _pick(rng, weighted):
    r = rng.random() * sum(w for *_, w in weighted)
    for item in weighted:
        r -= item[-1]
        if r <= 0:
            return item
    return weighted[-1]


def _round_price(rng, p):
    p = max(100_000, round(p / 100_000) * 100_000)
    return p - 10_000 if rng.random() < 0.3 else p


def _title(rng, gen, variant, storage, market, is_new, show_market, show_storage):
    head = rng.choice(["iPhone", "iPhone", "Iphone", "IPHONE", "Apple iPhone", "ip"])
    if head == "ip":
        model = f"ip {gen}" + {"pro-max": "pm", "pro": " pro", "": ""}[variant]
    else:
        model = f"{head} {gen} {rng.choice(_VAR_TEXT[variant])}".strip()
    parts = [model]
    if show_storage:
        parts.append("1TB" if storage == 1024 else rng.choice([f"{storage}GB", f"{storage}gb", f"{storage}G"]))
    if show_market:
        parts.append(rng.choice(_MARKET_TEXT[market]))
    if is_new:
        parts.append(rng.choice(["mới 100%", "nguyên seal", "fullbox chưa active"]))
    parts += rng.sample(_FILLERS, rng.choice([0, 1, 1, 2]))
    return " ".join(parts)


def _condition_text(rng, battery, cosmetic):
    """Câu pin/ngoại hình theo cách người bán thật hay viết; nhiều người không ghi."""
    parts = []
    if rng.random() < P_SAY_BATTERY:
        parts.append(rng.choice(["Pin 100%", "pin thay mới 100%", "pin new 100%"]) if battery == 100 else
                     rng.choice([f"Pin {battery}%", f"pin zin {battery}", f"pin còn {battery}%"]))
    if rng.random() < P_SAY_COSMETIC:
        if cosmetic >= 95:
            parts.append(rng.choice([f"Ngoại hình {cosmetic}%", f"đẹp {cosmetic}%", f"hình thức máy {cosmetic}%"]
                                    + (["máy đẹp keng"] if cosmetic == 99 else [])))
        else:
            parts.append("viền trầy xước nhẹ" if cosmetic >= 90 else "vỏ cấn móp nhẹ")
    return " / ".join(parts)


def make_ad(rng, list_id, t, end, kinds=KINDS):
    """Sinh 1 tin dạng JSON giống API Chợ Tốt; trường bắt đầu bằng '_' là đáp án."""
    gen, variant, storages, _ = _pick(rng, MODELS)
    sizes = list(storages)
    storage = rng.choices(sizes, weights=STORAGE_WEIGHTS[:len(sizes)])[0]
    market = rng.choices(list(MARKETS), weights=[m[0] for m in MARKETS.values()])[0]
    _, m_factor, p_show, origin_code = MARKETS[market]
    is_new = rng.random() < 0.04
    shop = rng.random() < 0.65
    kind = rng.choices(list(kinds), weights=list(kinds.values()))[0]
    region, region_code, _ = _pick(rng, REGIONS)
    battery, cosmetic = (100, 100) if is_new else (_pick(rng, BATTERY_DIST)[0], _pick(rng, COSMETIC_DIST)[0])

    fair = storages[storage] * m_factor * (NEW_FACTOR if is_new else 1)
    fair *= 1 + DEPRECIATION_PER_DAY * max(0.0, (end - t) / 86400)
    fair *= 1 + TRUE_BATTERY_K * (battery - 91) + TRUE_COSMETIC_K * (cosmetic - 99)  # giá đúng của máy này
    sd = NOISE_SD[gen] * (0.4 if is_new else 1)
    ask = fair * (SHOP_MARKUP if shop else 1) * math.exp(rng.gauss(0, sd))
    show_storage = rng.random() < 0.85
    title = _title(rng, gen, variant, storage, market, is_new, rng.random() < p_show, show_storage)
    body = " / ".join(x for x in (rng.choice(_BODY_BASE), _condition_text(rng, battery, cosmetic)) if x)
    ad_type = "s"
    if kind == "deal":
        ask = fair * rng.uniform(0.62, 0.80)
    elif kind == "scam":
        ask = fair * rng.uniform(0.20, 0.50)
    elif kind == "typo":
        ask = ask * rng.choice([10, 0.1])
    elif kind == "defect":
        title += " " + rng.choice(_DEFECTS)
        ask = fair * rng.uniform(0.45, 0.70)
    elif kind == "buyer":
        title = rng.choice(["Thu mua", "Cần mua", "Thu mua giá cao"]) + " " + title
        ad_type = rng.choice(["s", "k"])
    elif kind == "accessory":
        title = rng.choice(["Ốp lưng", "Cường lực", "Ốp da"]) + " " + title
        ask = rng.uniform(120_000, 450_000)
    elif kind in HIDDEN:
        bodies, title_words = _BODY_HIDDEN[kind]
        body = rng.choice(bodies) + " / " + body
        if rng.random() < 0.2:
            title += " " + rng.choice(title_words)
        if kind != "installment" or rng.random() < 0.5:  # nửa số tin "đưa trước" vẫn ghi giá đầy đủ
            ask = fair * rng.uniform(*_HIDDEN_PRICE[kind])
    if market == "lock" and rng.random() < 0.7:
        body = rng.choice(_BODY_LOCK) + " " + body
    p_lock, lock_code = _LOCK_FIELD[market]
    return {
        "list_id": list_id, "ad_id": list_id + 40_000_000, "subject": title, "body": body,
        "price": _round_price(rng, ask), "list_time": int(t * 1000),
        "region_name": region, "region_v2": region_code, "category": 5010,
        "category_name": "Điện thoại", "type": ad_type, "company_ad": True if shop else None,
        "mobile_capacity": CAPACITY_CODE.get(storage) if rng.random() < 0.8 else None,
        "elt_origin": origin_code if rng.random() < 0.6 else None,
        "elt_lock": lock_code if rng.random() < p_lock else None,
        "elt_condition": 1 if is_new else 2, "status": "active",
        "_truth": kind, "_fair": int(fair), "_gen": gen, "_market": market,
        "_battery": battery, "_cosmetic": cosmetic,
    }


def detail(ad):
    """Dạng trả về của API chi tiết tin (rút gọn)."""
    return {"ad": public(ad)}


def generate(days=30, seed=42, end=None, per_day=None):
    """Sinh lịch sử `days` ngày, kết thúc tại `end` (mặc định: bây giờ). Trả danh sách theo thời gian."""
    rng = random.Random(seed)
    end = time.time() if end is None else end
    start = end - days * 86400
    per_day = per_day or sum(m[-1] for m in MODELS) / (1 - KINDS["buyer"] - KINDS["accessory"])
    n = int(days * per_day)
    times = sorted(rng.uniform(start, end) for _ in range(n))
    return [make_ad(rng, 200_000_000 + i, t, end) for i, t in enumerate(times)]


def watch_for(ad):
    """Giả lập chỉ sinh tin iPhone: chỉ ghép với từ khóa dùng luật iPhone."""
    for w in config.WATCHLIST:
        if watch_type(w) == "iphone" and f" {ad['_gen']} " in f" {w['keywords']} ":
            return w
    return {"type": "iphone", "min_price": 0, "max_price": 10**12}


def public(ad):
    return {k: v for k, v in ad.items() if not k.startswith("_")}


# ---------------------------------------------------------------- backtest
def backtest(db_path, days=30, seed=42, warmup_days=7, use_codes=True, use_body=True, use_condition=True):
    """Phát lại toàn bộ tin giả lập theo thứ tự thời gian qua pipeline thật rồi chấm điểm.
    use_codes=False: bỏ các mã cấu trúc của Chợ Tốt; use_body=False: không đọc mô tả tin;
    use_condition=False: không quy đổi giá theo pin/ngoại hình. Tắt cả ba (+ DEAL_Z=0) = thiết kế gốc."""
    end = time.time()
    ads = generate(days, seed, end)
    conn = db.connect(db_path)
    db.set_status(conn, source="simulated", state="stopped", generated_at=end,
                  sim_days=days, sim_seed=seed)
    saved, config.USE_CONDITION = config.USE_CONDITION, use_condition
    t0 = ads[0]["list_time"] / 1000
    rows = []
    try:
        for ad in ads:
            t = ad["list_time"] / 1000
            pub = public(ad)
            if not use_codes:
                pub.update(dict.fromkeys(CODE_FIELDS))
            if not use_body:
                pub["body"] = ""
            status, res = pipeline.process(conn, watch_for(ad), pub, now=t, send=False)
            conn.execute("INSERT OR REPLACE INTO sim_truth (list_id, truth, fair) VALUES (?, ?, ?)",
                         (str(ad["list_id"]), ad["_truth"], ad["_fair"]))
            enough, got = False, None
            if status == "new":
                got = conn.execute("SELECT key, battery, cosmetic FROM listings WHERE list_id = ?",
                                   (str(ad["list_id"]),)).fetchone()
                h = analyzer.clean(db.prices(conn, got["key"], t - config.WINDOW_DAYS * 86400,
                                             exclude=str(ad["list_id"])))
                enough = len(h) >= config.MIN_SAMPLES
            rows.append({"ad": ad, "status": status, "pred": res["label"] if res else None,
                         "enough": enough, "warm": t - t0 >= warmup_days * 86400,
                         "battery": got["battery"] if got else None, "cosmetic": got["cosmetic"] if got else None})
    finally:
        config.USE_CONDITION = saved
    conn.execute("UPDATE listings SET url = NULL")  # mã tin giả: không được trỏ tới tin thật
    conn.commit()
    return _score(conn, rows, days, end)


def sweep_z(days=30, seed=42, values=(0.0, 1.0, 1.5, 2.0, 2.5, 3.0)):
    """Chạy lại toàn bộ backtest với từng giá trị DEAL_Z (bộ dữ liệu giữ nguyên)."""
    saved, out = config.DEAL_Z, []
    try:
        for z in values:
            config.DEAL_Z = z
            out.append((z, backtest(":memory:", days=days, seed=seed)))
    finally:
        config.DEAL_Z = saved
    return out


def _pr(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return p, r


def _truth(r):
    t = r["ad"]["_truth"]
    return "normal" if t in HIDDEN else t


def _spread_by_key(conn, end):
    out = []
    for key, _label, n in db.key_counts(conn, end - config.WINDOW_DAYS * 86400):
        if n >= 15 and "|" in key and key.count("|") == 1:
            p = db.prices(conn, key, end - config.WINDOW_DAYS * 86400)
            med = statistics.median(p)
            out.append(1.4826 * statistics.median(abs(x - med) for x in p) / med)
    return statistics.median(out) if out else None


# ---------------------------------------------------------------- tốc độ bán: kiểm chứng phương pháp
# GIẢ ĐỊNH dùng để kiểm tra bộ phân tích có tìm lại đúng hay không — KHÔNG phải số đo thật.
# Tốc độ biến mất (lần) so với tin cá nhân, giá quanh trung vị, pin 85–99%.
SPEED_TRUTH = {"mean_days": 5.0, "Tin của shop": 0.25, "Rẻ hơn trung vị ≥10%": 2.0,
               "Đắt hơn trung vị ≥10%": 0.6, "Pin < 85%": 0.7}


def _true_life_days(rng, ad, truth):
    rate = 1 / truth["mean_days"]
    shop = bool(ad["company_ad"])
    rel = ad["price"] / (ad["_fair"] * (SHOP_MARKUP if shop else 1))
    rate *= truth["Tin của shop"] if shop else 1
    rate *= truth["Rẻ hơn trung vị ≥10%"] if rel <= 0.90 else truth["Đắt hơn trung vị ≥10%"] if rel >= 1.10 else 1
    rate *= truth["Pin < 85%"] if ad["_battery"] < 85 else 1
    return rng.expovariate(rate)


def speed_backtest(days=30, seed=42, start_after=7, step_hours=1.0, truth=SPEED_TRUTH, db_path=":memory:"):
    """Giả lập: mỗi tin có thời gian còn đăng thật (theo giả định), bot bắt đầu chạy sau `start_after`
    ngày (nạp các tin đang còn = bị cắt trái), rồi mỗi giờ nhận tin mới và kiểm tra lại tin cũ đúng như
    pipeline thật (track_once, 6 giờ/lần). Cuối cùng phân tích và so với giả định."""
    import speed

    end = time.time()
    rng = random.Random(seed + 1)
    ads = generate(days, seed, end)
    gone = {str(a["list_id"]): a["list_time"] / 1000 + _true_life_days(rng, a, truth) * 86400 for a in ads}
    conn = db.connect(":memory:")  # ~10 vạn lượt ghi: chạy trong bộ nhớ, cuối cùng mới chép ra file
    db.set_status(conn, source="simulated", state="stopped", generated_at=end, sim_days=days, sim_seed=seed)

    def check_at(t):
        return lambda lid: (t < gone[lid], "active" if t < gone[lid] else "404", None)

    t = ads[0]["list_time"] / 1000 + start_after * 86400
    i = 0
    while t < end:
        while i < len(ads) and ads[i]["list_time"] / 1000 <= t:
            if gone[str(ads[i]["list_id"])] > t:  # chỉ thấy được tin còn đăng
                pipeline.process(conn, watch_for(ads[i]), public(ads[i]), alert=False, now=t)
            i += 1
        pipeline.track_once(conn, check_at(t), now=t, budget=100_000)
        t += step_hours * 3600
    conn.execute("UPDATE listings SET url = NULL")  # mã tin giả: không được trỏ tới tin thật
    conn.commit()
    if db_path != ":memory:":
        out = db.connect(db_path)
        conn.backup(out)
        out.close()
    return speed.analyze(conn), truth


def render_speed_validation(res, truth):
    import speed

    lines = [speed.render(res, "Kiểm chứng phương pháp đo tốc độ bán trên dữ liệu giả lập"), "",
             "## So với đáp án giả định", "",
             "Giả lập dùng giả định dưới đây (không phải số thật) để kiểm tra bộ phân tích có tìm lại đúng không.", "",
             "| Đặc điểm | Đáp án giả định | Ước lượng | Khoảng tin cậy 95% | Tìm lại đúng? |", "|---|---|---|---|---|"]
    for r in res["ratios"]:
        want = truth.get(r["name"], 1.0)
        ok = "đúng" if r["lo"] <= want <= r["hi"] else "lệch"
        lines.append(f"| {r['name']} | ×{want:g} | ×{r['rr']:.2f} | {r['lo']:.2f} – {r['hi']:.2f} | {ok} |")
    return "\n".join(lines) + "\n"


def _score(conn, rows, days, end):
    by_truth = collections.Counter(r["ad"]["_truth"] for r in rows)
    junk = [r for r in rows if r["ad"]["_truth"] in JUNK]
    hidden = [r for r in rows if r["ad"]["_truth"] in HIDDEN]
    sellable = [r for r in rows if r["ad"]["_truth"] in ("normal", "deal", "scam") + HIDDEN]
    parsed = [r for r in sellable if r["status"] == "new"]
    evaluable = [r for r in parsed if r["enough"] and r["warm"]]

    confusion = collections.Counter((_truth(r), r["pred"]) for r in evaluable)
    metrics = {}
    for truth, label in (("deal", "deal"), ("scam", "scam_risk")):
        tp = confusion[(truth, label)]
        fp = sum(v for (t, p), v in confusion.items() if p == label and t != truth)
        fn = sum(v for (t, p), v in confusion.items() if t == truth and p != label)
        metrics[truth] = _pr(tp, fp, fn) + (tp, fp, fn)
    alerts = [r for r in rows if r["pred"] and r["warm"]]
    useful = [r for r in alerts if r["ad"]["_truth"] in ("deal", "scam")]

    def reason(r):
        t = r["ad"]["_truth"]
        if t in HIDDEN:
            return {"bypass": "máy bypass (chỉ ghi trong mô tả)", "installment": "giá 'đưa trước' trả góp",
                    "parts": "đã thay màn/vỏ (mô tả)", "hidden_defect": "lỗi chỉ ghi trong mô tả"}[t]
        if r["ad"]["_market"] == "lock":
            return "máy lock không ghi 'lock'"
        if r["ad"]["_cosmetic"] <= 93:
            return "ngoại hình xấu (rẻ là hợp lý)"
        return "giá thường nhưng thấp (biến động giá)"

    # độ chính xác bộ trích pin/ngoại hình (so với đáp án, chỉ tính tin trích được số)
    ext = {}
    for field in ("battery", "cosmetic"):
        got = [(r[field], r["ad"]["_" + field]) for r in rows if r[field] is not None]
        ext[field] = (len(got), sum(abs(g - t) <= 0.5 for g, t in got) / len(got) if got else None)

    false_pos = [r for r in alerts if r["ad"]["_truth"] not in ("deal", "scam")]
    warm_days = max(1, days - 7)

    # độ chính xác trung vị cuối kỳ so với "giá hợp lý" thật (nhóm >= 15 tin)
    med_err = []
    fair_by_key = collections.defaultdict(list)
    for r in parsed:
        if r["ad"]["_truth"] == "normal" and end - r["ad"]["list_time"] / 1000 < 3 * 86400:
            key = conn.execute("SELECT key FROM listings WHERE list_id = ?",
                               (str(r["ad"]["list_id"]),)).fetchone()[0]
            fair_by_key[key].append(r["ad"]["_fair"])
    for key, label, n in db.key_counts(conn, end - config.WINDOW_DAYS * 86400):
        if n >= 15 and len(fair_by_key.get(key, [])) >= 3:
            med = analyzer.median_clean(db.prices(conn, key, end - config.WINDOW_DAYS * 86400))
            fair = statistics.median(fair_by_key[key])
            med_err.append((key, med, fair, (med - fair) / fair))

    return {
        "days": days, "total": len(rows), "by_truth": dict(by_truth),
        "junk": len(junk), "junk_leak": sum(bool(r["pred"]) for r in junk),
        "hidden": len(hidden), "hidden_leak": sum(bool(r["pred"]) for r in hidden),
        "sellable": len(sellable), "parsed": len(parsed), "evaluable": len(evaluable),
        "confusion": confusion, "metrics": metrics, "alerts": len(alerts), "useful": len(useful),
        "per_day": len(alerts) / warm_days,
        "fp_reasons": dict(collections.Counter(reason(r) for r in false_pos)),
        "fp_examples": [r["ad"]["subject"] for r in false_pos[:5]],
        "median_error": med_err, "spread": _spread_by_key(conn, end), "extract": ext,
    }


def _fmt(x, pct=True):
    if x is None:
        return "-"
    return f"{x * 100:.1f}%" if pct else f"{x:.1f}"


def render_report(r, variants=None, z_sweep=None):
    """Báo cáo Markdown tiếng Việt. variants: [(tên, kết quả)]; z_sweep: [(z, kết quả)]."""
    m = r["metrics"]
    lines = [
        f"# Báo cáo backtest dữ liệu giả lập ({r['days']} ngày)",
        "",
        f"Tạo lúc {time.strftime('%d/%m/%Y %H:%M')} · ngưỡng deal = max({config.DEAL_PCT:.0%}, "
        f"{config.DEAL_Z:g} × độ phân tán nhóm), nghi lừa đảo ≥ {config.SCAM_PCT:.0%}, "
        f"cửa sổ {config.WINDOW_DAYS} ngày, tối thiểu {config.MIN_SAMPLES} mẫu.",
        "",
        "## 1. Dữ liệu",
        "",
        f"- Tổng số tin: **{r['total']}**  ({', '.join(f'{k}: {v}' for k, v in sorted(r['by_truth'].items()))})",
        f"- Độ phân tán giá nhóm máy zin (sigma bền, trung vị các nhóm): giả lập **{_fmt(r['spread'])}** "
        f"— thật đo ngày 26/10/2026: **{REAL_SPREAD:.1%}**",
        f"- Tin rác lộ ở tiêu đề/giá (thu mua, phụ kiện, máy lỗi, gõ nhầm giá): {r['junk']} → lọt thành "
        f"cảnh báo: **{r['junk_leak']}**",
        f"- Tin có vấn đề chỉ ghi trong mô tả (bypass, giá trả trước, thay linh kiện, lỗi): {r['hidden']} → lọt "
        f"thành cảnh báo: **{r['hidden_leak']}**",
        "- Bộ trích tình trạng máy: " + " · ".join(
            f"{name} trích được {n} tin, đúng {_fmt(acc)}" for name, (n, acc) in
            (("pin", r["extract"]["battery"]), ("ngoại hình", r["extract"]["cosmetic"]))) +
        " (câu giả lập viết theo đúng các mẫu đã học nên chỉ kiểm tra đường đi dữ liệu; độ chính xác trên "
        "tin thật xem test `test_condition_info_from_real_listings`)",
        f"- Tin bán máy: {r['sellable']} → chuẩn hóa được: {r['parsed']} "
        f"({r['parsed'] / max(1, r['sellable']):.0%}); còn lại thiếu dung lượng hoặc tiêu đề lạ",
        f"- Đủ lịch sử để chấm (sau 7 ngày khởi động, nhóm có ≥ {config.MIN_SAMPLES} mẫu): {r['evaluable']}",
        "",
        "## 2. Chất lượng cảnh báo",
        "",
        "| Loại | Precision (báo đúng / tổng báo) | Recall (bắt được / tổng thật) | TP | FP | FN |",
        "|---|---|---|---|---|---|",
    ]
    for name, key in (("Deal hời", "deal"), ("Nghi lừa đảo", "scam")):
        p, rc, tp, fp, fn = m[key]
        lines.append(f"| {name} | {_fmt(p)} | {_fmt(rc)} | {tp} | {fp} | {fn} |")
    lines += [
        "",
        f"Tổng cảnh báo: {r['alerts']} (~{r['per_day']:.1f}/ngày), trong đó {r['useful']} là tin thật sự "
        f"rẻ bất thường ({r['useful'] / max(1, r['alerts']):.0%}).",
        "",
        "Ma trận nhầm lẫn (hàng = đáp án, cột = hệ thống báo; tin có vấn đề ẩn tính là 'normal'):",
        "",
        "| Đáp án \\ Báo | không báo | deal | scam_risk |",
        "|---|---|---|---|",
    ]
    for truth in ("normal", "deal", "scam"):
        c = r["confusion"]
        lines.append(f"| {truth} | {c[(truth, None)]} | {c[(truth, 'deal')]} | {c[(truth, 'scam_risk')]} |")
    if r["fp_reasons"]:
        lines += ["", "Nguyên nhân báo nhầm: " + ", ".join(f"{k}: {v}" for k, v in r["fp_reasons"].items())]
        lines += [f"- ví dụ: `{t}`" for t in r["fp_examples"]]
    if variants:
        lines += [
            "",
            "### So sánh phương án trên cùng bộ dữ liệu",
            "",
            "| Phương án | Chuẩn hóa được | Báo/ngày | Deal precision | Deal recall | Lừa đảo precision | Lừa đảo recall | Báo nhầm |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for name, x in variants:
            dp, dr, _tp, dfp, _fn = x["metrics"]["deal"]
            sp, sr, _tp2, sfp, _fn2 = x["metrics"]["scam"]
            lines.append(f"| {name} | {x['parsed'] / max(1, x['sellable']):.0%} | {x['per_day']:.1f} | "
                         f"{_fmt(dp)} | {_fmt(dr)} | {_fmt(sp)} | {_fmt(sr)} | {dfp + sfp} |")
    if z_sweep:
        lines += [
            "",
            f"## 3. Dò hệ số ngưỡng thích ứng DEAL_Z (ngưỡng deal = max({config.DEAL_PCT:.0%}, Z × độ phân tán))",
            "",
            "| DEAL_Z | Báo/ngày | Deal precision | Deal recall | Tin thật sự rẻ / tổng báo |",
            "|---|---|---|---|---|",
        ]
        for z, x in z_sweep:
            dp, dr = x["metrics"]["deal"][:2]
            mark = " ← đang dùng" if abs(z - config.DEAL_Z) < 1e-9 else ""
            note = " (= ngưỡng cố định)" if z == 0 else ""
            lines.append(f"| {z:g}{note}{mark} | {x['per_day']:.1f} | {_fmt(dp)} | {_fmt(dr)} | "
                         f"{x['useful'] / max(1, x['alerts']):.0%} |")
    lines += [
        "",
        "## 4. Trung vị so với giá hợp lý thật (nhóm ≥ 15 tin)",
        "",
        "| Nhóm | Trung vị hệ thống | Giá hợp lý hiện tại | Lệch |",
        "|---|---|---|---|",
    ]
    for key, med, fair, err in sorted(r["median_error"], key=lambda x: x[0]):
        lines.append(f"| {key} | {med:,.0f} | {fair:,.0f} | {err:+.1%} |")
    if r["median_error"]:
        mae = statistics.mean(abs(e[3]) for e in r["median_error"])
        lines += ["", f"Sai số tuyệt đối trung bình: **{mae:.1%}** (trung vị 30 ngày cao hơn giá hiện tại một "
                      "chút vì máy cũ mất giá theo thời gian và shop chào giá cao hơn)."]
    return "\n".join(lines) + "\n"
