"""Đo tốc độ bán: tin đăng bao lâu thì biến mất, so theo mức giá, pin, ngoại hình, người bán.

Dữ liệu theo dõi bị "cắt" ở hai đầu, phương pháp tính đúng điều đó:
- Cắt trái: nhiều tin đăng từ trước khi bắt đầu theo dõi → chỉ tính thời gian từ lúc thấy (delayed entry).
- Cắt phải: tin chưa mất khi kết thúc → chỉ biết còn đăng ít nhất đến lần cuối xác nhận.
- Thời điểm gỡ thật nằm giữa lần cuối thấy còn và lần phát hiện mất → lấy điểm giữa.
Mô hình: tỷ lệ biến mất theo từng khoảng tuổi tin (hàm mũ từng khúc, gần với mô hình Cox),
ước lượng bằng hồi quy Poisson. Lưu ý: biến mất ≠ chắc chắn đã bán (người bán có thể xóa tin,
tin hết hạn, bị gỡ do vi phạm). Tin của shop thường là tin bán nhiều máy, biến mất càng không phải "bán".
"""
import bisect
import collections
import math
import statistics
import time

import config
import db
from analyzer import _solve

DAY = 86400.0
AGE_BANDS = [(0, 1), (1, 3), (3, 7), (7, 14), (14, 30), (30, math.inf)]   # tuổi tin (ngày từ lúc đăng gốc)
KM_DAYS = (1, 3, 7, 14)
MIN_EVENTS = 30          # dưới mức này chưa kết luận
MIN_AT_RISK = 5          # điểm Kaplan–Meier có ít hơn 5 tin đang theo dõi thì không in
# Ước tính từ lưu lượng thật 26/10/2026 (5 từ khóa ~126 tin/ngày; máy zin rẻ ≥10% ~15%, pin < 85% ~6,6%)
NEEDED_TIME = ("Ước tính cần chạy liên tục ~1–2 tuần để kết luận về giá, ~4 tuần về pin "
               "(theo dõi thêm dòng máy sẽ nhanh hơn).")


def price_bucket(rel):
    return "rẻ hơn ≥10%" if rel <= 0.90 else "đắt hơn ≥10%" if rel >= 1.10 else "quanh trung vị (±10%)"


def battery_bucket(b):
    if b is None:
        return "pin không ghi"
    return "pin < 85%" if b < 85 else "pin 85–99%" if b < 100 else "pin 100% (đa số đã thay)"


def cosmetic_bucket(c):
    return "ngoại hình không ghi" if c is None else "ngoại hình ≤ 93%" if c <= 93 else "ngoại hình ≥ 95%"


def records(conn, used_only=True):
    """Mỗi tin → khoảng theo dõi [entry, exit] tính bằng ngày tuổi, có biến mất hay không, và đặc điểm."""
    rows = db.tracking_rows(conn)
    groups = collections.defaultdict(list)
    for r in rows:
        if r["condition"] == "used":
            groups[r["key"]].append(r["price"])
    median = {k: statistics.median(v) for k, v in groups.items() if len(v) >= 5}
    out = []
    for r in rows:
        if (used_only and r["condition"] != "used") or r["key"] not in median:
            continue
        posted = r["orig_posted_at"]
        end = (r["last_seen"] + r["gone_at"]) / 2 if r["gone_at"] else r["last_seen"]
        entry, exit_ = max(0.0, (r["first_seen"] - posted) / DAY), (end - posted) / DAY
        if exit_ <= entry:
            continue  # mới thấy 1 lần, chưa theo dõi được
        rel = r["price"] / median[r["key"]]
        out.append({"entry": entry, "exit": exit_, "event": 1 if r["gone_at"] else 0, "rel": rel,
                    "price": price_bucket(rel), "battery": battery_bucket(r["battery"]),
                    "cosmetic": cosmetic_bucket(r["cosmetic"]),
                    "seller": "shop" if r["seller"] == "shop" else "cá nhân", "status": r["gone_status"]})
    return out


def kaplan_meier(recs, days=KM_DAYS):
    """Tỷ lệ tin còn đăng sau N ngày (tính có thời điểm vào theo dõi). None nếu quá ít tin để tin cậy."""
    entries = sorted(r["entry"] for r in recs)
    exits = sorted(r["exit"] for r in recs)

    def at_risk(t):  # số tin đang theo dõi tại t: đã vào trước t và chưa ra trước t
        return bisect.bisect_left(entries, t) - bisect.bisect_left(exits, t)

    s, curve = 1.0, []
    for t, d in sorted(collections.Counter(r["exit"] for r in recs if r["event"]).items()):
        n = at_risk(t)
        if n:
            s *= 1 - d / n
        curve.append((t, s))
    out = {}
    for day in days:
        i = bisect.bisect_right(curve, (day, math.inf))
        out[day] = None if at_risk(day) < MIN_AT_RISK else (curve[i - 1][1] if i else 1.0)
    return out


