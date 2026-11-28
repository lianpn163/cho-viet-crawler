/* Dùng chung cho website khách (site/index.html) và trang admin (/admin). */
const CV = (() => {
  const L = { lang: 'vi' };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const CATS = ['Áo thun & polo', 'Sơ mi', 'Áo len & hoodie', 'Áo khoác', 'Quần', 'Mũ', 'Túi', 'Phụ kiện', 'Váy & đầm', 'Khác'];
  const BASE_CATS = CATS.slice();
  const CAT_EN_DEFAULT = { 'Áo thun & polo': 'Tees & polos', 'Sơ mi': 'Shirts', 'Áo len & hoodie': 'Sweaters & hoodies', 'Áo khoác': 'Jackets', 'Quần': 'Pants & shorts', 'Mũ': 'Hats', 'Túi': 'Bags', 'Phụ kiện': 'Accessories', 'Váy & đầm': 'Skirts & dresses', 'Khác': 'Other' };
  const SKIP = '__bỏ__', LEGACY = { 'Balo': 'Túi', 'Túi & ví': 'Túi', 'Áo khoác & hoodie': 'Áo khoác', 'Giày dép': SKIP, 'Đồ bơi': SKIP };
  const WEIGHT = { 'Áo thun & polo': .3, 'Sơ mi': .35, 'Áo len & hoodie': .7, 'Áo khoác': .9, 'Quần': .6, 'Mũ': .2, 'Túi': .7, 'Phụ kiện': .15, 'Váy & đầm': .4, 'Khác': .5 };
  const COLOURS = [
    ['Đen', '#111', ['black', 'đen', 'jet', 'onyx']],
    ['Trắng', '#fff', ['white', 'trắng', 'ivory', 'off white', 'offwhite', 'off-white']],
    ['Xám', '#9aa0a6', ['grey', 'gray', 'xám', 'charcoal', 'ash', 'silver', 'melange', 'ghi']],
    ['Be & kem', '#e4d3b3', ['beige', 'be', 'kem', 'cream', 'sand', 'khaki', 'tan', 'nude', 'ecru', 'oat', 'oatmeal']],
    ['Nâu', '#7a4a2a', ['brown', 'nâu', 'coffee', 'mocha', 'chocolate', 'camel', 'cà phê']],
    ['Đỏ', '#c0262d', ['red', 'đỏ', 'burgundy', 'maroon', 'wine', 'đô']],
    ['Hồng', '#ef8fb1', ['pink', 'hồng', 'rose', 'fuchsia']],
    ['Cam', '#f08a24', ['orange', 'cam', 'rust']],
    ['Vàng', '#f2c94c', ['yellow', 'vàng', 'mustard', 'gold']],
    ['Xanh lá', '#4f8a4b', ['green', 'xanh lá', 'olive', 'moss', 'rêu', 'mint', 'sage', 'army', 'xanh rêu']],
    ['Xanh dương', '#2f5fa7', ['blue', 'xanh dương', 'navy', 'aqua', 'tiffany', 'denim', 'sky', 'xanh biển', 'teal', 'cobalt', 'indigo']],
    ['Tím', '#7e57c2', ['purple', 'tím', 'lilac', 'lavender', 'violet']],
    ['Nhiều màu', 'conic-gradient(red,orange,yellow,green,blue,purple,red)', ['multi', 'multicolor', 'camo', 'rainbow', 'nhiều màu']]];
  const COLOUR_RE = COLOURS.map(([n, , ws]) => [n, new RegExp('(?<![\\p{L}\\p{N}])(' + ws.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')(?![\\p{L}\\p{N}])', 'iu')]);

  const D = { products: [], status: [], gen: '', ov: {}, clips: [], badm: {}, articles: [], kw: {}, set: { rate: 18400, ship_mode: 'flat', ship_flat: 15, ship: 14, ship_off: 0, free_first: true, free_over: 0, gst: false, acc_cap: 20, soldout_days: 180, fee: 10, deposit: 70, eta: '10–12 days', stale_hours: 6, site_name: 'VieBuy', typekit: '', order_endpoint: '', site_url: '',
    dep1: '{pct}% deposit once we confirm stock: {deposit}',
    dep2: 'Keep an eye on your inbox for our confirmation email, and pay your deposit as soon as possible to secure your pieces.',
    dep3: 'The remaining balance of {balance} is due before your parcel ships to Australia.', slogan: 'Exploring local brands from Vietnam - Emerging Fashion Capital', contact: '' } };
  const jget = u => fetch(u + '?t=' + Date.now()).then(r => r.ok ? r.json() : null).catch(() => null);
  // Gửi đơn / đăng ký báo hàng. Trên web online: gửi tới Google Apps Script (email báo bạn + lưu Google Sheet).
  // Chạy trên máy (localhost): gửi vào máy chủ local như cũ, không gửi email thật.
  const isLocal = () => /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  async function send(kind, body) {
    const ep = (D.set.order_endpoint || '').trim();
    if (!isLocal() && ep) {
      const r = await fetch(ep, { method: 'POST', body: JSON.stringify({ kind, ...body }) });   // text/plain: không cần CORS preflight
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.error) throw new Error(j.error || 'send failed');
      return j;
    }
    const r = await fetch('/api/' + kind, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || 'send failed');
    return j;
  }
  // Lấy lại tỷ giá mới nhất (lúc checkout / gửi đơn). Trả về true nếu tỷ giá vừa đổi.
  async function refreshRate(base = '') {
    const rt = await jget(base + 'data/rate.json'), before = D.set.rate;
    if (rt && rt.market > 10000) { D.rateInfo = rt; if ((D.set.rate_mode || 'auto') === 'auto') D.set.rate = Math.round(rt.market * (1 - (+D.set.rate_margin || 0) / 100)) }
    return D.set.rate !== before;
  }
  async function load(base = '') {
    const files = ['data/products.json', 'data/status.json', 'data/admin/overrides.json', 'data/admin/clips.json', 'data/admin/brands_admin.json', 'data/admin/settings.json', 'data/admin/articles.json', 'data/admin/keywords.json', 'data/rate.json', 'data/admin/insta.json'];
    const [pd, sd, ov, cl, ba, se, ar, kw, rt, ig] = await Promise.all(files.map(f => jget(base + f)));
    D.products = pd?.products || []; D.gen = pd?.generated_at || ''; D.status = sd?.brands || [];
    D.ov = ov || {}; D.clips = cl || []; D.insta = Array.isArray(ig) ? ig : []; D.badm = ba || {}; D.set = { ...D.set, ...(se || {}) };
    if (D.set.site_name === 'Viefs') D.set.site_name = 'VieBuy';
    if (D.set.eta === '5–7 days') D.set.eta = '10–12 days';   // thời gian giao mới
    if (D.set.soldout_days === 60) D.set.soldout_days = 180;   // hết hàng: nay giữ 6 tháng mới gỡ
    // tỷ giá tự động theo thị trường (crawler cập nhật mỗi lần đồng bộ), trừ hao rate_margin %
    D.rateInfo = rt && rt.market > 10000 ? rt : null;
    D.set.rate_manual = D.set.rate;
    if ((D.set.rate_mode || 'auto') === 'auto' && D.rateInfo) D.set.rate = Math.round(D.rateInfo.market * (1 - (+D.set.rate_margin || 0) / 100));   // tên cũ → tên mới
    if (D.set.slogan === "Vietnam's new wave, delivered.") D.set.slogan = 'Exploring local brands from Vietnam - Emerging Fashion Capital'; D.articles = ar || []; D.kw = kw || {};
    D.byId = Object.fromEntries(D.products.map(p => [p.id, p]));
    applyCats();
    return D;
  }
  /* Danh mục do admin cấu hình: thứ tự, tên tiếng Anh, ẩn, danh mục tự thêm */
  function applyCats() {
    const cfg = (D.set.cats || []).filter(c => c && c.key);
    const keys = [...cfg.map(c => c.key), ...BASE_CATS.filter(k => !cfg.some(c => c.key === k))];
    const other = keys.indexOf('Khác'); if (other > -1 && other !== keys.length - 1) keys.push(keys.splice(other, 1)[0]);
    CATS.splice(0, CATS.length, ...keys);
  }
  /* Nội dung chữ trên web khách: admin sửa được, có ô thay thế {eta} {deposit} {ship_flat} {fee} {shipping} {first_free} */
  const DEFAULT_CONTENT = {
    bar: ['Get your order in {eta}', 'Flat A${ship_flat} shipping Australia-wide', 'Free shipping on your first order'],
    lead: 'No payment until we confirm your items are in stock. Most orders arrive in {eta}.',
    steps: [['Pick your pieces', 'Shop authentic Vietnamese labels, priced in AUD with every fee shown in your bag.'],
      ['Confirmed within 24 hours', 'We email you to confirm stock, the final price and delivery date. Pay a {deposit}% deposit to lock it in.'],
      ['Consolidated in Vietnam', 'We buy from the brand, check every item and send you real photos before it flies.'],
      ['Delivered to your door', 'Pay the balance before dispatch. Your parcel arrives anywhere in Australia in {eta}.']],
    faq: [['How long does delivery take?', 'Usually {eta} from your deposit, depending on how quickly the brand dispatches. Your confirmation email includes an estimated delivery date.'],
      ['How do I pay?', 'Send an order request, no payment needed yet. Within 24 hours we email you to confirm stock, the final price and delivery date. You then pay a {deposit}% deposit by bank transfer; the balance is due once your items are consolidated and photographed, before they ship to Australia.'],
      ['What does shipping cost?', 'Shipping is {shipping}{first_free}. There is a {fee}% service fee on the item total. Every cost is shown in your bag before you order.'],
      ['Are the products authentic?', 'We only list verified brands: official website, official Instagram and registered business details. Every item is bought directly from the brand’s own store.'],
      ['What if I pick the wrong size?', 'You can change sizes or cancel for free until we place the order with the brand. After that the brand’s exchange policy applies, and return postage is agreed case by case.'],
      ['The item I want is sold out?', 'Tap "Notify me" and we’ll let you know as soon as the brand restocks.']],
    about: 'We buy authentic pieces from independent Vietnamese fashion labels on your behalf, consolidate them in Vietnam and deliver to your door in Australia. Prices are converted at an indicative exchange rate; product images and details belong to each brand.'
  };
  const content = () => ({ ...DEFAULT_CONTENT, ...Object.fromEntries(Object.entries(D.set.content || {}).filter(([, v]) => v && (!Array.isArray(v) || v.length))) });
  const fill = t => { const s = D.set; return String(t || '').replace(/\{eta\}/g, s.eta || '10–12 days').replace(/\{deposit\}/g, s.deposit).replace(/\{ship_flat\}/g, s.ship_flat).replace(/\{fee\}/g, s.fee)
    .replace(/\{shipping\}/g, s.ship_mode === 'flat' ? `a flat A$${s.ship_flat} per order, anywhere in Australia` : `A$${s.ship}/kg based on the estimated parcel weight`)
    .replace(/\{first_free\}/g, s.free_first ? ', and your first order ships free' : '') };
  const catCfg = k => (D.set.cats || []).find(c => c.key === k) || {};
  const catEN = k => catCfg(k).en || CAT_EN_DEFAULT[k] || k;
  const catHidden = k => !!catCfg(k).hidden;
  const aud = v => 'A$' + (v / D.set.rate).toFixed(2);
  const vnd = v => (v || 0).toLocaleString('vi-VN') + '₫';
  const ago = t => { if (L.lang === 'en') { if (!t) return 'never'; const m = Math.round((Date.now() - new Date(t)) / 6e4); return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago` } if (!t) return 'chưa từng'; const m = Math.round((Date.now() - new Date(t)) / 6e4); return m < 1 ? 'vừa xong' : m < 60 ? `${m} phút trước` : m < 1440 ? `${Math.round(m / 60)} giờ trước` : `${Math.round(m / 1440)} ngày trước` };
  const hue = s => [...s].reduce((a, c) => a * 31 + c.charCodeAt(0) >>> 0, 7) % 360;
  const st = id => D.status.find(b => b.id === id) || { id, name: id };
  const rec = id => { const r = D.badm[id] || {}; return { status: 'review', instagram: st(id).instagram || '', translate: false, verified_at: '', ...r, ver: { ...(r.ver || {}) } } };
  const isLive = id => rec(id).status === 'live';
  const stale = id => { const b = st(id); return !b.ok || !b.last_ok || (Date.now() - new Date(b.last_ok)) > D.set.stale_hours * 36e5 };
  const kwCat = p => { if (p.category !== 'Khác' || p.category_locked) return ''; const t = (p.title || '').toLowerCase();
    for (const [k, c] of Object.entries(D.kw)) if (new RegExp('(?<![\\p{L}\\p{N}])' + k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}\\p{N}])', 'iu').test(t)) return c; return '' };
  const catOf = p => { let c = D.ov[p.id]?.category || kwCat(p) || p.category; c = LEGACY[c] || c; return c === SKIP || CATS.includes(c) ? c : 'Khác' };
  const sleeve = p => /long ?sleeve|tay dài|\bl\/s\b/i.test(p.title) ? 'long' : 'short';
  const link = p => rec(p.brand).translate ? 'https://translate.google.com/translate?sl=vi&tl=en&u=' + encodeURIComponent(p.url) : p.url;
  const vopts = v => (v.options && v.options.length) ? v.options : String(v.name).split(' / ');
  const plain = p => p.variants.length <= 1;
  const rest = v => vopts(v).slice(1).join(' / ') || vopts(v)[0];
  function colours(p) {
    if (p._col) return p._col;
    const ci = (p.option_names || []).findIndex(n => /màu|mau|colou?r/i.test(n));
    const vals = ci >= 0 ? p.variants.map(v => vopts(v)[ci] || '') : p.variants.map(v => vopts(v).join(' '));
    const text = [p.title, ...vals].join(' | ');
    p._col = COLOUR_RE.filter(([, re]) => re.test(text)).map(([n]) => n);
    return p._col;
  }
  const slug = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 70) || 'bai-viet';
  const readMin = t => Math.max(1, Math.round(String(t || '').split(/\s+/).length / 220));
  const safeUrl = u => /^(https?:\/\/|data\/admin\/media\/|#)/i.test(u) ? u : '#';
  function inline(s) {   // s đã được esc
    return s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) => `<a href="${safeUrl(u)}" target="_blank" rel="noopener">${t}</a>`)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  }
  function md(src) {   // Markdown rút gọn: #, ##, >, -, ![ảnh](link "chú thích"), **đậm**, *nghiêng*, [link](url)
    return esc(src || '').replace(/\r/g, '').split(/\n{2,}/).map(b => {
      b = b.trim(); if (!b) return '';
      let m;
      if ((m = b.match(/^!\[([^\]]*)\]\(([^)\s]+)\)$/))) return `<figure><img src="${safeUrl(m[2])}" alt="${m[1]}" loading="lazy">${m[1] ? `<figcaption>${m[1]}</figcaption>` : ''}</figure>`;
      if (b.startsWith('### ')) return `<h4>${inline(b.slice(4))}</h4>`;
      if (b.startsWith('## ') || b.startsWith('# ')) return `<h3>${inline(b.replace(/^#+ /, ''))}</h3>`;
      if (b.split('\n').every(l => l.startsWith('&gt; ') || l === '&gt;')) return `<blockquote>${inline(b.split('\n').map(l => l.replace(/^&gt; ?/, '')).join('<br>'))}</blockquote>`;
      if (b.split('\n').every(l => /^[-*] /.test(l))) return `<ul>${b.split('\n').map(l => `<li>${inline(l.slice(2))}</li>`).join('')}</ul>`;
      return `<p>${inline(b).replace(/\n/g, '<br>')}</p>`;
    }).join('');
  }
  /* Tính tiền kiện hàng. goods = tổng tiền hàng (AUD), kg = cân ước tính. first = khách tự khai là đơn đầu. */
  function quote(goods, kg, first) {
    const s = D.set, bill = kg ? Math.max(.5, Math.ceil(kg * 2) / 2) : 0;
    const base = !goods ? 0 : s.ship_mode === 'flat' ? +s.ship_flat : bill * s.ship;
    const en = L.lang === 'en';
    let ship = base * (1 - (+s.ship_off || 0) / 100), note = s.ship_off ? (en ? `${s.ship_off}% off` : `giảm ${s.ship_off}%`) : '';
    if (s.free_over > 0 && goods >= s.free_over) { ship = 0; note = en ? `free over A$${s.free_over}` : `miễn phí cho đơn từ A$${s.free_over}` }
    const firstOff = s.free_first && first && ship > 0 ? ship : 0;
    const shipFinal = ship - firstOff, fee = goods * s.fee / 100, gst = s.gst ? (goods + shipFinal + fee) * .1 : 0, total = goods + shipFinal + fee + gst;
    const deposit = total * s.deposit / 100;
    return { goods, kg, bill, base, ship, note, firstOff, shipFinal, fee, gst, total, deposit, balance: total - deposit };
  }
  function promos() {
    const s = D.set, out = [];
    if (L.lang === 'en') {
      if (s.free_first) out.push('Free shipping on your first order');
      if (s.ship_mode === 'flat') out.push(`Flat A$${s.ship_flat} shipping Australia-wide`);
      if (s.ship_off > 0) out.push(`${s.ship_off}% off shipping`);
      if (s.free_over > 0) out.push(`Free shipping over A$${s.free_over}`);
      if (s.eta) out.push(`Delivered to your door in ${s.eta}`);
      return out;
    }
    if (s.free_first) out.push('Miễn phí ship đơn đầu tiên');
    if (s.ship_mode === 'flat') out.push(`Ship đồng giá A$${s.ship_flat} toàn nước Úc`);
    if (s.ship_off > 0) out.push(`Giảm ${s.ship_off}% phí ship`);
    if (s.free_over > 0) out.push(`Free ship đơn từ A$${s.free_over}`);
    if (s.eta) out.push(`Giao tận nhà ${s.eta}`);
    return out;
  }
  return { refreshRate, send, isLocal, DEFAULT_CONTENT, content, fill, applyCats, catEN, catHidden, CAT_EN_DEFAULT, BASE_CATS, SKIP, sleeve, L, quote, promos, esc, CATS, WEIGHT, COLOURS, D, load, aud, vnd, ago, hue, st, rec, isLive, stale, catOf, link, vopts, plain, rest, colours, slug, readMin, md, safeUrl };
})();
