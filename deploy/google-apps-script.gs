/**
 * VieBuy – nhận đơn hàng từ website (miễn phí, chạy trên Google).
 *  - Có đơn mới: lưu vào Google Sheet + gửi email báo cho bạn (mở trên điện thoại để đặt hàng ngay).
 *  - Khách bấm "Notify me": lưu vào sheet "Notify".
 *  - Admin trên laptop bấm "Lấy đơn mới" để kéo đơn về bảng kanban.
 *
 * CÀI ĐẶT: xem README.md, mục "Nhận đơn qua Google". Chỉ cần sửa 3 dòng dưới đây.
 * Báo cáo hằng ngày: chạy hàm setupDaily MỘT lần (8h sáng giờ Brisbane mỗi ngày sẽ có email).
 */
const OWNER_EMAIL = 'ban@gmail.com';            // ← email nhận thông báo đơn mới
const SECRET = 'doi-thanh-mot-chuoi-bi-mat';    // ← chuỗi bí mật, dán y hệt vào admin (Cài đặt → Online)
const SITE_URL = 'https://lianpn163.github.io/cho-viet-crawler';   // ← link web (dùng cho báo cáo hằng ngày)

const SITE_NAME = 'VieBuy';

function sheet_(name, header) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(header);
    sh.setFrozenRows(1);
  }
  return sh;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function clean_(v, n) { return String(v == null ? '' : v).slice(0, n); }
function esc_(s) { return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

function doPost(e) {
  let d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return json_({ error: 'Bad request' }); }
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    if (d.kind === 'notify') return notify_(d);
    if (d.kind === 'order') return order_(d);
    if (d.kind === 'mail') return mail_(d);
    if (d.kind === 'update') return update_(d);
    if (d.kind === 'visit') return visit_(d);
    if (d.kind === 'inquiry') return inquiry_(d);
    return json_({ error: 'Unknown request' });
  } finally {
    lock.releaseLock();
  }
}

const ORDER_HEADER = ['Mã đơn', 'Thời gian', 'Tên', 'Email', 'SĐT', 'Địa chỉ', 'Ghi chú', 'Món', 'Tổng (A$)', 'Cọc (A$)', 'Khách cũ?', 'Dữ liệu (đừng sửa)'];

function items_(arr) {
  return (Array.isArray(arr) ? arr.slice(0, 50) : []).map(i => ({ pid: clean_(i.pid, 200), title: clean_(i.title, 200), title_raw: clean_(i.title_raw, 200),
    variant: clean_(i.variant, 80), variant_raw: clean_(i.variant_raw, 80), q: Math.max(1, Math.min(20, parseInt(i.q, 10) || 1)),
    price_vnd: Number(i.price_vnd) || 0, url: clean_(i.url, 300), brand: clean_(i.brand, 80), price_check: !!i.price_check, image: clean_(i.image, 400) }));
}
const itemsText_ = items => items.map(i => `${i.q}× ${i.brand} – ${i.title} (${i.variant})`).join('\n');

// mã bảo vệ link "Update your bag" (admin tính giống hệt từ SECRET)
function tok_(id) {
  const b = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, SECRET + ':' + id, Utilities.Charset.UTF_8);
  return b.map(x => ((x + 256) % 256).toString(16).padStart(2, '0')).join('').slice(0, 12);
}

