#!/usr/bin/env python3
"""Chợ Việt crawler: đọc sản phẩm, giá, giá sale, tồn kho từng phân loại và ảnh
từ website brand chạy Shopify hoặc Haravan.

Cách dùng:
    python crawler.py              # chạy tất cả brand trong brands.json
    python crawler.py pushpush     # chỉ chạy một (hoặc vài) brand
Kết quả ghi vào site/data/: products.json, status.json, review.json
"""
import json
import os
import random
import re
import sys
import time
import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "site" / "data"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_PRODUCTS = int(os.environ.get("MAX_PRODUCTS", "500"))  # tối đa mỗi brand; đặt MAX_PRODUCTS=50 để chạy thử nhanh
DELAY = (0.5, 1.2)            # nghỉ giữa các request để không làm phiền web brand
PRICE_MIN, PRICE_MAX = 10_000, 50_000_000   # VND, ngoài khoảng này coi là lỗi
JUMP = 0.40                   # giá đổi quá 40% (không phải sale) thì giữ giá cũ, chờ duyệt
SHRINK = 0.5                  # số sản phẩm tụt quá 50% so với lần trước thì nghi lỗi

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "vi,en;q=0.8"})


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def pause():
    time.sleep(random.uniform(*DELAY))


def get(url):
    """GET có thử lại 3 lần. Trả về Response hoặc None."""
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=25)
            if r.status_code in (200, 404):
                return r
            if r.status_code == 429:          # bị giới hạn tốc độ: nghỉ lâu hơn
                time.sleep(10 * (attempt + 1))
                continue
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    return None


# ---------- chuẩn hoá ----------
def vnd(x, scale=1):
    if x in (None, "", 0, "0"):
        return 0
    try:
        return int(round(float(x) / scale))
    except (TypeError, ValueError):
        return 0


def img_url(src):
    if not src:
        return ""
    src = src if isinstance(src, str) else src.get("src", "")
    return "https:" + src if src.startswith("//") else src


SKIP = "__bỏ__"   # nhóm không đưa lên sàn
CATEGORIES = [  # thứ tự quan trọng: cái nào khớp trước thì nhận
    (SKIP, ["bikini", "swim", "swimwear", "swimsuit", "đồ bơi", "phone case", "ốp lưng", "ốp điện thoại", "case iphone",
            "giày", "dép", "sandal", "sandals", "sneaker", "sneakers", "shoe", "shoes", "slides", "boots", "loafer"]),
    ("Túi", ["balo", "ba lô", "backpack", "túi", "bag", "tote", "ví", "wallet", "crossbody", "duffle"]),
    ("Mũ", ["mũ", "nón", "cap", "hat", "beanie", "bucket", "snapback"]),
    ("Áo khoác", ["áo khoác", "khoác", "jacket", "bomber", "varsity", "windbreaker", "blazer", "parka", "puffer",
                  "outerwear", "coat", "gilet"]),
    ("Áo len & hoodie", ["hoodie", "áo len", "len", "nỉ", "sweater", "sweatshirt", "pullover", "cardigan", "knit",
                         "crewneck", "zip-up", "zip up"]),
    ("Áo thun & polo", ["áo thun", "t-shirt", "tshirt", "tee", "polo", "tank", "tanktop", "ba lỗ", "baby tee", "sleeveless"]),
    ("Sơ mi", ["sơ mi", "shirt", "overshirt", "blouse"]),
    ("Áo thun & polo", ["long sleeve", "longsleeve", "jersey"]),   # "long sleeve" đứng một mình = áo thun tay dài
    ("Quần", ["quần", "pants", "pant", "jeans", "jean", "shorts", "short", "trousers", "jogger", "denim", "cargo"]),
    ("Phụ kiện", ["tất", "vớ", "socks", "belt", "thắt lưng", "móc khoá", "móc khóa", "keychain", "key chain",
                  "lanyard", "dây đeo", "strap", "vòng", "dây chuyền", "necklace", "bracelet", "ring", "sticker",
                  "khẩu trang", "bandana", "scarf", "khăn", "pin", "badge", "patch", "card holder"]),
    ("Váy & đầm", ["váy", "đầm", "dress", "skirt"]),
]
LEGACY = {"Balo": "Túi", "Túi & ví": "Túi", "Áo khoác & hoodie": "Áo khoác", "Giày dép": SKIP, "Đồ bơi": SKIP}


