import httpx

import config


class Blocked(Exception):
    """Trang trả 403/429: dừng hoặc giảm tần suất, không tìm cách vượt chặn."""


def make_client():
    return httpx.Client(
        timeout=config.REQUEST_TIMEOUT,
        headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


def fetch_page(client, watch, page=1, path=None):
    params = {
        "q": watch["keywords"],
        "o": (page - 1) * config.PAGE_LIMIT,
        "limit": config.PAGE_LIMIT,
        "st": "s",  # chỉ tin bán, bỏ tin "cần mua"
    }
    if watch.get("cg"):
        params["cg"] = watch["cg"]
    if watch.get("region"):
        params["region_v2"] = watch["region"]
    r = client.get(config.GATEWAY + (path or config.LISTING_PATH), params=params)
    if r.status_code in (403, 429):
        raise Blocked(f"HTTP {r.status_code}")
    r.raise_for_status()
    return r.json().get("ads", [])


def ad_url(list_id):
    """Link tin thật trên chotot.com; khi chạy với mock thì trỏ về mock, không trỏ ra tin thật."""
    if config.GATEWAY.endswith("chotot.com"):
        return f"https://www.chotot.com/{list_id}.htm"
    return f"{config.GATEWAY}{config.LISTING_PATH}/{list_id}"


def _ts(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v / 1000 if v > 1e12 else v


def parse_ad(ad):
    list_id = ad.get("list_id") or ad.get("ad_id")
    title = ad.get("subject") or ""
    if not list_id or not title or ad.get("type", "s") != "s":
        return None
    try:
        price = int(ad.get("price") or 0)
    except (TypeError, ValueError):
        price = 0
    return {
        "list_id": str(list_id),
        "title": title,
        "price": price,
        "region": ad.get("region_name") or "",
        "seller": "shop" if ad.get("company_ad") else "cá nhân",
        # API danh sách trả mô tả đầy đủ (đã so với API chi tiết): đọc ngay, không cần request thêm.
        # Chỉ dùng để trích thông tin, không lưu nguyên văn (có thể chứa số điện thoại).
        "body": ad.get("body") or "",
        "url": ad_url(list_id),
        # list_time đổi khi tin được "đẩy"; dùng nó để biết tin còn nóng hay không
        "posted_at": _ts(ad.get("list_time")),
        # lúc đăng gốc (tin chưa đẩy lần nào thì không có orig_list_time, list_time chính là lúc đăng)
        "orig_posted_at": _ts(ad.get("orig_list_time")) or _ts(ad.get("list_time")),
        "attrs": {
            "capacity": ad.get("mobile_capacity"),
            "origin": ad.get("elt_origin"),
            "lock": ad.get("elt_lock"),
            "condition": ad.get("elt_condition"),
            # dùng cho từ khóa chung (mọi danh mục): danh mục, mới/đã dùng, năm và số km (xe)
            "category": ad.get("category"),
            "category_name": ad.get("category_name"),
            "condition_ad": ad.get("condition_ad"),
            "year": ad.get("regdate"),
            "mileage": ad.get("mileage_v2") or ad.get("mileage"),
        },
    }


def skip_view(ad):
    """Như parse_ad nhưng nhận cả tin không phải tin bán — để ghi vào danh sách "Tin bỏ qua". None nếu
    thiếu mã tin hoặc tiêu đề (không có gì để hiện)."""
    return parse_ad({**ad, "type": "s"})


def fetch_detail(client, list_id):
    """Chi tiết 1 tin (có phần mô tả). Chỉ gọi cho tin sắp bị báo deal, không gọi hàng loạt."""
    r = client.get(f"{config.GATEWAY}{config.LISTING_PATH}/{list_id}")
    if r.status_code in (403, 429):
        raise Blocked(f"HTTP {r.status_code}")
    r.raise_for_status()
    ad = r.json().get("ad") or {}
    return {"body": ad.get("body") or "", "lock": ad.get("elt_lock")}


def check_alive(client, list_id):
    """Tin còn đăng không? Trả (còn, trạng thái, lúc đăng gốc). Đã kiểm chứng 26/10/2026:
    mã không tồn tại → HTTP 404; tin đang đăng → status "active"."""
    r = client.get(f"{config.GATEWAY}{config.LISTING_PATH}/{list_id}")
    if r.status_code in (403, 429):
        raise Blocked(f"HTTP {r.status_code}")
    if r.status_code in (404, 410):
        return False, str(r.status_code), None
    r.raise_for_status()
    ad = r.json().get("ad") or {}
    if not ad:
        return False, "trống", None
    status = ad.get("status") or "?"
    return status == "active", status, _ts(ad.get("orig_list_time")) or _ts(ad.get("list_time"))
