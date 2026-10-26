"""Luồng xử lý chung cho chạy thật, mock và backtest:
tin thô -> lọc -> chuẩn hóa -> lưu -> so với lịch sử -> cảnh báo."""
import logging
import random
import time

import httpx

import analyzer
import collector
import config
import db
import notifier
from normalizer import (NO_ALERT, is_keyword_key, normalize, normalize_watch, read_body, skip_reason, slug,
                        watch_type)

log = logging.getLogger("deal-finder")


def _evaluate(conn, key, item, now):
    """So giá tin (quy đổi theo pin/ngoại hình) với lịch sử nhóm (cũng quy đổi)."""
    rows = db.history(conn, key, now - config.WINDOW_DAYS * 86400, exclude=item["list_id"])
    a = item["attrs"]
    adj = analyzer.adjusted(item["price"], a.get("battery"), a.get("cosmetic"), key)
    res = analyzer.evaluate(adj, analyzer.adjusted_history(rows, key))
    if res:
        res.update(price=item["price"], adj_price=adj)
    return res


def _below_preference(attrs):
    b, c = attrs.get("battery"), attrs.get("cosmetic")
    return (b is not None and b < config.ALERT_MIN_BATTERY) or (c is not None and c < config.ALERT_MIN_COSMETIC)


def _recheck(conn, watch, item, norm, now, verify):
    """Dự phòng khi tin trong danh sách không kèm mô tả: đọc chi tiết tin (1 request), chuyển nhóm
    nếu là máy lock/bypass/thay linh kiện..., trích pin/ngoại hình, rồi đánh giá lại.
    Trả None nếu không đọc được (khi đó giữ kết quả cũ)."""
    try:
        detail = verify(item["list_id"])
    except httpx.HTTPError as e:
        log.warning("Không xác minh được tin %s: %s", item["list_id"], e)
        return None
    item["attrs"].update(read_body(item["title"], detail.get("body") or ""),
                         lock=detail.get("lock") or item["attrs"].get("lock"))
    new = normalize_watch(watch, item["title"], item["attrs"])
    if not new:
        return None
    db.set_key(conn, item["list_id"], new, item["attrs"])  # lưu kết quả đọc mô tả để chuẩn hóa lại sau này
    if new["key"] != norm["key"]:
        log.info("Tin %s: theo mô tả thuộc nhóm %s — không so với %s", item["list_id"], new["key"], norm["key"])
    if new["condition"] in NO_ALERT:
        return new, None
    return new, _evaluate(conn, new["key"], item, now)


def _skip(conn, watch, item, reason, detail, now):
    """Ghi tin bị loại kèm lý do (tab "Tin bỏ qua"; không lưu mô tả) rồi trả kết quả "skip"."""
    if item:
        db.add_skipped(conn, watch.get("name"), item, reason, detail, now)
    return "skip", None


def process(conn, watch, ad, alert=True, now=None, send=True, verify=None):
    """Trả về (trạng thái, kết quả đánh giá). Trạng thái: skip | seen | new.
    Tin bị loại (skip) được ghi vào bảng skipped kèm lý do.
    verify(list_id) -> {"body", "lock"}: dự phòng khi tin không kèm mô tả (1 request/tin sắp báo)."""
    now = time.time() if now is None else now
    item = collector.parse_ad(ad)
    if not item:
        return _skip(conn, watch, collector.skip_view(ad), "khong-phai-ban", "", now)
    lo, hi = watch.get("min_price", 1), watch.get("max_price", 10**13)
    if not lo <= item["price"] <= hi:
        if item["price"] <= 0:
            return _skip(conn, watch, item, "gia-0", "", now)
        bound = f"thấp hơn mức tối thiểu {notifier.vnd(lo)}" if item["price"] < lo \
            else f"cao hơn mức tối đa {notifier.vnd(hi)}"
        return _skip(conn, watch, item, "ngoai-gia", bound, now)
    # mô tả: dấu hiệu bypass/thay linh kiện/lock + pin %, ngoại hình % (không lưu nguyên văn)
    item["attrs"].update(read_body(item["title"], item["body"]))
    norm = normalize_watch(watch, item["title"], item["attrs"])
    if not norm:
        return _skip(conn, watch, item, *skip_reason(watch, item["title"], item["attrs"]), now)
    db.unskip(conn, item["list_id"], watch.get("name"))  # từng bị loại nhưng nay hợp lệ
    # tin đã có (từ từ khóa khác) vẫn được ghi thêm vào nhóm của từ khóa này
    is_new = db.insert_if_new(conn, {**item, **norm, "first_seen": now, "last_seen": now, "watch": watch.get("name"),
                                     "battery": item["attrs"]["battery"], "cosmetic": item["attrs"]["cosmetic"]})
    if not is_new:
        return "seen", None
    if not alert or norm["condition"] in NO_ALERT:
        return "new", None
    if item["posted_at"] and now - item["posted_at"] > config.MAX_AGE_HOURS * 3600:
        return "new", None
    res = _evaluate(conn, norm["key"], item, now)
    if res and verify and not item["body"]:
        rechecked = _recheck(conn, watch, item, norm, now, verify)
        if rechecked:
            norm, res = rechecked
    if res and res["label"] == "deal" and _below_preference(item["attrs"]):
        log.info("Tin %s rẻ nhưng pin/ngoại hình dưới mức đã chọn — không báo", item["list_id"])
        res = None
    if res:
        sent = False
        if send:
            try:
                sent = notifier.send(notifier.format_alert({**item, **norm}, res))
            except httpx.HTTPError as e:
                log.warning("Gửi Telegram lỗi: %s", e)
        db.add_alert(conn, item["list_id"], res, now, sent)
    return "new", res


