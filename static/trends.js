/* Grafy firmy: jednoduché karty s jedným ukazovateľom (čisté SVG, bez knižníc).
   Záložky: Základné metriky / Ziskovosť / Investície a odkupy, prepínač Kvartálne / Ročne.
   Hover: hodnota a zmena, klik na dva stĺpce: rast medzi nimi, ⤢: veľký graf s hodnotami. */
(function () {
  var el = document.getElementById('trend-data');
  if (!el) return;
  var D = JSON.parse(el.textContent);
  var NS = 'http://www.w3.org/2000/svg';
  var BAR = '#c4570f', BAR_DARK = '#9c420a', NEG = '#94a3b8';
  var CATS = [
    {key: 'basic', label: 'Základné metriky', groups: ['money', 'eps']},
    {key: 'profit', label: 'Ziskovosť', groups: ['pct']},
    {key: 'capital', label: 'Investície a odkupy', groups: ['invest']}
  ];
  var CUR_SYM = {USD: '$', EUR: '€', GBP: '£', JPY: '¥', CHF: 'CHF ', CAD: 'C$', AUD: 'A$'}[D.currency];
  var mode = D.start, cat = 'basic';
  var grid = document.getElementById('g-grid');
  var tableBox = document.getElementById('trend-table');
  var cards = [];

  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function s(tag, attrs) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }
  function num(x, d) { return x.toLocaleString('sk-SK', {minimumFractionDigits: d || 0, maximumFractionDigits: d || 0}); }
  function money(v, axis) {
    var a = Math.abs(v), sgn = v < 0 ? '−' : '', t;
    if (a >= 1e9) t = num(a / 1e9, a >= 1e11 || axis ? (a % 1e9 === 0 || axis ? 0 : 1) : 1) + ' mld.';
    else if (a >= 1e6) t = num(a / 1e6, axis || a >= 1e8 ? 0 : 1) + ' mil.';
    else if (a >= 1e3) t = num(a / 1e3, axis ? 0 : 1) + ' tis.';
    else t = num(a, 0);
    if (axis && a === 0) t = '0';
    return CUR_SYM ? sgn + CUR_SYM + t : sgn + t + ' ' + D.currency;
  }
  function fmt(v, g, axis) {
    if (v == null) return '–';
    if (g === 'pct') return (v * 100).toFixed(axis ? 0 : 1).replace('.', ',') + ' %';
    if (g === 'eps') return (v < 0 ? '−' : '') + (CUR_SYM || '') + num(Math.abs(v), 2) + (CUR_SYM ? '' : ' ' + D.currency);
    return money(v, axis);
  }
  function change(v, p, g) {
    if (v == null || p == null) return null;
    if (g === 'pct') {
      var pp = (v - p) * 100;
      return Math.abs(pp) < 0.05 ? '0,0 p. b.' : (pp >= 0 ? '▲ +' : '▼ −') + Math.abs(pp).toFixed(1).replace('.', ',') + ' p. b.';
    }
    if (p === 0) return null;
    var c = (v - p) / Math.abs(p) * 100;
    return (c >= 0 ? '▲ +' : '▼ −') + Math.abs(c).toFixed(1).replace('.', ',') + ' %';
  }
  function niceTicks(lo, hi) {
    if (lo === hi) hi = lo + 1;
    var span = hi - lo, raw = span / 4, p = Math.pow(10, Math.floor(Math.log10(raw)));
    var f = raw / p, step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
    var a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
    for (var v = a; v <= b + step / 2; v += step) t.push(Math.abs(v) < step / 1e6 ? 0 : v);
    return t;
  }
  function pctTxt(g) { return (g >= 0 ? '+' : '−') + Math.abs(g * 100).toFixed(1).replace('.', ',') + ' %'; }

  /* ------------------------------------------------------------ jeden graf */
  function drawBars(host, sr, d, opt) {
    host.textContent = '';
    var W = Math.max(260, host.clientWidth || 320), H = opt.big ? 380 : 230;
    var L = opt.big ? 74 : 62, R = 8, T = opt.big ? 24 : 12, B = 28, n = d.labels.length;
    var vals = sr.values.filter(function (v) { return v != null; });
    var ticks = niceTicks(Math.min.apply(null, vals.concat([0])), Math.max.apply(null, vals.concat([0])));
    var lo = ticks[0], hi = ticks[ticks.length - 1];
    var y = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    var band = (W - L - R) / n;
    var svg = s('svg', {width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': sr.label});
    ticks.forEach(function (t) {
      svg.appendChild(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t), stroke: t === 0 ? '#d9cbbd' : '#efe6dc',
        'stroke-width': 1, 'stroke-dasharray': t === 0 ? '0' : '4 4'}));
      var tx = s('text', {x: L - 8, y: y(t) + 4, 'text-anchor': 'end', class: 'ax'});
      tx.textContent = fmt(t, sr.group, true); svg.appendChild(tx);
    });
    var every = band < 34 ? (band < 18 ? 4 : 2) : 1;
    d.labels.forEach(function (lb, i) {
      if (i % every !== (n - 1) % every) return;
      var tx = s('text', {x: L + band * (i + 0.5), y: H - 8, 'text-anchor': 'middle', class: 'ax'});
      tx.textContent = lb; svg.appendChild(tx);
    });
    var bw = Math.max(4, Math.min(opt.big ? 56 : 30, band * 0.62));
    var bars = [];
    sr.values.forEach(function (v, i) {
      if (v == null) { bars.push(null); return; }
      var x = L + band * (i + 0.5) - bw / 2, y0 = y(0), y1 = y(v);
      var r = s('rect', {x: x, y: Math.min(y0, y1), width: bw, height: Math.max(1.5, Math.abs(y0 - y1)),
        fill: v < 0 ? NEG : BAR, rx: Math.min(4, bw / 2), opacity: i === n - 1 || opt.big ? 1 : 0.88});
      svg.appendChild(r); bars.push(r);
      if (opt.big && band >= 40) {
        var vt = s('text', {x: x + bw / 2, y: (v >= 0 ? Math.min(y0, y1) - 6 : Math.max(y0, y1) + 14),
          'text-anchor': 'middle', class: 'ax', 'font-weight': 600});
        vt.textContent = fmt(v, sr.group, false); svg.appendChild(vt);
      }
    });
    var pk = opt.pick || {a: null, b: null};
    [pk.a, pk.b].forEach(function (pi) {
      if (pi == null || pi >= n) return;
      svg.insertBefore(s('rect', {x: L + band * pi + 1, y: T, width: band - 2, height: H - T - B,
        fill: 'rgba(196,87,15,.10)', rx: 6}), svg.firstChild);
    });
    var hit = s('rect', {x: L, y: 0, width: W - L - R, height: H, fill: 'transparent'});
    hit.style.cursor = 'pointer';
    svg.appendChild(hit);
    host.appendChild(svg);
    var tip = h('div', 'tip'); tip.style.display = 'none'; host.appendChild(tip);
    function at(ev) {
      var r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) * (W / r.width);
      return Math.max(0, Math.min(n - 1, Math.floor((x - L) / band)));
    }
    var last = -1;
    function show(i) {
      if (last >= 0 && bars[last]) bars[last].setAttribute('fill', sr.values[last] < 0 ? NEG : BAR);
      last = i;
      if (bars[i]) bars[i].setAttribute('fill', BAR_DARK);
      var v = sr.values[i];
      tip.textContent = '';
      var head = h('div', 'th', d.labels[i]); head.appendChild(h('span', 'td', d.dates[i])); tip.appendChild(head);
      tip.appendChild(h('div', 'tl', '')); tip.lastChild.appendChild(h('strong', null, fmt(v, sr.group)));
      var c1 = change(v, i > 0 ? sr.values[i - 1] : null, sr.group);
      var c2 = i - d.lag >= 0 ? change(v, sr.values[i - d.lag], sr.group) : null;
      if (d.lag === 1) { if (c1) tip.appendChild(h('div', 'tc', c1 + '  r/r')); }
      else { if (c1) tip.appendChild(h('div', 'tc', c1 + '  q/q')); if (c2) tip.appendChild(h('div', 'tc', c2 + '  r/r')); }
      tip.style.display = 'block';
      var cx = (L + band * (i + 0.5)) * (host.clientWidth / W), tw = tip.offsetWidth;
      var left = cx + 14; if (left + tw > host.clientWidth - 4) left = cx - tw - 14;
      tip.style.left = Math.max(4, left) + 'px'; tip.style.top = '6px';
    }
    function hide() {
      if (last >= 0 && bars[last]) bars[last].setAttribute('fill', sr.values[last] < 0 ? NEG : BAR);
      last = -1; tip.style.display = 'none';
    }
    hit.addEventListener('pointermove', function (ev) { show(at(ev)); });
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('click', function (ev) { opt.onPick && opt.onPick(at(ev)); });
  }

  function cmpText(sr, d, pk) {
    if (pk.a == null) return null;
    if (pk.b == null) return 'Od ' + d.labels[pk.a] + ': klikni na druhé obdobie';
    var i0 = Math.min(pk.a, pk.b), i1 = Math.max(pk.a, pk.b), a = sr.values[i0], b = sr.values[i1];
    var head = d.labels[i0] + ' → ' + d.labels[i1] + ': ';
    if (a == null || b == null) return head + 'chýbajú údaje';
    if (sr.group === 'pct') { var pp = (b - a) * 100; return head + (pp >= 0 ? '+' : '−') + Math.abs(pp).toFixed(1).replace('.', ',') + ' p. b.'; }
    if (a <= 0) return head + 'zmena v % nejde vypočítať';
    var steps = i1 - i0, years = d.lag === 1 ? steps : steps / 4, t = head + pctTxt(b / a - 1);
    if (b > 0 && years >= 1) t += ' (' + pctTxt(Math.pow(b / a, 1 / years) - 1) + ' ročne)';
    return t;
  }

  function Card(sr) {
    var self = this;
    this.sr = sr; this.pick = {a: null, b: null};
    this.el = h('div', 'gcard');
    var head = h('div', 'ghead');
    head.appendChild(h('h3', 'gtitle', sr.label));
    var ex = h('button', 'gexp', '⤢'); ex.type = 'button'; ex.title = 'Zväčšiť'; ex.setAttribute('aria-label', 'Zväčšiť graf');
    ex.onclick = function () { openModal(self.sr); };
    head.appendChild(ex); this.el.appendChild(head);
    this.cmp = h('div', 'gcmp'); this.el.appendChild(this.cmp);
    this.host = h('div', 'cwrap'); this.el.appendChild(this.host);
    grid.appendChild(this.el);
  }
  Card.prototype.draw = function () {
    var self = this, d = D[mode];
    drawBars(this.host, this.sr, d, {pick: this.pick, onPick: function (i) {
      var p = self.pick;
      if (p.a == null) p.a = i; else if (p.b == null) { if (i === p.a) p.a = null; else p.b = i; } else { p.a = i; p.b = null; }
      self.draw();
    }});
    var t = cmpText(this.sr, d, this.pick);
    this.cmp.textContent = t || ''; this.cmp.style.display = t ? 'block' : 'none';
    if (t) {
      var x = h('button', 'cmpx', 'zrušiť'); x.type = 'button'; x.onclick = function () { self.pick = {a: null, b: null}; self.draw(); };
      this.cmp.appendChild(document.createTextNode(' ')); this.cmp.appendChild(x);
    }
  };

  function render() {
    grid.textContent = ''; cards = [];
    var d = D[mode], groups = CATS.filter(function (c) { return c.key === cat; })[0].groups;
    var list = d ? d.series.filter(function (x) { return groups.indexOf(x.group) >= 0; }) : [];
    if (!list.length) grid.appendChild(h('div', 'note', 'Pre túto záložku nie sú údaje.'));
    list.forEach(function (sr) { var c = new Card(sr); cards.push(c); });
    cards.forEach(function (c) { c.draw(); });
    buildTable();
  }
  window.addEventListener('resize', function () { cards.forEach(function (c) { c.draw(); }); });

  /* --------------------------------------------------------------- modal */
  var modal = document.getElementById('g-modal');
  function openModal(sr) {
    var d = D[mode];
    modal.textContent = '';
    var box = h('div', 'gmbox');
    var head = h('div', 'ghead'); head.appendChild(h('h3', 'gtitle', sr.label + ' · ' + (mode === 'annual' ? 'ročne' : 'kvartálne')));
    var cl = h('button', 'gexp', '✕'); cl.type = 'button'; cl.setAttribute('aria-label', 'Zavrieť'); cl.onclick = closeModal;
    head.appendChild(cl); box.appendChild(head);
    var host = h('div', 'cwrap'); box.appendChild(host);
    box.appendChild(h('div', 'note', 'Kurzorom nad stĺpcom uvidíš hodnotu a zmenu oproti predchádzajúcemu obdobiu.'));
    modal.appendChild(box); modal.hidden = false; document.body.classList.add('noscroll');
    drawBars(host, sr, d, {big: true});
    modal.onclick = function (e) { if (e.target === modal) closeModal(); };
  }
  function closeModal() { modal.hidden = true; modal.textContent = ''; document.body.classList.remove('noscroll'); }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !modal.hidden) closeModal(); });

  /* -------------------------------------------------------------- tabuľka */
  var GROUP_TITLE = {money: 'Výnosy, zisky a cash flow', pct: 'Marže a pomery', invest: 'Investície a návrat kapitálu', eps: 'Na akciu'};
  function buildTable() {
    tableBox.textContent = '';
    var d = D[mode]; if (!d) return;
    var wrap = h('div', 'tablewrap'), t = h('table', 'ttable');
    var thead = h('thead'), hr = h('tr');
    hr.appendChild(h('th', null, mode === 'annual' ? 'Ročné údaje' : 'Kvartálne údaje'));
    d.labels.forEach(function (lb, i) { var th = h('th', null, lb); th.title = d.dates[i]; hr.appendChild(th); });
    thead.appendChild(hr); t.appendChild(thead);
    var tb = h('tbody');
    ['money', 'pct', 'invest', 'eps'].forEach(function (gk) {
      var list = d.series.filter(function (x) { return x.group === gk; });
      if (!list.length) return;
      var sec = h('tr', 'sec'), c = h('td', null, GROUP_TITLE[gk]); c.colSpan = d.labels.length + 1; sec.appendChild(c); tb.appendChild(sec);
      list.forEach(function (sr) {
        var r = h('tr'); r.appendChild(h('td', null, sr.label));
        sr.values.forEach(function (v) { r.appendChild(h('td', v != null && v < 0 ? 'neg' : '', fmt(v, sr.group))); });
        tb.appendChild(r);
      });
    });
    t.appendChild(tb); wrap.appendChild(t); tableBox.appendChild(wrap);
  }

  /* ------------------------------------------------------ ovládacie prvky */
  function pills(el, opts, get, set) {
    opts.forEach(function (o) {
      var b = h('button', 'gtab', o[1]); b.type = 'button'; b.dataset.v = o[0];
      b.onclick = function () { set(o[0]); mark(); };
      el.appendChild(b);
    });
    function mark() {
      Array.prototype.forEach.call(el.children, function (b) { b.classList.toggle('on', b.dataset.v === get()); });
    }
    mark();
  }
  var present = CATS.filter(function (c) {
    return ['annual', 'quarterly'].some(function (m) { return D[m] && D[m].series.some(function (x) { return c.groups.indexOf(x.group) >= 0; }); });
  });
  if (present.length && present.every(function (c) { return c.key !== cat; })) cat = present[0].key;
  pills(document.getElementById('g-cat'), present.map(function (c) { return [c.key, c.label]; }),
        function () { return cat; }, function (v) { cat = v; render(); });
  var mopts = [];
  if (D.quarterly) mopts.push(['quarterly', 'Kvartálne']);
  if (D.annual) mopts.push(['annual', 'Ročne']);
  pills(document.getElementById('g-mode'), mopts, function () { return mode; }, function (v) { mode = v; render(); });
  render();
})();
