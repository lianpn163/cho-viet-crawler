# VieBuy – crawler + website

Hệ thống gồm 3 phần:

| Phần | File | Làm gì |
|---|---|---|
| Danh sách brand | `brands.json` | Website nào cần đọc |
| Crawler | `crawler.py` | Đọc sản phẩm, giá, giá sale, tồn kho từng size, ảnh → ghi ra `site/data/` |
| Website | `site/index.html` | Đọc `site/data/` và hiển thị, ảnh lấy thẳng từ CDN của brand |
| Lịch chạy tự động | `.github/workflows/site.yml` | GitHub chạy crawler mỗi tiếng và đăng web (miễn phí) |
| Nhận đơn | `deploy/google-apps-script.gs` | Google nhận đơn, lưu Google Sheet, email báo bạn (miễn phí) |
| Admin | `admin/index.html` + `serve.py` | Chỉ chạy trên laptop của bạn, không lên mạng |

## Crawler đọc dữ liệu thế nào

**Shopify** (vd. pushpush.vn): đọc `/products.json`, mỗi lần 250 sản phẩm.
Có: tên, loại, giá, giá gốc khi sale, từng phân loại còn/hết, ảnh.
Không có: số lượng tồn chính xác (Shopify ẩn con số này).

**Haravan** (birdybag, dico, ripofff, goldie, whenever):
1. Lấy danh sách sản phẩm từ `sitemap.xml`. Nếu không có thì đọc các trang `/collections/all?page=1,2,3…`.
2. Đọc từng sản phẩm ở `/products/<tên-sản-phẩm>.js`.
   Có: giá, giá sale, **số lượng tồn từng size**, tất cả ảnh.
   Lưu ý: Haravan lưu giá nhân 100 (40000000 = 400.000₫). Crawler đã tự chia.

**Các lớp kiểm tra chính xác:**
- Giá ngoài khoảng 10.000₫ – 50.000.000₫, thiếu tên hoặc thiếu ảnh → sản phẩm bị ẩn và ghi vào danh sách cần xem.
- Giá đổi quá 40% mà không phải do sale → giữ giá cũ, ghi vào `review.json` chờ duyệt.
- Brand lỗi (web sập, bị chặn) → giữ dữ liệu lần cuối, đánh dấu "cũ". Website hiện "chưa xác nhận tồn kho".
- Số sản phẩm tụt quá 50% so với lần trước → coi là lỗi, không ghi đè dữ liệu cũ.
- Sản phẩm không xếp được danh mục → `review.json`.
- File dữ liệu được ghi xong rồi mới thay, nên website không bao giờ đọc phải file dở.

## Cách 1: chạy thử trên laptop (khoảng 10 phút)

1. Cài Python 3 từ python.org (Windows: nhớ tick "Add Python to PATH").
2. Giải nén thư mục này, mở Terminal (Mac) hoặc Command Prompt (Windows), đi vào thư mục:
   ```
   cd đường-dẫn/cho-viet-crawler
   pip install -r requirements.txt
   ```
3. Chạy thử một brand trước cho nhanh:
   ```
   python crawler.py pushpush
   ```
   Màn hình sẽ in ra kiểu `✓ Pushpush: 120 sản phẩm…`. Chạy đủ 6 brand:
   ```
   python crawler.py
   ```
   Haravan đọc từng sản phẩm một và nghỉ ~1 giây giữa các lần, nên brand nhiều hàng (Whenever ~500 món) mất khoảng 10 phút. Muốn thử nhanh: `MAX_PRODUCTS=30 python crawler.py` (Windows: `set MAX_PRODUCTS=30` rồi chạy).
4. Mở website (kèm trang admin):
   ```
   python3 serve.py
   ```
   Lần đầu sẽ hỏi đặt mật khẩu admin (gõ không hiện chữ là bình thường).
   - Website khách: http://localhost:8000
   - Admin (trang riêng): http://localhost:8000/admin, gồm xếp danh mục, xác minh brand, danh sách khách chờ hàng, viết bài Journal, thêm clip TikTok, chỉnh tỷ giá/phí, đồng bộ, xem đơn.
   - Trang admin nằm trong thư mục `admin/`, ngoài thư mục `site/`, nên không bao giờ bị đưa lên web cùng website khách.
   - Đơn hàng và mật khẩu nằm trong thư mục `private/`, không bao giờ hiện ra website.
   - Quên mật khẩu: xoá `private/admin_config.json` rồi chạy lại.
5. Xem kết quả kiểm tra trong `site/data/status.json` (brand nào lỗi, vì sao) và `site/data/review.json` (cần duyệt).

## Cách 2: đưa web lên mạng miễn phí (GitHub + Google)

Web chạy trên GitHub Pages, GitHub tự cập nhật giá & tồn kho mỗi tiếng. Khách đặt hàng → Google lưu vào Google Sheet và **email báo bạn ngay** (có link từng món để đặt hàng trên điện thoại). Admin vẫn chạy trên laptop như cũ, bấm **⇣ Lấy đơn mới** để kéo đơn về bảng kanban. Tổng chi phí: 0đ.

