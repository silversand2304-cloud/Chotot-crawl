# Tư vấn thiết kế — Deal Finder (dữ liệu & deal theo từ khóa trên Chợ Tốt)

> Đánh giá bản thiết kế gốc `deal-finder-demo.md`, các thay đổi đã áp dụng kèm bằng chứng
> (chạy thật trên Chợ Tốt ngày 26/10/2026, nhiều lần nạp ~650 tin + backtest dữ liệu giả lập hiệu
> chỉnh theo số đo thật), kiến trúc triển khai lên VPS và lộ trình.

---

## 1. Tóm tắt khuyến nghị

**Giữ khung kiến trúc gốc** (collector → normalizer → analyzer → notifier, SQLite, trung vị + IQR):
đơn giản, đúng hướng, đủ cho quy mô cá nhân/nhóm nhỏ.

**Nhưng phần phân tích của bản gốc sẽ "spam" khi chạy thật.** Trên dữ liệu thật, ~30% tin là máy
**đã thay màn/vỏ, có lỗi, bypass, hoặc rao kèm "đưa trước"** — chỉ lộ ra trong phần mô tả — nên
giá cùng một nhóm phân tán ~16%. Với ngưỡng cố định 15%, bản gốc gắn cờ **99/638 tin thật (16%)**;
trong backtest chỉ **36% cảnh báo deal và 54% cảnh báo "lừa đảo" là đúng**.

**Bản hiện tại** gắn cờ **21/649 tin thật (3%)**; backtest: **77% deal đúng, 90% "lừa đảo" đúng**,
~3,6 cảnh báo/ngày.

| # | Thay đổi | Vì sao | Bằng chứng |
|---|---|---|---|
| 1 | Đường dẫn API `v2` → **`/v1/public/ad-listing`** | `v2` trả 404 | `python main.py probe` |
| 2 | **Dùng mã cấu trúc của Chợ Tốt** (`mobile_capacity`, `elt_origin`, `elt_lock`, `elt_condition`) | 15% tin không ghi dung lượng/nguồn gốc ở tiêu đề | Chuẩn hóa được **85% → 96%** tin |
| 3 | **Máy lock là nhóm riêng** | 15 Pro Max 256GB: lock **11,2 tr**, xách tay **16,5 tr**, VN/A **17,5 tr** | Dashboard dữ liệu thật |
| 4 | **Đọc mô tả của mọi tin ngay khi nhận** (API danh sách đã kèm mô tả đầy đủ → 0 request thêm): thay linh kiện, lỗi, bypass, "đưa trước", lock → xếp nhóm riêng, không bao giờ báo deal | Tiêu đề hầu như không ghi (chỉ 3/665 tin) | Thật: loại **190/649** tin khỏi so sánh; độ phân tán nhóm máy zin **15,8% → 9,0%**. Backtest: deal đúng **34% → 72%**, "lừa đảo" **56% → 87%** |
| 5 | **Ngưỡng deal thích ứng** = max(15%, 2 × độ phân tán của nhóm) | Nhóm giá lộn xộn (đời 13–14) cần rẻ hơn nhiều mới là bất thường | Backtest: deal đúng **72% → 79%**, cảnh báo **4,1 → 3,6/ngày** |
| 6 | **Trích % pin, % ngoại hình** từ tiêu đề/mô tả; quy đổi giá theo hệ số **học từ dữ liệu**; hiện trong cảnh báo | Kiểm tra giả thuyết "deal giả do máy pin yếu/xấu" | Thật: **% pin không ảnh hưởng giá rao**; ngoại hình +0,58%/điểm; deal **22 → 18**. Backtest: trung tính (mục 6) |
| 6b | **Đo tốc độ bán**: kiểm tra lại tin cũ còn đăng hay đã gỡ (404), phân tích sống còn có xử lý dữ liệu bị cắt | Giá rao không phản ánh pin — có thể tốc độ bán thì có; tin rẻ bán nhanh = deal thật | Giả lập: tìm lại đáp án (rẻ ×2 → đo ×1,74; shop ×0,25 → ×0,27). Thật: đang thu thập, cần ~2–4 tuần (mục 6.3) |
| 7 | Loại tin **máy lỗi** ở tiêu đề (hiểu phủ định "không lỗi") và tin **"cần mua"** (`st=s`, `type=k`) | Giá thấp vì hỏng, hoặc không phải tin bán | Tin rác lọt thành cảnh báo: **0** |
| 8 | **Nới `min_price`** về ~20% giá thị trường | Bản gốc đặt 8 tr cho 15 Pro Max → lọc mất chính tin mồi giá cần cảnh báo | Có tin thật 15 Pro Max 256GB VN/A giá **4,5 tr** |
| 9 | Mỗi request lấy **50 tin**, quét **120 giây/vòng**, cách nhau ≥ 2 giây | Ít request mà không sót tin mới | ~2,5 request/phút cho 5 từ khóa |
| 10 | **Lưu mã thô + kết quả đọc mô tả** (cột `attrs`, `battery`, `cosmetic`) và lệnh `renormalize` | Luật chuẩn hóa phải sửa nhiều lần; áp luật tiêu đề mới cho dữ liệu cũ không cần gọi mạng | Test `test_renormalize_keeps_description_findings` |
| 11 | **Từ khóa chung cho mọi sản phẩm** (mục 6.4): nhóm theo danh mục + mới/đã dùng + năm (xe) + cấu hình GB/TB (điện thoại, laptop, máy tính bảng); dữ liệu, thống kê, Excel/CSV riêng từng từ khóa; thêm/bỏ từ khóa trên dashboard không cần khởi động lại | Dùng cho nhiều loại hàng, không chỉ iPhone | Thật: MacBook Air M2 độ phân tán **18% → 7–10%** khi tách cấu hình; Honda Vision tách năm cho trung vị tăng đều theo năm |

