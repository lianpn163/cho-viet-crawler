/**
 * VieBuy – nhận đơn hàng từ website (miễn phí, chạy trên Google).
 *  - Có đơn mới: lưu vào Google Sheet + gửi email báo cho bạn (mở trên điện thoại để đặt hàng ngay).
 *  - Khách bấm "Notify me": lưu vào sheet "Notify".
 *  - Admin trên laptop bấm "Lấy đơn mới" để kéo đơn về bảng kanban.
 *
 * CÀI ĐẶT: xem README.md, mục "Nhận đơn qua Google". Chỉ cần sửa 2 dòng dưới đây.
 */
const OWNER_EMAIL = 'ban@gmail.com';            // ← email nhận thông báo đơn mới
const SECRET = 'doi-thanh-mot-chuoi-bi-mat';    // ← chuỗi bí mật, dán y hệt vào admin (Cài đặt → Online)

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
    return json_({ error: 'Unknown request' });
  } finally {
    lock.releaseLock();
  }
}

const ORDER_HEADER = ['Mã đơn', 'Thời gian', 'Tên', 'Email', 'SĐT', 'Địa chỉ', 'Ghi chú', 'Món', 'Tổng (A$)', 'Cọc (A$)', 'Khách cũ?', 'Dữ liệu (đừng sửa)'];

function items_(arr) {
  return (Array.isArray(arr) ? arr.slice(0, 50) : []).map(i => ({ pid: clean_(i.pid, 200), title: clean_(i.title, 200), title_raw: clean_(i.title_raw, 200),
    variant: clean_(i.variant, 80), variant_raw: clean_(i.variant_raw, 80), q: Math.max(1, Math.min(20, parseInt(i.q, 10) || 1)),
    price_vnd: Number(i.price_vnd) || 0, url: clean_(i.url, 300), brand: clean_(i.brand, 80), price_check: !!i.price_check }));
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
    ref: clean_(d.ref, 20).replace(/[^A-Za-z0-9-]/g, ''), totals: d.totals || {}, rate: d.rate, deposit_pct: d.deposit_pct, first_claim: !!d.first_claim, repeat_customer: repeat, status: 'new'
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
    ${repeat ? '<br><b>Khách cũ</b>' : ''}${o.first_claim ? '<br>Khách chọn free ship đơn đầu' : ''}</p>
    <table style="width:100%;border-collapse:collapse">${rows}</table>
    <p style="margin:12px 0 0">Tổng: <b>A$${t.total || '?'}</b> · Cọc ${o.deposit_pct || ''}%: <b>A$${t.deposit || '?'}</b></p>
    ${o.note ? `<p>Ghi chú: ${esc_(o.note)}</p>` : ''}
    <p style="color:#777;font-size:13px">Về laptop: mở admin → Đơn hàng → "Lấy đơn mới" để cập nhật tiến độ.</p></div>`;
  MailApp.sendEmail({ to: OWNER_EMAIL, subject: `${SITE_NAME}: ${o.ref ? `cập nhật giỏ ${id} (đơn cũ ${o.ref})` : `đơn mới ${id}`} – ${o.name} – A$${t.total || '?'}`, htmlBody: html, replyTo: email, name: SITE_NAME });
  return json_({ id });
}

// Admin trên laptop gửi email xác nhận cho khách (từ Gmail của bạn). Cần đúng SECRET.
function mail_(d) {
  if (d.key !== SECRET) return json_({ error: 'forbidden' });
  const to = clean_(d.to, 120).trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)) return json_({ error: 'Email khách không hợp lệ' });
  MailApp.sendEmail({ to, subject: clean_(d.subject, 200), body: clean_(d.text, 20000), htmlBody: clean_(d.html, 80000),
    name: SITE_NAME, replyTo: clean_(d.reply_to, 120) || OWNER_EMAIL });
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
  return json_({ orders: read('Orders'), notify: read('Notify') });
}

// Chạy hàm này 1 lần trong trình soạn script để cấp quyền gửi email + thử email
function testEmail() {
  MailApp.sendEmail(OWNER_EMAIL, SITE_NAME + ': thử thông báo', 'Nếu bạn nhận được email này là đã cài xong.');
}
