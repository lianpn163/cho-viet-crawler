"""Kiểm tra crawler bằng dữ liệu mẫu (không cần mạng).
Chạy: python -m pytest -q
Dữ liệu mẫu chép theo đúng định dạng đã thấy trên pushpush.vn (Shopify),
birdybag.com và whenever.vn (Haravan) ngày 25/11/2026."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crawler  # noqa: E402


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return json.loads(self.text)


SHOPIFY_PAGE = {"products": [{
    "handle": "pp-jkp-tee", "title": "PP JKP TEE", "product_type": "LONG SLEEVE",
    "tags": ["new", "T-Shirt"],
    "images": [{"src": "https://cdn.shopify.com/s/files/1/0750/5507/1475/files/a.jpg"}],
    "variants": [
        {"title": "White / S", "price": "650000", "compare_at_price": None, "available": True},
        {"title": "White / L", "price": "650000", "compare_at_price": None, "available": False}]}]}

HARAVAN_BIRDY = {
    "handle": "balo-bandana-backpack-brown", "title": "BALO BIRDYBAG BANDANA BACKPACK/Brown",
    "type": "Balo", "tags": [], "images": ["//product.hstatic.net/200000405371/product/x.jpg"],
    "variants": [{"title": "BROWN", "price": 40000000, "compare_at_price": 55000000,
                  "available": True, "inventory_quantity": 14, "inventory_management": "haravan"}]}

HARAVAN_WHENEVER = {
    "handle": "ao-thun-whenever-hwd-slub-t-shirt-pink",
    "title": 'ÁO THUN "WHENEVER" HWD SLUB T-SHIRT/ PINK', "type": "T-SHIRT", "tags": [],
    "images": ["https://cdn.hstatic.net/products/200001023102/a.jpg"],
    "variants": [
        {"title": "SIZE S", "price": 65500000, "compare_at_price": 0, "available": True,
         "inventory_quantity": 47, "inventory_management": "haravan"},
        {"title": "SIZE L", "price": 65500000, "compare_at_price": 0, "available": True,
         "inventory_quantity": 10, "inventory_management": "haravan"}]}

SITEMAP = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://birdybag.com/sitemap_products_1.xml</loc></sitemap>
<sitemap><loc>https://birdybag.com/sitemap_pages_1.xml</loc></sitemap></sitemapindex>"""
SITEMAP_P = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://birdybag.com/products/balo-bandana-backpack-brown</loc></url></urlset>"""
COLLECTION = '<a href="/products/ao-thun-whenever-hwd-slub-t-shirt-pink">x</a><a href="/products/ao-thun-whenever-hwd-slub-t-shirt-pink?v=1">'


DICO_BULK = {"products": [{
    "handle": "dico-tee", "title": "DICO RELAXED TEE", "product_type": "T-SHIRT", "tags": [],
    "images": [{"src": "//cdn.hstatic.net/products/200001142340/a.jpg"}],
    "variants": [{"title": "S", "price": "390000.0", "compare_at_price": "450000.0", "available": True,
                  "inventory_quantity": 5, "inventory_management": "haravan"},
                 {"title": "M", "price": "390000.0", "compare_at_price": "450000.0", "available": False,
                  "inventory_quantity": 0, "inventory_management": "haravan"}]}]}
GOLDIE_COLLECTION = '<a href="/products/drive-heavy-tshirt">x</a>'


def fake_get(url):
    routes = {
        "https://dico.vn/collections/all/products.json?limit=250&page=1&sort_by=best-selling": Resp(200, DICO_BULK),
        "https://dico.vn/collections/all/products.json?limit=250&page=2&sort_by=best-selling": Resp(200, DICO_BULK),
        "https://goldie.vn/collections/all?page=1": Resp(200, GOLDIE_COLLECTION),
        "https://goldie.vn/collections/all?page=2": Resp(200, GOLDIE_COLLECTION),
        "https://pushpush.vn/products.json?limit=250&page=1": Resp(200, SHOPIFY_PAGE),
        "https://pushpush.vn/products.json?limit=250&page=2": Resp(200, {"products": []}),
        "https://birdybag.com/sitemap.xml": Resp(200, SITEMAP),
        "https://birdybag.com/sitemap_products_1.xml": Resp(200, SITEMAP_P),
        "https://birdybag.com/products/balo-bandana-backpack-brown.js": Resp(200, HARAVAN_BIRDY),
        "https://whenever.vn/sitemap.xml": Resp(404, ""),
        "https://whenever.vn/collections/all?page=1": Resp(200, COLLECTION),
        "https://whenever.vn/collections/all?page=2": Resp(200, COLLECTION),
        "https://whenever.vn/products/ao-thun-whenever-hwd-slub-t-shirt-pink.js": Resp(200, HARAVAN_WHENEVER),
    }
    return routes.get(url, Resp(404, ""))