**Bổ sung để dùng hằng ngày và chạy trên máy chủ:** web dashboard + JSON API, lưu cảnh báo vào DB,
trạng thái collector, `/healthz`, đăng nhập dashboard, bộ giả lập có đáp án + backtest, máy chủ mock
Chợ Tốt, lệnh `audit` (soát dữ liệu thật) và `calibrate` (học hệ số pin/ngoại hình), bộ cài VPS
(systemd + Nginx + sao lưu) và Docker.

---

## 2. Phát hiện khi chạy thật trên Chợ Tốt (26/10/2026)

| Hạng mục | Thiết kế gốc giả định | Thực tế đo được | Đã xử lý |
|---|---|---|---|
| Đường dẫn danh sách tin | `/v2/public/ad/listing` | **404**; `/v1/public/ad-listing` trả 200 | Đổi sang v1 |
| Mô tả tin | Phải gọi API chi tiết | API danh sách **đã kèm mô tả đầy đủ** (so 3/3 tin: trùng khớp) | Đọc mô tả mọi tin, không tốn request |
| Thứ tự kết quả | "chưa kiểm chứng mới nhất" | Mặc định ≈ mới nhất (trang 1 toàn tin trong ~40 giờ), không tuyệt đối | Khử trùng theo `list_id` + 50 tin/trang |
| Thời gian tin | `list_time` = lúc đăng | `list_time` = lúc **đẩy tin** gần nhất | Tin đẩy lại không báo lặp |
| Mặt bằng giá | ~25 tr cho 15 Pro Max 256GB | **~16,5 tr** (xách tay), **~17,5 tr** (VN/A), **~11,2 tr** (lock) | Hiệu chỉnh giả lập |
| Tin có vấn đề trong mô tả | Không xét | Thay linh kiện **18%** (giá ~85% máy zin), lỗi **5%** (~81%), bypass **3%** (~69%), "đưa trước" **3%** (~94% — đa số vẫn là giá đầy đủ kèm góp) | Nhóm riêng, không báo |
| Độ phân tán giá | Nhỏ | Cả nhóm: **~15,8%**; chỉ máy zin: **~9,0%** (đời 16–17: 6–8%, đời 13–14: 14–15%) | Đọc mô tả + ngưỡng thích ứng |
| **Pin / ngoại hình** | — | 47% tin ghi % pin (1/3 trong đó ghi 100% — đa số pin đã thay), 52% ghi ngoại hình. **Giá rao không phụ thuộc % pin** | Mục 6 |
| Tỷ lệ tin của shop | — | **~68%** (`company_ad`) | Cột `seller` |
| Console Windows | — | In emoji/tiếng Việt ra file/pipe bị lỗi `cp1252` | `main.py` ép stdout UTF-8 |

---

## 3. Kiến trúc đề xuất

```
                ┌──────────────────── VPS Ubuntu (đặt tại Việt Nam) ────────────────────┐
 Chợ Tốt  ◀──── │  deal-finder-worker  (systemd, Restart=on-failure)                    │
 gateway        │    collector ─▶ đọc mô tả ─▶ normalizer ─▶ analyzer ─▶ notifier ───────┼──▶ Telegram
 (v1 listing,   │        │      (cờ, pin, ngoại hình)   (giá quy đổi)                    │
  có mô tả)     │        └──────────▶  data/deals.db (SQLite WAL)  ◀──────┐               │
                │                     listings · alerts · status          │               │
                │  deal-finder-web  (FastAPI, chỉ nghe 127.0.0.1:8000) ───┘               │
                │        ▲                                                                │
                │  Nginx :80/:443  (giới hạn 10 req/s/IP, HTTPS bằng certbot)            │
                └────────┼───────────────────────────────────────────────────────────────┘
                         ▼
               Trình duyệt / điện thoại (đăng nhập DASH_USER / DASH_PASS)
```

**Vì sao tách 2 tiến trình (worker, web):** worker hỏng không kéo web chết theo; chính sách khởi động
lại khác nhau — worker **cố ý dừng hẳn** khi bị chặn 5 lần liên tiếp (thoát mã 0 → systemd không
bật lại), còn web luôn bật lại. Trên máy cá nhân có lệnh `all` chạy cả hai trong một cửa sổ.

