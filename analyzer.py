import math
import statistics

import config


def _percentile(sorted_vals, p):
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def clean(prices):
    """Loại giá ngoại lai bằng IQR (cần tối thiểu 8 mẫu)."""
    if len(prices) < 8:
        return list(prices)
    s = sorted(prices)
    q1, q3 = _percentile(s, 0.25), _percentile(s, 0.75)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [p for p in prices if lo <= p <= hi]


def median_clean(prices):
    h = clean(prices)
    return statistics.median(h) if h else None


def spread(sorted_vals, med):
    """Độ phân tán tương đối: sigma ước lượng từ IQR (bền với ngoại lai) chia trung vị."""
    q1, q3 = _percentile(sorted_vals, 0.25), _percentile(sorted_vals, 0.75)
    return (q3 - q1) / 1.349 / med if med else 0.0


def deal_cut(spread_ratio, deal_pct=None, deal_z=None):
    """Ngưỡng deal của 1 nhóm: tối thiểu DEAL_PCT, nhóm giá càng lộn xộn thì đòi rẻ hơn càng nhiều."""
    deal_pct = config.DEAL_PCT if deal_pct is None else deal_pct
    deal_z = config.DEAL_Z if deal_z is None else deal_z
    return max(deal_pct, deal_z * spread_ratio)


def stats(prices, adjusted_prices=None):
    """Thống kê cho dashboard: n (sau lọc), trung vị, P25, P75 theo giá thật; độ phân tán và ngưỡng
    deal theo giá đã quy đổi tình trạng máy (nếu có) — đúng như lúc quyết định báo."""
    h = sorted(clean(prices))
    if not h:
        return {"n": 0, "median": None, "p25": None, "p75": None, "spread": None, "cut": None}
    med = statistics.median(h)
    a = sorted(clean(adjusted_prices)) if adjusted_prices else h
    sp = spread(a, statistics.median(a))
    cut = deal_cut(sp)
    return {"n": len(h), "median": med, "p25": _percentile(h, 0.25), "p75": _percentile(h, 0.75),
            "spread": sp, "cut": cut, "dispersed": cut >= config.SCAM_PCT}


# ---------------------------------------------------------------- tình trạng máy (pin, ngoại hình)
def condition_factor(battery, cosmetic, model=None):
    """Giá máy này so với máy tình trạng điển hình của thị trường. Người bán không ghi thì coi là điển hình."""
    m = model or config.CONDITION_MODEL
    f = 1.0
    if battery is not None:
        f += m["battery_k"] * (float(battery) - m["battery_ref"])
    if cosmetic is not None:
        f += m["cosmetic_k"] * (float(cosmetic) - m["cosmetic_ref"])
    return min(1.25, max(0.7, f))


def adjusted(price, battery=None, cosmetic=None, key=None):
    """Quy giá về máy tình trạng điển hình: máy pin 76% giá 14tr được so như máy pin chuẩn giá cao hơn.
    Hệ số chỉ học trên iPhone: nhóm từ khóa chung (key "kw:…") giữ nguyên giá."""
    if not config.USE_CONDITION or (key or "").startswith("kw:"):
        return price
    return price / condition_factor(battery, cosmetic)


def adjusted_history(rows, key=None):
    return [adjusted(p, b, c, key) for p, b, c in rows]


def _solve(a, b):
    """Giải hệ tuyến tính nhỏ bằng khử Gauss (đủ cho hồi quy vài biến, không cần numpy)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


BATTERY_BUCKETS = [(0, 79), (80, 84), (85, 89), (90, 94), (95, 100)]
COSMETIC_BUCKETS = [(0, 92), (93, 96), (97, 98), (99, 100)]


def fit_condition_model(rows, min_group=8, max_log_dev=0.35, min_samples=30):
    """Học từ dữ liệu: pin/ngoại hình thêm 1 điểm % thì giá cao hơn bao nhiêu.
    rows = [(khóa nhóm, giá, pin, ngoại hình)]. So mỗi tin với trung vị nhóm của nó (log tỷ lệ),
    bỏ tin lệch quá xa (rác còn sót), rồi hồi quy tuyến tính có biến "có ghi / không ghi"."""
    groups = {}
    for key, price, b, c in rows:
        groups.setdefault(key, []).append((price, b, c))
    data = []
    for items in groups.values():
        if len(items) < min_group:
            continue
        med = statistics.median(p for p, _, _ in items)
        for p, b, c in items:
            y = math.log(p / med)
            if abs(y) <= max_log_dev:
                data.append((y, None if b is None else float(b), None if c is None else float(c)))
    bs = [b for _, b, _ in data if b is not None]
    cs = [c for _, _, c in data if c is not None]
    model = dict(config.CONDITION_MODEL)
    model.update(n=len(data), n_battery=len(bs), n_cosmetic=len(cs))
    use_b, use_c = len(bs) >= min_samples, len(cs) >= min_samples
    if use_b:
        model["battery_ref"] = statistics.median(bs)
    if use_c:
        model["cosmetic_ref"] = statistics.median(cs)

    def features(b, c):
        x = [1.0]
        if use_b:
            x += [0.0, 0.0] if b is None else [1.0, b - model["battery_ref"]]
        if use_c:
            x += [0.0, 0.0] if c is None else [1.0, c - model["cosmetic_ref"]]
        return x

    xs = [features(b, c) for _, b, c in data]
    if xs and (use_b or use_c):
        k = len(xs[0])
        xtx = [[sum(x[i] * x[j] for x in xs) for j in range(k)] for i in range(k)]
        xty = [sum(x[i] * y for x, (y, _, _) in zip(xs, data)) for i in range(k)]
        beta = _solve(xtx, xty)
        if beta:
            pos = 1
            if use_b:
                model["battery_k"] = max(0.0, beta[pos + 1])
                pos += 2
            if use_c:
                model["cosmetic_k"] = max(0.0, beta[pos + 1])

    def bucket_table(idx, buckets):
        out = []
        for lo, hi in buckets:
            ys = [d[0] for d in data if d[idx] is not None and lo <= d[idx] <= hi]
            out.append((lo, hi, len(ys), math.exp(statistics.median(ys)) - 1 if ys else None))
        return out

    model["battery_table"] = bucket_table(1, BATTERY_BUCKETS)
    model["cosmetic_table"] = bucket_table(2, COSMETIC_BUCKETS)
    model["unknown_n"] = sum(1 for _, b, c in data if b is None and c is None)
    return model


def evaluate(price, history, deal_pct=None, scam_pct=None, deal_z=None):
    """Trả về dict {label, median, discount, n, cut} hoặc None (không đáng báo / thiếu dữ liệu)."""
    scam_pct = config.SCAM_PCT if scam_pct is None else scam_pct
    h = sorted(clean(history))
    if len(h) < config.MIN_SAMPLES:
        return None
    med = statistics.median(h)
    discount = (med - price) / med
    cut = deal_cut(spread(h, med), deal_pct, deal_z)
    # nhóm giá quá phân tán (ngưỡng deal vượt ngưỡng lừa đảo, vd. xe máy gộp nhiều đời): rẻ hơn mức phân tán
    # bình thường của nhóm mới đáng ngờ — không gắn "nghi lừa đảo" cho tin chỉ là đời cũ/bản thấp
    if discount >= max(scam_pct, cut):
        label = "scam_risk"
    elif discount >= cut:
        label = "deal"
    else:
        return None
    return {"label": label, "median": med, "discount": discount, "n": len(h), "cut": cut}
