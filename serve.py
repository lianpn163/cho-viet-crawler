#!/usr/bin/env python3
"""Máy chủ chạy trên laptop: phục vụ website + lưu dữ liệu admin.

    python3 serve.py
    Website khách:  http://localhost:8000
    Trang admin:    http://localhost:8000/admin   (trang riêng, không nằm trong website khách)

Lần đầu chạy sẽ hỏi đặt mật khẩu admin. Mật khẩu chỉ lưu dạng mã hoá trong private/.
Muốn đổi mật khẩu: xoá file private/admin_config.json rồi chạy lại.
"""
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import datetime as dt
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
ADMIN = SITE / "data" / "admin"          # dữ liệu admin mà website cần đọc (danh mục, clip, brand…)
PRIVATE = ROOT / "private"               # không bao giờ được phục vụ ra ngoài: mật khẩu, đơn hàng
CONFIG = PRIVATE / "admin_config.json"
ORDERS = PRIVATE / "orders.json"
NOTIFY = PRIVATE / "notify.json"
DELETED = PRIVATE / "deleted_orders.json"   # đơn đã xoá: không kéo lại từ Google
ADMIN_PAGE = ROOT / "admin" / "index.html"   # trang admin nằm NGOÀI thư mục site: không bao giờ bị đưa lên web
MEDIA = ADMIN / "media"
SAVABLE = {"overrides.json", "clips.json", "brands_admin.json", "settings.json", "articles.json", "keywords.json"}
PRIVATE_SAVABLE = {"payment.json", "remote.json"}   # thông tin chuyển khoản: chỉ admin đọc được, không bao giờ lên web
ORDER_STATUS = {"new", "awaiting_deposit", "deposit_paid", "ordered", "awaiting_balance", "shipped", "done", "cancelled"}
IMG_MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp", b"GIF8": "gif"}
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "127.0.0.1")
AUTO_SYNC_HOURS = float(os.environ.get("AUTO_SYNC_HOURS", "0") or 0)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CFG = {}
SYNC = {"running": False, "output": "", "finished_at": ""}
LOCK = threading.Lock()


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def setup_password():
    PRIVATE.mkdir(exist_ok=True)
    cfg = load(CONFIG, None)
    if cfg:
        return cfg
    print("\nLần đầu chạy: đặt mật khẩu admin (gõ sẽ không hiện chữ, gõ xong bấm Enter)")
    while True:
        p1 = getpass.getpass("Mật khẩu (ít nhất 6 ký tự): ")
        p2 = getpass.getpass("Nhập lại: ")
        if len(p1) >= 6 and p1 == p2:
            break
        print("Chưa được: cần ít nhất 6 ký tự và hai lần gõ phải giống nhau.\n")
    salt = secrets.token_hex(16)
    cfg = {"salt": salt, "hash": hash_pw(p1, salt)}
    save(CONFIG, cfg)
    print("Đã lưu mật khẩu.\n")
    return cfg


def check_pw(pw):
    return bool(pw) and hmac.compare_digest(hash_pw(pw, CFG["salt"]), CFG["hash"])