**Luồng xử lý một tin** (`pipeline.process`, dùng chung cho chạy thật, mock và backtest):
1. Bỏ tin không phải tin bán, ngoài khoảng giá của từ khóa.
2. Đọc mô tả: dấu hiệu thay linh kiện/lỗi/bypass/đưa trước/lock, % pin, % ngoại hình
   (lưu kết quả, **không lưu nguyên văn** vì mô tả hay chứa số điện thoại).
3. Chuẩn hóa: tiêu đề → mã cấu trúc → kết quả đọc mô tả → khóa `iphone-15-pro-max-256gb|grey`
   (tin có dấu hiệu → `…|thay-linh-kien`, không bao giờ báo).
4. Tin đã thấy → chỉ cập nhật `last_seen`.
5. Tin mới, còn nóng (< 6 giờ): quy đổi giá theo tình trạng máy, so với trung vị 30 ngày của nhóm
   (cũng quy đổi, lọc ngoại lai IQR, ≥ 8 mẫu). Rẻ hơn ≥ max(15%, 2σ nhóm) → *deal*; ≥ 40% → *nghi lừa đảo*.
6. Tùy chọn người mua (`ALERT_MIN_BATTERY`, `ALERT_MIN_COSMETIC`) → bỏ deal không hợp ý.
   Còn lại → lưu `alerts`, gửi Telegram kèm tình trạng máy.
7. Dự phòng: nếu tin trong danh sách không kèm mô tả, đọc API chi tiết (1 request/tin sắp báo).

---

## 4. Lựa chọn công nghệ

| Thành phần | Chọn | Lý do | Khi nào đổi |
|---|---|---|---|
| Ngôn ngữ | Python 3.11+ | Giữ như thiết kế gốc | — |
| HTTP | `httpx` | Timeout, redirect, dùng chung cho test | — |
| CSDL | **SQLite chế độ WAL** | Không cần cài server; web đọc song song khi worker ghi; ~1 KB/tin | > 1 triệu tin, nhiều worker ghi đồng thời → PostgreSQL |
| Web | **FastAPI + Jinja2**, biểu đồ SVG dựng phía máy chủ | ~70 MB RAM cho cả worker + web (đo thực tế); có JSON API; không cần Node/CDN | Cần biểu đồ tương tác phức tạp |
| Thống kê | Tự viết (trung vị, IQR, hồi quy tuyến tính nhỏ) | Không cần numpy/pandas → cài nhẹ trên VPS | Mô hình phức tạp hơn |
| Chạy nền | **systemd** (khuyên dùng) / Docker Compose | systemd nhẹ nhất cho VPS 1 GB | — |
| Cổng vào | Nginx + certbot | Giới hạn tốc độ, HTTPS miễn phí | — |
| Cảnh báo | Telegram Bot API | Miễn phí, tức thời, có trên điện thoại | Zalo OA (cần doanh nghiệp) |

---

## 5. Mô hình dữ liệu và bảng mã

```
listings(list_id PK, title, price, key, label, market, condition, region, seller, url,
         posted_at, first_seen, last_seen,
         attrs,                 -- JSON: mã thô Chợ Tốt + kết quả đọc mô tả (cờ, lock, pin, ngoại hình)
         battery, cosmetic,     -- % pin, % ngoại hình người bán ghi (NULL = không ghi)
         orig_posted_at,        -- lúc đăng gốc (orig_list_time; tin chưa đẩy thì = list_time)
         checked_at, gone_at, gone_status)  -- theo dõi còn/mất; last_seen = lần cuối biết chắc còn đăng
skipped (list_id, watch PK, reason, detail, title, price, region, seller, category, url, first_seen, last_seen)
                                -- tin bị loại kèm lý do (mục 6.5); không lưu mô tả
settings(k PK, v)               -- cài đặt đặt từ dashboard (nhịp quét mặc định)
listing_keys(list_id, key, label, watch)  PK (list_id, key, watch)
                                -- tin thuộc nhóm nào, qua từ khóa nào: 1 tin khớp nhiều từ khóa được
                                -- tính ở mọi từ khóa; watch = '' là dữ liệu bản cũ chưa gắn từ khóa
alerts  (list_id PK, kind, price, adj_price, median, discount, n, created_at, sent)
status  (k PK, v)               -- trạng thái collector cho dashboard/healthz
sim_truth(list_id PK, truth, fair)  -- chỉ có trong DB giả lập: đáp án để chấm điểm
data/condition_model.json       -- hệ số pin/ngoại hình do `calibrate --save` ghi (tùy chọn)
```

Khóa sản phẩm iPhone: `iphone-<đời>-<biến thể>-<dung lượng>gb|<grey|vna|lock|unk>[|new|repaired|bypass|tra-truoc|thay-linh-kien|loi]`.
Từ khóa chung: `kw:<tên từ khóa>~<mã danh mục>[~<năm>][~<cấu hình>]|<new|used|na>[|loi|tra-truoc|repaired|…]`.
Thống kê nhóm đếm mỗi tin 1 lần (`list_id IN (SELECT … FROM listing_keys WHERE key = ?)`).

