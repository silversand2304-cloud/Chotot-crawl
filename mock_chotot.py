"""Máy chủ giả lập API Chợ Tốt (cùng đường dẫn, cùng dạng JSON) để test trọn vòng không cần mạng.

- Lịch sử 30 ngày sinh sẵn bằng simulator, tin mới sinh liên tục theo thời gian thực.
- Tỷ lệ deal/lừa đảo của tin mới được tăng lên để demo vài phút là thấy cảnh báo.
- block_every > 0: cứ N request thì trả 429 một lần (thử cơ chế giãn nhịp/dừng).
"""
import json
import random
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import simulator

DEMO_KINDS = {**simulator.KINDS, "normal": 0.78, "deal": 0.12, "scam": 0.05}


class MockMarket:
    def __init__(self, seed=7, history_days=30, seconds_per_ad=4.0, block_every=0, list_body=True):
        self.rng = random.Random(seed)
        now = time.time()
        self.ads = simulator.generate(history_days, seed, end=now)
        self.next_id = 300_000_000
        self.last_tick = now
        self.seconds_per_ad = seconds_per_ad
        self.block_every = block_every
        self.list_body = list_body  # False: danh sách không kèm mô tả (thử đường dự phòng đọc chi tiết tin)
        self.requests = 0
        self.lock = threading.Lock()

    def add(self, ad):
        with self.lock:
            self.ads.append(ad)

    def find(self, list_id):
        """Tin còn đăng theo mã; tin đã bán/gỡ thì trả None (API thật trả 404)."""
        with self.lock:
            return next((a for a in reversed(self.ads) if a["list_id"] == list_id and not a.get("_sold")), None)

    def sell(self, list_id):
        with self.lock:
            for a in self.ads:
                if a["list_id"] == list_id:
                    a["_sold"] = True

    def tick(self, now=None):
        """Sinh tin mới cho khoảng thời gian đã trôi qua; thỉnh thoảng "đẩy" lại tin cũ hoặc bán bớt tin
        (tin rẻ dễ được bán hơn, để demo có dữ liệu tốc độ bán)."""
        now = time.time() if now is None else now
        while self.seconds_per_ad and self.last_tick + self.seconds_per_ad <= now:
            self.last_tick += self.seconds_per_ad
            self.next_id += 1
            self.ads.append(simulator.make_ad(self.rng, self.next_id, self.last_tick, now, DEMO_KINDS))
            recent = self.ads[-300:]
            if self.rng.random() < 0.2:
                old = self.rng.choice(recent)
                if old["_truth"] == "normal":
                    old["list_time"] = int(self.last_tick * 1000)
            if self.rng.random() < 0.3:
                old = self.rng.choice(recent)
                if self.rng.random() < (0.9 if old["price"] < old["_fair"] * 0.9 else 0.3):
                    old["_sold"] = True

    def query(self, q, offset, limit):
        with self.lock:
            self.tick()
            gen = re.search(r"\b(\d{2})\b", q or "")
            hits = [a for a in self.ads if (not gen or a["_gen"] == gen.group(1)) and not a.get("_sold")]
            hits.sort(key=lambda a: a["list_time"], reverse=True)
            page = [simulator.public(a) for a in hits[offset:offset + limit]]
            if not self.list_body:
                for a in page:
                    a.pop("body", None)
            return len(hits), page


def make_handler(market):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/healthz":
                return self._json(200, {"ok": True, "ads": len(market.ads)})
            detail = re.fullmatch(r"/v1/public/ad-listing/(\d+)", url.path)
            if url.path != "/v1/public/ad-listing" and not detail:
                return self._json(404, {"error": "not found"})
            with market.lock:
                market.requests += 1
                blocked = market.block_every and market.requests % market.block_every == 0
            if blocked:
                return self._json(429, {"error": "too many requests"})
            if detail:
                ad = market.find(int(detail.group(1)))
                return self._json(200, simulator.detail(ad)) if ad else self._json(404, {})
            qs = parse_qs(url.query)
            total, ads = market.query(qs.get("q", [""])[0], int(qs.get("o", ["0"])[0]),
                                      min(50, int(qs.get("limit", ["20"])[0])))
            return self._json(200, {"ads": ads, "total": total})

        def log_message(self, *args):  # im lặng, tránh lẫn với log của collector
            pass

    return Handler


def serve(port=8900, host="127.0.0.1", market=None):
    """Chạy máy chủ ở luồng nền. Trả về (server, market); gọi server.shutdown() để dừng."""
    market = market or MockMarket()
    server = ThreadingHTTPServer((host, port), make_handler(market))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, market