// Khách bấm "Update your bag" trong email rồi gửi lại: cập nhật món của CHÍNH đơn đó (giữ mã đơn, không hỏi lại thông tin)
function update_(d) {
  const id = clean_(d.ref, 20).replace(/[^A-Za-z0-9-]/g, '');
  if (!id || clean_(d.t, 20) !== tok_(id)) return json_({ error: 'This link has expired. Please reply to our email and we will help.' });
  const items = items_(d.items);
  if (!items.length) return json_({ error: 'Your bag is empty' });
  const sh = sheet_('Orders', ORDER_HEADER), last = sh.getLastRow();
  const ids = last > 1 ? sh.getRange(2, 1, last - 1, 1).getValues().flat().map(String) : [];
  const r = ids.indexOf(id);
  if (r < 0) return json_({ error: 'We could not find this order. Please reply to our email and we will help.' });
  const row = r + 2, col = sh.getLastColumn();
  const o = JSON.parse(sh.getRange(row, col).getValue());
  o.items = items; o.totals = d.totals || {}; o.updated_at = new Date().toISOString().slice(0, 19); o.update_count = (o.update_count || 0) + 1;
  const t = o.totals;
  sh.getRange(row, 8, 1, 3).setValues([[itemsText_(items), t.total || '', t.deposit || '']]);
  sh.getRange(row, col).setValue(JSON.stringify(o));
  const rows = items.map(i => `<li><b>${esc_(i.brand)}</b> – <a href="${esc_(i.url)}">${esc_(i.title_raw || i.title)}</a> · ${esc_(i.variant)} · SL ${i.q}</li>`).join('');
  MailApp.sendEmail({ to: OWNER_EMAIL, subject: `${SITE_NAME}: khách cập nhật giỏ ${id} – ${o.name} – A$${t.total || '?'}`, name: SITE_NAME, replyTo: o.email,
    htmlBody: `<div style="font-family:Arial,sans-serif;font-size:15px"><h2 style="margin:0 0 6px">Khách cập nhật giỏ ${id}</h2><p>${esc_(o.name)} · ${esc_(o.email)}</p><ul>${rows}</ul><p>Tổng mới: <b>A$${t.total || '?'}</b></p><p style="color:#777;font-size:13px">Về laptop bấm "Lấy đơn mới", đơn sẽ có tag "Bag updated" để bạn tick lại availability.</p></div>` });
  return json_({ id });
}

function order_(d) {
  const email = clean_(d.email, 120).trim().toLowerCase();
  const items = Array.isArray(d.items) ? d.items.slice(0, 50) : [];
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || !items.length || !clean_(d.name, 120).trim() || !clean_(d.address, 300).trim())
    return json_({ error: 'Please fill in your name, email and address' });

  const sh = sheet_('Orders', ORDER_HEADER);
  const emails = sh.getRange(1, 4, Math.max(sh.getLastRow(), 1), 1).getValues().flat().map(String);
  const repeat = emails.indexOf(email) > 0;
  const id = 'VB-' + Utilities.getUuid().replace(/-/g, '').slice(0, 6).toUpperCase();
  const o = {
    id, created: new Date().toISOString().slice(0, 19), name: clean_(d.name, 120), email, phone: clean_(d.phone, 30),
    address: clean_(d.address, 300), note: clean_(d.note, 500),
    items: items_(items),
    ref: clean_(d.ref, 20).replace(/[^A-Za-z0-9-]/g, ''), src: clean_(d.src, 24).toLowerCase().replace(/[^a-z0-9-]/g, ''), totals: d.totals || {}, rate: d.rate, deposit_pct: d.deposit_pct, first_claim: !!d.first_claim, repeat_customer: repeat, status: 'new'
  };
  const t = o.totals;
  sh.appendRow([id, o.created, o.name, email, o.phone, o.address, o.note,
    itemsText_(o.items), t.total || '', t.deposit || '', repeat ? 'Có' : '', JSON.stringify(o)]);

  // Email báo bạn: có link từng món để bấm đặt hàng ngay trên điện thoại
  const rows = o.items.map(i => `<tr><td style="padding:6px 0;border-bottom:1px solid #eee"><b>${esc_(i.brand)}</b> – <a href="${esc_(i.url)}">${esc_(i.title_raw || i.title)}</a><br>
    <span style="color:#555">${esc_(i.variant)} · SL ${i.q} · ${Number(i.price_vnd).toLocaleString('vi-VN')}₫${i.price_check ? ' · ⚠️ kiểm tra giá' : ''}</span></td></tr>`).join('');
  const html = `<div style="font-family:Arial,sans-serif;font-size:15px;max-width:560px">
    <h2 style="margin:0 0 6px">${o.ref ? `Khách cập nhật giỏ: ${id} (thay đơn ${esc_(o.ref)})` : `Đơn mới ${id}`}</h2>
    <p style="margin:0 0 12px">${esc_(o.name)} · <a href="mailto:${esc_(email)}">${esc_(email)}</a> ${o.phone ? '· ' + esc_(o.phone) : ''}<br>${esc_(o.address)}
    ${repeat ? '<br><b>Khách cũ</b>' : ''}${o.src ? '<br>Đến từ QR: <b>' + esc_(o.src) + '</b>' : ''}${o.first_claim ? '<br>Khách chọn free ship đơn đầu' : ''}</p>
    <table style="width:100%;border-collapse:collapse">${rows}</table>
    <p style="margin:12px 0 0">Tổng: <b>A$${t.total || '?'}</b> · Cọc ${o.deposit_pct || ''}%: <b>A$${t.deposit || '?'}</b></p>
    ${o.note ? `<p>Ghi chú: ${esc_(o.note)}</p>` : ''}
    <p style="color:#777;font-size:13px">Về laptop: mở admin → Đơn hàng → "Lấy đơn mới" để cập nhật tiến độ.</p></div>`;
  MailApp.sendEmail({ to: OWNER_EMAIL, subject: `${SITE_NAME}: ${o.ref ? `cập nhật giỏ ${id} (đơn cũ ${o.ref})` : `đơn mới ${id}`} – ${o.name} – A$${t.total || '?'}`, htmlBody: html, replyTo: email, name: SITE_NAME });
  return json_({ id });
}