CUSTOM = []       # từ khoá admin tự thêm: [(danh mục, [từ khoá])], ưu tiên trước bộ có sẵn
UNSURE = {}       # từ khoá chưa rõ danh mục -> {"count", "samples"}
STOP = set("the and with for new set ver pack mini basic oversize oversized boxy regular fit slim relaxed logo print graphic "
           "black white grey gray blue navy red pink brown beige cream green olive yellow orange purple size free".split())


def note_unsure(title, brand_words=()):
    for w in re.findall(r"[^\W\d_][\w'-]{2,}", (title or "").lower()):
        if w in STOP or w in brand_words:
            continue
        u = UNSURE.setdefault(w, {"count": 0, "samples": []})
        u["count"] += 1
        if len(u["samples"]) < 3:
            u["samples"].append(title)


# từ chỉ chất liệu/kiểu dệt: chỉ dùng khi tên không có từ nào nói rõ loại áo/quần
# (vd "Knit Polo" là polo, "Denim Jacket" là áo khoác, "Knit Vest" mới là áo len)
WEAK = {"knit", "len", "nỉ", "denim", "jersey", "cargo"}


def categorize(title, ptype="", tags=()):
    def find(text, weak):
        for cat, words in CUSTOM + CATEGORIES:
            for w in words:
                if (w in WEAK) == weak and re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text):
                    return cat
        return None
    # ưu tiên tên sản phẩm, rồi loại sản phẩm, cuối cùng mới tới tag (tag của shop hay gắn bừa theo bộ sưu tập)
    parts = [(title or "").lower(), (ptype or "").lower(), " ".join(tags or []).lower()]
    for weak in (False, True):
        for text in parts:
            c = find(text, weak) if text else None
            if c:
                return c
    return "Khác"   # sẽ hiện trong review.json để người duyệt xếp tay


def make_product(brand, domain, handle, title, ptype, tags, images, variants, opt_names=(), created=""):
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    prices = [v["price"] for v in variants if v["price"]] or [0]
    price = min(prices)
    compare = max([v["compare_at"] for v in variants] + [0])
    return {
        "id": f"{domain}:{handle}",
        "brand": brand,
        "url": f"https://{domain}/products/{handle}",
        "title": (title or "").strip(),
        "type": ptype or "",
        "category": categorize(title, ptype, tags),
        "images": [i for i in images if i][:6],
        "price": price,
        "compare_at": compare if compare > price else 0,
        "option_names": list(opt_names),
        "created": created or "",
        "variants": variants,
        "in_stock": any(v["available"] for v in variants),
    }


# ---------- Shopify ----------
def variant_options(v):
    return [str(x) for x in (v.get("option1"), v.get("option2"), v.get("option3")) if x not in (None, "")]


def grams(v):
    try:
        return int(float(v.get("grams") or v.get("weight") or 0))
    except (TypeError, ValueError):
        return 0


def option_names(p):
    out = []
    for o in p.get("options") or []:
        out.append(o.get("name", "") if isinstance(o, dict) else str(o))
    return out


def shopify_variant(v):
    return {
        "name": v.get("title") or "Mặc định",
        "options": variant_options(v),
        "grams": grams(v),
        "price": vnd(v.get("price")),                 # Shopify: giá đúng đơn vị VND
        "compare_at": vnd(v.get("compare_at_price")),
        "available": bool(v.get("available")),
        "qty": None,                                   # Shopify công khai không trả số lượng
    }