def _split(r):
    """Chia khoảng theo dõi của 1 tin theo các khoảng tuổi: [(khoảng, số ngày, có mất trong khoảng)]."""
    pieces = []
    for i, (lo, hi) in enumerate(AGE_BANDS):
        a, b = max(lo, r["entry"]), min(hi, r["exit"])
        if b > a:
            pieces.append((i, b - a, 1 if r["event"] and lo < r["exit"] <= hi else 0))
    return pieces


def poisson_fit(x, y, exposure, iters=60, ridge=1e-6):
    """Hồi quy Poisson log-link với offset log(thời gian theo dõi), Newton–Raphson. Trả (beta, sai số chuẩn)."""
    k = len(x[0])
    beta = [0.0] * k
    beta[0] = math.log(max(sum(y), 0.5) / sum(exposure))
    hess = None
    for _ in range(iters):
        mu = [e * math.exp(min(50.0, sum(b * v for b, v in zip(beta, xi)))) for xi, e in zip(x, exposure)]
        grad = [sum((yi - mi) * xi[j] for xi, yi, mi in zip(x, y, mu)) for j in range(k)]
        hess = [[sum(mi * xi[a] * xi[b] for xi, mi in zip(x, mu)) + (ridge if a == b else 0.0)
                 for b in range(k)] for a in range(k)]
        step = _solve(hess, grad)
        if step is None:
            break
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-9:
            break
    se = []
    for j in range(k):
        col = _solve(hess, [1.0 if i == j else 0.0 for i in range(k)]) if hess else None
        se.append(math.sqrt(col[j]) if col and col[j] > 0 else float("inf"))
    return beta, se


# đặc điểm đưa vào mô hình: (tên, nhóm so sánh, hàm kiểm tra); mốc so sánh ghi trong nhãn
COVARIATES = [
    ("Rẻ hơn trung vị ≥10%", "quanh trung vị", lambda r: r["price"] == "rẻ hơn ≥10%"),
    ("Đắt hơn trung vị ≥10%", "quanh trung vị", lambda r: r["price"] == "đắt hơn ≥10%"),
    ("Pin < 85%", "pin 85–99%", lambda r: r["battery"] == "pin < 85%"),
    ("Pin 100% (đa số đã thay)", "pin 85–99%", lambda r: r["battery"] == "pin 100% (đa số đã thay)"),
    ("Pin không ghi", "pin 85–99%", lambda r: r["battery"] == "pin không ghi"),
    ("Ngoại hình ≤ 93%", "ngoại hình ≥ 95%", lambda r: r["cosmetic"] == "ngoại hình ≤ 93%"),
    ("Ngoại hình không ghi", "ngoại hình ≥ 95%", lambda r: r["cosmetic"] == "ngoại hình không ghi"),
    ("Tin của shop", "cá nhân", lambda r: r["seller"] == "shop"),
]


def rate_ratios(recs):
    """Tốc độ biến mất của từng đặc điểm so với nhóm mốc, đã kiểm soát tuổi tin và các đặc điểm khác."""
    pieces = [(r, band, expo, ev) for r in recs for band, expo, ev in _split(r)]
    bands = sorted({p[1] for p in pieces})[1:]           # khoảng tuổi đầu tiên làm mốc
    covs = [c for c in COVARIATES if any(c[2](r) for r in recs) and not all(c[2](r) for r in recs)]
    x = [[1.0] + [1.0 if band == b else 0.0 for b in bands] + [1.0 if c[2](r) else 0.0 for c in covs]
         for r, band, _, _ in pieces]
    y = [ev for *_, ev in pieces]
    expo = [e for _, _, e, _ in pieces]
    if not x or sum(y) == 0:
        return []
    beta, se = poisson_fit(x, y, expo)
    out = []
    for j, (name, ref, test) in enumerate(covs, start=1 + len(bands)):
        events = sum(r["event"] for r in recs if test(r))
        lo, hi = beta[j] - 1.96 * se[j], beta[j] + 1.96 * se[j]
        out.append({"name": name, "ref": ref, "events": events, "n": sum(1 for r in recs if test(r)),
                    "rr": math.exp(beta[j]), "lo": math.exp(max(-30, lo)), "hi": math.exp(min(30, hi))})
    return out


