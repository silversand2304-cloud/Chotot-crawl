"""Deal Finder — lệnh dòng lệnh.

Theo từ khóa:         search "từ khóa" (tìm ngay + xuất Excel, --add để theo dõi tiếp) | export | keywords
Chạy thật (Chợ Tốt):  probe | seed | run | report | audit | calibrate | renormalize | telegram-test
Tốc độ bán:           track (1 lượt kiểm tra tin còn/mất) | speed (báo cáo) | speedsim (kiểm chứng trên giả lập)
Web:                  web (chỉ dashboard) | all (collector + dashboard trong 1 tiến trình)
Giả lập / test:       demo | simulate | mock | mockdemo
"""
import argparse
import collections
import json
import logging
import os
import random
import sys
import threading
import time

import analyzer
import collector
import config
import db
import notifier
import pipeline
from normalizer import (FLAG_LABEL, NO_ALERT, SKIP_LABEL, fold, is_keyword_key, normalize, normalize_watch,
                        skip_reason, watch_type)

log = logging.getLogger("deal-finder")


def cmd_probe(args):
    client = collector.make_client()
    print(f"Nguồn: {config.GATEWAY}")
    for path in [config.LISTING_PATH] + config.LISTING_PATH_ALT:
        try:
            ads = collector.fetch_page(client, config.WATCHLIST[0], 1, path=path)
            print(f"[OK ] {path}: {len(ads)} tin")
            for ad in ads[:5]:
                it = collector.parse_ad(ad)
                if it:
                    n = normalize_watch(config.WATCHLIST[0], it["title"], it["attrs"])
                    print(f"      - {it['title'][:50]:50} | {notifier.vnd(it['price']):>12} | "
                          f"{n['key'] if n else 'BỎ QUA'}")
        except Exception as e:  # noqa: BLE001 - lệnh thăm dò, in lỗi để người dùng xem
            print(f"[ERR] {path}: {e}")
        time.sleep(config.REQUEST_GAP_SECONDS)


def cmd_seed(args):
    conn = db.connect(config.DB_PATH)
    pipeline.seed(conn, collector.make_client())
    print("Tổng số tin trong DB:", db.count(conn))


def cmd_run(args):
    conn = db.connect(config.DB_PATH)
    ok = pipeline.run_loop(conn, collector.make_client(), cycles=args.cycles)
    if not ok:
        sys.exit(0)  # dừng có chủ đích: systemd (Restart=on-failure) sẽ không bật lại


def cmd_report(args):
    conn = db.connect(config.DB_PATH)
    status = db.get_status(conn)
    now = float(status["generated_at"]) if status.get("source") == "simulated" else time.time()
    print(f"DB: {config.DB_PATH}  ({db.count(conn)} tin)")
    print(f"{'NHÓM SẢN PHẨM':40}{'N':>5}{'TV 7N':>14}{'TV 30N':>14}{'XU HƯỚNG':>10}")
    for key, _label, n in db.key_counts(conn, now - config.WINDOW_DAYS * 86400):
        m30 = analyzer.median_clean(db.prices(conn, key, now - config.WINDOW_DAYS * 86400))
        m7 = analyzer.median_clean(db.prices(conn, key, now - config.TREND_DAYS * 86400))
        trend = f"{(m7 - m30) / m30 * 100:+.1f}%" if m7 and m30 else "-"
        print(f"{key:40}{n:>5}{(m7 or 0):>14,.0f}{(m30 or 0):>14,.0f}{trend:>10}")


def _flag_scan(conn, since, use_condition):
    """Mọi tin (trừ nhóm bypass/thay linh kiện…) sẽ bị báo nếu vừa đăng, có/không quy đổi tình trạng."""
    saved, config.USE_CONDITION = config.USE_CONDITION, use_condition
    try:
        out = []
        for r in conn.execute("SELECT * FROM listings WHERE first_seen >= ?", (since,)).fetchall():
            if r["condition"] in NO_ALERT:
                continue
            adj = analyzer.adjusted(r["price"], r["battery"], r["cosmetic"], r["key"])
            res = analyzer.evaluate(adj, analyzer.adjusted_history(db.history(conn, r["key"], since, r["list_id"]),
                                                                   r["key"]))
            if res:
                res["adj_price"] = adj
                out.append((r, res))
        return sorted(out, key=lambda x: -x[1]["discount"])
    finally:
        config.USE_CONDITION = saved


