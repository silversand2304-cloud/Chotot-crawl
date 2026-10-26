# Hướng dẫn chạy chi tiết — Deal Finder

> **Quy tắc số 1:** mọi lệnh đều chạy **bên trong thư mục `deal-finder`**
> (`...\Desktop\CLAUDE CODE\Crawl DATA ChoTot\deal-finder`). Các file `.bat` tự chuyển vào đúng thư mục,
> nên cách dễ nhất là **double-click file `.bat`**.

Mục lục: [1. Cài đặt](#1-cài-đặt-trên-windows-1-lần) · [2. Demo giả lập](#2-demo-1--dữ-liệu-giả-lập--chấm-điểm-offline) ·
[3. Demo trọn vòng](#3-demo-2--trọn-vòng-với-chợ-tốt-giả-offline) · [4. Chạy thật](#4-chạy-thật-trên-chợ-tốt) ·
[4b. Tốc độ bán](#4b-đo-tốc-độ-bán-tin-rẻ-có-bán-nhanh-hơn-pin-yếu-có-bán-chậm-hơn) ·
[4c. Dữ liệu theo từ khóa](#4c-dữ-liệu-theo-từ-khóa-cho-mọi-sản-phẩm) ·
[Nhịp quét 5–60 phút](#nhịp-quét-chủ-động-5--10--15--20--30--45--60-phút) ·
[4d. Tin bỏ qua](#4d-tin-bỏ-qua-tin-bị-loại-kèm-lý-do) ·
[5. Telegram](#5-thiết-lập-telegram) · [6. Tùy chỉnh](#6-tùy-chỉnh) · [7. Lên VPS](#7-đưa-lên-vps-ubuntu-chạy-247) ·
[8. Kịch bản test](#8-kịch-bản-test-và-tiêu-chí-đạt) · [9. Sự cố](#9-xử-lý-sự-cố) · [10. Lệnh](#10-bảng-lệnh)

---

## 0. Trong thư mục có gì

```
deal-finder/
├── 1_CAI_DAT.bat               ← chạy đầu tiên (1 lần)
├── 2_DEMO_GIA_LAP.bat          ← demo offline: 30 ngày dữ liệu giả lập + chấm điểm + dashboard
├── 3_DEMO_TRON_VONG_MOCK.bat   ← demo offline: "Chợ Tốt giả" sinh tin liên tục → cảnh báo trực tiếp
├── 4_CHAY_THAT_CHOTOT.bat      ← chạy thật trên Chợ Tốt + dashboard
├── 5_DONG_GOI_VPS.bat          ← đóng gói để chép lên VPS
├── 6_TIM_THEO_TU_KHOA.bat      ← gõ 1 từ khóa bất kỳ → lấy dữ liệu ngay + mở file Excel
├── HUONG_DAN.md                ← file này
├── THIET_KE.md                 ← tư vấn thiết kế, số liệu backtest, kiến trúc
├── watchlist.json              ← danh sách từ khóa theo dõi (sửa trên dashboard, hoặc sửa file)
├── .env.example                ← mẫu cấu hình (Telegram, mật khẩu dashboard, nhịp quét)
├── main.py                     ← tất cả các lệnh
├── config.py  db.py  collector.py  normalizer.py  analyzer.py  notifier.py  pipeline.py
├── speed.py                    ← phân tích tốc độ bán (tin còn đăng bao lâu)
├── export.py                   ← thống kê nhóm + xuất Excel/CSV theo từ khóa
├── simulator.py  mock_chotot.py   ← giả lập thị trường + máy chủ Chợ Tốt giả
├── web/                        ← dashboard (FastAPI)
├── tests/                      ← 144 test tự động
├── deploy/                     ← cài lên VPS: script Ubuntu, systemd, Nginx, Docker
├── data/                       ← (tự tạo) deals.db = dữ liệu thật, sim.db = giả lập
├── exports/                    ← (tự tạo) file Excel/CSV xuất theo từ khóa
└── reports/                    ← (tự tạo) báo cáo backtest .md
```

---

## 1. Cài đặt trên Windows (1 lần)

**Yêu cầu:** Python 3.11 trở lên (máy anh/chị đang có 3.14 — dùng được). Nếu chưa có: tải ở
python.org, khi cài **tick "Add python.exe to PATH"**.

**Cách nhanh:** double-click **`1_CAI_DAT.bat`**. Cửa sổ sẽ: tạo môi trường `.venv`, cài thư viện,
tạo file `.env`, rồi chạy test. Kết quả đúng là dòng cuối có **`65 passed`**.

**Cách gõ lệnh** (PowerShell):

```bash
cd "$HOME\Desktop\CLAUDE CODE\Crawl DATA ChoTot\deal-finder"
```

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python.exe -m pytest -q
```

> Ở các mục dưới, `python` nghĩa là `.venv\Scripts\python.exe` (hoặc kích hoạt môi trường trước bằng
> `.venv\Scripts\Activate.ps1`, khi đó gõ `python` là đủ).

---

## 2. Demo 1 — dữ liệu giả lập + chấm điểm (offline)

Mục đích: kiểm tra bộ phân tích trên dữ liệu **có đáp án**, không cần mạng.

Double-click **`2_DEMO_GIA_LAP.bat`** — hoặc:

```bash
.venv\Scripts\python.exe main.py simulate --days 30
```

```bash
.venv\Scripts\python.exe main.py web --db data\sim.db --port 8001
```

Mở **http://127.0.0.1:8001**. Huy hiệu góc phải ghi **GIẢ LẬP (backtest)**.

Điều xảy ra bên trong:
1. Sinh 30 ngày tin đăng iPhone (~1.900 tin) **hiệu chỉnh theo tin thật trên Chợ Tốt** (26/10/2026):
   giá nền (15 Pro Max 256GB ~15,8 tr…), tỷ lệ VN/A/lock/shop, độ phân tán giá máy zin (~9–10%),
   phân bố pin/ngoại hình; có tin thường, deal, tin mồi lừa đảo, máy lỗi, "thu mua", phụ kiện, gõ nhầm
   giá, và các tin **trông bình thường nhưng mô tả ghi đã thay màn / lỗi / bypass / đưa trước**
   (~30% số tin — đúng tỷ lệ đo được ngoài đời).
2. Phát lại từng tin theo thời gian **qua đúng pipeline chạy thật** rồi so với đáp án.
3. Chạy lại 5 phương án (thiết kế gốc → bản hiện tại) và 6 giá trị `DEAL_Z` trên cùng bộ dữ liệu.
4. In báo cáo và lưu vào `reports\backtest_*.md`.

Kết quả mong đợi (seed 42), mất ~40 giây:

| | Thiết kế gốc | Bản hiện tại |
|---|---|---|
| Cảnh báo/ngày | 9,2 | 3,6 |
| Deal đúng (precision) | 36% | 77% |
| "Lừa đảo" đúng | 54% | 90% |
| Tin rác / tin có vấn đề ẩn lọt thành cảnh báo | nhiều | 0 |

Trên dashboard có cột **"Đáp án"** để đối chiếu từng cảnh báo. Thử: `--days 60`, `--seed 7`, hoặc
đặt `DEAL_Z=2.5` trong `.env` rồi chạy lại.

---

## 3. Demo 2 — trọn vòng với "Chợ Tốt giả" (offline)

Mục đích: xem hệ thống **chạy như thật**: quét → phát hiện → cảnh báo → dashboard cập nhật.

Double-click **`3_DEMO_TRON_VONG_MOCK.bat`** — hoặc:

```bash
.venv\Scripts\python.exe main.py mockdemo --port 8002
```

- Một máy chủ giả lập API Chợ Tốt chạy ở `127.0.0.1:8900` (cùng đường dẫn, cùng dạng JSON), có 30 ngày
  lịch sử và **cứ 4 giây sinh 1 tin mới** (tỷ lệ deal/lừa đảo được tăng lên để demo nhanh).
- Collector thật quét mỗi ~15 giây. Sau **vài phút** sẽ thấy khối cảnh báo trong cửa sổ:

```
[CONSOLE]
🔥 DEAL -23%
iPhone 15 Pro 128GB (xách tay, shop)
Tình trạng: pin 87% · ngoại hình 98%
Giá: 10.100.000đ | Trung vị: 13.100.000đ (n=9)
```

- Dashboard **http://127.0.0.1:8002** (tự làm mới mỗi 60 giây) hiện huy hiệu **MOCK**, trạng thái
  "Đang quét", số tin mới và cảnh báo của phiên.
- Thử cơ chế bị chặn: `main.py mockdemo --block-every 3` (cứ 3 request trả lỗi 429) → log hiện
  "Bị chặn… nghỉ …s", dashboard hiện lỗi màu đỏ; 5 lần liên tiếp thì collector dừng hẳn.

Mỗi lần chạy lại, `data\mockdemo.db` được xóa và làm mới.

---

## 4. Chạy thật trên Chợ Tốt

Double-click **`4_CHAY_THAT_CHOTOT.bat`** — hoặc từng bước:

**Bước 1 — thăm dò API** (2 request):

```bash
.venv\Scripts\python.exe main.py probe
```

Đúng là: `[OK ] /v1/public/ad-listing: 50 tin` kèm vài tin và khóa sản phẩm. Dòng `[ERR] /v2/...404`
là bình thường (đường dẫn cũ của thiết kế gốc, giữ lại để đối chiếu).

**Bước 2 — chạy collector + dashboard trong một cửa sổ:**

```bash
.venv\Scripts\python.exe main.py all --port 8000
```

- Lần đầu: nạp baseline 3 trang × 5 từ khóa (~30 giây, ~600 tin hợp lệ).
- Sau đó quét mỗi **120 giây**; tin mới rẻ bất thường → cảnh báo (màn hình hoặc Telegram).
- Dashboard: **http://127.0.0.1:8000** — huy hiệu **LIVE · gateway.chotot.com**, link "Mở tin ↗" dẫn
  thẳng tới tin trên chotot.com.
- Đóng cửa sổ (hoặc Ctrl+C) để dừng. Dữ liệu giữ trong `data\deals.db`, lần sau chạy tiếp.

**Lưu ý những ngày đầu:** cột "Xu hướng", "Tin mới 24 giờ" và biểu đồ theo ngày chỉ có ý nghĩa sau
≥ 7 ngày chạy liên tục (baseline được ghi nhận cùng một thời điểm). Cảnh báo chỉ bật với nhóm đủ ≥ 8 tin.
Cột **"Báo deal khi rẻ hơn"** là ngưỡng riêng của từng nhóm: nhóm giá đồng đều (VD 17 Pro Max VN/A)
chỉ cần rẻ hơn 15%, nhóm lộn xộn (VD "chưa rõ nguồn gốc") cần rẻ hơn 30–40%.

**Bước 3 — kiểm chứng ngay trên dữ liệu thật** (không cần chờ tin mới, không gọi mạng):

```bash
.venv\Scripts\python.exe main.py audit
```

Lệnh liệt kê mọi tin **sẽ bị báo nếu vừa đăng** (kèm pin, ngoại hình, giá quy đổi) và ghi
`reports\audit_*.md` có link + cột "Đúng?". Mở từng link, ghi Đúng/Sai → biết precision thật để chỉnh
`DEAL_Z`. Kết quả ngày 26/10/2026 trên 649 tin: đọc mô tả loại 190 tin (thay linh kiện 119, lỗi 32,
bypass 21, đưa trước 18); còn **18 deal + 3 nghi lừa đảo** (so giá thô thì 22 deal).

**Bước 4 (tùy chọn) — học lại hệ số pin/ngoại hình** khi đã có nhiều dữ liệu hơn:

```bash
.venv\Scripts\python.exe main.py calibrate
```

In bảng "giá so với trung vị nhóm" theo từng mức pin/ngoại hình và hệ số hồi quy. Thấy hợp lý thì
chạy lại với `--save` để dùng (ghi `data\condition_model.json`). Ngày 26/10/2026: % pin không ảnh hưởng
giá rao; ngoại hình +0,6% giá mỗi 1% (xem [THIET_KE.md](THIET_KE.md) mục 6.1).

Các lệnh riêng lẻ (nếu muốn tách): `seed` (chỉ nạp baseline), `run` (chỉ collector),
`run --cycles 2` (quét 2 vòng rồi dừng), `report` (bảng trung vị ra màn hình), `web` (chỉ dashboard),
`renormalize` (áp luật chuẩn hóa mới cho dữ liệu cũ, sau khi sửa `normalizer.py`).

---

## 4b. Đo tốc độ bán (tin rẻ có bán nhanh hơn? pin yếu có bán chậm hơn?)

**Cách làm:** khi chạy `run` / `all` / trên VPS, sau mỗi vòng quét bot kiểm tra lại **3 tin cũ**
(mặc định) xem còn đăng không — tin đã gỡ thì API trả 404. Mỗi tin được kiểm tra tối đa 6 giờ/lần
trong 21 ngày kể từ lúc thấy, ưu tiên tin cá nhân. Tin xuất hiện lại trong kết quả tìm kiếm cũng tính
là "còn" mà không tốn request. Không cần làm gì thêm, chỉ cần **để bot chạy liên tục**.

**Cần chạy bao lâu** (ước tính từ lưu lượng thật: 5 từ khóa ~126 tin/ngày):

| Câu hỏi | Cần | Thời gian chạy liên tục |
|---|---|---|
| Tin rẻ hơn ≥10% có biến mất nhanh hơn? | ~60 tin rẻ biến mất | **~1–2 tuần** |
| Tin pin < 85% có biến mất chậm hơn? | ~90 tin pin yếu biến mất | **~4 tuần** (thêm dòng máy vào `watchlist.json` để nhanh hơn) |

**Xem kết quả** bất cứ lúc nào: trang **Tốc độ bán** trên dashboard, hoặc:

```bash
.venv\Scripts\python.exe main.py speed
```

Báo cáo (lưu `reports\speed_*.md`) có bảng **"Tốc độ biến mất so với nhóm mốc"**: ×1,7 nghĩa là biến mất
nhanh gấp 1,7 lần nhóm mốc, kèm khoảng tin cậy 95% và kết luận tự động ("biến mất nhanh hơn ×…",
"chưa thấy khác biệt rõ", hoặc "chưa đủ dữ liệu"). Các con số đã được tách khỏi ảnh hưởng của tuổi tin
và các đặc điểm khác (VD tin rẻ thường là tin cá nhân — đã tính riêng). Bảng thứ hai cho tỷ lệ tin
còn đăng sau 1/3/7/14 ngày theo từng nhóm.

**Lưu ý khi đọc:**
- Biến mất ≠ chắc chắn đã bán (người bán có thể xóa tin, tin hết hạn, bị gỡ). Tin **shop** thường bán
  nhiều máy trên 1 tin và để rất lâu (thấy có tin đăng từ 2 tháng trước) — xem kết luận ở tin cá nhân là chính.
- "Rẻ/đắt" tính so với trung vị nhóm nên tác động đo được thường **nhỏ hơn** thực tế một chút (đã kiểm
  chứng trên giả lập: đáp án ×2 thì đo được ×1,7).

**Thử trước trên dữ liệu giả lập** (có đáp án, ~3 giây):

```bash
.venv\Scripts\python.exe main.py speedsim
```

```bash
.venv\Scripts\python.exe main.py web --db data\speedsim.db --port 8004
```

Mở http://127.0.0.1:8004/speed. Giả lập dùng **giả định** (tin rẻ biến mất nhanh ×2, pin yếu chậm ×0,7,
shop chậm ×0,25) chỉ để kiểm tra phương pháp tìm lại đúng — không phải kết quả thị trường.

**Kiểm tra tay một lượt** (thường không cần, worker tự làm): `main.py track --budget 30` (30 request).

---

## 4c. Dữ liệu theo từ khóa (cho mọi sản phẩm)

Không chỉ iPhone: gõ **bất kỳ từ khóa nào** như khi tìm trên Chợ Tốt (laptop, xe máy, máy lạnh, máy ảnh,
máy tính bảng…). Mỗi từ khóa có **dữ liệu riêng**: bảng giá theo nhóm, danh sách tin, file Excel.

**Cách 1 — lấy dữ liệu ngay (1 lần):** double-click **`6_TIM_THEO_TU_KHOA.bat`**, trả lời các câu hỏi
(từ khóa, số trang, chữ cần loại trừ, khoảng giá, có theo dõi tiếp không). Chương trình tải các trang kết quả,
lưu vào `data\deals.db`, in bảng giá theo nhóm và **mở file Excel** (lưu trong `exports\`). Hoặc gõ lệnh:

```bash
.venv\Scripts\python.exe main.py search "macbook air m2" --pages 5 --exclude "m1" --add --every 30
```

**Cách 2 — theo dõi liên tục:** trên dashboard mở trang **Từ khóa** → ô "Thêm từ khóa" → **Thêm**.
Collector đang chạy (`4_CHAY_THAT_CHOTOT.bat` hoặc VPS) tự đọc lại danh sách mỗi vòng quét, nạp 3 trang
(~150 tin) cho từ khóa mới (không báo deal ở lượt nạp đó), rồi quét đều như các từ khóa khác.
Không cần khởi động lại. Bỏ từ khóa: nút **Bỏ** (tick "xóa dữ liệu" nếu muốn xóa luôn tin đã thu).

**Xem và tải dữ liệu:**
- Trang **Từ khóa**: số tin 30 ngày / tổng, số nhóm, link **Excel · CSV · Xem tin** cho từng từ khóa.
- Trang **Tổng quan**: thanh chọn từ khóa phía trên bảng "Giá theo nhóm sản phẩm".
- File Excel gồm 3 sheet: **Tổng hợp** (mỗi nhóm: số tin, trung vị 30 và 7 ngày, xu hướng, P25–P75,
  thấp/cao nhất, độ phân tán, ngưỡng deal) · **Tin đăng** (mọi tin đã thu: tiêu đề, giá, khu vực, cá nhân/shop,
  danh mục, năm, số km, ngày đăng, còn đăng/đã gỡ, link) · **Ghi chú**. Không có mô tả, tên hay số điện thoại người bán.
- CSV dùng dấu `;` và mã UTF-8 có BOM để Excel cài tiếng Việt mở đúng cột, đúng dấu.

**Tin được chia nhóm thế nào (luật "từ khóa chung"):** theo **danh mục** Chợ Tốt (laptop tách khỏi linh kiện,
xe máy tách khỏi phụ tùng) + **mới / đã dùng**, cộng thêm:
- **Xe** (Chợ Tốt có năm đăng ký): tách theo **năm** — VD Honda Vision 2016 ~16 tr, 2019 ~17,7 tr, 2023 ~25,3 tr.
- **Điện thoại, laptop, máy tính bảng**: tách theo **cấu hình GB/TB** ghi trong tiêu đề ("16GB/512GB", "8/256").
  Đo trên MacBook Air M2 thật: gộp chung độ phân tán 18% (chỉ báo deal khi rẻ hơn 37%); tách cấu hình còn
  7–10% (báo khi rẻ hơn 15–21%).
- Tin ghi **lỗi / hư / bể / dính iCloud** hoặc **trả trước** trong tiêu đề vào nhóm riêng, không báo deal.
- Một tin khớp 2 từ khóa ("macbook air" và "macbook air m2") được tính trong **cả hai**.
- Pin/ngoại hình chỉ quy đổi giá cho iPhone (hệ số học trên iPhone); nhóm từ khóa chung so giá thô.

**Mẹo để giá trong nhóm đồng đều (báo deal đúng hơn):**
- Từ khóa càng cụ thể càng tốt: "macbook air m2 15 inch" thay vì "macbook".
- Dùng ô **loại trừ**: "iphone 15 pro" cũng ra 15 Pro Max → loại trừ `max`; "máy lạnh daikin" có cả remote
  → loại trừ `điều khiển, remote`.
- Nhóm có pill **"giá quá phân tán"** (ngưỡng deal vượt 40%): không báo deal, chỉ báo nghi lừa đảo khi rẻ bất
  thường so với chính độ phân tán đó. Đo thật: máy lạnh Daikin vẫn phân tán 18–24% kể cả tách theo HP
  (lẫn inverter/mono, hàng Nhật/VN) — với loại hàng này, dùng phần **dữ liệu/Excel** là chính.

**Lưu ý:** collector đang mở từ trước khi cập nhật vẫn chạy code cũ — **đóng cửa sổ và mở lại**
`4_CHAY_THAT_CHOTOT.bat` để dùng bản mới. Dữ liệu iPhone cũ được giữ và tự gắn vào đúng từ khóa.

### Nhịp quét chủ động: 5 / 10 / 15 / 20 / 30 / 45 / 60 phút

Trang **Từ khóa** có 2 chỗ chọn nhịp, đổi là có hiệu lực từ vòng quét tới (không cần khởi động lại):

- **Nhịp quét mặc định** (ô trên cùng): áp dụng cho mọi từ khóa chưa chọn riêng. Mặc định "mỗi vòng quét" (~2 phút) như trước.
  Lưu trong DB, đổi bằng lệnh: `main.py keywords --default-every 15` (`0` = mỗi vòng quét).
- **Nhịp riêng từng từ khóa** (cột "Nhịp quét"): chọn ngay trong bảng, hoặc ở ô "Nhịp quét" khi thêm từ khóa
  (`--every 30` với lệnh `search --add`). Chọn "Mặc định" để quay về nhịp chung. Dưới ô chọn có dòng "quét gần nhất …".

Cách chọn: **săn deal** (iPhone, hàng hot) → 5–10 phút hoặc mỗi vòng; **chỉ thu dữ liệu/giá tham khảo** (laptop, xe,
máy lạnh…) → 30–60 phút. Trang hiển thị ước tính tổng request/ngày của cả danh sách. Mỗi từ khóa tốn:

| Nhịp | 5 | 10 | 15 | 20 | 30 | 45 | 60 | mỗi vòng (2 phút) |
|---|---|---|---|---|---|---|---|---|
| Request/ngày | 288 | 144 | 96 | 72 | 48 | 32 | 24 | ~680 |

Sai số: collector thức dậy mỗi vòng (mặc định 120 giây) nên lần quét thực tế lệch tối đa ±1 vòng so với nhịp chọn
(trung bình đúng nhịp). Khi khởi động lại, mọi từ khóa được quét ngay ở vòng đầu rồi mới theo nhịp. Muốn nhịp
5 phút sát hơn, giảm `POLL_SECONDS`. Không nên để quá ~10 từ khóa quét mỗi vòng.

---

## 4d. Tin bỏ qua (tin bị loại kèm lý do)

Tin bot tải về nhưng **không đưa vào bảng giá** không bị bỏ đi âm thầm nữa: được ghi lại kèm lý do ở tab
**Tin bỏ qua** (menu trên cùng) để bạn kiểm tra bộ lọc có loại nhầm không:

| Lý do | Khi nào |
|---|---|
| Tin thu mua / cần mua / giao lưu | Tiêu đề có "thu mua", "cần mua", "giao lưu"… |
| Linh kiện, xác máy, mô hình | iPhone: tiêu đề có "linh kiện", "xác máy", "mô hình" |
| Máy hỏng/bể ghi ngay ở tiêu đề | iPhone: "bể", "vỡ", "lỗi"… (đã loại "không lỗi") |
| Tiêu đề thiếu chữ của từ khóa | VD tin phụ tùng "Cảng sau Honda SH" khi tìm "xe sh 150i"; chi tiết ghi chữ còn thiếu |
| Có chữ loại trừ | Trùng một chữ trong ô "loại trừ"; chi tiết ghi chữ nào |
| Không nhận ra đời máy / thiếu dung lượng | iPhone: không thấy "iPhone 15…", hoặc không biết dung lượng. Dung lượng được đọc theo thứ tự: tiêu đề (GB/TB, kể cả "2T") → mã Chợ Tốt (kể cả 1TB, 2TB) → mô tả (chỉ khi mô tả ghi đúng 1 dung lượng). Đo thật: ~8% tin iPhone không ghi ở đâu cả — đa số là tin shop, không lấy lại được |
| Giá ngoài khoảng đã đặt | Giá dưới "Giá từ" hoặc trên "Giá đến"; chi tiết ghi mức nào |
| Không ghi giá / Không phải tin bán | Giá 0 (thỏa thuận) / tin loại "cần mua" |

- Lọc theo **từ khóa**, theo **lý do** (các nút có số tin), hoặc gõ chữ trong tiêu đề. Mỗi dòng có link **Mở ↗** để đối chiếu.
- Loại nhầm thì chỉnh khoảng giá / chữ loại trừ ở trang Từ khóa: tin hợp lệ trở lại sẽ tự rời danh sách ở lần quét sau.
- Cũng có trong **file Excel** (sheet **Tin bỏ qua**), **CSV** (nút "tải CSV" trong tab) và API `/api/skipped`.
- Cột "Bỏ qua" ở trang Từ khóa cho biết mỗi từ khóa đang loại bao nhiêu tin. Lệnh `search` in sẵn tóm tắt lý do loại.
- Giữ **30 ngày** kể từ lần cuối thấy tin (`SKIP_KEEP_DAYS` trong `.env`). Không lưu mô tả hay thông tin người bán.
- Tin ghi **lỗi / bypass / thay linh kiện / trả trước** *không* nằm ở đây: chúng vào **nhóm riêng** và vẫn tính giá
  (trang Tổng quan, cột "không báo").
- Danh sách được ghi **từ lúc collector chạy bản mới**; tin đã bị loại trước đó không còn dữ liệu.

---

## 5. Thiết lập Telegram

1. Trong Telegram, chat với **@BotFather** → gõ `/newbot` → đặt tên → nhận **token**.
2. Nhắn cho bot vừa tạo một câu bất kỳ.
3. Mở trình duyệt: `https://api.telegram.org/bot<TOKEN>/getUpdates` → tìm `"chat":{"id": ...}` → đó là **chat id**.
4. Mở file `.env` (trong thư mục `deal-finder`) bằng Notepad, điền:

```text
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

5. Kiểm tra:

```bash
.venv\Scripts\python.exe main.py telegram-test
```

Nhận được "✅ Deal Finder: tin nhắn thử." là xong. Không điền thì cảnh báo chỉ in ra màn hình.
**Không** gửi file `.env` cho ai, không đưa lên GitHub.

---

## 6. Tùy chỉnh

**Từ khóa theo dõi** — dễ nhất là trang **Từ khóa** trên dashboard (mục 4c). Hoặc sửa `watchlist.json`
(giữ đúng dấu phẩy, ngoặc; collector tự đọc lại, file lỗi thì giữ danh sách cũ và báo trên dashboard):

```json
{"name": "iPhone 15 Pro Max", "keywords": "iphone 15 pro max", "type": "iphone", "cg": 5010,
 "min_price": 3000000, "max_price": 32000000},
{"name": "MacBook Air M2", "keywords": "macbook air m2", "exclude": ["m1"], "every_minutes": 30}
```

| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `name` | có | Tên hiển thị, cũng là tên dữ liệu (đổi tên = dữ liệu cũ thành "từ khóa đã bỏ") |
| `keywords` | có | Chữ gõ vào ô tìm của Chợ Tốt |
| `type` | | `iphone` (tách đời máy, dung lượng, xách tay/VN/A/lock) hoặc `keyword` (từ khóa chung). Bỏ trống: có chữ "iphone" thì dùng luật iPhone |
| `min_price` / `max_price` | | Bỏ tin ngoài khoảng giá. Mặc định bỏ tin giá 0 ("thỏa thuận"). Với iPhone đặt `min_price` ~20% giá thị trường |
| `exclude` | | Bỏ tin có các chữ này trong tiêu đề (không phân biệt dấu, khớp trọn từ) |
| `cg` | | Mã danh mục: 5010 điện thoại, 5030 laptop, 5040 máy tính bảng, 5050 máy ảnh, 2020 xe máy, 9060 máy lạnh |
| `region` | | Mã tỉnh: 13000 TP.HCM, 12000 Hà Nội |
| `group_by` | | `["year"]`, `["spec"]`, `["year", "spec"]` hoặc `[]` (không tách). Mặc định: xe theo năm, điện thoại/laptop/máy tính bảng theo GB/TB |
| `phone_rules` | | `true`: đọc mô tả như luật iPhone (bypass, thay màn, lỗi, trả trước) — cho Samsung, iPad… |
| `every_minutes` | | Nhịp quét riêng: `5`, `10`, `15`, `20`, `30`, `45` hoặc `60` phút. Bỏ trống = theo nhịp mặc định chung (trang Từ khóa), nếu chưa đặt thì mỗi vòng quét |
| `pages` | | Số trang nạp lần đầu (mặc định `BASELINE_PAGES` = 3) |

Sửa tùy chọn chia nhóm của từ khóa đã có dữ liệu → chạy `main.py renormalize` để chia lại dữ liệu cũ.
- Gặp cách viết mới (VD người bán ghi "ko nghe gọi" cho máy bypass): thêm từ khóa vào `FLAGS` trong
  `normalizer.py`, thêm câu đó vào test, chạy `pytest`. Luật đọc **tiêu đề**: chạy `main.py renormalize`
  để áp cho dữ liệu cũ. Luật đọc **mô tả**: mô tả không được lưu (vì hay có số điện thoại) nên phải
  nạp lại — đổi tên `data\deals.db` thành file khác rồi chạy `main.py seed`.

**Tham số trong `.env`:**

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `POLL_SECONDS` | 120 | Giây giữa 2 vòng quét. Khuyến nghị ≥ 120 |
| `DEAL_PCT` | 0.15 | Mức rẻ tối thiểu so với trung vị để báo deal |
| `DEAL_Z` | 2.0 | Nhóm giá lộn xộn phải rẻ hơn Z × độ phân tán. Tăng (2.5–3) = ít báo, chắc hơn; giảm (1.5) = báo nhiều hơn |
| `SCAM_PCT` | 0.40 | Rẻ hơn bao nhiêu thì cảnh báo nghi lừa đảo |
| `USE_CONDITION` | 1 | 1 = quy đổi giá theo pin/ngoại hình trước khi so (hệ số học từ dữ liệu); 0 = so giá thô |
| `ALERT_MIN_BATTERY` | 0 (tắt) | VD `80`: không báo deal nếu người bán ghi pin dưới 80% (lựa chọn của người mua) |
| `ALERT_MIN_COSMETIC` | 0 (tắt) | VD `93`: không báo deal nếu ngoại hình ghi dưới 93% (hoặc tả "cấn móp", "trầy xước") |
| `TRACK_PER_CYCLE` | 3 | Số tin cũ kiểm tra còn/mất mỗi vòng quét (0 = tắt đo tốc độ bán); ~2.160 request/ngày |
| `TRACK_INTERVAL_HOURS` | 6 | Mỗi tin kiểm tra lại tối đa bao nhiêu giờ một lần |
| `TRACK_DAYS` | 21 | Theo dõi mỗi tin trong bao nhiêu ngày kể từ lúc thấy |
| `BASELINE_PAGES` | 3 | Số trang nạp lịch sử lúc đầu (mỗi trang 50 tin) |
| `DASH_USER` / `DASH_PASS` | trống | Đặt thì dashboard đòi đăng nhập. **Bắt buộc trên VPS** |
| `DEAL_DB` | `data/deals.db` | Đường dẫn file dữ liệu |
| `WATCHLIST` | `watchlist.json` | Đường dẫn danh sách từ khóa (Docker: `/data/watchlist.json`) |
| `EXPORT_DIR` | `exports/` | Thư mục lưu file Excel/CSV của lệnh `search` / `export` |
| `SKIP_KEEP_DAYS` | 30 | Giữ tin bỏ qua (tab Tin bỏ qua) bao nhiêu ngày kể từ lần cuối thấy |
| `CHOTOT_GATEWAY` | chotot thật | Trỏ sang mock (`http://127.0.0.1:8900`) để test |

---

## 7. Đưa lên VPS Ubuntu (chạy 24/7)

### 7.1. Chuẩn bị VPS
- Thuê VPS đặt tại Việt Nam: **1 vCPU, 1 GB RAM, 20 GB SSD, Ubuntu 24.04** (hoặc 22.04).
  Hệ thống dùng ~70 MB RAM nên gói rẻ nhất là đủ.
- Nhà cung cấp gửi: **IP**, user **root**, **mật khẩu** (hoặc SSH key).

### 7.2. Đóng gói và chép lên (từ máy Windows)
Double-click **`5_DONG_GOI_VPS.bat`** → tạo file `Crawl DATA ChoTot\deal-finder.tgz` (~40 KB).
Mở PowerShell **trong thư mục `Crawl DATA ChoTot`**:

```bash
scp deal-finder.tgz root@IP_VPS:/root/
```

(Windows 10/11 có sẵn `scp`/`ssh`. Lần đầu gõ `yes` để tin máy chủ, rồi nhập mật khẩu VPS.)

### 7.3. Cài đặt (trên VPS)

```bash
ssh root@IP_VPS
```

```bash
tar -xzf deal-finder.tgz && cd deal-finder && sudo bash deploy/install_ubuntu.sh
```

Script tự làm 7 bước: cài Python/Nginx/sqlite3 → đặt múi giờ Việt Nam → tạo user hệ thống
`dealfinder` → chép code vào `/opt/deal-finder` → tạo môi trường Python → cài 2 dịch vụ systemd
(`deal-finder-worker`, `deal-finder-web`) + Nginx + tường lửa + sao lưu hằng ngày → khởi động.

Cuối cùng in ra: **`XONG. Mở http://IP_VPS`** và **tài khoản dashboard `admin / <mật khẩu ngẫu nhiên>`** —
ghi lại mật khẩu này.

### 7.4. Điền Telegram, đổi mật khẩu

```bash
sudo nano /opt/deal-finder/.env
```

Sửa xong: Ctrl+O, Enter, Ctrl+X, rồi khởi động lại:

```bash
sudo systemctl restart deal-finder-worker deal-finder-web
```

### 7.5. Kiểm tra

| Việc | Lệnh | Đúng là |
|---|---|---|
| Trạng thái dịch vụ | `systemctl status deal-finder-worker deal-finder-web` | `active (running)` |
| Log collector trực tiếp | `journalctl -u deal-finder-worker -f` | "Đã nạp baseline…", "Quét xong…" mỗi ~2 phút |
| Sức khỏe | `curl -s localhost/healthz` | `{"ok":true,"state":"ok",...}` |
| Dashboard | mở `http://IP_VPS` | hỏi đăng nhập → huy hiệu LIVE, "Đang quét" |
| Thử Telegram | `cd /opt/deal-finder && sudo -u dealfinder .venv/bin/python main.py telegram-test` | nhận tin nhắn |

### 7.6. Tên miền + HTTPS (khuyến nghị)
Trỏ bản ghi A của tên miền (vd. `deal.tenban.vn`) về IP VPS, sửa `server_name _;` thành tên miền trong
`/etc/nginx/sites-available/deal-finder`, rồi:

```bash
sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d deal.tenban.vn
```

### 7.7. Giám sát, cập nhật, sao lưu
- **Giám sát:** tạo monitor miễn phí trên UptimeRobot trỏ tới `http://IP_VPS/healthz` — trả **503** khi
  collector chết hoặc bị chặn → nhận email/Telegram.
- **Cập nhật code:** đóng gói lại ở Windows, `scp`, rồi trên VPS chạy lại đúng lệnh 7.3. Dữ liệu, `.env` và
  `watchlist.json` trên VPS (từ khóa đã thêm qua dashboard) được giữ — muốn dùng lại danh sách ở máy Windows thì
  chép đè `watchlist.json` bằng tay.
- **Sao lưu:** tự động 3 giờ sáng vào `/opt/deal-finder/backup/` (giữ 14 ngày). Tải về máy:
  `scp root@IP_VPS:/opt/deal-finder/backup/deals-2026-10-26.db .`
- **Khôi phục:** dừng dịch vụ, chép file backup đè lên `/opt/deal-finder/data/deals.db`, `chown dealfinder:dealfinder`, khởi động lại.
- **Nếu collector dừng vì bị chặn** (Telegram báo 🛑): tăng `POLL_SECONDS` (vd. 300), chờ vài giờ, rồi
  `sudo systemctl start deal-finder-worker`.
- **Gỡ cài đặt:** `sudo systemctl disable --now deal-finder-worker deal-finder-web`, xóa `/opt/deal-finder`,
  `/etc/systemd/system/deal-finder-*.service`, `/etc/nginx/sites-*/deal-finder`, `/etc/cron.d/deal-finder-backup`.

### 7.8. Cách khác: Docker
Trên máy đã có Docker (trong thư mục `deal-finder`, đã tạo `.env` từ `.env.example`):

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

Dashboard ở `127.0.0.1:8000` của máy chủ (đặt Nginx phía trước như mục 7.3, hoặc bỏ `127.0.0.1:` trong
`docker-compose.yml` để mở thẳng — khi đó **bắt buộc** có `DASH_USER/DASH_PASS`).
Log: `docker compose -f deploy/docker-compose.yml logs -f worker`.
Danh sách từ khóa nằm ở `data/watchlist.json` (ổ dùng chung của 2 container, tạo từ `watchlist.json` lần đầu).

---

## 8. Kịch bản test và tiêu chí đạt

Chạy từ trên xuống, dừng ở bước đầu tiên không đạt.

| # | Lệnh | Mạng | Kết quả mong đợi | Đã chạy 26/10/2026 |
|---|---|---|---|---|
| 1 | `python -m pytest -q` | Không | `144 passed` | ✅ 144/144 |
| 2 | `python main.py demo` | Không | "giá thường", "hơi rẻ" → không báo; "deal hời" → deal; "nghi lừa đảo" → scam_risk | ✅ |
| 3 | `python main.py simulate` | Không | Rác + tin có vấn đề ẩn lọt 0; "lừa đảo" đúng ≥ 80%; deal đúng hơn thiết kế gốc ≥ 20 điểm | ✅ 0 lọt; 90%; deal 77% (gốc 36%) |
| 4 | `python main.py mockdemo` (5 phút) | Không | Có cảnh báo; dashboard "MOCK · Đang quét" | ✅ |
| 5 | `python main.py probe` | Có | `[OK ] /v1/public/ad-listing: 50 tin` | ✅ |
| 6 | `python main.py all` (≥ 30 phút) | Có | Baseline ~650 tin; "Quét xong" mỗi ~2 phút; không có 403/429 | ✅ baseline 653 tin, quét đều |
| 7 | Dashboard nhóm đủ mẫu | Có | Trung vị khớp mặt bằng giá anh/chị biết (lệch < 10%) | 15 Pro Max 256GB: xách tay 16,5 tr · VN/A 17,5 tr · lock 11,2 tr |
| 8 | `python main.py audit` | Không | Tin có vấn đề trong mô tả bị loại; còn lại vài % số tin bị gắn cờ | ✅ loại 190/649; còn 18 deal + 3 lừa đảo |
| 9 | `python main.py telegram-test` | Có | Nhận tin nhắn | Cần token của anh/chị |
| 10 | `python main.py speedsim` | Không | Tìm lại đúng đáp án giả định trong khoảng tin cậy | ✅ rẻ ×1,74 (đáp án ×2), shop ×0,27 (×0,25) |
| 11 | `python main.py track --budget 40 --hours 0` | Có | Tin còn → còn; tin đã gỡ → ghi nhận 404 | ✅ 40/40 còn (mới theo dõi ~15 phút) |
| 12 | Chạy 24/7 trên VPS ≥ 3 ngày | Có | `/healthz` luôn 200; kiểm tra tay 20–50 cảnh báo, ghi đúng/sai | Cần VPS |
| 13 | Chạy liên tục 2–4 tuần rồi `python main.py speed` | Có | Kết luận về giá (~2 tuần) và pin (~4 tuần) | Cần chạy |
| 14 | `python main.py search "macbook air m2" --pages 2` | Có | Tin vào đúng danh mục, tách theo cấu hình; ra file Excel | ✅ 100 tin; 16/256 · 8/256 · 16/512 độ phân tán 7–10% (trên bản sao DB) |
| 15 | `python main.py search "honda vision" --pages 2` | Có | Xe tự tách theo năm, trung vị tăng dần theo năm | ✅ 2016 ~16 tr · 2019 ~17,7 tr · 2023 ~25,3 tr (trên bản sao DB) |
| 16 | Dashboard → Từ khóa → Thêm | Không | Từ khóa vào `watchlist.json`; collector nạp ở vòng quét tới | ✅ form ghi đúng (thử trên bản sao) |
| 17 | Tab **Tin bỏ qua** sau `search "macbook air m2" --min-price 18tr` | Có | Tin dưới 18 tr xuất hiện với lý do "Giá ngoài khoảng đã đặt" + mức tối thiểu | ✅ 32/100 tin; 4 tin phụ tùng "xe sh 150i" → "thiếu chữ" (bản sao DB) |
| 18 | Trang Từ khóa → đổi "Nhịp quét" (5…60 phút, mặc định chung) | Không | `watchlist.json` / DB đổi; ước tính request/ngày cập nhật | ✅ chọn trên giao diện ghi đúng; giá trị ngoài danh sách bị từ chối |

**Tiêu chí đạt demo:** bước 1–8 đạt; ở bước 10, ≥ 70% cảnh báo kiểm tra tay thấy hợp lý
(ghi lại để chỉnh `DEAL_Z`), không gặp chuỗi 403/429.

---

## 9. Xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `No such file or directory: main.py` / `can't open file` | Chạy sai thư mục | `cd` vào `...\Crawl DATA ChoTot\deal-finder` hoặc dùng file `.bat` |
| `'python' is not recognized` | Chưa cài Python / chưa thêm PATH | Cài lại Python, tick "Add to PATH" |
| `ModuleNotFoundError: fastapi` | Chưa cài thư viện hoặc dùng nhầm Python hệ thống | Chạy `1_CAI_DAT.bat`; gọi `.venv\Scripts\python.exe` |
| `[Errno 10048] ... address already in use` | Cổng 8000/8001/8002/8900 đang bị chương trình khác dùng | Đóng cửa sổ Deal Finder cũ, hoặc thêm `--port 8010` |
| Dashboard "Collector không chạy" | Đang chạy lệnh `web` (chỉ dashboard) hoặc worker đã tắt | Dùng lệnh `all`, hoặc chạy thêm `run` ở cửa sổ khác |
| Log "Bị chặn (HTTP 429)" | Quét quá dày | Tăng `POLL_SECONDS` (≥ 180), giảm số từ khóa; **không** dùng proxy để lách |
| `probe` báo `[ERR]` cả v1 | Mất mạng hoặc Chợ Tốt đổi API | Kiểm tra mạng; nếu API đổi, cập nhật `LISTING_PATH` trong `config.py` |
| Không có cảnh báo nào | Nhóm chưa đủ 8 mẫu / chưa có tin rẻ thật / tin rẻ đều bị loại vì mô tả ghi bypass, thay màn… | Bình thường (deal thật hiếm). Xem cột "Báo deal khi rẻ hơn"; chạy `audit` để thấy vì sao; thử `mockdemo` để chắc pipeline chạy |
| Báo quá nhiều | Ngưỡng thấp so với thị trường | Tăng `DEAL_Z` lên 2.5 trong `.env` |
| Chữ tiếng Việt lỗi trong cửa sổ đen | Font console | Không ảnh hưởng dữ liệu; xem trên dashboard |
| Telegram không nhận | Sai token/chat id, chưa nhắn bot trước | Làm lại mục 5, chạy `telegram-test` |

---

## 10. Bảng lệnh

Cú pháp: `.venv\Scripts\python.exe main.py <lệnh> [tùy chọn]`

| Lệnh | Mạng | Làm gì |
|---|---|---|
| `search "từ khóa" [--pages 3] [--exclude "a,b"] [--min-price 3tr] [--max-price 40tr] [--add] [--every 30] [--open]` | Có | Tìm ngay 1 từ khóa, lưu DB, in giá theo nhóm và lý do loại tin, xuất Excel; `--add` = theo dõi tiếp (`--every`: 5/10/15/20/30/45/60 phút). Không kèm từ khóa thì hỏi từng mục |
| `export ["tên từ khóa"] [--csv] [--open]` | Không | Xuất Excel (hoặc CSV) cho 1 từ khóa hoặc tất cả vào `exports/` |
| `keywords [--default-every N]` | Không | Danh sách từ khóa + nhịp quét + số tin đã thu / bỏ qua; `--default-every` đặt nhịp mặc định chung (5/10/15/20/30/45/60, `0` = mỗi vòng) |
| `probe` | Có | Thử API Chợ Tốt, in vài tin và khóa sản phẩm |
| `seed` | Có | Nạp baseline (`BASELINE_PAGES` trang × mỗi từ khóa), không cảnh báo |
| `run [--cycles N]` | Có | Vòng quét + cảnh báo (mặc định chạy mãi) |
| `all [--port 8000]` | Có | `run` + dashboard trong 1 tiến trình |
| `web [--db FILE] [--port]` | Không | Chỉ dashboard |
| `report [--db FILE]` | Không | Bảng trung vị 7/30 ngày ra màn hình |
| `audit` | Không | Liệt kê tin sẽ bị báo (kèm pin/ngoại hình, so giá thô và quy đổi); ghi `reports/audit_*.md` |
| `calibrate [--save]` | Không | Học hệ số pin/ngoại hình từ dữ liệu; `--save` để dùng |
| `speed` | Không | Báo cáo tốc độ bán từ dữ liệu theo dõi; ghi `reports/speed_*.md` |
| `track [--budget N] [--hours H]` | Có | Một lượt kiểm tra N tin cũ còn/mất (worker tự làm mỗi vòng) |
| `speedsim [--days 30]` | Không | Kiểm chứng phương pháp đo tốc độ bán trên giả lập; ghi `data/speedsim.db` |
| `renormalize [--db FILE]` | Không | Áp luật chuẩn hóa hiện tại cho toàn bộ dữ liệu cũ |
| `telegram-test` | Có | Gửi tin nhắn thử |
| `demo` | Không | Kiểm tra nhanh chuẩn hóa + phân tích bằng dữ liệu cố định |
| `simulate [--days 30] [--seed 42]` | Không | Sinh dữ liệu giả lập, backtest, ghi `data/sim.db` + `reports/` |
| `mock [--mock-port 8900]` | Không | Chỉ chạy máy chủ Chợ Tốt giả (để `run` trỏ vào qua `CHOTOT_GATEWAY`) |
| `mockdemo [--port 8002] [--block-every N]` | Không | Mock + collector + dashboard trong 1 lệnh |

JSON API (cùng tài khoản dashboard): `/api/status`, `/api/keywords`, `/api/skipped?watch=TÊN&reason=ngoai-gia`, `/api/groups?watch=TÊN`,
`/api/alerts?kind=deal`, `/api/listings?watch=TÊN&q=256`, `/healthz` (không cần đăng nhập).
Tải file: `/export?watch=TÊN` (Excel), `/export?fmt=csv&watch=TÊN` (CSV); bỏ `watch` = tất cả từ khóa.