def setup(monkeypatch, tmp_path, brands):
    monkeypatch.setattr(crawler, "get", fake_get)
    monkeypatch.setattr(crawler, "pause", lambda: None)
    monkeypatch.setattr(crawler, "ROOT", tmp_path)
    monkeypatch.setattr(crawler, "DATA", tmp_path / "site" / "data")
    (tmp_path / "brands.json").write_text(json.dumps(brands))


BRANDS = [
    {"id": "pushpush", "name": "Pushpush", "domain": "pushpush.vn", "platform": "shopify"},
    {"id": "birdybag", "name": "BirdyBag", "domain": "birdybag.com", "platform": "haravan"},
    {"id": "whenever", "name": "Whenever", "domain": "whenever.vn", "platform": "haravan"},
    {"id": "dico", "name": "DICO", "domain": "dico.vn", "platform": "haravan"},
    {"id": "goldie", "name": "Goldie", "domain": "goldie.vn", "platform": "haravan"},
    {"id": "dead", "name": "Dead", "domain": "dead.vn", "platform": "haravan"},
]


def test_full_run(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, BRANDS)
    products, status, review = crawler.run()
    by = {p["brand"]: p for p in products}
    # Shopify: giá đúng, size L hết hàng, không có số lượng
    pp = by["pushpush"]
    assert pp["price"] == 650000 and pp["variants"][1]["available"] is False
    assert pp["variants"][0]["qty"] is None and pp["category"] == "Áo thun & polo"
    # Haravan: chia 100, có sale, có tồn kho thật, ảnh có https
    bb = by["birdybag"]
    assert bb["price"] == 400000 and bb["compare_at"] == 550000
    assert bb["variants"][0]["qty"] == 14 and bb["images"][0].startswith("https://")
    assert bb["category"] == "Túi"
    # Haravan qua trang danh mục (không có sitemap), không trùng sản phẩm
    wh = [p for p in products if p["brand"] == "whenever"]
    assert len(wh) == 1 and wh[0]["price"] == 655000 and wh[0]["variants"][0]["qty"] == 47
    # brand không đọc được: báo lỗi, không làm hỏng brand khác
    # Haravan đọc theo lô (Dico): giá thường, sale, tồn kho, không trùng khi web trả lại trang cũ
    dc = [p for p in products if p["brand"] == "dico"]
    assert len(dc) == 1 and dc[0]["price"] == 390000 and dc[0]["compare_at"] == 450000
    assert dc[0]["variants"][0]["qty"] == 5 and dc[0]["variants"][1]["available"] is False
    st = {s["id"]: s for s in status}
    # tìm được sản phẩm nhưng không đọc được chi tiết -> phải báo lỗi, không được ✓ với 0 món
    assert st["goldie"]["ok"] is False and "không đọc được chi tiết" in st["goldie"]["error"]
    assert st["dead"]["ok"] is False and st["birdybag"]["ok"] is True
    assert all(p["sellable"] for p in products)


def test_price_jump_is_held(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, BRANDS[:1])
    crawler.run()
    SHOPIFY_PAGE["products"][0]["variants"][0]["price"] = "65000"   # gõ nhầm thiếu một số 0
    SHOPIFY_PAGE["products"][0]["variants"][1]["price"] = "65000"
    try:
        products, _, review = crawler.run()
    finally:
        for v in SHOPIFY_PAGE["products"][0]["variants"]:
            v["price"] = "650000"
    assert products[0]["price"] == 650000 and products[0]["price_held"]
    assert review[0]["type"] == "price_jump" and review[0]["new"] == 65000


def test_brand_failure_keeps_old_data(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, BRANDS[1:2])
    crawler.run()
    monkeypatch.setattr(crawler, "get", lambda url: None)   # web brand sập
    products, status, _ = crawler.run()
    assert len(products) == 1 and status[0]["ok"] is False and status[0]["last_ok"]