// Khách gửi ảnh + link nhờ tìm một món chưa có trên web
// Sheet "Inquiries": ảnh nhỏ (thumb) nằm ở 3 cột riêng vì mỗi ô Google Sheet chỉ chứa được 50.000 ký tự; ảnh lớn gửi kèm email cho bạn.
const INQ_HEADER = ['Thời gian', 'Mã', 'Tên', 'Email', 'SĐT', 'Brand', 'Link', 'Size/màu', 'SL', 'Ghi chú', 'Ảnh 1', 'Ảnh 2', 'Ảnh 3', 'Dữ liệu (đừng sửa)'];
function inquiry_(d) {
  const email = clean_(d.email, 120).trim().toLowerCase();
  const photos = (Array.isArray(d.photos) ? d.photos : []).slice(0, 3).filter(p => p && p.full);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || !clean_(d.name, 120).trim() || !photos.length)
    return json_({ error: 'Please add a photo, your name and email' });
  const sh = sheet_('Inquiries', INQ_HEADER);
  if (sh.getLastRow() > 3000) return json_({ error: "We're busy right now, please try again later" });
  const id = 'RQ-' + Utilities.getUuid().replace(/-/g, '').slice(0, 6).toUpperCase();
  const n = { id, created: new Date().toISOString().slice(0, 19), name: clean_(d.name, 120), email, phone: clean_(d.phone, 30),
    brand: clean_(d.brand, 80), source: clean_(d.source, 500), variant: clean_(d.variant, 80), q: Math.max(1, Math.min(20, parseInt(d.q) || 1)),
    note: clean_(d.note, 800), src: clean_(d.src, 24).toLowerCase().replace(/[^a-z0-9-]/g, ''), done: false };
  const thumbs = [0, 1, 2].map(i => photos[i] && String(photos[i].thumb || '').length < 49000 ? String(photos[i].thumb || '') : '');
  sh.appendRow([n.created, id, n.name, email, n.phone, n.brand, n.source, n.variant, n.q, n.note, ...thumbs, JSON.stringify(n)]);
  const blobs = photos.map((p, i) => { const m = String(p.full).match(/^data:(image\/[a-z]+);base64,(.+)$/); return m ? Utilities.newBlob(Utilities.base64Decode(m[2]), m[1], `${id}-${i + 1}.jpg`) : null; }).filter(Boolean);
  const inl = {}; blobs.forEach((b, i) => inl['p' + i] = b);
  const link = /^https?:\/\//.test(n.source) ? `<a href="${esc_(n.source)}">${esc_(n.source)}</a>` : esc_(n.source);
  MailApp.sendEmail({ to: OWNER_EMAIL, replyTo: email, name: SITE_NAME, subject: `${SITE_NAME}: nhờ tìm hàng ${id} – ${n.brand} – ${n.name}`, attachments: blobs, inlineImages: inl,
    htmlBody: `<div style="font-family:Arial,sans-serif;font-size:15px;max-width:560px"><h2 style="margin:0 0 6px">Khách nhờ tìm hàng ${id}</h2>
      <p>${esc_(n.name)} · <a href="mailto:${esc_(email)}">${esc_(email)}</a>${n.phone ? ' · ' + esc_(n.phone) : ''}</p>
      <p><b>Brand:</b> ${esc_(n.brand)}<br><b>Thấy ở:</b> ${link}<br><b>Size/màu:</b> ${esc_(n.variant || '–')} · <b>SL:</b> ${n.q}${n.note ? '<br><b>Ghi chú:</b> ' + esc_(n.note) : ''}${n.src ? '<br>Đến từ QR: <b>' + esc_(n.src) + '</b>' : ''}</p>
      ${blobs.map((b, i) => `<img src="cid:p${i}" style="max-width:100%;margin:0 0 8px;display:block">`).join('')}
      <p style="color:#777;font-size:13px">Trả lời email này là trả lời thẳng cho khách.</p></div>` });
  MailApp.sendEmail({ to: email, replyTo: OWNER_EMAIL, name: SITE_NAME, subject: `We received your request ${id}`,
    htmlBody: `<div style="font-family:Arial,sans-serif;font-size:15px;max-width:560px;color:#111"><p>Hi ${esc_(n.name)},</p>
      <p>Thanks for sending us this piece from <b>${esc_(n.brand)}</b>. I'll check availability and price with the brand and get back to you within 24 hours with a quote in AUD.</p>
      <p>No payment is needed until you confirm.</p><p>${SITE_NAME}</p></div>` });
  return json_({ id });
}

