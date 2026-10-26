# Deal Finder — dữ liệu & deal theo từ khóa trên Chợ Tốt

Gõ từ khóa bất kỳ (iPhone, laptop, xe máy, máy lạnh, máy ảnh…), bot quét tin đăng trên Chợ Tốt và giữ
**dữ liệu riêng cho từng từ khóa**: bảng giá theo nhóm (trung vị 30 ngày, P25–P75, xu hướng), danh sách tin,
file **Excel/CSV**. Tin được chia nhóm để so giá cùng loại: iPhone theo đời máy, dung lượng, xách tay / VN/A / lock;
sản phẩm khác theo danh mục, mới/đã dùng, năm (xe) và cấu hình GB/TB (điện thoại, laptop, máy tính bảng).
Báo **deal** (rẻ hơn ≥ 15% và vượt độ phân tán của nhóm) và **nghi lừa đảo** qua Telegram, kèm web dashboard chạy được trên VPS.
Chọn **nhịp quét chủ động 5 / 10 / 15 / 20 / 30 / 45 / 60 phút** cho từng từ khóa hoặc mặc định chung; tab **Tin bỏ qua** cho
biết tin nào bị loại và vì sao.

| Đọc gì | Ở đâu |
|---|---|
| Cách cài, chạy demo, chạy thật, thêm từ khóa, đưa lên VPS | [HUONG_DAN.md](HUONG_DAN.md) (mục 4c: dữ liệu theo từ khóa) |
| Tư vấn thiết kế, số liệu backtest, kiến trúc | [THIET_KE.md](THIET_KE.md) |
| Thiết kế gốc | [../deal-finder-demo.md](../deal-finder-demo.md) |

Bắt đầu nhanh trên Windows: double-click lần lượt `1_CAI_DAT.bat` → `2_DEMO_GIA_LAP.bat` →
`3_DEMO_TRON_VONG_MOCK.bat` → `4_CHAY_THAT_CHOTOT.bat`. Lấy dữ liệu 1 từ khóa ngay: `6_TIM_THEO_TU_KHOA.bat`.

Nguyên tắc: chỉ đọc API công khai, nhịp chậm (≥ 2 giây/request, 120 giây/vòng; từ khóa thu dữ liệu nên quét
30–60 phút/lần), bị chặn thì giãn rồi dừng hẳn; không proxy xoay, không giải CAPTCHA, không lưu thông tin cá nhân người bán.