_last_poll = {}  # tên từ khóa -> lúc quét gần nhất (cho "every_minutes")


def scan_every(watch, default=0):
    """Nhịp quét (phút) của 1 từ khóa: cài riêng, không có thì mặc định chung, 0 = mỗi vòng quét."""
    return int(watch.get("every_minutes") or default or 0)


def default_every(conn):
    """Nhịp quét mặc định chung (phút) đặt trên trang Từ khóa; 0 = mỗi vòng quét."""
    try:
        return int(db.get_setting(conn, "default_every_minutes") or 0)
    except ValueError:
        return 0


def _due(watch, now, default=0):
    """Đến lượt quét chưa. Collector chỉ thức dậy mỗi vòng (POLL_SECONDS) nên cho phép sớm nửa vòng:
    trung bình khoảng cách giữa 2 lần quét đúng bằng nhịp đã chọn (sai số ±1 vòng)."""
    every = scan_every(watch, default) * 60
    return not every or now - _last_poll.get(watch["name"], 0) >= every - config.POLL_SECONDS / 2


def _is_fresh(conn, watch):
    """Từ khóa chưa có dữ liệu và chưa nạp lần đầu: cần nạp vài trang lịch sử (không báo)."""
    return not (db.has_watch(conn, watch["name"]) or db.get_status(conn).get(f"seeded:{watch['name']}"))


def poll_once(conn, client, pages=1, alert=True, watches=None):
    """Quét mọi từ khóa đến lượt trong watchlist (đọc lại file nếu đã đổi), nghỉ REQUEST_GAP_SECONDS giữa
    2 request. Từ khóa mới thêm được nạp BASELINE_PAGES trang lịch sử trước, không báo deal ở lượt đó."""
    stats = {"fetched": 0, "new": 0, "alerts": 0, "seeded": []}
    if watches is None:
        watches, err = config.refresh_watchlist()
        if err:
            log.warning(err)
            db.set_status(conn, watch_error=err)

    def verify(list_id):
        time.sleep(config.REQUEST_GAP_SECONDS)
        return collector.fetch_detail(client, list_id)

    first = True
    default = default_every(conn)
    for w in watches:
        fresh = _is_fresh(conn, w)
        if not fresh and not _due(w, time.time(), default):
            continue
        n_pages = max(pages, int(w.get("pages") or config.BASELINE_PAGES)) if fresh else pages
        for page in range(1, min(n_pages, config.SEARCH_MAX_PAGES) + 1):
            if not first:
                time.sleep(config.REQUEST_GAP_SECONDS)
            first = False
            ads = collector.fetch_page(client, w, page)
            stats["fetched"] += len(ads)
            for ad in ads:
                status, res = process(conn, w, ad, alert=alert and not fresh, verify=verify)
                stats["new"] += status == "new"
                stats["alerts"] += bool(res)
            if len(ads) < config.PAGE_LIMIT:
                break
        _last_poll[w["name"]] = time.time()
        db.set_status(conn, **{f"scanned:{w['name']}": time.time()})  # dashboard: "quét gần nhất"
        if fresh:
            db.set_status(conn, **{f"seeded:{w['name']}": time.time()})
            stats["seeded"].append(w["name"])
            log.info("Từ khóa mới '%s': đã nạp dữ liệu ban đầu", w["name"])
    return stats


def search(conn, client, watch, pages):
    """Lệnh search: tải đúng `pages` trang kết quả của 1 từ khóa và lưu (không báo deal).
    Trả {"fetched": số tin tải về, "kept": số tin hợp lệ (kể cả đã có), "new": số tin mới}."""
    stats = {"fetched": 0, "kept": 0, "new": 0}
    for page in range(1, pages + 1):
        if page > 1:
            time.sleep(config.REQUEST_GAP_SECONDS)
        ads = collector.fetch_page(client, watch, page)
        stats["fetched"] += len(ads)
        for ad in ads:
            status, _ = process(conn, watch, ad, alert=False)
            stats["kept"] += status != "skip"
            stats["new"] += status == "new"
        if len(ads) < config.PAGE_LIMIT:
            break
    db.set_status(conn, **{f"seeded:{watch['name']}": time.time()})
    return stats