def crawl_shopify(brand, domain):
    out, page = [], 1
    while len(out) < MAX_PRODUCTS:
        r = get(f"https://{domain}/products.json?limit=250&page={page}")
        if r is None or r.status_code != 200:
            if page == 1:
                raise RuntimeError("Không đọc được /products.json")
            break
        items = r.json().get("products", [])
        if not items:
            break
        for p in items:
            out.append(make_product(
                brand, domain, p["handle"], p.get("title"), p.get("product_type"),
                p.get("tags") or [], [img_url(i) for i in p.get("images", [])],
                [shopify_variant(v) for v in p.get("variants", [])], option_names(p),
                p.get("published_at") or p.get("created_at")))
        page += 1
        pause()
    return out[:MAX_PRODUCTS], 0


# ---------- Haravan ----------
HANDLE_RE = re.compile(r"/products/([a-z0-9][a-z0-9\-]*)(?=[\"'?#/\s<]|$)")


def handles_from_sitemap(domain, xml_text, depth=0):
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    locs = [e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text]
    handles = []
    for loc in locs:
        if loc.endswith(".xml"):
            if depth == 0 and "product" in loc.lower():
                r = get(loc)
                if r is not None and r.status_code == 200:
                    handles += handles_from_sitemap(domain, r.text, depth + 1)
        else:
            m = HANDLE_RE.search(loc)
            if m:
                handles.append(m.group(1))
    return handles


def haravan_handles(domain):
    handles = []
    r = get(f"https://{domain}/sitemap.xml")              # cách 1: sitemap
    if r is not None and r.status_code == 200 and r.text.lstrip().startswith("<"):
        handles = handles_from_sitemap(domain, r.text)
    if not handles:                                        # cách 2: trang danh mục
        for page in range(1, 60):
            r = get(f"https://{domain}/collections/all?page={page}")
            if r is None or r.status_code != 200:
                break
            new = [h for h in dict.fromkeys(HANDLE_RE.findall(r.text)) if h not in handles]
            if not new:
                break
            handles += new
            pause()
    return list(dict.fromkeys(handles))[:MAX_PRODUCTS]


def haravan_variant(v, scale=100):
    managed = bool(v.get("inventory_management"))
    qty = v.get("inventory_quantity") if managed else None
    if isinstance(qty, (int, float)):
        qty = max(0, int(qty))
    return {
        "name": v.get("title") or "Mặc định",
        "options": variant_options(v),
        "grams": grams(v),
        "price": vnd(v.get("price"), scale),           # Haravan .js: giá lưu x100 -> chia 100
        "compare_at": vnd(v.get("compare_at_price"), scale),
        "available": bool(v.get("available", True)),
        "qty": qty,                                    # Haravan thường trả số lượng thật
    }