def resolve_tiktok(url):
    """Từ link TikTok -> mã video, tác giả, tiêu đề, ảnh thumbnail (tải về máy)."""
    if not re.match(r"^https://(www\.|vm\.|vt\.|m\.)?tiktok\.com/", url):
        raise ValueError("Link phải bắt đầu bằng https://www.tiktok.com/ hoặc https://vm.tiktok.com/")
    final = url
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20, allow_redirects=True)
        final = r.url
    except requests.RequestException:
        pass
    m = re.search(r"/video/(\d+)", final) or re.search(r"/video/(\d+)", url)
    if not m:
        raise ValueError("Không tìm thấy mã video trong link. Hãy dùng link có dạng …/video/123…")
    vid = m.group(1)
    info = {}
    try:
        o = requests.get("https://www.tiktok.com/oembed", params={"url": final if "/video/" in final else url},
                         headers={"User-Agent": UA}, timeout=20)
        if o.ok:
            info = o.json()
    except (requests.RequestException, ValueError):
        pass
    hm = re.search(r"@([\w.]+)", final) or re.search(r"@([\w.]+)", url)
    handle = info.get("author_unique_id") or (hm.group(1) if hm else "")
    clean = f"https://www.tiktok.com/@{handle}/video/{vid}" if handle else final.split("?")[0]
    if not info:   # thử lại oEmbed với link gọn (bỏ ?is_from_webapp=…)
        try:
            o = requests.get("https://www.tiktok.com/oembed", params={"url": clean},
                             headers={"User-Agent": UA}, timeout=20)
            if o.ok:
                info = o.json()
        except (requests.RequestException, ValueError):
            pass
    candidates = [info.get("thumbnail_url")]
    if not candidates[0]:  # dự phòng: ảnh og:image trên trang video
        try:
            page = requests.get(clean, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=20).text
            m2 = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', page)
            if m2:
                candidates.append(m2.group(1).replace("&amp;", "&"))
        except requests.RequestException:
            pass
    thumb, remote = "", ""
    for cu in [c for c in candidates if c]:
        remote = remote or cu
        try:
            t = requests.get(cu, headers={"User-Agent": UA, "Referer": "https://www.tiktok.com/"}, timeout=20)
            if t.ok and len(t.content) > 1000 and t.content[:3] in (b"\xff\xd8\xff", b"\x89PN", b"RIF", b"GIF"):
                (ADMIN / "thumbs").mkdir(parents=True, exist_ok=True)
                (ADMIN / "thumbs" / f"{vid}.jpg").write_bytes(t.content)
                thumb = f"data/admin/thumbs/{vid}.jpg"
                break
            print(f"[clip] tải thumbnail lỗi: HTTP {t.status_code}, {len(t.content)} byte")
        except requests.RequestException as e:
            print(f"[clip] tải thumbnail lỗi: {e}")
    if not candidates[0]:
        print(f"[clip] oEmbed không trả thumbnail cho {clean}")
    # tải về không được thì vẫn giữ link ảnh gốc để trình duyệt tự tải (có thể hết hạn sau vài ngày)
    return {"id": vid, "handle": handle, "author": info.get("author_name") or handle,
            "title": info.get("title", ""), "thumb": thumb or remote, "url": clean}


def run_sync(max_products, ids=()):
    env = dict(os.environ)
    if max_products:
        env["MAX_PRODUCTS"] = str(max_products)
    try:
        p = subprocess.run([sys.executable, str(ROOT / "crawler.py"), *ids], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=3600)
        out = (p.stdout + p.stderr)[-4000:]
    except Exception as e:  # noqa: BLE001
        out = f"Lỗi: {e}"
    with LOCK:
        SYNC.update(running=False, output=out, finished_at=dt.datetime.now().strftime("%H:%M:%S"))


def bag_token(oid):
    """Mã bảo vệ link "Update your bag" (giống hệt cách Google Apps Script tính)."""
    secret = (load(PRIVATE / "remote.json", {}).get("secret") or "").strip()
    return hashlib.sha256(f"{secret}:{oid}".encode()).hexdigest()[:12] if secret else ""


