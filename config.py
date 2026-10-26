"""Cấu hình chung. Mọi giá trị có thể ghi đè bằng biến môi trường hoặc file .env cạnh file này."""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env(path=os.path.join(BASE_DIR, ".env")):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _int(name, default):
    return int(os.environ.get(name) or default)


def _float(name, default):
    return float(os.environ.get(name) or default)


# --- Nguồn dữ liệu (đã kiểm chứng ngày 26/10/2026: v1 trả 200, v2 trả 404) ---
GATEWAY = os.environ.get("CHOTOT_GATEWAY", "https://gateway.chotot.com").rstrip("/")
LISTING_PATH = "/v1/public/ad-listing"
LISTING_PATH_ALT = ["/v2/public/ad/listing"]
CATEGORY_PHONE = 5010
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

# --- Danh sách từ khóa theo dõi: sửa watchlist.json, trang "Từ khóa" trên dashboard, hoặc main.py search --add.
# Collector đọc lại file mỗi vòng quét: thêm/xóa từ khóa không cần khởi động lại. Mỗi mục:
#   name (bắt buộc, tên hiển thị = định danh dữ liệu), keywords (bắt buộc, chữ gõ vào ô tìm Chợ Tốt),
#   type: "iphone" | "keyword" (bỏ trống = tự chọn: có chữ iphone thì dùng luật iPhone),
#   min_price / max_price, exclude: [từ loại trừ], cg: mã danh mục, region: mã tỉnh,
#   group_by: ["year"] tách nhóm theo năm ([] = không tách; mặc định chỉ tách khi Chợ Tốt có năm — xe),
#   phone_rules: true = đọc mô tả như luật iPhone (bypass, thay linh kiện…) cho điện thoại/máy tính bảng khác,
#   every_minutes: quét từ khóa này mỗi N phút (mặc định mỗi vòng), pages: số trang nạp lần đầu.
WATCHLIST_PATH = os.environ.get("WATCHLIST", os.path.join(BASE_DIR, "watchlist.json"))
WATCH_DEFAULTS = {"min_price": 1, "max_price": 10**13}  # min 1: bỏ tin giá 0 ("thỏa thuận")
# Nhịp quét chủ động (phút) cho từ khóa: chọn trên dashboard / --every. Không chọn = mỗi vòng quét (POLL_SECONDS).
# Chọn riêng từng từ khóa (trường every_minutes) hoặc 1 mặc định chung (trang Từ khóa). Sai số ±1 vòng quét.
SCAN_CHOICES = (5, 10, 15, 20, 30, 45, 60)


def load_watchlist(path=None):
    with open(path or WATCHLIST_PATH, encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError("watchlist.json phải là một danh sách [...]")
    out = []
    for w in items:
        if not (isinstance(w, dict) and str(w.get("keywords") or "").strip()):
            raise ValueError(f"Mục thiếu 'keywords': {w!r}")
        w = {"name": str(w.get("name") or w["keywords"]).strip(),
             **{k: v for k, v in w.items() if v is not None and k != "name"}}
        for k, v in WATCH_DEFAULTS.items():
            w.setdefault(k, v)
        out.append(w)
    names = [w["name"] for w in out]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"Trùng tên từ khóa: {', '.join(sorted(dup))}")
    return out


def save_watchlist(items, path=None):
    """Ghi an toàn (file tạm rồi thay thế) để collector không bao giờ đọc phải file ghi dở."""
    path = path or WATCHLIST_PATH
    keep = []
    for w in items:
        d = {k: w[k] for k in ("name", "keywords", "type") if k in w}
        d.update({k: v for k, v in w.items() if k not in d and WATCH_DEFAULTS.get(k, object()) != v})
        keep.append(d)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join("  " + json.dumps(w, ensure_ascii=False) for w in keep) + "\n]\n")
    os.replace(tmp, path)


_DEFAULT_WATCHLIST = os.path.join(BASE_DIR, "watchlist.json")
if not os.path.exists(WATCHLIST_PATH) and os.path.exists(_DEFAULT_WATCHLIST):
    # WATCHLIST trỏ ra ổ dữ liệu (Docker: /data/watchlist.json) mà chưa có file: lấy danh sách mặc định
    os.makedirs(os.path.dirname(os.path.abspath(WATCHLIST_PATH)), exist_ok=True)
    save_watchlist(load_watchlist(_DEFAULT_WATCHLIST), WATCHLIST_PATH)
WATCHLIST = load_watchlist()
_watchlist_mtime = os.path.getmtime(WATCHLIST_PATH)


def refresh_watchlist():
    """Đọc lại watchlist.json nếu file đã đổi. File lỗi thì giữ danh sách cũ và trả kèm thông báo lỗi."""
    global WATCHLIST, _watchlist_mtime
    try:
        mtime = os.path.getmtime(WATCHLIST_PATH)
        if mtime != _watchlist_mtime:
            WATCHLIST, _watchlist_mtime = load_watchlist(), mtime
    except (OSError, ValueError) as e:
        return WATCHLIST, f"watchlist.json lỗi, vẫn dùng danh sách cũ: {e}"
    return WATCHLIST, ""