def analyze(conn, used_only=True):
    recs = records(conn, used_only)
    events = sum(r["event"] for r in recs)
    result = {
        "n": len(recs), "events": events, "followup_days": sum(r["exit"] - r["entry"] for r in recs),
        "status": dict(collections.Counter(r["status"] for r in recs if r["event"])),
        "by": {}, "ratios": rate_ratios(recs) if events else [], "enough": events >= MIN_EVENTS,
        "tracked_total": conn.execute("SELECT COUNT(*) FROM listings WHERE orig_posted_at IS NOT NULL").fetchone()[0],
        "gone_total": conn.execute("SELECT COUNT(*) FROM listings WHERE gone_at IS NOT NULL").fetchone()[0],
    }
    for field in ("price", "battery", "cosmetic", "seller"):
        groups = collections.defaultdict(list)
        for r in recs:
            groups[r[field]].append(r)
        result["by"][field] = [
            {"bucket": b, "n": len(g), "events": sum(r["event"] for r in g),
             "rate": sum(r["event"] for r in g) / max(1e-9, sum(r["exit"] - r["entry"] for r in g)),
             "km": kaplan_meier(g)} for b, g in sorted(groups.items())]
    return result


def verdict(ratio, enough):
    if not enough or ratio["events"] < 5:
        return "chưa đủ dữ liệu"
    if ratio["lo"] > 1:
        return f"biến mất nhanh hơn ×{ratio['rr']:.1f}"
    if ratio["hi"] < 1:
        return f"biến mất chậm hơn (×{ratio['rr']:.2f})"
    return "chưa thấy khác biệt rõ"


def render(res, title="Tốc độ bán (thời gian tin còn đăng)"):
    pct = lambda v: "-" if v is None else f"{v:.0%}"  # noqa: E731
    lines = [
        f"# {title}", "",
        f"Tạo lúc {time.strftime('%d/%m/%Y %H:%M')}. Đang theo dõi {res['tracked_total']} tin, đã phát hiện "
        f"{res['gone_total']} tin biến mất. Phân tích máy zin: **{res['n']} tin**, **{res['events']} tin biến mất**, "
        f"tổng {res['followup_days']:.0f} tin-ngày theo dõi.", "",
    ]
    if not res["enough"]:
        lines += [f"> **Chưa đủ dữ liệu để kết luận** (cần ≥ {MIN_EVENTS} tin biến mất, đang có {res['events']}). "
                  f"{NEEDED_TIME} Các bảng dưới chỉ để tham khảo.", ""]
    if res["status"]:
        lines += ["Cách biến mất: " + ", ".join(f"{k}: {v}" for k, v in res["status"].items()), ""]
    lines += ["## Tốc độ biến mất so với nhóm mốc", "",
              "Đã kiểm soát tuổi tin và các đặc điểm còn lại. ×1 = như nhóm mốc; >1 = biến mất nhanh hơn.", "",
              "| Đặc điểm | So với | Số tin | Biến mất | Tốc độ | Khoảng tin cậy 95% | Kết luận |",
              "|---|---|---|---|---|---|---|"]
    for r in res["ratios"]:
        lines.append(f"| {r['name']} | {r['ref']} | {r['n']} | {r['events']} | ×{r['rr']:.2f} | "
                     f"{r['lo']:.2f} – {r['hi']:.2f} | {verdict(r, res['enough'])} |")
    names = {"price": "Theo mức giá", "battery": "Theo pin", "cosmetic": "Theo ngoại hình", "seller": "Theo người bán"}
    for field, rows in res["by"].items():
        lines += ["", f"## {names[field]}", "",
                  "| Nhóm | Số tin | Biến mất | Biến mất/ngày | Còn sau 1 ngày | 3 ngày | 7 ngày | 14 ngày |",
                  "|---|---|---|---|---|---|---|---|"]
        for g in rows:
            km = g["km"]
            lines.append(f"| {g['bucket']} | {g['n']} | {g['events']} | {g['rate']:.1%} | {pct(km[1])} | "
                         f"{pct(km[3])} | {pct(km[7])} | {pct(km[14])} |")
    lines += ["", "Ghi chú: biến mất ≠ chắc chắn đã bán (có thể xóa tin, hết hạn, bị gỡ). "
              "\"-\" = quá ít tin đang theo dõi ở mốc đó để tính."]
    return "\n".join(lines) + "\n"