| Trường Chợ Tốt | Mã → ý nghĩa (học từ tin thật) | Độ tin cậy |
|---|---|---|
| `mobile_capacity` | 5 = 64GB, 6 = 128GB, 7 = 256GB, 9 = 512GB, **10 = 1TB, 11 = 2TB** (thêm 26/10/2026) | 98% khớp tiêu đề; mã 10: 20/20 tin có "1TB"; mã 11: 1 tin "2T" |
| `elt_origin` | 1 = Việt Nam (VN/A); 8 = Mỹ; mã khác = nước ngoài → "xách tay" | mã 1: 45/50 tin có ghi nguồn gốc ở tiêu đề là VN/A |
| `elt_lock` | 1 = Quốc tế, 2 = Lock | mã 2: 40/43 tin có chữ "lock" |
| `elt_condition` | 1 = mới, 2 = đã dùng (chưa sửa), 3 = đã qua sửa chữa | nhãn lấy từ API chi tiết tin |
| `body` | Mô tả đầy đủ (giống API chi tiết) | 3/3 tin so khớp |

Cách người bán ghi tình trạng (học từ 100 mô tả thật, có test cho từng mẫu): *"Pin 86%"*, *"pin zin 85"*,
*"pin còn 72%"*, *"pin 7x"*, *"pin new 100%"*, *"thay pin"*; *"Ngoại hình 95%"*, *"hình thức máy 95%"*,
*"đẹp 99"*, *"keng 99%"*, *"trầy xước"*, *"cấn móp"*. "% trơn" trong tiêu đề: dưới 95% là pin
(*"Xanh 72%"*), từ 95% là ngoại hình (*"256GB 98%"*). Ghi định tính kiểu *"pin trâu"*, *"pin tốt"* → coi như không ghi.

---

## 6. Thuật toán, tham số và kết quả đo

### 6.1. Pin và ngoại hình ảnh hưởng giá bao nhiêu (dữ liệu thật)

Hồi quy trên ~350 tin máy cũ zin (log giá so với trung vị nhóm), 2 lần nạp độc lập cho cùng kết quả:

| Yếu tố | Ảnh hưởng tới giá rao (khoảng tin cậy 95%) |
|---|---|
| Mỗi 1% pin (pin zin, dưới 100%) | **−0,31% ± 0,36%** → không phát hiện ảnh hưởng |
| Pin ghi 100% (đa số pin đã thay) | +2,7% ± 3,4% |
| Mỗi 1% ngoại hình | **+0,58% ± 0,37%** |
| Tin của shop so với cá nhân | −0,4% ± 2,4% |
| Phần độ phân tán giá được giải thích (R²) | **4,6%** |

Theo nhóm pin, giá so với trung vị: dưới 80% −0,6% · 80–84% 0% · 85–89% 0% · 90–94% −3% · 95–100% +2,1%.

**Kết luận:** người bán trên Chợ Tốt **không hạ giá rao theo % pin**; ngoại hình có tác động nhỏ.
Vì vậy quy đổi giá theo tình trạng máy (bật mặc định, hệ số học từ dữ liệu) chỉ thay đổi ít: trên dữ
liệu thật deal **22 → 18**; trong backtest gần như trung tính. Giả thuyết "báo nhầm do máy pin yếu"
**không đúng với dữ liệu**. Phần lớn báo nhầm đến từ máy có vấn đề ghi trong mô tả, và mục 4 đã xử lý.

Thông tin pin/ngoại hình vẫn hữu ích theo hai cách:
- **Hiện trong cảnh báo và dashboard** để quyết định nhanh.
- **Tùy chọn của người mua**: `ALERT_MIN_BATTERY=80` (hoặc `ALERT_MIN_COSMETIC=93`) bỏ deal của
  máy pin dưới 80%. Đây là lựa chọn cá nhân (chi phí thay pin), không phải thị trường định giá.

### 6.2. Backtest

Backtest 30 ngày, 1.907 tin giả lập. Giá nền, tỷ lệ VN/A/lock/shop, tỷ lệ và mức giá của tin thay
linh kiện/lỗi/bypass/đưa trước, phân bố pin/ngoại hình và độ phân tán (**10,1%** so với thật
**9,0%**) đều hiệu chỉnh theo dữ liệu thật. Dữ liệu được phát lại qua đúng pipeline chạy thật
(`python main.py simulate`; báo cáo đầy đủ trong `reports/`):

| Phương án | Chuẩn hóa | Báo/ngày | Deal đúng | Deal bắt được | "Lừa đảo" đúng | Báo nhầm (23 ngày) |
|---|---|---|---|---|---|---|
| Thiết kế gốc: chỉ đọc tiêu đề, ngưỡng cố định 15% | 86% | 9,2 | 35,6% | 93,4% | 53,8% | 127 |
| + mã cấu trúc Chợ Tốt | 96% | 9,8 | 33,9% | 90,6% | 56,4% | 137 |
| + đọc mô tả mọi tin | 96% | 4,1 | 71,9% | 93,9% | 86,7% | 22 |
| + ngưỡng thích ứng Z = 2 | 96% | 3,6 | 79,2% | 85,7% | 86,7% | 15 |
| **+ quy đổi pin/ngoại hình (bản hiện tại)** | **96%** | **3,6** | **77,4%** | **83,7%** | **89,7%** | **15** |