def apply_bag_update(o, items, totals):
    """Khách đổi món: thay món của đơn, xoá phần đã tick để bạn kiểm tra lại từ đầu."""
    if o.get("confirm"):
        o["prev_confirm"] = o.pop("confirm")
    o["items"], o["totals"] = items, totals or {}
    o.pop("avail", None)   # món mới: tick lại từ đầu
    o["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    o["update_count"] = o.get("update_count", 0) + 1


def pull_online():
    """Kéo đơn hàng + đăng ký báo hàng từ Google, và dữ liệu sản phẩm mới nhất từ web online về máy."""
    settings = load(SITE / "data" / "admin" / "settings.json", {})
    ep = (settings.get("order_endpoint") or "").strip()
    site = (settings.get("site_url") or "").strip().rstrip("/")
    secret = (load(PRIVATE / "remote.json", {}).get("secret") or "").strip()
    out = {"orders": 0, "notify": 0, "data": False, "msgs": []}
    if ep and secret:
        try:
            j = requests.get(ep, params={"key": secret}, timeout=30).json()
            if j.get("error"):
                out["msgs"].append("Google từ chối: kiểm tra lại mã bí mật")
            else:
                orders = load(ORDERS, [])
                gone = set(load(DELETED, []))
                by_id = {o.get("id"): o for o in orders}
                remote = [o for o in j.get("orders", []) if isinstance(o, dict) and o.get("id") and o["id"] not in gone]
                new = [o for o in remote if o["id"] not in by_id]
                for o in new:
                    o["remote_updated_at"] = o.get("updated_at")
                upd = 0
                for ro in remote:   # khách đã cập nhật giỏ trên web
                    lo = by_id.get(ro["id"])
                    if lo and ro.get("updated_at") and ro.get("updated_at") != lo.get("remote_updated_at"):
                        apply_bag_update(lo, ro.get("items") or lo["items"], ro.get("totals"))
                        lo["remote_updated_at"] = ro["updated_at"]
                        upd += 1
                if new or upd:
                    orders = sorted(new, key=lambda o: o.get("created", ""), reverse=True) + orders
                    save(ORDERS, orders)
                out["updated"] = upd
                notes = load(NOTIFY, [])
                haven = {n.get("id") for n in notes}
                newn = [n for n in j.get("notify", []) if isinstance(n, dict) and n.get("id") and n["id"] not in haven]
                if newn:
                    save(NOTIFY, newn[::-1] + notes)
                out.update(orders=len(new), notify=len(newn))
        except Exception as e:  # noqa: BLE001
            out["msgs"].append(f"Không lấy được đơn từ Google: {e}")
    elif ep or secret:
        out["msgs"].append("Thiếu link Google Apps Script hoặc mã bí mật (Cài đặt → Online)")
    else:
        out["msgs"].append(f"Chưa cài web online (Cài đặt → Online). Đang đọc cài đặt ở: {SITE / 'data' / 'admin' / 'settings.json'}")
    if site:
        try:
            got = {}
            for f in ("products", "status", "review", "warnings"):
                r = requests.get(f"{site}/data/{f}.json", timeout=30)
                if r.ok:
                    got[f] = r.json()
            if "products" in got and got["products"].get("products"):
                for f in ("products", "status", "review"):
                    if f in got:
                        save(SITE / "data" / f"{f}.json", got[f])
                if "warnings" in got:
                    save(PRIVATE / "warnings.json", got["warnings"])
                out["data"] = True
            else:
                out["msgs"].append("Web online chưa có dữ liệu sản phẩm")
        except Exception as e:  # noqa: BLE001
            out["msgs"].append(f"Không lấy được dữ liệu từ web online: {e}")
    return out


def auto_sync():
    """Tự chạy crawler mỗi AUTO_SYNC_HOURS giờ (bật trên máy chủ online)."""
    while True:
        with LOCK:
            busy = SYNC["running"]
            if not busy:
                SYNC.update(running=True, output="Tự đồng bộ…")
        if not busy:
            print(time.strftime("%d/%m %H:%M"), "tự đồng bộ bắt đầu", flush=True)
            run_sync(None)
            print(time.strftime("%d/%m %H:%M"), "tự đồng bộ xong", flush=True)
        time.sleep(AUTO_SYNC_HOURS * 3600)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(SITE), **k)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if args and "/api/" in str(args[0]):
            sys.stderr.write("%s\n" % (fmt % args))

    def reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 12_000_000:
            raise ValueError("quá lớn")
        return json.loads(self.rfile.read(n) or b"{}")

    def is_admin(self):
        if check_pw(self.headers.get("X-Admin-Password", "")):
            return True
        time.sleep(1)                      # chống dò mật khẩu
        self.reply(401, {"error": "Sai mật khẩu admin"})
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/admin", "/admin/"):
            body = ADMIN_PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/warnings":
            if self.is_admin():
                self.reply(200, load(PRIVATE / "warnings.json", {"items": []}))
            return
        if path == "/api/private":
            name = urlparse(self.path).query.replace("file=", "")
            if self.is_admin():
                if name not in PRIVATE_SAVABLE:
                    return self.reply(400, {"error": "Không có file này"})
                self.reply(200, load(PRIVATE / name, {}))
            return
        if path == "/api/brands":
            if self.is_admin():
                self.reply(200, load(ROOT / "brands.json", []))
            return
        if path == "/api/notify-list":
            if self.is_admin():
                self.reply(200, load(NOTIFY, []))
            return
        if path == "/api/orders":
            if self.is_admin():
                self.reply(200, load(ORDERS, []))
            return
        if path == "/api/sync-status":
            if self.is_admin():
                with LOCK:
                    self.reply(200, dict(SYNC))
            return
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json()
        except ValueError:
            return self.reply(400, {"error": "Dữ liệu không hợp lệ"})
        if path == "/api/order":
            return self.order(data)
        if path == "/api/update":   # (chạy thử trên máy) khách gửi lại giỏ từ link trong email
            oid = re.sub(r"[^A-Za-z0-9-]", "", str(data.get("ref", "")))[:20]
            tok = bag_token(oid)
            if tok and str(data.get("t", "")) != tok:
                return self.reply(400, {"error": "This link has expired. Please reply to our email and we will help."})
            orders = load(ORDERS, [])
            o = next((x for x in orders if x.get("id") == oid), None)
            items = (data.get("items") or [])[:50]
            if not o or not items:
                return self.reply(400, {"error": "We could not find this order. Please reply to our email and we will help."})
            apply_bag_update(o, items, data.get("totals"))
            save(ORDERS, orders)
            return self.reply(200, {"id": oid})
        if path == "/api/notify":
            return self.notify(data)
        if not self.is_admin():
            return
        if path == "/api/login":
            return self.reply(200, {"ok": True})
        if path == "/api/save":
            name = data.get("file")
            if name not in SAVABLE:
                return self.reply(400, {"error": "Không được lưu file này"})
            save(ADMIN / name, data.get("data"))
            return self.reply(200, {"ok": True})
        if path == "/api/brands":
            clean, seen = [], set()
            for b in data.get("brands") or []:
                bid = re.sub(r"[^a-z0-9-]", "", str(b.get("id", "")).lower())[:40]
                dom = re.sub(r"^https?://", "", str(b.get("domain", "")).strip().lower()).split("/")[0].removeprefix("www.")
                if not bid or bid in seen or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", dom):
                    return self.reply(400, {"error": f"Brand không hợp lệ: {b.get('name') or bid or dom}"})
                plat = b.get("platform", "")
                seen.add(bid)
                clean.append({"id": bid, "name": str(b.get("name") or bid)[:60], "domain": dom,
                              "platform": plat if plat in ("", "shopify", "haravan", "jsonld") else "",
                              "instagram": str(b.get("instagram", "")).lstrip("@")[:40]})
            save(ROOT / "brands.json", clean)
            return self.reply(200, {"ok": True, "brands": clean})
        if path == "/api/private-save":
            name = data.get("file")
            if name not in PRIVATE_SAVABLE:
                return self.reply(400, {"error": "Không được lưu file này"})
            save(PRIVATE / name, data.get("data"))
            return self.reply(200, {"ok": True})
        if path == "/api/order-update":
            orders = load(ORDERS, [])
            o = next((x for x in orders if x.get("id") == data.get("id")), None)
            if not o:
                return self.reply(404, {"error": "Không tìm thấy đơn"})
            patch = data.get("patch") or {}
            if "status" in patch:
                if patch["status"] not in ORDER_STATUS:
                    return self.reply(400, {"error": "Trạng thái không hợp lệ"})
                o["status"] = patch["status"]
                o.setdefault("history", []).append({"at": dt.datetime.now().isoformat(timespec="seconds"), "status": patch["status"]})
            ff = patch.get("items_ff")
            if isinstance(ff, list) and len(ff) == len(o.get("items", [])):
                ok = {"pending", "ordered", "brand_shipped", "at_hub", "shipped_au", "unavailable"}
                for it, v in zip(o["items"], ff):
                    if v in ok:
                        it["ff"] = v
            av = patch.get("avail")
            if isinstance(av, list) and len(av) == len(o.get("items", [])):
                o["avail"] = [None if v is None else bool(v) for v in av]
            if isinstance(patch.get("confirm"), dict):
                o["confirm"] = patch["confirm"]
            if isinstance(patch.get("cost"), dict):
                o["cost"] = {k: patch["cost"][k] for k in ("kg", "route", "extra") if k in patch["cost"]}
            if isinstance(patch.get("email_log"), dict):   # đã gửi email chặng nào
                o.setdefault("emails", []).append({"tpl": str(patch["email_log"].get("tpl", ""))[:20],
                                                   "at": dt.datetime.now().isoformat(timespec="seconds")})
                o["emails"] = o["emails"][-30:]
            if isinstance(patch.get("ship"), dict):          # hãng + mã tracking
                o["ship"] = {k: str(patch["ship"].get(k, ""))[:200] for k in ("carrier", "number", "link")}
            if "admin_note" in patch:
                o["admin_note"] = str(patch["admin_note"])[:1000]
            save(ORDERS, orders)
            return self.reply(200, {"ok": True, "order": o})
        if path == "/api/notify-done":
            items = load(NOTIFY, [])
            for it in items:
                if it.get("id") == data.get("id"):
                    it["done"] = bool(data.get("done"))
            save(NOTIFY, items)
            return self.reply(200, {"ok": True})
        if path == "/api/upload":
            try:
                raw = base64.b64decode(str(data.get("data", "")).split(",", 1)[-1], validate=True)
            except (ValueError, TypeError):
                return self.reply(400, {"error": "Ảnh không đọc được"})
            ext = next((e for m, e in IMG_MAGIC.items() if raw.startswith(m)), None)
            if not ext or len(raw) > 8_000_000:
                return self.reply(400, {"error": "Chỉ nhận ảnh JPG, PNG, WEBP, GIF dưới 8MB"})
            MEDIA.mkdir(parents=True, exist_ok=True)
            name = f"{dt.datetime.now():%Y%m%d}-{secrets.token_hex(4)}.{ext}"
            (MEDIA / name).write_bytes(raw)
            return self.reply(200, {"path": f"data/admin/media/{name}"})
        if path == "/api/clip":
            try:
                return self.reply(200, resolve_tiktok(str(data.get("url", "")).strip()))
            except ValueError as e:
                return self.reply(400, {"error": str(e)})
        if path == "/api/send-email":
            settings = load(SITE / "data" / "admin" / "settings.json", {})
            ep = (settings.get("order_endpoint") or "").strip()
            secret = (load(PRIVATE / "remote.json", {}).get("secret") or "").strip()
            if not ep or not secret:
                return self.reply(400, {"error": "Chưa nối Google (Cài đặt → Online: link Apps Script + mã bí mật)"})
            payload = {"kind": "mail", "key": secret, **{k: str(data.get(k, "")) for k in ("to", "subject", "html", "text", "reply_to")}}
            imgs = data.get("images") or []
            if isinstance(imgs, list):
                payload["images"] = [{"mime": str(i.get("mime", "image/jpeg"))[:40], "data": str(i.get("data", ""))}
                                     for i in imgs[:10] if isinstance(i, dict) and len(str(i.get("data", ""))) < 3_000_000]
            try:
                r = requests.post(ep, data=json.dumps(payload), headers={"Content-Type": "text/plain"}, timeout=45)
                j = r.json()
            except Exception as e:  # noqa: BLE001
                return self.reply(502, {"error": f"Không gửi được qua Google: {e}"})
            if j.get("error") == "forbidden":
                return self.reply(400, {"error": "Google từ chối: mã bí mật trong admin khác dòng SECRET trong Apps Script"})
            if j.get("error") == "Unknown request":
                return self.reply(400, {"error": "Apps Script đang là bản cũ: dán code mới rồi Deploy → New version"})
            if j.get("error"):
                return self.reply(400, {"error": "Google: " + str(j["error"])})
            return self.reply(200, {"ok": True})
        if path == "/api/order-delete":
            oid = str(data.get("id", ""))
            orders = load(ORDERS, [])
            if not any(o.get("id") == oid for o in orders):
                return self.reply(404, {"error": "Không tìm thấy đơn"})
            save(ORDERS, [o for o in orders if o.get("id") != oid])
            gone = load(DELETED, [])
            if oid not in gone:
                save(DELETED, (gone + [oid])[-5000:])
            return self.reply(200, {"ok": True})
        if path == "/api/pull":
            return self.reply(200, pull_online())
        if path == "/api/sync":
            with LOCK:
                if SYNC["running"]:
                    return self.reply(409, {"error": "Đang đồng bộ, chờ chút"})
                SYNC.update(running=True, output="Đang chạy…")
            ids = [b for b in (data.get("brands") or []) if re.fullmatch(r"[a-z0-9-]{1,40}", str(b))]
            threading.Thread(target=run_sync, args=(data.get("max_products"), ids), daemon=True).start()
            return self.reply(202, {"ok": True})
        return self.reply(404, {"error": "Không có chức năng này"})

    def notify(self, d):
        email = str(d.get("email", "")).strip()[:120]
        phone = re.sub(r"[^\d+ ]", "", str(d.get("phone", "")))[:20].strip()
        if not (re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or len(re.sub(r"\D", "", phone)) >= 8):
            return self.reply(400, {"error": "Please enter a valid email or mobile number"})
        items = load(NOTIFY, [])
        if len(items) > 5000:
            return self.reply(429, {"error": "We're busy right now, please try again later"})
        items.insert(0, {"id": secrets.token_hex(4), "created": dt.datetime.now().isoformat(timespec="seconds"),
                         "pid": str(d.get("pid", ""))[:200], "title": str(d.get("title", ""))[:200],
                         "url": str(d.get("url", ""))[:300], "brand": str(d.get("brand", ""))[:80],
                         "variant": str(d.get("variant", ""))[:80], "email": email, "phone": phone, "done": False})
        save(NOTIFY, items)
        return self.reply(200, {"ok": True})

    def order(self, d):
        items = d.get("items") or []
        need = [d.get("name"), d.get("email"), d.get("address")]
        if not all(isinstance(x, str) and x.strip() for x in need) or not items or len(items) > 50:
            return self.reply(400, {"error": "Some order details are missing"})
        code = "VB-" + secrets.token_hex(3).upper()
        orders = load(ORDERS, [])
        email = d["email"].strip().lower()[:120]
        repeat = any(o.get("email", "").lower() == email for o in orders)
        orders.insert(0, {"id": code, "created": dt.datetime.now().isoformat(timespec="seconds"),
                          "name": d["name"][:120], "email": email, "phone": str(d.get("phone", ""))[:30],
                          "address": d["address"][:300], "note": str(d.get("note", ""))[:500], "items": items[:50],
                          "totals": d.get("totals", {}), "rate": d.get("rate"), "deposit_pct": d.get("deposit_pct"),
                          "source": "manual" if d.get("source") == "manual" else "web",
                          "first_claim": bool(d.get("first_claim")), "repeat_customer": repeat, "status": "new"})
        save(ORDERS, orders)
        return self.reply(200, {"id": code})


if __name__ == "__main__":
    if "--set-password" in sys.argv:  # đặt / đổi mật khẩu admin rồi thoát
        CONFIG.unlink(missing_ok=True)
        setup_password()
        sys.exit(0)
    CFG = setup_password()
    ADMIN.mkdir(parents=True, exist_ok=True)
    try:
        srv = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        print(f"Cổng {PORT} đang bận: có một máy chủ cũ vẫn đang chạy.\nChạy lệnh này rồi thử lại:  pkill -f serve.py")
        sys.exit(1)
    print(f"Website:  http://localhost:{PORT}")
    print(f"Admin:    http://localhost:{PORT}/admin")
    if AUTO_SYNC_HOURS > 0:
        threading.Thread(target=auto_sync, daemon=True).start()
        print(f"Tự đồng bộ giá & tồn kho mỗi {AUTO_SYNC_HOURS:g} giờ")
    print("Tắt máy chủ: bấm Ctrl+C\n", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã tắt.")