def cmd_audit(args):
    """Soát mọi tin đang có: tin nào SẼ bị báo nếu vừa đăng — kiểm tra tay ngưỡng trên dữ liệu thật ngay
    sau khi seed, không phải chờ tin mới. Không gọi mạng (mô tả đã được đọc lúc nhận tin)."""
    conn = db.connect(config.DB_PATH)
    status = db.get_status(conn)
    now = float(status["generated_at"]) if status.get("source") == "simulated" else time.time()
    since = now - config.WINDOW_DAYS * 86400
    raw = _flag_scan(conn, since, use_condition=False)
    flagged = _flag_scan(conn, since, use_condition=config.USE_CONDITION)
    total = db.count(conn)
    by_flag = collections.Counter(FLAG_LABEL.get(r[0], r[0]) for r in conn.execute(
        "SELECT condition FROM listings WHERE first_seen >= ? AND condition IN (%s)" % ",".join("?" * len(NO_ALERT)),
        (since, *NO_ALERT)))
    known = conn.execute("SELECT COUNT(battery), COUNT(cosmetic) FROM listings WHERE first_seen >= ?",
                         (since,)).fetchone()
    deals = sum(res["label"] == "deal" for _, res in flagged)
    raw_deals = sum(res["label"] == "deal" for _, res in raw)
    m = config.CONDITION_MODEL
    lines = [f"# Soát dữ liệu — {time.strftime('%d/%m/%Y %H:%M')}", "",
             f"DB `{config.DB_PATH}`: {total} tin; mô tả cho biết pin ở {known[0]} tin, ngoại hình ở {known[1]} tin.",
             "",
             "- Loại khỏi so sánh nhờ đọc mô tả: " + (", ".join(f"{k}: {v}" for k, v in by_flag.most_common()) or "0"),
             f"- So giá thô: sẽ báo {raw_deals} deal, {len(raw) - raw_deals} nghi lừa đảo",
             f"- **So giá đã quy đổi theo pin/ngoại hình: sẽ báo {deals} deal, {len(flagged) - deals} nghi lừa đảo** "
             f"(pin +1% ≈ giá +{m['battery_k']:.1%}, ngoại hình +1% ≈ giá +{m['cosmetic_k']:.1%})",
             "",
             "Ngưỡng deal: max("
             f"{config.DEAL_PCT:.0%}, {config.DEAL_Z:g} × độ phân tán nhóm); lừa đảo: ≥ {config.SCAM_PCT:.0%}. "
             "Mở từng link, ghi Đúng/Sai vào cột cuối để ước lượng precision thật.", "",
             "| Loại | Rẻ hơn | Ngưỡng nhóm | Giá | Quy đổi | Tình trạng | Trung vị (n) | Nhóm | Người bán | Tiêu đề | Link | Đúng? |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r, res in flagged:
        lines.append(f"| {'deal' if res['label'] == 'deal' else 'lừa đảo?'} | {res['discount']:.0%} | "
                     f"{res['cut']:.0%} | {notifier.vnd(r['price'])} | {notifier.vnd(res['adj_price'])} | "
                     f"{notifier.condition_text(r['battery'], r['cosmetic'])} | "
                     f"{notifier.vnd(res['median'])} ({res['n']}) | {r['key']} | {r['seller']} | "
                     f"{r['title'].replace('|', '/')} | {r['url'] or '-'} | |")
    text = "\n".join(lines) + "\n"
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    path = os.path.join(config.REPORT_DIR, f"audit_{time.strftime('%Y%m%d_%H%M%S')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print("Đã lưu:", path)


def _save_report(prefix, text):
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    path = os.path.join(config.REPORT_DIR, f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def cmd_track(args):
    """Một lượt kiểm tra tin cũ còn đăng hay đã gỡ (worker tự làm việc này mỗi vòng quét)."""
    if args.hours is not None:
        config.TRACK_INTERVAL_HOURS = args.hours
    conn = db.connect(config.DB_PATH)
    client = collector.make_client()
    st = pipeline.track_once(conn, lambda lid: collector.check_alive(client, lid),
                             budget=args.budget, gap=config.REQUEST_GAP_SECONDS)
    print(f"Đã kiểm tra {st['checked']} tin: {st['gone']} tin đã gỡ.")


def cmd_speed(args):
    """Báo cáo tốc độ bán từ dữ liệu theo dõi."""
    import speed

    text = speed.render(speed.analyze(db.connect(config.DB_PATH)))
    print(text)
    print("Đã lưu:", _save_report("speed", text))


def cmd_speedsim(args):
    """Kiểm chứng phương pháp đo tốc độ bán trên dữ liệu giả lập có đáp án."""
    import simulator

    log.setLevel(logging.WARNING)
    out = args.db or os.path.join(config.BASE_DIR, "data", "speedsim.db")
    _remove_db(out)
    print(f"Giả lập {args.days} ngày (seed={args.seed}), bot chạy từ ngày thứ 7, kiểm tra lại tin mỗi 6 giờ...")
    res, truth = simulator.speed_backtest(days=args.days, seed=args.seed, db_path=out)
    text = simulator.render_speed_validation(res, truth)
    print(text)
    print("Đã lưu:", _save_report("speedsim", text))
    print(f"Xem trên dashboard:  python main.py web --db \"{out}\"  rồi mở trang Tốc độ bán")


def cmd_calibrate(args):
    """Học từ dữ liệu đang có: pin/ngoại hình thêm 1% thì giá cao hơn bao nhiêu. --save để ghi lại
    (data/condition_model.json, được dùng từ lần chạy sau)."""
    conn = db.connect(config.DB_PATH)
    rows = [tuple(r) for r in conn.execute(  # chỉ iPhone: nhóm từ khóa chung không quy đổi theo tình trạng
        "SELECT key, price, battery, cosmetic FROM listings WHERE condition = 'used' AND key NOT LIKE 'kw:%'")]
    m = analyzer.fit_condition_model(rows)
    print(f"DB {config.DB_PATH}: dùng {m['n']} tin máy cũ (pin: {m['n_battery']}, ngoại hình: {m['n_cosmetic']}, "
          f"không ghi gì: {m['unknown_n']})\n")
    for name, table in (("Pin", m["battery_table"]), ("Ngoại hình", m["cosmetic_table"])):
        print(f"{name:12}{'số tin':>8}{'giá so với trung vị nhóm':>28}")
        for lo, hi, n, rel in table:
            print(f"  {lo:>3}–{hi:<3}%{n:>10}{('-' if rel is None else f'{rel:+.1%}'):>24}")
        print()
    print(f"Kết quả hồi quy: pin +1% → giá +{m['battery_k']:.2%} (mốc {m['battery_ref']:.0f}%) · "
          f"ngoại hình +1% → giá +{m['cosmetic_k']:.2%} (mốc {m['cosmetic_ref']:.0f}%)")
    if args.save:
        keep = {k: m[k] for k in ("battery_ref", "battery_k", "cosmetic_ref", "cosmetic_k", "n", "n_battery",
                                  "n_cosmetic")}
        keep["learned_at"] = time.strftime("%Y-%m-%d %H:%M")
        with open(config.CONDITION_MODEL_PATH, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=2)
        print("Đã lưu:", config.CONDITION_MODEL_PATH)
    else:
        print("(Chưa lưu. Thêm --save để dùng hệ số này.)")


def cmd_renormalize(args):
    """Chuẩn hóa lại mọi tin bằng luật hiện tại (sau khi sửa normalizer.py hoặc tùy chọn từ khóa trong
    watchlist.json). Không gọi mạng; kết quả đọc mô tả trước đó (lock, bypass...) được giữ vì đã lưu trong
    cột attrs. Tin của từ khóa đã bỏ khỏi danh sách được giữ nguyên."""
    conn = db.connect(config.DB_PATH)
    pipeline.assign_old_rows(conn)
    watches = {w["name"]: w for w in config.WATCHLIST}
    changed = removed = 0
    rows = conn.execute("SELECT k.list_id, k.key, MIN(k.watch) AS watch, l.title, l.attrs, l.price, l.region, "
                        "l.seller, l.url FROM listing_keys k JOIN listings l USING (list_id) "
                        "GROUP BY k.list_id, k.key").fetchall()
    for r in rows:
        w = watches.get(r["watch"])
        if w is None:
            if is_keyword_key(r["key"]):
                continue
            w = {"type": "iphone"}
        attrs = json.loads(r["attrs"]) if r["attrs"] else {}
        norm = normalize_watch(w, r["title"], attrs)
        if norm is None:
            conn.execute("DELETE FROM listing_keys WHERE list_id = ? AND key = ?", (r["list_id"], r["key"]))
            code, detail = skip_reason(w, r["title"], attrs)  # tin không mất hẳn khỏi tầm nhìn: vào "Tin bỏ qua"
            db.add_skipped(conn, r["watch"], {**dict(r), "attrs": attrs}, code, detail)
            removed += 1
        elif norm["key"] != r["key"]:
            db.set_key(conn, r["list_id"], norm, old_key=r["key"])
            changed += 1
    gone = db.purge_orphans(conn)
    print(f"Đã chuẩn hóa lại {config.DB_PATH}: {changed} tin đổi nhóm, {removed} lượt bị loại khỏi nhóm "
          f"({gone} tin bị xóa hẳn), còn {db.count(conn)} tin.")


def _watch_from_args(args):
    """Từ khóa của lệnh search: lấy mục đã có trong watchlist (cùng tên hoặc cùng chữ tìm), nếu chưa có thì
    dựng mới từ tham số dòng lệnh. Trả (mục, đã có sẵn?)."""
    query = " ".join((args.query or "").split())
    name = " ".join((args.name or "").split()) or query
    for w in config.WATCHLIST:
        if w["name"].lower() == name.lower() or fold(w["keywords"]) == fold(query):
            return w, True
    w = {"name": name, "keywords": query}
    if args.type:
        w["type"] = args.type
    elif watch_type(w) == "iphone":
        w["type"] = "iphone"
    for k in ("min_price", "max_price", "cg", "every"):
        v = getattr(args, k)
        if v:
            w["every_minutes" if k == "every" else k] = v
    if args.exclude:
        w["exclude"] = [x.strip() for x in args.exclude.split(",") if x.strip()]
    if args.by_year is not None:
        w["group_by"] = ["year"] if args.by_year else []
    return w, False


def _print_groups(conn, now, watch):
    import export

    groups = export.group_rows(conn, now, watch=watch)
    print(f"\n{'NHÓM':52}{'SỐ TIN':>7}{'TRUNG VỊ':>14}{'P25':>13}{'P75':>13}  GHI CHÚ")
    for g in groups:
        note = (f"không báo ({g['flag']})" if g["flag"] else "giá quá phân tán" if g["dispersed"] and g["ready"]
                else f"deal khi rẻ hơn {g['cut']:.0%}" if g["ready"] else "chưa đủ mẫu")
        label = f"{g['label']} · {g['market_vn']}"
        print(f"{label[:51]:52}{g['n']:>7}{notifier.vnd(g['median'] or 0):>14}{notifier.vnd(g['p25'] or 0):>13}"
              f"{notifier.vnd(g['p75'] or 0):>13}  {note}")
    if not groups:
        print("(chưa có tin nào hợp lệ)")


def _ask_search(args):
    """Hỏi từng mục khi chạy search không kèm từ khóa (file 6_TIM_THEO_TU_KHOA.bat). Hỏi trong Python thay vì
    `set /p` của cmd để gõ tiếng Việt có dấu không bị lỗi bảng mã."""
    while not args.query:
        args.query = input("Từ khóa cần tìm (vd: macbook air m2, honda vision 2020): ").strip()
    pages = input(f"Số trang cần lấy, 50 tin/trang, tối đa {config.SEARCH_MAX_PAGES} [{args.pages}]: ").strip()
    if pages.isdigit():
        args.pages = int(pages)
    args.exclude = args.exclude or input("Bỏ tin có chữ (cách nhau dấu phẩy, Enter = không): ").strip() or None
    lo = input("Giá từ (vd 3tr, Enter = không lọc): ").strip()
    hi = input("Giá đến (vd 40tr, Enter = không lọc): ").strip()
    args.min_price, args.max_price = notifier.parse_vnd(lo) or args.min_price, notifier.parse_vnd(hi) or args.max_price
    args.add = args.add or input("Thêm vào danh sách theo dõi liên tục? (c/k) [k]: ").strip().lower()[:1] in ("c", "y")
    if args.add and not args.every:
        choices = "/".join(map(str, config.SCAN_CHOICES))
        while True:
            every = input(f"Quét từ khóa này mỗi bao nhiêu phút? ({choices}; Enter = theo mặc định chung): ").strip()
            if not every:
                break
            if every.isdigit() and int(every) in config.SCAN_CHOICES:
                args.every = int(every)
                break
            print(f"  Chỉ chọn một trong: {choices}")
    print()


def cmd_search(args):
    """Tìm ngay 1 từ khóa bất kỳ trên Chợ Tốt: tải N trang vào DB (không báo deal), in giá theo nhóm và
    xuất Excel. --add: thêm vào watchlist.json để collector theo dõi tiếp."""
    import export

    if not args.query:
        if not sys.stdin.isatty():
            sys.exit('Cần từ khóa, vd:  python main.py search "macbook air m2" --pages 5 --add')
        _ask_search(args)
    w, existing = _watch_from_args(args)
    run = {**config.WATCH_DEFAULTS, **w}
    pages = max(1, min(args.pages, config.SEARCH_MAX_PAGES))
    conn = db.connect(config.DB_PATH)
    pipeline.assign_old_rows(conn)
    print(f"Tìm “{run['keywords']}” trên {config.GATEWAY} ({pages} trang × {config.PAGE_LIMIT} tin, "
          f"luật {'iPhone' if watch_type(run) == 'iphone' else 'từ khóa chung'}"
          f"{', đã có trong danh sách theo dõi' if existing else ''})...")
    started = time.time()
    st = pipeline.search(conn, collector.make_client(), run, pages)
    print(f"Tải về {st['fetched']} tin: {st['kept']} tin hợp lệ ({st['new']} tin mới vào DB), "
          f"{st['fetched'] - st['kept']} tin bị loại.")
    why = db.skipped_counts(conn, watch=run["name"], since=started)
    if why:
        print("  Lý do loại: " + "; ".join(f"{SKIP_LABEL.get(c, c)}: {n}" for c, n in why)
              + "  (chi tiết: tab Tin bỏ qua trên dashboard / sheet Tin bỏ qua trong file Excel)")
    now = time.time()
    _print_groups(conn, now, run["name"])
    path = export.save_xlsx(conn, now, run["name"])
    print(f"\nĐã xuất Excel: {path}")
    if args.open and hasattr(os, "startfile"):
        os.startfile(path)  # noqa: S606 - mở file vừa xuất bằng Excel (chỉ Windows)
    if args.add and not existing:
        config.save_watchlist(config.load_watchlist() + [w])
        print(f"Đã thêm “{w['name']}” vào {config.WATCHLIST_PATH}: collector sẽ theo dõi tiếp từ vòng quét tới.")
    elif not existing:
        print("(Chưa thêm vào danh sách theo dõi. Thêm --add để collector theo dõi liên tục.)")


def cmd_export(args):
    """Xuất Excel (Tổng hợp + Tin đăng + Tin bỏ qua) cho 1 từ khóa (--watch hoặc tham số) hoặc tất cả."""
    import export

    conn = db.connect(config.DB_PATH)
    pipeline.assign_old_rows(conn)
    watch = args.watch or args.query
    if args.csv:
        os.makedirs(config.EXPORT_DIR, exist_ok=True)
        path = os.path.join(config.EXPORT_DIR, export.filename(watch, "csv"))
        with open(path, "wb") as f:
            f.write(export.to_csv(conn, watch))
    else:
        path = export.save_xlsx(conn, time.time(), watch)
    print("Đã xuất:", path)
    if args.open and hasattr(os, "startfile"):
        os.startfile(path)  # noqa: S606


def cmd_keywords(args):
    """Danh sách từ khóa đang theo dõi và lượng dữ liệu đã thu."""
    conn = db.connect(config.DB_PATH)
    pipeline.assign_old_rows(conn)
    if args.default_every is not None:
        db.set_setting(conn, "default_every_minutes", args.default_every or None)
    counts = db.watch_counts(conn, time.time() - config.WINDOW_DAYS * 86400)
    skipped = db.skipped_by_watch(conn)
    default = pipeline.default_every(conn)
    print(config.WATCHLIST_PATH)
    print(f"Nhịp quét mặc định: " + (f"mỗi {default} phút" if default else "mỗi vòng quét") + "\n")
    print(f"{'TÊN':28}{'TÌM':30}{'LUẬT':10}{'QUÉT':>10}{'TIN 30N':>9}{'TỔNG':>7}{'NHÓM':>6}{'BỎ QUA':>8}")
    for w in config.WATCHLIST:
        c = counts.get(w["name"], (0, 0, 0, None))
        every = pipeline.scan_every(w, default)
        every = ("" if w.get("every_minutes") else "~") + f"{every}p" if every else "mỗi vòng"
        print(f"{w['name'][:27]:28}{w['keywords'][:29]:30}{watch_type(w):10}{every:>10}{c[0]:>9}{c[1]:>7}{c[2]:>6}"
              f"{skipped.get(w['name'], 0):>8}")
    for name in sorted(set(counts) - {w["name"] for w in config.WATCHLIST}):
        print(f"{name[:27]:28}{'(đã bỏ khỏi danh sách)':30}{'':10}{'':>10}{counts[name][0]:>9}{counts[name][1]:>7}")
    print("\n(~ = theo nhịp mặc định chung)")


def cmd_demo(args):
    """Chạy hoàn toàn offline với dữ liệu giả: kiểm tra chuẩn hóa + phân tích + thông báo."""
    random.seed(42)
    now = time.time()
    conn = db.connect(":memory:")
    key = "iphone-15-pro-max-256gb|grey"
    for i in range(40):
        t = now - random.randint(0, 20 * 86400)
        db.insert_if_new(conn, {
            "list_id": f"base{i}", "title": "iPhone 15 Pro Max 256GB xách tay",
            "price": int(random.gauss(15_800_000, 500_000)), "key": key, "market": "grey",
            "region": "TP.HCM", "url": f"https://example.invalid/{i}",
            "posted_at": t, "first_seen": t,
        })

    print("=== Chuẩn hóa tiêu đề ===")
    for t, attrs in [("iPhone 15 Pro Max 256GB xách tay LL/A", None), ("ip15pm 256g", None),
                     ("iphone 14 pro max 1TB VN/A", None), ("Apple iPhone 15 Pro Max", {"capacity": 7, "origin": 8}),
                     ("iPhone 15 Pro Max 256GB lock", None), ("iPhone 15 Pro Max 256GB bể màn", None),
                     ("iPhone 15 Pro Max 256GB không lỗi", None), ("Thu mua iPhone 15 Pro Max", None),
                     ("iPhone 15 Pro Max đẹp keng", None)]:
        n = normalize(t, attrs)
        extra = f" + mã {attrs}" if attrs else ""
        print(f"{(t + extra)[:60]:62} -> {n['key'] if n else 'BỎ QUA'}")

    print("\n=== Phân tích giá (nền ~15,8 triệu) ===")
    cases = [("giá thường", 16_000_000), ("deal hời", 13_200_000),
             ("nghi lừa đảo", 8_500_000), ("hơi rẻ", 15_000_000)]
    norm = normalize("iPhone 15 Pro Max 256GB xách tay LL/A")
    for name, price in cases:
        res = analyzer.evaluate(price, db.prices(conn, norm["key"], now - 30 * 86400))
        print(f"{name:14} {price:>12,}đ -> {res['label'] if res else 'không báo'}")
        if res:
            item = {"label": norm["label"], "market": "grey", "price": price, "seller": "cá nhân",
                    "region": "TP.HCM", "url": "https://example.invalid/demo"}
            notifier.send(notifier.format_alert(item, res))


def cmd_telegram_test(args):
    ok = notifier.send("✅ Deal Finder: tin nhắn thử.")
    print("Đã gửi Telegram" if ok else "Chưa cấu hình token/chat id — đã in ra màn hình")


def _remove_db(path):
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


def cmd_simulate(args):
    import simulator

    out = args.db or config.SIM_DB_PATH
    _remove_db(out)
    print(f"Sinh {args.days} ngày dữ liệu giả lập (seed={args.seed}) và chạy qua pipeline...")
    t = time.time()
    log.setLevel(logging.WARNING)  # bớt log "tin lock" khi phát lại hàng nghìn tin
    kw = {"days": args.days, "seed": args.seed}
    z = config.DEAL_Z
    try:
        config.DEAL_Z = 0.0  # ngưỡng cố định như thiết kế gốc
        v0 = simulator.backtest(":memory:", use_codes=False, use_body=False, use_condition=False, **kw)
        v1 = simulator.backtest(":memory:", use_body=False, use_condition=False, **kw)
        v2 = simulator.backtest(":memory:", use_condition=False, **kw)
    finally:
        config.DEAL_Z = z
    v3 = simulator.backtest(":memory:", use_condition=False, **kw)
    result = simulator.backtest(out, **kw)
    report = simulator.render_report(result, [
        ("Thiết kế gốc: chỉ đọc tiêu đề, ngưỡng cố định 15%", v0),
        ("+ mã cấu trúc Chợ Tốt (dung lượng, xuất xứ, lock)", v1),
        ("+ đọc mô tả mọi tin (bypass, thay linh kiện, lỗi, trả trước, lock)", v2),
        (f"+ ngưỡng thích ứng DEAL_Z = {z:g}", v3),
        ("+ quy đổi giá theo pin/ngoại hình (bản hiện tại)", result),
    ], simulator.sweep_z(**kw))
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    path = os.path.join(config.REPORT_DIR, f"backtest_{time.strftime('%Y%m%d_%H%M%S')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"Xong sau {time.time() - t:.1f}s. DB: {out}\nBáo cáo: {path}")
    print(f"Xem dashboard:  python main.py web --db \"{out}\"")


def _serve_web(db_path, host, port):
    import uvicorn

    from web.app import create_app

    print(f"Dashboard: http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}  (Ctrl+C để dừng)")
    uvicorn.run(create_app(db_path), host=host, port=port, log_level="warning")


def cmd_web(args):
    _serve_web(config.DB_PATH, args.host, args.port)


def _start_worker(db_path):
    stop = threading.Event()

    def work():
        conn = db.connect(db_path)
        try:
            pipeline.run_loop(conn, collector.make_client(), stop_event=stop)
        except Exception:  # noqa: BLE001 - để web vẫn chạy, lỗi hiện trong log
            log.exception("Collector dừng vì lỗi")
            db.set_status(conn, state="stopped", last_error="Collector lỗi, xem log")

    threading.Thread(target=work, daemon=True, name="collector").start()
    return stop


def cmd_all(args):
    stop = _start_worker(config.DB_PATH)
    try:
        _serve_web(config.DB_PATH, args.host, args.port)
    finally:
        stop.set()


def cmd_mock(args):
    import mock_chotot

    server, market = mock_chotot.serve(args.mock_port, market=mock_chotot.MockMarket(
        seconds_per_ad=args.seconds_per_ad, block_every=args.block_every))
    print(f"Mock Chợ Tốt: http://127.0.0.1:{args.mock_port}/v1/public/ad-listing  "
          f"({len(market.ads)} tin lịch sử, 1 tin mới mỗi {args.seconds_per_ad}s). Ctrl+C để dừng.")
    print(f"Ở cửa sổ PowerShell khác:  $env:CHOTOT_GATEWAY=\"http://127.0.0.1:{args.mock_port}\"; "
          f".venv\\Scripts\\python.exe main.py run --db data\\mock.db")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


def cmd_mockdemo(args):
    """Trọn vòng offline trong 1 lệnh: mock Chợ Tốt + collector thật (nhịp nhanh) + dashboard."""
    import mock_chotot

    mock_chotot.serve(args.mock_port, market=mock_chotot.MockMarket(
        seconds_per_ad=args.seconds_per_ad, block_every=args.block_every))
    config.GATEWAY = f"http://127.0.0.1:{args.mock_port}"
    config.POLL_SECONDS, config.JITTER_SECONDS, config.REQUEST_GAP_SECONDS = 15, 3, 0.2
    path = args.db or os.path.join(config.BASE_DIR, "data", "mockdemo.db")
    _remove_db(path)
    print(f"Mock Chợ Tốt chạy tại {config.GATEWAY}; collector quét mỗi ~15s; DB: {path}")
    stop = _start_worker(path)
    try:
        _serve_web(path, args.host, args.port)
    finally:
        stop.set()


COMMANDS = {
    "search": cmd_search, "export": cmd_export, "keywords": cmd_keywords,
    "probe": cmd_probe, "seed": cmd_seed, "run": cmd_run, "report": cmd_report, "audit": cmd_audit,
    "renormalize": cmd_renormalize, "calibrate": cmd_calibrate,
    "track": cmd_track, "speed": cmd_speed, "speedsim": cmd_speedsim,
    "demo": cmd_demo, "telegram-test": cmd_telegram_test, "simulate": cmd_simulate,
    "web": cmd_web, "all": cmd_all, "mock": cmd_mock, "mockdemo": cmd_mockdemo,
}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252 -> lỗi khi in tiếng Việt/emoji
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # không in từng request
    ap = argparse.ArgumentParser(description="Deal Finder — thu dữ liệu & săn deal theo từ khóa trên Chợ Tốt")
    ap.add_argument("command", choices=list(COMMANDS))
    ap.add_argument("query", nargs="?", help="search: từ khóa cần tìm; export: tên từ khóa (bỏ trống = tất cả)")
    ap.add_argument("--pages", type=int, default=config.BASELINE_PAGES, help="search: số trang (50 tin/trang)")
    ap.add_argument("--name", help="search: tên hiển thị (mặc định = từ khóa)")
    ap.add_argument("--add", action="store_true", help="search: thêm từ khóa vào watchlist để theo dõi liên tục")
    ap.add_argument("--min-price", type=notifier.parse_vnd, help="search: bỏ tin rẻ hơn, vd 3000000 hoặc 3tr")
    ap.add_argument("--max-price", type=notifier.parse_vnd, help="search: bỏ tin đắt hơn, vd 40tr")
    ap.add_argument("--exclude", help='search: bỏ tin có các chữ này, cách nhau dấu phẩy, vd "max,ốp"')
    ap.add_argument("--cg", type=int, help="search: mã danh mục Chợ Tốt (5010 điện thoại, 5030 laptop, 2020 xe máy…)")
    ap.add_argument("--type", choices=["iphone", "keyword"], help="search: luật chuẩn hóa (mặc định tự chọn)")
    ap.add_argument("--by-year", action=argparse.BooleanOptionalAction, default=None,
                    help="search: tách nhóm theo năm (mặc định: chỉ khi Chợ Tốt có năm — xe)")
    ap.add_argument("--every", type=int, choices=config.SCAN_CHOICES,
                    help="search --add: quét từ khóa này mỗi N phút (mặc định theo nhịp chung)")
    ap.add_argument("--default-every", type=int, choices=(0, *config.SCAN_CHOICES), dest="default_every",
                    help="keywords: đặt nhịp quét mặc định chung cho mọi từ khóa (0 = mỗi vòng quét)")
    ap.add_argument("--open", action="store_true", help="search/export: mở file Excel sau khi xuất (Windows)")
    ap.add_argument("--watch", help="export: tên từ khóa (bỏ trống = tất cả)")
    ap.add_argument("--csv", action="store_true", help="export: xuất CSV thay cho Excel")
    ap.add_argument("--db", help="đường dẫn file SQLite (mặc định data/deals.db)")
    ap.add_argument("--cycles", type=int, help="run: số vòng quét rồi dừng (mặc định chạy mãi)")
    ap.add_argument("--save", action="store_true", help="calibrate: lưu hệ số vừa học")
    ap.add_argument("--budget", type=int, default=30, help="track: số tin kiểm tra (1 request/tin)")
    ap.add_argument("--hours", type=float, help="track: chỉ kiểm tra tin chưa xác nhận trong N giờ (mặc định 6)")
    ap.add_argument("--host", default=config.WEB_HOST, help="web: địa chỉ lắng nghe")
    ap.add_argument("--port", type=int, default=config.WEB_PORT, help="web: cổng (mặc định 8000)")
    ap.add_argument("--days", type=int, default=30, help="simulate: số ngày dữ liệu")
    ap.add_argument("--seed", type=int, default=42, help="simulate: hạt giống ngẫu nhiên")
    ap.add_argument("--mock-port", type=int, default=8900)
    ap.add_argument("--seconds-per-ad", type=float, default=4.0, help="mock: tốc độ sinh tin mới")
    ap.add_argument("--block-every", type=int, default=0, help="mock: cứ N request trả 429 một lần")
    args = ap.parse_args(argv)
    if args.db and args.command not in ("simulate", "speedsim"):
        config.DB_PATH = args.db
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