Dò hệ số `DEAL_Z` (bản hiện tại):

| DEAL_Z | Báo/ngày | Deal đúng | Deal bắt được | Tin thật sự rẻ / tổng báo |
|---|---|---|---|---|
| 0 (cố định 15%) | 4,1 | 70,3% | 91,8% | 80% |
| 1,5 | 3,9 | 75,0% | 91,8% | 83% |
| **2 (mặc định)** | **3,6** | **77,4%** | **83,7%** | **86%** |
| 2,5 | 3,3 | 82,2% | 75,5% | 89% |
| 3 | 3,0 | 84,2% | 65,3% | 91% |

Khuyến nghị:
- **Giữ Z = 2**; muốn ít báo hơn nữa thì 2,5. Cảnh báo "lừa đảo" giữ ngưỡng cố định 40%.
- Báo nhầm còn lại là tin máy zin có giá thấp ngẫu nhiên (người bán cần tiền, định giá sai…),
  không có dấu hiệu nào trong tin. Muốn giảm tiếp cần dữ liệu mới: tốc độ bán (mục 8).
- **Trung vị 30 ngày cao hơn giá hiện tại ~2%** (máy cũ mất giá ~3,6%/tháng). Cân nhắc cửa sổ 14 ngày
  cho đời máy mới khi đã đủ dữ liệu.

> Số liệu backtest là **ước lượng**. Precision thật đo bằng `python main.py audit` rồi mở từng link ghi
> Đúng/Sai (file `reports/audit_*.md` có sẵn cột), sau đó chỉnh `DEAL_Z`.

### 6.3. Tốc độ bán: tin rẻ có bán nhanh hơn? pin yếu có bán chậm hơn?

**Vì sao không dùng được `last_seen` có sẵn:** kết quả tìm kiếm xếp theo tin mới đăng/đẩy, nên tin rơi
khỏi trang đầu chỉ vì có tin mới hơn, không phải đã bán. Phải **kiểm tra lại từng tin**: API chi tiết
trả HTTP 404 khi tin không còn, `status: "active"` khi còn (đã kiểm chứng 26/10/2026).

**Cách thu thập:** mỗi vòng quét kiểm tra thêm 3 tin cũ (~2.160 request/ngày), mỗi tin tối đa 6 giờ/lần,
trong 21 ngày từ lúc thấy, ưu tiên tin cá nhân. Tin xuất hiện lại trong kết quả tìm kiếm = còn đăng
(không tốn request). Thời điểm gỡ thật nằm giữa lần cuối thấy còn và lần phát hiện mất → lấy điểm giữa.

**Cách phân tích** (`speed.py`): dữ liệu bị cắt hai đầu — nhiều tin đăng trước khi bắt đầu theo dõi
(có tin đăng từ 2 tháng trước, shop đẩy liên tục), nhiều tin còn khi kết thúc. Dùng Kaplan–Meier có
thời điểm vào theo dõi và hồi quy Poisson theo khoảng tuổi tin (0–1, 1–3, 3–7, 7–14, 14–30, >30 ngày;
tương đương mô hình Cox), kiểm soát cùng lúc: mức giá so với trung vị nhóm, pin, ngoại hình, shop/cá nhân.

**Kiểm chứng trên giả lập** (`main.py speedsim`, đáp án là giả định chỉ để thử phương pháp):

| Đặc điểm | Đáp án giả định | Đo được (khoảng tin cậy 95%) |
|---|---|---|
| Rẻ hơn trung vị ≥10% | biến mất nhanh ×2 | ×1,74 (1,43–2,11) — tìm lại đúng |
| Tin của shop | chậm ×0,25 | ×0,27 (0,23–0,32) — tìm lại đúng |
| Pin < 85% | chậm ×0,7 | ×0,81 (0,56–1,17) — đúng hướng, **chưa đủ dữ liệu** để khẳng định |
| Đắt hơn trung vị ≥10% | chậm ×0,6 | ×0,82 (0,63–1,06) — bị kéo về gần ×1 |

Hai điều rút ra: (1) tác động đo được **nhỏ hơn thật** vì "rẻ/đắt" so với trung vị nhóm chỉ là ước lượng
của giá đúng; (2) hiệu ứng pin cần nhiều tin pin yếu biến mất (~90) mới kết luận được.

**Tình trạng trên dữ liệu thật:** cơ chế đã chạy với API thật (40/40 tin kiểm tra còn đăng; mới theo dõi
vài giờ nên chưa có tin nào biến mất). Lưu lượng thật 5 từ khóa ~126 tin/ngày (cá nhân ~41), trong máy
zin ~15% rẻ hơn ≥10%, ~6,6% ghi pin < 85% → cần chạy liên tục **~1–2 tuần** để kết luận về giá,
**~4 tuần** về pin. Muốn nhanh hơn: thêm dòng máy vào `watchlist.json` (hiệu ứng pin chắc tương tự giữa các đời).
Lưu ý: biến mất ≠ chắc chắn đã bán; kết luận nên dựa vào tin cá nhân.