def detect_scale(raw_products):
    """Đoán đơn vị giá: VND thường (1) hay VND x100 (100).
    Giá quần áo VN hầu như không có trung vị trên 5 triệu, nên trung vị quá cao = x100."""
    prices = sorted(vnd(v.get("price")) for p in raw_products for v in p.get("variants", []) if vnd(v.get("price")))
    if not prices:
        return 1
    median = prices[len(prices) // 2]
    return 100 if median > 5_000_000 and all(x % 100 == 0 for x in prices) else 1


def crawl_haravan_bulk(brand, domain):
    """Cách nhanh: /collections/all/products.json (đọc theo lô, không cần từng sản phẩm)."""
    raw, seen, page = [], set(), 1
    while len(raw) < MAX_PRODUCTS and page <= 100:
        r = get(f"https://{domain}/collections/all/products.json?limit=250&page={page}&sort_by=best-selling")
        if r is None or r.status_code != 200:
            break
        try:
            items = r.json().get("products", [])
        except ValueError:
            break
        new = [p for p in items if p.get("handle") and p["handle"] not in seen]
        if not new:            # hết trang, hoặc web trả lại trang cũ
            break
        for p in new:
            seen.add(p["handle"])
        raw += new
        page += 1
        pause()
    raw = raw[:MAX_PRODUCTS]
    scale = detect_scale(raw)
    out = [make_product(
        brand, domain, p["handle"], p.get("title"), p.get("product_type") or p.get("type"),
        p.get("tags") or [], [img_url(i) for i in p.get("images", [])],
        [haravan_variant(v, scale) for v in p.get("variants", [])], option_names(p),
        p.get("published_at") or p.get("created_at")) for p in raw]
    return out


def crawl_haravan(brand, domain):
    bulk = crawl_haravan_bulk(brand, domain)
    if bulk:
        return bulk, 0
    handles = haravan_handles(domain)
    if not handles:
        raise RuntimeError("Không tìm được danh sách sản phẩm (products.json, sitemap và trang danh mục đều trống)")
    out, fails = [], 0
    for n, h in enumerate(handles, 1):
        print(f"  … {brand}: {n}/{len(handles)}", end="\r", flush=True)
        r = get(f"https://{domain}/products/{h}.js")
        pause()
        if r is None or r.status_code != 200:
            fails += 1
            continue
        try:
            p = r.json()
        except ValueError:
            fails += 1
            continue
        out.append(make_product(
            brand, domain, p.get("handle") or h, p.get("title"),
            p.get("type") or p.get("product_type"), p.get("tags") or [],
            [img_url(i) for i in p.get("images", [])],
            [haravan_variant(v) for v in p.get("variants", [])], option_names(p),
            p.get("published_at") or p.get("created_at")))
    if not out:
        raise RuntimeError(f"Tìm được {len(handles)} sản phẩm nhưng không đọc được chi tiết món nào (web chặn hoặc đã tắt cổng dữ liệu)")
    return out, fails


# ---------- Web tự làm: chỉ dùng dữ liệu công khai (sitemap + JSON-LD trên từng trang) ----------
LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
SIZE_MAP_RE = re.compile(r'(?:SIZE_VARIANTS|SIZE_VARIANT_MAP|sizeVariants)\s*=\s*(\{.*?\})\s*;?\s*(?:\n|$|window\.)', re.S)


def ld_product(html):
    for block in LD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for d in (data if isinstance(data, list) else [data]):
            if isinstance(d, dict) and d.get("@type") == "Product":
                return d
    return None


def public_size_map(domain, html):
    """Tìm bảng size công khai (vd /assets/size-variant-map.js). Trả về {slug: [size,…]}."""
    for src in re.findall(r'<script[^>]+src="([^"]*size[^"]*\.js)"', html):
        url = src if src.startswith("http") else f"https://{domain}{src if src.startswith('/') else '/' + src}"
        r = get(url)
        if r is None or r.status_code != 200:
            continue
        m = SIZE_MAP_RE.search(r.text)
        if not m:
            continue
        raw = re.sub(r",\s*([}\]])", r"\1", m.group(1))            # bỏ dấu phẩy thừa kiểu JS
        raw = re.sub(r"([{,]\s*)([A-Za-z_][\w-]*)\s*:", r'\1"\2":', raw)   # khoá chưa có ngoặc kép
        try:
            data = json.loads(raw)
            return {k: list(v.keys()) if isinstance(v, dict) else list(v) for k, v in data.items()}
        except (ValueError, AttributeError):
            continue
    return {}


def parse_price_file(js):
    """Đọc file dữ liệu sản phẩm công khai dạng JS (vd window.RVB_PRODUCTS = [...]).
    Trả về {slug: {price, compare_at, sale, discount}}."""
    out = {}
    parts = re.split(r'["\']?slug["\']?\s*:\s*["\']', js)[1:]
    num = lambda key, chunk: (lambda m: int(m.group(1).replace("_", "").replace(".", "")) if m else 0)(
        re.search(r'(?<![A-Za-z])["\']?' + key + r'["\']?\s*:\s*["\']?([\d_.]+)', chunk))
    for chunk in parts:
        slug = re.match(r'([^"\']+)', chunk).group(1)
        body = chunk[:1500]
        nxt = re.search(r'["\']?slug["\']?\s*:', body)
        body = body[:nxt.start()] if nxt else body
        out[slug] = {"price": num("price", body), "compare_at": num("compareAtPrice", body),
                     "sale": num("salePrice", body), "discount": num("discountPct", body)}
    return out


def public_price_file(domain, html):
    for src in re.findall(r'<script[^>]+src="([^"]*product[^"]*\.js)"', html):
        url = src if src.startswith("http") else f"https://{domain}{src if src.startswith('/') else '/' + src}"
        r = get(url)
        if r is None or r.status_code != 200 or "slug" not in r.text:
            continue
        live = bool(re.search(r"fetch\(\s*['\"]https?://", r.text))   # web tự gọi nguồn giá trực tiếp
        return parse_price_file(r.text), live, url
    return {}, False, ""


OLD_DATE = "2026-01-01T00:00:00+00:00"   # sản phẩm có từ trước khi bắt đầu theo dõi "hàng mới"
WARN = []   # cảnh báo cho admin, ghi ra private/warnings.json


def warn(brand, level, kind, msg, pid="", url=""):
    WARN.append({"brand": brand, "level": level, "kind": kind, "msg": msg, "pid": pid, "url": url})


def crawl_jsonld(brand, domain):
    r = get(f"https://{domain}/sitemap.xml")
    if r is None or r.status_code != 200:
        raise RuntimeError("Không đọc được sitemap.xml")
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", r.text) if re.search(r"/products?/", u)]
    if not urls:
        raise RuntimeError("Sitemap không có trang sản phẩm")
    out, fails, sizes, prices, live = [], 0, None, None, False
    today = dt.date.today().isoformat()
    todo = urls[:MAX_PRODUCTS]
    for n, url in enumerate(todo, 1):
        print(f"  … {brand}: {n}/{len(todo)}", end="\r", flush=True)
        r = get(url)
        pause()
        if r is None or r.status_code != 200:
            fails += 1
            continue
        d = ld_product(r.text)
        if not d:
            fails += 1
            continue
        if sizes is None:
            sizes = public_size_map(domain, r.text)
            prices, live, pfile = public_price_file(domain, r.text)
            if live:
                warn(brand, "high", "live_price",
                     "Web brand tự cập nhật giá trực tiếp từ hệ thống nội bộ. Giá trên VieBuy lấy từ dữ liệu công khai, "
                     "có thể khác giá brand đang hiện. Xác nhận giá với brand trước khi báo giá cuối cho khách.", url=pfile)
        offer = d.get("offers") or {}
        offer = offer[0] if isinstance(offer, list) and offer else offer
        ld_price = vnd(offer.get("price"))
        handle = url.rstrip("/").split("/")[-1]
        pf = (prices or {}).get(handle)
        compare = 0
        if pf and (pf["price"] or pf["compare_at"]):
            base = pf["compare_at"] or pf["price"]
            sale = pf["sale"] if 0 < pf["sale"] < base else 0
            price = sale or pf["price"] or base
            compare = base if price < base else 0
        else:
            price = ld_price
        checks = []
        if ld_price and price and abs(ld_price - price) / price > 0.01:
            checks.append(f"Hai nguồn công khai báo giá khác nhau: trang sản phẩm {ld_price:,}₫, file dữ liệu {price:,}₫")
        until = str(offer.get("priceValidUntil", ""))[:10]
        if until and until < today:
            checks.append(f"Giá trên trang ghi hạn đến {until}, đã qua, có thể là giá khuyến mãi cũ")
        for c in checks:
            warn(brand, "medium", "price_mismatch", c, pid=f"{domain}:{handle}", url=url)
        avail = "InStock" in str(offer.get("availability", "")) or "PreOrder" in str(offer.get("availability", ""))
        img = d.get("image")
        imgs = img if isinstance(img, list) else [img] if img else []
        size_list = sizes.get(handle) or []
        # web chỉ công khai còn/hết cho cả sản phẩm, không công khai từng size -> size được xác nhận lại khi chốt đơn
        variants = [{"name": s_, "options": [s_], "grams": 0, "price": price, "compare_at": compare,
                     "available": avail, "qty": None} for s_ in size_list] or \
                   [{"name": "Default Title", "options": [], "grams": 0, "price": price, "compare_at": compare,
                     "available": avail, "qty": None}]
        p = make_product(brand, domain, handle, d.get("name", ""), d.get("category", ""), [],
                         [img_url(i if isinstance(i, str) else (i or {}).get("url", "")) for i in imgs], variants)
        p["url"] = url
        p["size_unverified"] = bool(size_list)
        p["price_check"] = bool(live or checks)
        out.append(p)
    print(" " * 40, end="\r")
    if sizes:
        warn(brand, "low", "size_unverified", "Web brand không công khai tồn kho từng size. Size được xác nhận lại với brand khi chốt đơn.")
    if not out:
        raise RuntimeError(f"Có {len(urls)} trang sản phẩm nhưng không đọc được trang nào")
    return out, fails


def detect_platform(domain):
    r = get(f"https://{domain}/products.json?limit=1")
    if r is not None and r.status_code == 200:
        try:
            if "products" in r.json():
                return "shopify"
        except ValueError:
            pass
    r = get(f"https://{domain}/")
    if r is not None and ("hstatic.net" in r.text or "haravan" in r.text.lower()):
        return "haravan"
    return "jsonld"   # web tự làm: thử đọc dữ liệu công khai


# ---------- kiểm tra chính xác ----------
def check_product(p, prev, review):
    """Trả về danh sách vấn đề. Có thể sửa p (giữ giá cũ khi giá nhảy bất thường)."""
    issues = []
    if not p["title"]:
        issues.append("thiếu tên")
    if not p["images"]:
        issues.append("thiếu ảnh")
    if not (PRICE_MIN <= p["price"] <= PRICE_MAX):
        issues.append(f"giá ngoài khoảng hợp lý: {p['price']:,}₫")
    if p["category"] == "Khác" and not p.get("category_locked"):
        review.append({"type": "category", "id": p["id"], "title": p["title"],
                       "note": "Chưa xếp được danh mục"})
    if prev and prev.get("price") and p["price"]:
        change = abs(p["price"] - prev["price"]) / prev["price"]
        explained_by_sale = p["compare_at"] and abs(p["compare_at"] - prev["price"]) / prev["price"] < 0.05
        ended_sale = prev.get("compare_at") and abs(p["price"] - prev["compare_at"]) / prev["compare_at"] < 0.05
        if change > JUMP and not explained_by_sale and not ended_sale:
            review.append({"type": "price_jump", "id": p["id"], "title": p["title"],
                           "old": prev["price"], "new": p["price"]})
            p["price"], p["compare_at"], p["price_held"] = prev["price"], prev.get("compare_at", 0), True
    p["sellable"] = not issues
    p["issues"] = issues
    return issues


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)   # ghi xong mới thay file, web không bao giờ đọc phải file dở