def test_categories():
    c = crawler.categorize
    assert c("RIPOFFF Basic Nylon Shorts") == "Quần"
    assert c("SNOW SUEDE HOODIE") == "Áo len & hoodie"
    assert c("OUTTA SPACE JACKET") == "Áo khoác"
    assert c("KNIT SWEATER") == "Áo len & hoodie"
    assert c("JIYU LONG SLEEVE SHIRT BLACK") == "Sơ mi"
    assert c("KAIHO MERCURY Long Sleeve BLUE") == "Áo thun & polo"
    assert c("GOLDIE FLASHING POLO") == "Áo thun & polo"
    assert c('ÁO SƠ MI TAY DÀI "WHENEVER" PANEL OVERSHIRT/ NAVY') == "Sơ mi"
    assert c('ÁO QUẦN "WHENEVER" CAMO BIKINI SET') == crawler.SKIP
    assert c("IPHONE PHONE CASE") == crawler.SKIP and c("LEATHER SNEAKER") == crawler.SKIP
    assert c("PP CORD BASEBALL CAP") == "Mũ"
    assert c("BROKEN WASHED DENIM PANTS") == "Quần"
    assert c("Something odd") == "Khác"


def test_scale_detection():
    x100 = [{"variants": [{"price": 40000000}, {"price": 65500000}]}]
    normal = [{"variants": [{"price": "390000.0"}, {"price": "2250000"}]}]
    assert crawler.detect_scale(x100) == 100 and crawler.detect_scale(normal) == 1


RVB_SITEMAP = """<urlset><url><loc>https://rvb.vn/shop</loc></url>
<url><loc>https://rvb.vn/product/ao-calligraphy-boxy-t-shirt-black</loc></url></urlset>"""
RVB_PAGE = """<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
"name":"Áo CALLIGRAPHY Boxy T-Shirt BLACK","image":"https://rvb.vn/assets/shop/calligraphy.jpg","category":"tees",
"offers":{"@type":"Offer","priceCurrency":"VND","price":"432000","availability":"https://schema.org/InStock","priceValidUntil":"2026-10-31"}}</script>
<script src="/assets/products-data.js"></script>
<script type="application/ld+json">{"@type":"BreadcrumbList"}</script>
<script src="/assets/size-variant-map.js"></script></html>"""
RVB_PRICES = """window.RVB_PRODUCTS = [
 {slug: 'ao-calligraphy-boxy-t-shirt-black', name: 'Áo CALLIGRAPHY', category: 'tees', price: 540000, discountPct: 45, compareAtPrice: 540000, salePrice: 297000, img: 'x.jpg'},
 {slug: 'ao-other', price: 690000, compareAtPrice: 690000, salePrice: 621000}];
(async()=>{const r=await fetch('https://team.example/api/products.json')})();"""
RVB_SIZES = 'window.RVB_SIZE_VARIANTS = {"ao-calligraphy-boxy-t-shirt-black": {"S": 111, "M": 222, "L": 333,}};\n'


def test_public_jsonld_site(monkeypatch, tmp_path):
    routes = {"https://rvb.vn/sitemap.xml": Resp(200, RVB_SITEMAP),
              "https://rvb.vn/product/ao-calligraphy-boxy-t-shirt-black": Resp(200, RVB_PAGE),
              "https://rvb.vn/assets/size-variant-map.js": Resp(200, RVB_SIZES),
              "https://rvb.vn/assets/products-data.js": Resp(200, RVB_PRICES)}
    setup(monkeypatch, tmp_path, [{"id": "rvb", "name": "RVB", "domain": "rvb.vn", "platform": "jsonld"}])
    monkeypatch.setattr(crawler, "get", lambda u: routes.get(u, Resp(404, "")))
    products, status, _ = crawler.run()
    assert status[0]["ok"] and len(products) == 1
    p = products[0]
    assert p["price"] == 297000 and p["compare_at"] == 540000 and p["price_check"]
    assert p["in_stock"] and p["images"][0].endswith("calligraphy.jpg")
    kinds = {w["kind"] for w in crawler.WARN}
    assert {"live_price", "price_mismatch", "size_unverified"} <= kinds
    assert any("432,000" in w["msg"] and "297,000" in w["msg"] for w in crawler.WARN)
    assert [v["name"] for v in p["variants"]] == ["S", "M", "L"] and p["size_unverified"]
    assert p["category"] == "Áo thun & polo"