// Khách vào web bằng QR code (?src=...): cộng 1 lượt quét cho nguồn đó
function visit_(d) {
  const src = clean_(d.src, 24).toLowerCase().replace(/[^a-z0-9-]/g, '');
  if (!src) return json_({ ok: true });
  const lock = LockService.getScriptLock();
  try { lock.waitLock(5000); } catch (x) { return json_({ ok: true }); }
  try {
    const sh = sheet_('Scans', ['Nguồn', 'Lượt quét', 'Lần cuối']);
    const n = sh.getLastRow();
    const keys = n > 1 ? sh.getRange(2, 1, n - 1, 1).getValues().flat().map(String) : [];
    const i = keys.indexOf(src), now = new Date().toISOString().slice(0, 19);
    if (i < 0) { if (keys.length < 300) sh.appendRow([src, 1, now]); }
    else { const r = sh.getRange(i + 2, 2, 1, 2); r.setValues([[Number(r.getValues()[0][0] || 0) + 1, now]]); }
  } finally { lock.releaseLock(); }
  return json_({ ok: true });
}

// Admin trên laptop gửi email xác nhận cho khách (từ Gmail của bạn). Cần đúng SECRET.
function mail_(d) {
  if (d.key !== SECRET) return json_({ error: 'forbidden' });
  const to = clean_(d.to, 120).trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)) return json_({ error: 'Email khách không hợp lệ' });
  // ảnh hàng thật (tải lên từ admin) gắn thẳng vào email
  const inlineImages = {};
  (Array.isArray(d.images) ? d.images.slice(0, 10) : []).forEach((im, k) => {
    try { inlineImages['p' + k] = Utilities.newBlob(Utilities.base64Decode(String(im.data)), String(im.mime || 'image/jpeg'), 'photo' + (k + 1) + '.jpg'); } catch (e) {}
  });
  const opt = { to, subject: clean_(d.subject, 200), body: clean_(d.text, 20000), htmlBody: clean_(d.html, 120000),
    name: SITE_NAME, replyTo: clean_(d.reply_to, 120) || OWNER_EMAIL };
  if (Object.keys(inlineImages).length) opt.inlineImages = inlineImages;
  MailApp.sendEmail(opt);
  return json_({ ok: true });
}