def watch_of_key(watches):
    """Hàm đoán từ khóa của 1 nhóm — để gắn dữ liệu từ bản cũ (trước khi có listing_keys.watch)."""
    iphone, generic = [], {}
    for w in watches:
        if watch_type(w) == "iphone":
            n = normalize(w["keywords"] + " 128gb")
            if n:
                iphone.append((n["key"].split("|")[0].rsplit("-", 1)[0], w["name"]))
        else:
            generic[slug(w["name"])] = w["name"]

    def find(key):
        product = key.split("|")[0]
        if is_keyword_key(key):
            return generic.get(product[3:].split("~")[0])
        model = product.rsplit("-", 1)[0]
        return next((name for m, name in iphone if m == model), None)

    return find


def assign_old_rows(conn, watches=None):
    n = db.assign_watches(conn, watch_of_key(watches or config.WATCHLIST))
    if n:
        log.info("Đã gắn từ khóa cho %d tin từ bản cũ", n)
    return n


def track_once(conn, check, now=None, budget=None, gap=0.0):
    """Đo tốc độ bán: kiểm tra lại các tin đến hạn xem còn đăng hay đã gỡ.
    check(list_id) -> (còn, trạng thái, lúc đăng gốc). Thời điểm gỡ thật nằm giữa lần cuối thấy còn
    (last_seen) và lần phát hiện mất (gone_at)."""
    now = time.time() if now is None else now
    budget = config.TRACK_PER_CYCLE if budget is None else budget
    ids = db.due_for_check(conn, now, config.TRACK_INTERVAL_HOURS, config.TRACK_DAYS, budget, tuple(NO_ALERT))
    stats = {"checked": 0, "gone": 0}
    for list_id in ids:
        if gap:
            time.sleep(gap)
        alive, status, posted = check(list_id)
        stats["checked"] += 1
        if alive:
            db.mark_alive(conn, list_id, now, posted)
        else:
            db.mark_gone(conn, list_id, now, status)
            stats["gone"] += 1
    return stats


def seed(conn, client, watches=None):
    assign_old_rows(conn, watches)
    st = poll_once(conn, client, pages=config.BASELINE_PAGES, alert=False, watches=watches)
    db.set_status(conn, seeded_at=time.time(), source=config.GATEWAY)
    log.info("Đã nạp baseline: %d tin tải về, %d tin mới hợp lệ", st["fetched"], st["new"])
    return st


def run_loop(conn, client, cycles=None, stop_event=None):
    """Vòng quét. Trả False nếu dừng vì bị chặn liên tục (để systemd không tự bật lại)."""
    db.set_status(conn, state="running", source=config.GATEWAY, started_at=time.time(),
                  poll_seconds=config.POLL_SECONDS, fails=0, last_error="")
    assign_old_rows(conn, config.refresh_watchlist()[0])
    fails = done = total_new = total_alerts = 0
    while cycles is None or done < cycles:
        delay = config.POLL_SECONDS + random.uniform(0, config.JITTER_SECONDS)
        try:
            st = poll_once(conn, client)  # từ khóa chưa có dữ liệu tự nạp baseline trước
            db.prune_skipped(conn, time.time() - config.SKIP_KEEP_DAYS * 86400)
            tr = {"checked": 0, "gone": 0}
            if config.TRACK_PER_CYCLE:
                tr = track_once(conn, lambda lid: collector.check_alive(client, lid),
                                gap=config.REQUEST_GAP_SECONDS)
            fails = 0
            total_new += st["new"]
            total_alerts += st["alerts"]
            db.set_status(conn, last_poll_at=time.time(), last_ok_at=time.time(), fails=0,
                          last_error="", total_new=total_new, total_alerts=total_alerts)
            log.info("Quét xong: %d tin tải về, %d tin mới, %d cảnh báo · kiểm tra còn/mất %d tin, %d đã gỡ",
                     st["fetched"], st["new"], st["alerts"], tr["checked"], tr["gone"])
        except collector.Blocked as e:
            fails += 1
            delay = min(60 * 2 ** fails, 900)
            db.set_status(conn, last_poll_at=time.time(), fails=fails, last_error=f"Bị chặn ({e})")
            log.warning("Bị chặn (%s), lần %d — nghỉ %ds", e, fails, delay)
            if fails >= config.MAX_BLOCKS:
                msg = ("🛑 Deal Finder đã dừng: bị chặn liên tục. Hãy giảm tần suất / xem lại "
                       "điều khoản trang. Không dùng proxy xoay hay giải CAPTCHA.")
                log.error(msg)
                db.set_status(conn, state="stopped_blocked")
                try:
                    notifier.send(msg)
                except httpx.HTTPError:
                    pass
                return False
        except httpx.HTTPError as e:
            db.set_status(conn, last_poll_at=time.time(), last_error=f"Lỗi mạng: {e}")
            log.warning("Lỗi mạng: %s", e)
        done += 1
        if cycles is not None and done >= cycles:
            break
        if stop_event is not None:
            if stop_event.wait(delay):
                break
        else:
            time.sleep(delay)
    db.set_status(conn, state="stopped")
    return True