### 6.4. Từ khóa chung: dữ liệu cho mọi sản phẩm

**Thăm dò API thật (26/10/2026)** với "macbook air m2", "honda vision", "máy lạnh daikin", "sony a7 iii",
"ipad pro m4", "xe sh 150i", không lọc danh mục: Chợ Tốt đã trả **đúng từ khóa** (100% tiêu đề chứa đủ các
chữ, trừ 4 tin phụ tùng thiếu chữ "xe") và kèm `category`/`category_name`. Lẫn lộn thật sự nằm ở **danh mục**
(phụ tùng trong kết quả "sh 150i", ốp/phụ kiện trong "ipad pro m4") và **biến thể** ("iphone 15 pro" ra cả Pro Max).
Mã đã kiểm chứng: 5010 Điện thoại, 5030 Laptop, 5040 Máy tính bảng, 5050 Máy ảnh, 5060 Phụ kiện, 2020 Xe máy,
2030 Phụ tùng xe, 9060 Máy lạnh. `condition_ad`: 1 = Đã sử dụng, 2 = Mới (ngược chiều với `elt_condition`
của đồ điện tử: 1 = mới); xe có `regdate` (năm) và `mileage_v2` (km).

**Chia nhóm** (`normalize_keyword`): danh mục + mới/đã dùng (mã Chợ Tốt, thiếu mã thì đọc "nguyên seal",
"mới 100%"…), cộng:

| Tách thêm | Mặc định | Đo trên tin thật |
|---|---|---|
| Năm | Khi Chợ Tốt có `regdate` (xe) | Honda Vision 100 tin: trung vị 2011 ~7,2 tr → 2016 ~16 tr → 2023 ~25,3 tr; phân tán 2023: 5%, 2022: 5%, 2016: 7%, nhưng 2019: 21%, 2013: 26% (lẫn phiên bản, tình trạng xe) |
| Cấu hình GB/TB trong tiêu đề | Danh mục 5010, 5030, 5040 | MacBook Air M2 97 tin: gộp 18,4% (ngưỡng deal 37%) → 16/256: 9,4%, 8/256: 10,0%, 16/512: 6,9% |
| Công suất HP (máy lạnh) | **Không** áp dụng | Daikin 48 tin: gộp 20%; tách HP vẫn 18% (1.5HP), 24% (2HP) — lẫn inverter/mono, hàng Nhật/VN → không đáng thêm luật |

Dấu hiệu chỉ đọc ở **tiêu đề** (mô tả shop hay có "bảo hành lỗi 1 đổi 1", "hỗ trợ trả góp"): lỗi/hư/bể/vỡ/
dính iCloud/xác → `|loi`; "trả trước/đưa trước" → `|tra-truoc`; không báo deal. Tùy chọn `phone_rules` dùng
toàn bộ luật đọc mô tả của iPhone cho điện thoại/máy tính bảng khác. Quy đổi pin/ngoại hình **chỉ cho iPhone**
(hệ số học trên iPhone, chưa có dữ liệu để học cho loại khác).

**Nhóm giá quá phân tán:** ngưỡng deal = max(15%, 2σ) có thể vượt ngưỡng lừa đảo 40% (xe gộp nhiều đời, máy lạnh).
Trước đây mọi tin rẻ hơn 40% trong nhóm như vậy bị gắn "nghi lừa đảo" dù chỉ là đời cũ. Nay nghi lừa đảo khi
rẻ hơn **max(40%, ngưỡng deal của nhóm)**; deal không thể xảy ra ở nhóm này, dashboard ghi "giá quá phân tán".
Nhóm iPhone có ngưỡng < 40% không đổi gì — backtest giả lập cho **đúng các số cũ** (deal 77,4% / 83,7%,
lừa đảo 89,7% / 100%). Trên dữ liệu thật chỉ 1 nhóm iPhone bị ảnh hưởng (14 Pro Max 256GB chưa rõ nguồn gốc, phân tán 27%).

**Từ khóa chồng nhau** ("macbook air" và "macbook air m2", "iphone 15" và "iphone 15 pro max"): bảng
`listing_keys` ghi mọi (tin, nhóm, từ khóa) nên dữ liệu và thống kê của từng từ khóa đủ tin; tin vẫn lưu 1 lần,
cảnh báo chỉ gửi lần đầu thấy tin.

**Vận hành:** collector đọc lại `watchlist.json` mỗi vòng (file ghi dở/lỗi thì giữ danh sách cũ); từ khóa mới
nạp `BASELINE_PAGES` trang không báo; `every_minutes` cho từ khóa chỉ để thu dữ liệu (30–60 phút: ~24–48
request/ngày thay vì 720). DB bản cũ tự nâng cấp khi mở (kể cả khi bản cũ còn chạy song song: tin bản cũ ghi
được bổ sung vào `listing_keys` ở lần mở sau) và tự gắn từ khóa cho dữ liệu iPhone cũ theo đời máy.