def test_accessory_cap_soldout_and_keywords(monkeypatch, tmp_path):
    items = [{"handle": f"lanyard-{i}", "title": f"DICO LANYARD {i}", "product_type": "", "tags": [], "images": [{"src": "//x/a.jpg"}],
              "variants": [{"title": "One", "price": "150000", "available": True}]} for i in range(30)]
    items += [{"handle": "tee-out", "title": "DICO TEE", "product_type": "", "tags": [], "images": [{"src": "//x/b.jpg"}],
               "variants": [{"title": "M", "price": "300000", "available": False}]},
              {"handle": "zorb-1", "title": "DICO ZORBLAT THING", "product_type": "", "tags": [], "images": [{"src": "//x/c.jpg"}],
               "variants": [{"title": "M", "price": "300000", "available": True}]}]
    setup(monkeypatch, tmp_path, [{"id": "dico", "name": "DICO", "domain": "dico.vn", "platform": "shopify"}])
    routes = {"https://dico.vn/products.json?limit=250&page=1": Resp(200, {"products": items}),
              "https://dico.vn/products.json?limit=250&page=2": Resp(200, {"products": []})}
    monkeypatch.setattr(crawler, "get", lambda u: routes.get(u, Resp(404, "")))
    products, status, _ = crawler.run()
    cats = [p["category"] for p in products]
    assert cats.count("Phụ kiện") == 20                       # tối đa 20 phụ kiện
    out = next(p for p in products if p["title"] == "DICO TEE")   # hết hàng vẫn hiện, xếp cuối
    assert out["soldout_since"] and products[-1]["title"] == "DICO TEE"
    w = json.loads((tmp_path / "private" / "warnings.json").read_text())
    assert any(k["word"] == "zorblat" for k in w["keywords"])   # từ khoá lạ được báo
    (tmp_path / "site" / "data" / "admin").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "data" / "admin" / "keywords.json").write_text(json.dumps({"zorblat": "Mũ"}))
    products, _, _ = crawler.run()
    assert next(p for p in products if "ZORBLAT" in p["title"])["category"] == "Mũ"


def test_soldout_retired_after_days(monkeypatch, tmp_path):
    items = [{"handle": "tee-out", "title": "DICO TEE", "product_type": "", "tags": [], "images": [{"src": "//x/b.jpg"}],
              "variants": [{"title": "M", "price": "300000", "available": False}]},
             {"handle": "tee-in", "title": "DICO SHIRT", "product_type": "", "tags": [], "images": [{"src": "//x/c.jpg"}],
              "variants": [{"title": "M", "price": "300000", "available": True}]}]
    setup(monkeypatch, tmp_path, [{"id": "dico", "name": "DICO", "domain": "dico.vn", "platform": "shopify"}])
    routes = {"https://dico.vn/products.json?limit=250&page=1": Resp(200, {"products": items}),
              "https://dico.vn/products.json?limit=250&page=2": Resp(200, {"products": []})}
    monkeypatch.setattr(crawler, "get", lambda u: routes.get(u, Resp(404, "")))
    products, _, _ = crawler.run()
    assert len(products) == 2
    # giả sử mẫu đã hết từ 61 ngày trước
    f = tmp_path / "site" / "data" / "products.json"
    d = json.loads(f.read_text())
    for p in d["products"]:
        if p["title"] == "DICO TEE":
            p["soldout_since"] = "2026-01-01T00:00:00+00:00"
    f.write_text(json.dumps(d))
    products, _, _ = crawler.run()
    assert [p["title"] for p in products] == ["DICO SHIRT"]
    d = json.loads(f.read_text())
    assert len(d["retired"]) == 1
    products, _, _ = crawler.run()                      # lần sau vẫn không quay lại
    assert [p["title"] for p in products] == ["DICO SHIRT"]
    items[0]["variants"][0]["available"] = True         # có hàng lại -> lên sàn lại
    routes["https://dico.vn/products.json?limit=250&page=1"] = Resp(200, {"products": items})
    products, _, _ = crawler.run()
    assert len(products) == 2 and not json.loads(f.read_text())["retired"]