RATE_SOURCES = [   # tỷ giá thị trường miễn phí, không cần key (cập nhật vài lần/ngày)
    ("open.er-api.com", "https://open.er-api.com/v6/latest/AUD", lambda j: j["rates"]["VND"]),
    ("fawazahmed0/currency-api", "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/aud.json", lambda j: j["aud"]["vnd"]),
]


def update_rate():
    """Lấy tỷ giá AUD→VND mới nhất, ghi site/data/rate.json. Lỗi thì giữ file cũ.
    Có OXR_APP_ID (Open Exchange Rates, gói Free cập nhật mỗi giờ) thì dùng trước, tối đa 1 lần/giờ."""
    key = os.environ.get("OXR_APP_ID", "").strip()
    old = load(DATA / "rate.json", {})
    if key:
        fresh = old.get("source") == "openexchangerates.org" and old.get("updated", "") > (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=50)).isoformat(timespec="seconds")
        if fresh:
            return old.get("market")
        try:
            r = get(f"https://openexchangerates.org/api/latest.json?app_id={key}&symbols=AUD,VND")
            j = r.json() if r is not None and r.status_code == 200 else {}
            v = float(j["rates"]["VND"]) / float(j["rates"]["AUD"])
        except Exception:  # noqa: BLE001
            v = 0
        if 10000 < v < 40000:
            save(DATA / "rate.json", {"market": round(v, 2), "source": "openexchangerates.org", "updated": now_iso()})
            return v
    for name, url, pick in RATE_SOURCES:
        try:
            r = get(url)
            v = float(pick(r.json())) if r is not None and r.status_code == 200 else 0
        except Exception:  # noqa: BLE001
            v = 0
        if 10000 < v < 40000:   # chặn số vô lý
            save(DATA / "rate.json", {"market": round(v, 2), "source": name, "updated": now_iso()})
            return v
    print("  ⚠ Không lấy được tỷ giá, giữ tỷ giá cũ")
    return None