### 6.5. Tin bỏ qua và nhịp quét chủ động

**Tin bỏ qua.** Trước đây `process()` trả "skip" rồi quên tin: không có cách kiểm tra bộ lọc loại nhầm hay đúng.
Nay mọi tin bị loại được ghi vào bảng `skipped(list_id, watch, reason, detail, title, price, region, seller,
category, url, first_seen, last_seen)` kèm **mã lý do** (`SKIP_LABEL` trong `normalizer.py`): thu mua/cần mua, linh kiện,
máy hỏng ở tiêu đề, thiếu chữ từ khóa, chữ loại trừ, thiếu đời/dung lượng (iPhone), giá ngoài khoảng, giá 0,
không phải tin bán. `skip_reason()` chạy lại đúng thứ tự kiểm tra của `normalize_watch` để biết tin bị loại ở bước nào.
Khóa chính (tin, từ khóa): thấy lại thì chỉ cập nhật `last_seen`; tin hợp lệ trở lại (giá sửa, đổi khoảng giá) thì
tự bị xóa khỏi bảng; dọn tin quá `SKIP_KEEP_DAYS` (30 ngày) mỗi vòng quét. Không lưu mô tả. Hiển thị: tab **Tin bỏ qua**,
sheet **Tin bỏ qua** trong Excel, CSV (`/export?what=skipped`), `/api/skipped`. Sim backtest 30 ngày cho 175 tin bỏ qua
(hỏng 58, thiếu dung lượng 52, ngoài giá 35, thu mua 19, không phải tin bán 11) và **không đổi** chất lượng cảnh báo.

Sửa kèm: chữ **loại trừ** (`exclude`) trước đây chỉ áp dụng cho từ khóa chung; nay áp dụng cả từ khóa dùng luật iPhone
(vd "iphone 15 pro" loại trừ "max").

**Nhịp quét.** `every_minutes` ∈ {5, 10, 15, 20, 30, 45, 60} (`config.SCAN_CHOICES`, kiểm tra ở form, `--every` và
`--default-every`; giá trị lạ trong `watchlist.json` vẫn được collector tôn trọng). Thứ tự ưu tiên: nhịp riêng của từ khóa
→ nhịp mặc định chung (bảng `settings`, khóa `default_every_minutes`, đặt trên trang Từ khóa) → mỗi vòng quét.
Collector vẫn thức dậy mỗi `POLL_SECONDS`, nên `_due()` cho phép quét sớm nửa vòng: khoảng cách thực tế giữa 2 lần quét lệch
tối đa ±1 vòng quanh nhịp chọn (trung bình đúng). Từ khóa mới luôn được nạp ngay. Mỗi lần quét ghi `scanned:<tên>` vào
bảng `status` để dashboard hiện "quét gần nhất". Tải: 288 request/ngày/từ khóa ở 5 phút, 24 ở 60 phút, ~680 ở mỗi vòng.

### 6.6. Dung lượng iPhone: đọc từ đâu

Tab Tin bỏ qua cho thấy lý do lớn nhất là **thiếu dung lượng**: 58/721 tin iPhone thật (8%) không so giá được. Giả thuyết
"mô tả sẽ ghi dung lượng" **gần như sai**: trong 58 tin đó, 0 tin ghi GB/TB trong mô tả, chỉ 1 tin ghi số trần
("14 Promax 256 lla") và 1 tin có số 512 là *địa chỉ cửa hàng*. Nguồn dung lượng nay theo thứ tự tin cậy:

| # | Nguồn | Ghi chú đo trên 721 tin thật (26/10/2026) |
|---|---|---|
| 1 | Tiêu đề ("256GB", "1TB", **"2T"**) | `_storage()` nay hiểu 2TB; trước đây "2T" bị bỏ qua |
| 2 | Mã `mobile_capacity` | bổ sung **mã 10 = 1TB, mã 11 = 2TB** (trước đây tin chỉ có mã 10/11 bị loại) |
| 3 | Mô tả (`body_storage`) | chỉ nhận khi mô tả có **đúng 1** dung lượng (đơn vị GB/TB, hoặc số trần đứng ngay sau tên máy) **và** không còn số 64/128/256/512 nào khác đứng riêng; kết quả lưu vào `attrs["storage"]` (không lưu mô tả) |

Độ chính xác của luật mô tả: **530/531 = 99,8%** trên 664 tin đã biết dung lượng (2 mẫu sai khi chưa có điều kiện "không có số khác" là
mô tả liệt kê nhiều bản: "128 và 256gb", "256-512-1Tb"). Số trần *không* kèm tên máy bị loại vì chỉ đúng 47/55 (địa chỉ, giá…).

**Kết quả thật:** lấy lại **2/57** tin thiếu dung lượng (1 tin "2T" nhờ sửa tiêu đề + mã 11, 1 tin nhờ mô tả); trên bản sao DB thật,
tin "iPhone 14 Pro Max Tím" tự rời tab Tin bỏ qua sau 1 vòng quét. **55 tin còn lại không thể gán nhóm**: 44 là tin của shop, 40
không có cờ lỗi nào, giá trung vị 0,98 so với mặt bằng — tức dữ liệu thị trường bình thường mà người bán không ghi dung lượng ở đâu cả.
Hướng xử lý nếu cần (chưa làm): đưa nhóm "chưa rõ dung lượng" vào dữ liệu/Excel nhưng không so giá và không báo deal.

