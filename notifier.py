import httpx

import config
from normalizer import MARKET_VN


def vnd(n):
    return f"{int(n):,}".replace(",", ".") + "đ"


def parse_vnd(text):
    """'15000000', '15.000.000', '15tr', '15 triệu', '1,5tr', '800k' -> số đồng (None nếu trống)."""
    t = str(text or "").strip().lower().replace(" ", "")
    if not t:
        return None
    mult = 1
    for suffix, m in (("triệu", 10**6), ("trieu", 10**6), ("tr", 10**6), ("m", 10**6), ("k", 10**3)):
        if t.endswith(suffix):
            t, mult = t[: -len(suffix)], m
            break
    t = t.replace(",", ".") if mult > 1 else t.replace(".", "").replace(",", "")
    try:
        return int(float(t) * mult)
    except ValueError:
        raise ValueError(f"Giá không hợp lệ: {text}") from None


def condition_text(battery, cosmetic):
    parts = []
    if battery is not None:
        parts.append(f"pin {float(battery):.0f}%")
    if cosmetic is not None:
        parts.append(f"ngoại hình {float(cosmetic):.0f}%")
    return " · ".join(parts) or "người bán không ghi pin/ngoại hình"


def format_alert(item, res):
    pct = round(res["discount"] * 100)
    head = (
        f"⚠️ GIÁ QUÁ THẤP -{pct}% — nghi lừa đảo/đặt cọc, kiểm tra kỹ"
        if res["label"] == "scam_risk"
        else f"🔥 DEAL -{pct}%"
    )
    a = item.get("attrs") or {}
    adj = res.get("adj_price")
    adj_txt = f" (quy về tình trạng điển hình: {vnd(adj)})" if adj and abs(adj - item["price"]) >= 50_000 else ""
    return (
        f"{head}\n"
        f"{item['label']} ({MARKET_VN.get(item['market'], '')}, {item.get('seller') or '-'})\n"
        f"Tình trạng: {condition_text(a.get('battery'), a.get('cosmetic'))}\n"
        f"Giá: {vnd(item['price'])}{adj_txt} | Trung vị: {vnd(res['median'])} (n={res['n']})\n"
        f"Khu vực: {item.get('region') or '-'}\n"
        f"{item.get('url') or ''}"
    )


def send(text):
    """Gửi Telegram nếu đã cấu hình, nếu không thì in ra màn hình."""
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        print("[CONSOLE]\n" + text + "\n", flush=True)
        return False
    r = httpx.post(
        f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )
    r.raise_for_status()
    return True