def run(only=None):
    brands = load(ROOT / "brands.json", [])
    prev_file = load(DATA / "products.json", {"products": []})
    prev_products = prev_file["products"]
    retired = dict(prev_file.get("retired") or {})   # id → ngày bắt đầu hết hàng, đã gỡ khỏi sàn
    prev_by_id = {p["id"]: p for p in prev_products}
    prev_status = {b["id"]: b for b in load(DATA / "status.json", {"brands": []})["brands"]}
    WARN.clear()
    UNSURE.clear()
    CUSTOM.clear()
    by_cat = {}
    for kw, cat in load(DATA / "admin" / "keywords.json", {}).items():
        by_cat.setdefault(LEGACY.get(cat, cat), []).append(kw.lower())
    CUSTOM.extend(by_cat.items())
    cfg = load(DATA / "admin" / "settings.json", {})
    acc_cap = int(cfg.get("acc_cap", 20))
    soldout_days = float(cfg.get("soldout_days", 60))   # hết hàng quá số ngày này thì gỡ khỏi sàn
    now = dt.datetime.now(dt.timezone.utc)

    def age_days(iso):
        try:
            t = dt.datetime.fromisoformat(iso)
            return (now - (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc))).total_seconds() / 86400
        except (TypeError, ValueError):
            return 0
    overrides = load(DATA / "admin" / "overrides.json", {})   # danh mục admin đã xếp tay
    products, status, review = [], [], []

    for b in brands:
        bid, domain = b["id"], b["domain"]
        old = [p for p in prev_products if p["brand"] == bid]
        if only and bid not in only:
            products += old
            if bid in prev_status:
                status.append(prev_status[bid])
            continue
        t0 = time.time()
        st = {"id": bid, "name": b["name"], "domain": domain, "instagram": b.get("instagram", ""),
              "checked_at": now_iso()}
        try:
            plat = b.get("platform") or detect_platform(domain)
            st["platform"] = plat
            if plat == "shopify":
                items, fails = crawl_shopify(bid, domain)
            elif plat == "haravan":
                items, fails = crawl_haravan(bid, domain)
            elif plat == "jsonld":
                items, fails = crawl_jsonld(bid, domain)
            else:
                raise RuntimeError("Chưa hỗ trợ nền tảng này (cần crawler chạy trình duyệt)")
            if old and len(items) < min(len(old), MAX_PRODUCTS) * SHRINK:
                raise RuntimeError(f"Chỉ lấy được {len(items)}/{len(old)} sản phẩm so với lần trước, nghi lỗi")
            for p in items:
                ov = overrides.get(p["id"])
                if ov and ov.get("category"):
                    p["category"], p["category_locked"] = LEGACY.get(ov["category"], ov["category"]), True
                prev = prev_by_id.get(p["id"])
                check_product(p, prev, review)
                # ngày lần đầu thấy sản phẩm (để xếp hàng mới lên đầu + báo cáo hằng ngày)
                if prev:
                    p["first_seen"] = prev.get("first_seen") or OLD_DATE
                    p["price_changed_at"] = now_iso() if prev.get("price") and prev["price"] != p["price"] else prev.get("price_changed_at", "")
                else:
                    p["first_seen"] = now_iso() if old and p["id"] not in retired else OLD_DATE
            total_read = len(items)
            items = [p for p in items if p["category"] != SKIP]   # bỏ đồ bơi, ốp điện thoại, giày dép
            # chọn hàng lên sàn: ưu tiên còn hàng, giữ thứ tự bán chạy của brand (nếu web brand hỗ trợ)
            # hết hàng: vẫn hiện (xếp cuối) và ghi ngày bắt đầu hết; hết quá soldout_days ngày thì gỡ
            keep = []
            for p in items:
                if p["in_stock"]:
                    retired.pop(p["id"], None)
                    keep.append(p)
                    continue
                prev = prev_by_id.get(p["id"]) or {}
                p["soldout_since"] = prev.get("soldout_since") or retired.get(p["id"]) or now_iso()
                if age_days(p["soldout_since"]) >= soldout_days:
                    retired[p["id"]] = p["soldout_since"]
                else:
                    keep.append(p)
            items = keep
            items.sort(key=lambda p: not p["in_stock"])
            acc = [p for p in items if p["category"] == "Phụ kiện"]
            if len(acc) > acc_cap:
                drop = {p["id"] for p in acc[acc_cap:]}
                items = [p for p in items if p["id"] not in drop]
            bw = set(b["name"].lower().split()) | {domain.split(".")[0]}
            for p in items:
                if p["category"] == "Khác" and not p.get("category_locked"):
                    note_unsure(p["title"], bw)
            products += items
            st.update(ok=True, last_ok=now_iso(), products=len(items), read=total_read, failed=fails,
                      bad=sum(1 for p in items if not p["sellable"]),
                      seconds=round(time.time() - t0, 1), error="")
            print(f"✓ {b['name']}: {len(items)} sản phẩm lên sàn (đọc {total_read}), {fails} lỗi, {st['bad']} cần xem")
        except Exception as e:   # brand lỗi: giữ dữ liệu cũ, đánh dấu cũ
            products += old
            prev = prev_status.get(bid, {})
            st.update(ok=False, last_ok=prev.get("last_ok", ""), products=len(old),
                      failed=0, bad=0, seconds=round(time.time() - t0, 1), error=str(e)[:200])
            st.setdefault("platform", b.get("platform", ""))
            print(f"✕ {b['name']}: {e}")
        status.append(st)

    update_rate()
    retired = {k: v for k, v in retired.items() if age_days(v) < 400}   # quên các mẫu đã gỡ hơn 1 năm
    save(DATA / "products.json", {"generated_at": now_iso(), "products": products, "retired": retired})
    save(DATA / "status.json", {"generated_at": now_iso(), "brands": status})
    save(DATA / "review.json", {"generated_at": now_iso(), "items": review})
    for st_ in status:
        if not st_.get("ok"):
            warn(st_["id"], "high", "sync_error", f"Đồng bộ lỗi: {st_.get('error','')}. Đang dùng dữ liệu cũ từ lần thành công gần nhất.")
        elif st_.get("failed"):
            warn(st_["id"], "low", "partial", f"{st_['failed']} sản phẩm không đọc được ở lần đồng bộ này.")
    owner = {p["id"]: p["brand"] for p in products}
    for it in review:
        if it["type"] == "price_jump":
            warn(owner.get(it["id"], it["id"].split(":")[0]), "high", "price_jump",
                 f"Giá đổi bất thường {it['old']:,}₫ → {it['new']:,}₫. Đang giữ giá cũ, cần kiểm tra.", pid=it["id"])
    for p in products:
        for iss in p.get("issues", []):
            warn(p["brand"], "medium", "bad_data", f"{p['title']}: {iss}. Sản phẩm đang bị ẩn.", pid=p["id"], url=p["url"])
    unsure = sorted(({"word": w, **u} for w, u in UNSURE.items() if u["count"] >= 1), key=lambda x: -x["count"])[:40]
    if unsure:
        print("\nTừ khoá chưa rõ danh mục (vào admin → Danh mục để gán):")
        for u in unsure[:15]:
            print(f"  · {u['word']} ({u['count']} sp) — vd: {u['samples'][0][:60]}")
    wf = Path(os.environ.get("WARNINGS_FILE") or ROOT / "private" / "warnings.json")
    wf.parent.mkdir(parents=True, exist_ok=True)
    save(wf, {"generated_at": now_iso(), "items": WARN, "keywords": unsure})
    print(f"Xong: {len(products)} sản phẩm, {len(review)} mục chờ duyệt")
    return products, status, review


if __name__ == "__main__":
    run(set(sys.argv[1:]) or None)