function notify_(d) {
  const email = clean_(d.email, 120).trim(), phone = clean_(d.phone, 20).replace(/[^\d+ ]/g, '').trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) && phone.replace(/\D/g, '').length < 8)
    return json_({ error: 'Please enter a valid email or mobile number' });
  const sh = sheet_('Notify', ['Thời gian', 'Brand', 'Sản phẩm', 'Size/màu', 'Email', 'SĐT', 'Link', 'Dữ liệu (đừng sửa)']);
  if (sh.getLastRow() > 5000) return json_({ error: "We're busy right now, please try again later" });
  const n = { id: Utilities.getUuid().slice(0, 8), created: new Date().toISOString().slice(0, 19), pid: clean_(d.pid, 200), title: clean_(d.title, 200),
    url: clean_(d.url, 300), brand: clean_(d.brand, 80), variant: clean_(d.variant, 80), email, phone, done: false };
  sh.appendRow([n.created, n.brand, n.title, n.variant, email, phone, n.url, JSON.stringify(n)]);
  return json_({ ok: true });
}

// Admin trên laptop kéo đơn về:  GET ...?key=SECRET
function doGet(e) {
  if (!e || !e.parameter || e.parameter.key !== SECRET) return json_({ error: 'forbidden' });
  const read = (name) => {
    const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
    if (!sh || sh.getLastRow() < 2) return [];
    const col = sh.getLastColumn();
    return sh.getRange(2, col, sh.getLastRow() - 1, 1).getValues().flat()
      .map(v => { try { return JSON.parse(v); } catch (x) { return null; } }).filter(Boolean);
  };
  const scans = {};
  const ss = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Scans');
  if (ss && ss.getLastRow() > 1) ss.getRange(2, 1, ss.getLastRow() - 1, 3).getValues()
    .forEach(([k, c, t]) => { if (k) scans[String(k)] = { count: Number(c) || 0, last: t instanceof Date ? t.toISOString().slice(0, 19) : String(t) }; });
  const inquiries = [];
  const iq = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Inquiries');
  if (iq && iq.getLastRow() > 1) iq.getRange(2, 1, iq.getLastRow() - 1, INQ_HEADER.length).getValues().forEach(r => {
    try { const n = JSON.parse(r[INQ_HEADER.length - 1]); n.thumbs = r.slice(10, 13).filter(Boolean).map(String); inquiries.push(n); } catch (x) {}
  });
  return json_({ orders: read('Orders'), notify: read('Notify'), scans, inquiries });
}

// Chạy hàm này 1 lần trong trình soạn script để cấp quyền gửi email + thử email
function testEmail() {
  MailApp.sendEmail(OWNER_EMAIL, SITE_NAME + ': thử thông báo', 'Nếu bạn nhận được email này là đã cài xong.');
}