# --- Nhịp quét: 1 request/từ khóa/chu kỳ, cố ý chậm và có độ lệch ngẫu nhiên ---
POLL_SECONDS = _int("POLL_SECONDS", 120)
JITTER_SECONDS = _int("JITTER_SECONDS", 15)
PAGE_LIMIT = 50
BASELINE_PAGES = _int("BASELINE_PAGES", 3)   # số trang nạp lịch sử lúc khởi động (lệnh seed)
REQUEST_GAP_SECONDS = _float("REQUEST_GAP_SECONDS", 2.0)  # nghỉ giữa 2 request liên tiếp
REQUEST_TIMEOUT = 20
MAX_BLOCKS = 5            # bị 403/429 liên tiếp từng này lần thì dừng hẳn

# --- Đo tốc độ bán: kiểm tra lại tin cũ còn đăng hay đã gỡ ---
TRACK_PER_CYCLE = _int("TRACK_PER_CYCLE", 3)          # số tin kiểm tra mỗi vòng quét (0 = tắt)
TRACK_INTERVAL_HOURS = _float("TRACK_INTERVAL_HOURS", 6)  # mỗi tin kiểm tra lại tối đa 6 giờ/lần
TRACK_DAYS = _int("TRACK_DAYS", 21)                   # theo dõi tin trong 21 ngày kể từ lúc thấy

# --- Phân tích giá ---
WINDOW_DAYS = 30          # cửa sổ tính trung vị
TREND_DAYS = 7            # so trung vị 7 ngày với 30 ngày
MIN_SAMPLES = 8           # chưa đủ mẫu thì không báo
DEAL_PCT = _float("DEAL_PCT", 0.15)   # rẻ hơn trung vị >= 15% => deal (mức tối thiểu)
DEAL_Z = _float("DEAL_Z", 2.0)        # ... và >= DEAL_Z lần độ phân tán của nhóm (ngưỡng thích ứng)
SCAM_PCT = _float("SCAM_PCT", 0.40)   # rẻ hơn >= 40% => cảnh báo nghi lừa đảo
MAX_AGE_HOURS = 6         # chỉ báo tin đăng/đẩy trong 6 giờ gần nhất

DB_PATH = os.environ.get("DEAL_DB", os.path.join(BASE_DIR, "data", "deals.db"))

# --- Quy đổi giá theo tình trạng máy (pin %, ngoại hình %) trước khi so ---
# Mặc định: hồi quy trên ~350 tin máy cũ thật ngày 26/10/2026 (2 lần nạp độc lập cho cùng kết quả):
# % pin KHÔNG ảnh hưởng giá rao (-0,31% ± 0,36% mỗi 1%), ngoại hình +0,58% ± 0,37% mỗi 1%.
# `python main.py calibrate --save` học lại từ dữ liệu đang có và ghi vào file dưới đây (được ưu tiên).
USE_CONDITION = os.environ.get("USE_CONDITION", "1") != "0"
CONDITION_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "condition_model.json")
CONDITION_MODEL = {"battery_ref": 92.0, "battery_k": 0.0, "cosmetic_ref": 99.0, "cosmetic_k": 0.006}
# Tùy chọn của người mua (0 = tắt): không báo deal nếu người bán GHI pin/ngoại hình thấp hơn mức này.
# Khác với quy đổi giá ở trên: đây là lựa chọn cá nhân, không phải điều thị trường định giá.
ALERT_MIN_BATTERY = _float("ALERT_MIN_BATTERY", 0)
ALERT_MIN_COSMETIC = _float("ALERT_MIN_COSMETIC", 0)
if os.path.exists(CONDITION_MODEL_PATH):
    with open(CONDITION_MODEL_PATH, encoding="utf-8") as _f:
        CONDITION_MODEL.update({k: v for k, v in json.load(_f).items() if k in CONDITION_MODEL})
SIM_DB_PATH = os.path.join(BASE_DIR, "data", "sim.db")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
EXPORT_DIR = os.environ.get("EXPORT_DIR", os.path.join(BASE_DIR, "exports"))
SKIP_KEEP_DAYS = _int("SKIP_KEEP_DAYS", 30)   # tin bỏ qua giữ lại bao nhiêu ngày (tab "Tin bỏ qua")
SEARCH_MAX_PAGES = 20     # lệnh search: tối đa 20 trang × 50 tin cho 1 từ khóa

# --- Web dashboard ---
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = _int("WEB_PORT", 8000)
DASH_USER = os.environ.get("DASH_USER", "")
DASH_PASS = os.environ.get("DASH_PASS", "")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