---

## 7. Vận hành, an toàn và tuân thủ

**Nhịp quét và xử lý bị chặn**
- 5 từ khóa × 1 request / 120 giây ≈ 3.600 request/ngày, cộng đo tốc độ bán 3 tin/vòng ≈ 2.160 request/ngày
  (tắt bằng `TRACK_PER_CYCLE=0`); mỗi request cách nhau ≥ 2 giây. Đọc mô tả không tốn thêm request.
- Gặp 403/429: giãn nhịp lũy thừa (2, 4, 8 … tối đa 15 phút); **5 lần liên tiếp thì dừng hẳn**,
  gửi Telegram báo dừng, systemd không tự bật lại. Không dùng proxy xoay, không giải CAPTCHA.
- **Không lưu** tên, số điện thoại, avatar người bán, cũng **không lưu nguyên văn mô tả**.
  Hệ quả: khi sửa luật đọc mô tả, phải nạp lại (`seed` trên DB mới); luật chỉ đọc tiêu đề/mã thì
  `renormalize` là đủ.
- Hãy tự đọc điều khoản sử dụng của Chợ Tốt; dùng dữ liệu cho mục đích cá nhân, không đăng lại tin.

**Bảo mật trên VPS**: web chỉ nghe `127.0.0.1`, Nginx đứng trước (10 request/giây/IP); dashboard
**bắt buộc** đăng nhập (script cài tự sinh mật khẩu); `.env` quyền 600; `ufw` chỉ mở SSH + HTTP/HTTPS;
dịch vụ chạy bằng user hệ thống không đăng nhập được; có tên miền thì bật HTTPS bằng certbot.

**Giám sát và sao lưu**: `GET /healthz` trả 503 khi collector dừng → gắn UptimeRobot (miễn phí);
sao lưu DB mỗi ngày 3 giờ sáng, giữ 14 bản; log `journalctl -u deal-finder-worker -f`.

**Cấu hình VPS**: 1 vCPU, 1 GB RAM, 20 GB SSD, Ubuntu 24.04, đặt tại Việt Nam. Worker + web dùng
~70 MB RAM (đo thực tế). Giá tham khảo các nhà cung cấp trong nước khoảng 100.000–250.000đ/tháng —
hãy kiểm tra giá hiện hành khi mua.

---

## 8. Lộ trình mở rộng (theo thứ tự đáng làm)

1. **Chạy đo tốc độ bán 2–4 tuần** (đã xây xong, mục 6.3) rồi dùng kết quả: nếu tin rẻ biến mất nhanh
   rõ rệt thì cảnh báo cần đến tay sớm hơn (giảm `POLL_SECONDS` cho dòng máy hot); nếu pin yếu bán chậm
   thì đưa pin vào ngưỡng deal dù giá rao không phản ánh.
2. **Vòng phản hồi**: nút Đúng/Sai trên dashboard (hoặc nút bấm trong tin Telegram) → tự chỉnh
   `DEAL_Z` theo precision thật.
3. **Theo dõi giảm giá của tin cũ**: tin đã thấy mà hạ giá ≥ 10% cũng là deal (thêm bảng lịch sử giá).
4. ~~Thêm dòng sản phẩm~~ — đã có từ khóa chung (mục 6.4). Bước tiếp: dùng mã cấu trúc theo danh mục
   (`pc_ram`, `pc_drive_capacity`, `airconcapacity`, `motorbikecapacity`…) khi tiêu đề không ghi cấu hình —
   cần bảng mã → nhãn, học từ tin thật như đã làm với `mobile_capacity`.
5. **Nhiều người dùng**: bot Telegram nhận lệnh `/watch iphone 15 pro max 256`, mỗi người một watchlist.
6. **Quy mô lớn**: PostgreSQL + nhiều worker — chỉ khi vượt ~1 triệu tin.

## 9. Rủi ro còn lại

- API Chợ Tốt **không chính thức**, có thể đổi bất cứ lúc nào → chạy `probe` định kỳ, `/healthz` báo khi worker chết.
- Bộ dấu hiệu trong mô tả dựa trên cách viết hiện tại của người bán; cách viết đổi thì bổ sung từ
  khóa trong `normalizer.py` (có test với câu thật), rồi nạp lại.
- "Màn OLED" trong mô tả bị coi là màn thay. Kiểm tra trên 100 mô tả thật thì đa số đúng, nhưng
  shop tả thông số máy theo kiểu này sẽ bị gắn cờ nhầm (mất deal, không gây báo nhầm).
- Phân biệt xách tay/VN/A/lock và tình trạng máy dựa vào người bán khai báo.
- Cảnh báo "nghi lừa đảo" không phải kết luận: luôn giao dịch trực tiếp, kiểm tra máy tại chỗ,
  không đặt cọc chuyển khoản.