Thư mục `private/` (mật khẩu admin, đơn hàng, chuyển khoản, mã bí mật) **không bao giờ** được đưa lên GitHub (đã chặn trong `.gitignore`).

### A. Đưa web lên GitHub (làm 1 lần, ~10 phút)
1. Tạo tài khoản github.com. Tải app **GitHub Desktop** (desktop.github.com), đăng nhập.
2. GitHub Desktop → **File → Add Local Repository** → chọn thư mục `cho-viet-crawler` → bấm **create a repository** → **Create Repository**.
3. Bấm **Publish repository**: Name `viebuy`, **bỏ tick** "Keep this code private" (Pages miễn phí cần public; thông tin riêng vẫn không lên) → Publish.
4. Trên github.com, mở repo `viebuy` → **Settings → Pages** → Source: **GitHub Actions**.
5. Tab **Actions** → **Cập nhật & đăng web** → **Run workflow**. Đợi ~5 phút (dấu tích xanh).
6. Web ở `https://<tên-github>.github.io/viebuy/`.

### B. Nhận đơn qua Google (làm 1 lần, ~10 phút)
1. Vào sheets.google.com tạo bảng tính trống, đặt tên `VieBuy đơn hàng`.
2. Menu **Extensions (Tiện ích) → Apps Script**. Xoá hết code mẫu, dán toàn bộ file `deploy/google-apps-script.gs`.
3. Sửa 2 dòng đầu: `OWNER_EMAIL` = email của bạn, `SECRET` = một chuỗi bí mật tự nghĩ (vd. `viebuy-8x2k-q9`). Bấm 💾 lưu.
4. Chọn hàm `testEmail` → **Run** → cấp quyền (Advanced → Go to … → Allow). Kiểm tra hộp thư có email thử.
5. **Deploy → New deployment** → loại **Web app**: Execute as **Me**, Who has access **Anyone** → Deploy → chép **Web app URL**.
6. Trên laptop mở admin → **Quản lý sàn → Cài đặt & đồng bộ → Online**: dán link web (bước A6), link Web app, mã bí mật → Lưu.
7. Đẩy lên mạng (mục C). Xong: đặt thử một đơn trên web online, email sẽ tới trong vài giây.
   Sửa script sau này: **Deploy → Manage deployments → ✏️ → Version: New version → Deploy** (giữ nguyên link).

### C. Sửa giao diện / debug rồi đăng lại
1. Sửa trên laptop, xem thử ở `http://localhost:8000` (`python3 serve.py`). Đặt hàng ở localhost chỉ lưu trên máy, không gửi email.
2. Mở GitHub Desktop: thấy danh sách file thay đổi → gõ mô tả ngắn → **Commit to main** → **Push origin**.
3. ~1–2 phút sau web online cập nhật. Sai thì trong GitHub Desktop bấm chuột phải commit → **Revert** rồi Push.

Thay đổi trong admin (sản phẩm, danh mục, journal, moodboard, cài đặt…) cũng là file trong `site/data/admin/`, nên cũng cần **Commit + Push** để lên web.

### Lưu ý
- Lịch chạy của GitHub có thể trễ 10–30 phút; web tự khoá nút mua nếu dữ liệu cũ hơn 6 tiếng (đổi trong Cài đặt).
- Nếu 60 ngày repo không có thay đổi, GitHub tạm tắt lịch tự chạy và gửi email; vào Actions bấm Enable là chạy lại.
- Lần chạy nào lỗi, GitHub gửi email cho bạn. Cảnh báo giá vẫn xem trong admin sau khi bấm **⇣ Lấy đơn mới**.

## Thêm brand mới

Thêm một dòng vào `brands.json`:
```json
{"id": "tenbrand", "name": "Tên Brand", "domain": "tenbrand.vn", "platform": "", "instagram": "tenbrand"}
```
Để `platform` trống thì crawler tự nhận diện. Nếu ra lỗi "chưa hỗ trợ nền tảng" thì web đó dùng nền tảng khác (Sapo, WooCommerce, tự code) và cần viết thêm phần đọc riêng.

## Kiểm tra crawler (không cần mạng)
```
pip install pytest
python -m pytest -q
```

## Giới hạn hiện tại
- Trang admin và nút đặt hàng cần `serve.py` (chạy trên laptop). Khi website chạy trên GitHub Pages, khách vẫn xem và thêm giỏ được, nhưng admin và gửi đơn cần một bước nối thêm (sẽ làm ở bước đưa lên mạng).
- Chưa chạy thử với mạng thật từ máy chủ: crawler được viết theo dữ liệu đã đọc được từ 6 web này và có test, nhưng lần chạy đầu có thể lộ ra web nào chặn bot.
- Sapo, WooCommerce, web tự code: chưa hỗ trợ.
- Xếp danh mục bằng từ khoá. Muốn chính xác hơn và dịch tên sang tiếng Anh, bước sau sẽ thêm AI (Claude API) cho các món rơi vào "Khác".
- Ảnh và thông tin là của brand. Dùng nội bộ để thử thì được, còn đưa lên bán công khai thì cần brand đồng ý.