// ===== Báo cáo hằng ngày: số sản phẩm đồng bộ, hàng mới, hàng vừa hết, đổi giá =====
function dailyDigest() {
  const get = f => {
    const r = UrlFetchApp.fetch(SITE_URL + '/data/' + f + '.json?t=' + Date.now(), { muteHttpExceptions: true });
    return r.getResponseCode() === 200 ? JSON.parse(r.getContentText()) : null;
  };
  const st = get('status'), pr = get('products');
  if (!st || !pr) {
    MailApp.sendEmail(OWNER_EMAIL, SITE_NAME + ': không đọc được dữ liệu web', 'Không mở được ' + SITE_URL + '/data/. Kiểm tra tab Actions trên GitHub.');
    return;
  }
  const since = Date.now() - 864e5, recent = iso => iso && Date.parse(iso) > since;
  const prods = pr.products || [];
  const rows = (st.brands || []).map(b => {
    const mine = prods.filter(p => p.brand === b.id);
    const ago = b.last_ok ? Math.round((Date.now() - Date.parse(b.last_ok)) / 36e5) : null;
    return { name: b.name, ok: b.ok, err: b.error || '', ago, total: mine.length, instock: mine.filter(p => p.in_stock).length,
      fresh: mine.filter(p => recent(p.first_seen)), out: mine.filter(p => !p.in_stock && recent(p.soldout_since)).length,
      price: mine.filter(p => recent(p.price_changed_at)).length };
  });
  const sum = k => rows.reduce((a, r) => a + (Array.isArray(r[k]) ? r[k].length : r[k]), 0);
  const td = 'padding:7px 10px;border-bottom:1px solid #eee;text-align:right';
  const table = `<table style="border-collapse:collapse;font-size:14px;width:100%;max-width:620px">
    <tr style="color:#787774;font-size:12px;text-transform:uppercase"><td style="${td};text-align:left">Brand</td><td style="${td}">Trên web</td><td style="${td}">Còn hàng</td><td style="${td}">Mới</td><td style="${td}">Vừa hết</td><td style="${td}">Đổi giá</td></tr>
    ${rows.map(r => `<tr><td style="${td};text-align:left"><b>${esc_(r.name)}</b>${r.ok ? '' : ' <span style="color:#e03e3e">⚠ lỗi</span>'}<br><span style="color:#999;font-size:12px">${r.ago == null ? 'chưa đồng bộ' : 'đồng bộ ' + r.ago + ' giờ trước'}</span></td>
      <td style="${td}">${r.total}</td><td style="${td}">${r.instock}</td><td style="${td};color:#448361"><b>${r.fresh.length ? '+' + r.fresh.length : 0}</b></td><td style="${td}">${r.out}</td><td style="${td}">${r.price}</td></tr>`).join('')}
    <tr><td style="${td};text-align:left"><b>Tổng</b></td><td style="${td}"><b>${sum('total')}</b></td><td style="${td}"><b>${sum('instock')}</b></td><td style="${td}"><b>${sum('fresh')}</b></td><td style="${td}"><b>${sum('out')}</b></td><td style="${td}"><b>${sum('price')}</b></td></tr></table>`;
  const fresh = rows.flatMap(r => r.fresh.map(p => `<li><b>${esc_(r.name)}</b> – <a href="${esc_(p.url)}">${esc_(p.title)}</a> · ${Number(p.price).toLocaleString('vi-VN')}₫</li>`)).slice(0, 30);
  const errs = rows.filter(r => !r.ok).map(r => `<li><b>${esc_(r.name)}</b>: ${esc_(r.err)}</li>`);
  const html = `<div style="font-family:Arial,sans-serif;font-size:15px;color:#37352f;max-width:620px">
    <h2 style="margin:0 0 4px">Báo cáo đồng bộ 24 giờ qua</h2><p style="color:#787774;margin:0 0 14px">${new Date().toLocaleDateString('vi-VN')} · <a href="${SITE_URL}">mở web</a></p>
    ${table}
    ${errs.length ? `<h3 style="color:#e03e3e">Brand đang lỗi đồng bộ</h3><ul>${errs.join('')}</ul>` : ''}
    ${fresh.length ? `<h3>Hàng mới lên web</h3><ul>${fresh.join('')}</ul>` : '<p>Không có sản phẩm mới trong 24 giờ qua.</p>'}</div>`;
  MailApp.sendEmail({ to: OWNER_EMAIL, subject: `${SITE_NAME}: ${sum('total')} sản phẩm trên web · ${sum('fresh')} mới${errs.length ? ' · ' + errs.length + ' brand lỗi' : ''}`, htmlBody: html, name: SITE_NAME });
}

// Chạy MỘT lần để bật báo cáo 8h sáng mỗi ngày (giờ Brisbane). Chạy lại cũng không bị trùng.
function setupDaily() {
  ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'dailyDigest').forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('dailyDigest').timeBased().everyDays(1).atHour(8).inTimezone('Australia/Brisbane').create();
  dailyDigest();   // gửi luôn một bản để xem thử
}