def test_first_seen_marks_new_products(monkeypatch, tmp_path):
    mk = lambda h, t: {"handle": h, "title": t, "product_type": "", "tags": [], "images": [{"src": "//x/a.jpg"}],
                       "variants": [{"title": "M", "price": "300000", "available": True}]}
    items = [mk("tee-a", "DICO TEE A")]
    setup(monkeypatch, tmp_path, [{"id": "dico", "name": "DICO", "domain": "dico.vn", "platform": "shopify"}])
    routes = {"https://dico.vn/products.json?limit=250&page=2": Resp(200, {"products": []})}
    routes["https://dico.vn/products.json?limit=250&page=1"] = Resp(200, {"products": items})
    monkeypatch.setattr(crawler, "get", lambda u: routes.get(u, Resp(404, "")))
    products, _, _ = crawler.run()
    assert products[0]["first_seen"] == crawler.OLD_DATE          # lần đầu theo dõi: không tính là hàng mới
    routes["https://dico.vn/products.json?limit=250&page=1"] = Resp(200, {"products": items + [mk("tee-b", "DICO TEE B")]})
    products, _, _ = crawler.run()
    fs = {p["title"]: p["first_seen"] for p in products}
    assert fs["DICO TEE A"] == crawler.OLD_DATE and fs["DICO TEE B"] > "2026-11"


def test_rate_saved_and_kept_on_failure(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, [])
    monkeypatch.setattr(crawler, "get", lambda u: Resp(200, {"rates": {"VND": 18228.6}}) if "er-api" in u else Resp(404, ""))
    crawler.run()
    f = tmp_path / "site" / "data" / "rate.json"
    assert json.loads(f.read_text())["market"] == 18228.6
    monkeypatch.setattr(crawler, "get", lambda u: Resp(500, ""))
    crawler.run()
    assert json.loads(f.read_text())["market"] == 18228.6     # lỗi thì giữ tỷ giá cũ


def test_rate_uses_openexchangerates_hourly(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, [])
    monkeypatch.setenv("OXR_APP_ID", "k")
    calls = []

    def fake(u):
        calls.append(u)
        if "openexchangerates" in u:
            return Resp(200, {"rates": {"AUD": 1.5, "VND": 27300}})
        return Resp(200, {"rates": {"VND": 1}})
    monkeypatch.setattr(crawler, "get", fake)
    crawler.run()
    f = tmp_path / "site" / "data" / "rate.json"
    d = json.loads(f.read_text())
    assert d["source"] == "openexchangerates.org" and d["market"] == 18200.0
    n = len([c for c in calls if "openexchangerates" in c])
    crawler.run()                                   # chạy lại trong cùng giờ: không gọi thêm
    assert len([c for c in calls if "openexchangerates" in c]) == n


def test_haravan_reads_extra_collections(monkeypatch, tmp_path):
    """Món chỉ nằm trong danh mục riêng (vd DICO All Star) cũng phải được đọc."""
    setup(monkeypatch, tmp_path, [{"id": "dico", "name": "DICO", "domain": "dico.vn", "platform": "haravan"}])
    base = dict(DICO_BULK["products"][0])
    star = dict(base, handle="ao-thun-dico-silver-logo", title="Áo Thun DICO Silver Logo")
    routes = {
        "https://dico.vn/collections/all/products.json?limit=250&page=1&sort_by=best-selling": Resp(200, {"products": [base]}),
        "https://dico.vn/collections/all/products.json?limit=250&page=2&sort_by=best-selling": Resp(200, {"products": []}),
        "https://dico.vn/": Resp(200, '<a href="/collections/dico-all-star">All star</a><a href="https://dico.vn/collections/tops">Tops</a>'),
        "https://dico.vn/collections/dico-all-star/products.json?limit=250&page=1": Resp(200, {"products": [star]}),
        "https://dico.vn/collections/dico-all-star/products.json?limit=250&page=2": Resp(200, {"products": []}),
        "https://dico.vn/collections/tops/products.json?limit=250&page=1": Resp(200, {"products": [base]}),
    }
    monkeypatch.setattr(crawler, "get", lambda url: routes.get(url, Resp(404, "")))
    products, status, review = crawler.run()
    titles = sorted(p["title"] for p in products)
    assert len(titles) == 2 and any("Silver Logo" in x for x in titles)
