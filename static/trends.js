/* Grafy vývoja v čase (čisté SVG, bez knižníc). Hover: zvislá čiara + tooltip so zmenami. */
(function () {
  var el = document.getElementById('trend-data');
  if (!el) return;
  var D = JSON.parse(el.textContent);
  var CUR = D.currency;
  var COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
  var NS = 'http://www.w3.org/2000/svg';
  var mode = D.start, kind = 'bar';
  var selected = {money: new Set(D.defaults.money || []), pct: new Set(D.defaults.pct || []),
                  eps: new Set(D.defaults.eps || []),
                  invest: new Set(D.defaults.invest || [])};
  var GROUPS = [
    {key: 'money', title: 'Výnosy, zisky a cash flow (mil. ' + CUR + ')'},
    {key: 'pct', title: 'Marže a pomery (%)'},
    {key: 'invest', title: 'Investície (CapEx) a návrat kapitálu akcionárom (mil. ' + CUR + ')'},
    {key: 'eps', title: 'Na akciu (' + CUR + ')'}
  ];
  var MAXSEL = 4;
  var root = document.getElementById('trend-charts');
  var tableBox = document.getElementById('trend-table');
  var charts = [];
  var pick = {a: null, b: null};   // vybrané obdobia na porovnanie (indexy)

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
  function fmt(v, g, short) {
    if (v == null) return '–';
    if (g === 'money' || g === 'invest') {
      var m = v / 1e6, a = Math.abs(m);
      return m.toLocaleString('sk-SK', {maximumFractionDigits: a >= 1000 ? 0 : (a >= 100 ? 0 : 1)});
    }
    if (g === 'pct') return (v * 100).toFixed(1).replace('.', ',') + ' %';
    return v.toFixed(2).replace('.', ',');
  }
  function change(v, p, g) {
    if (v == null || p == null) return null;
    if (g === 'pct') {
      var pp = (v - p) * 100;
      if (Math.abs(pp) < 0.05) return '■ 0,0 p. b.';
      return (pp >= 0 ? '▲ +' : '▼ ') + pp.toFixed(1).replace('.', ',') + ' p. b.';
    }
    if (p === 0) return null;
    var c = (v - p) / Math.abs(p) * 100;
    return (c >= 0 ? '▲ +' : '▼ ') + c.toFixed(1).replace('.', ',') + ' %';
  }
  function niceTicks(lo, hi) {
    if (lo === hi) { hi = lo + 1; }
    var span = hi - lo, raw = span / 5, p = Math.pow(10, Math.floor(Math.log10(raw)));
    var f = raw / p, step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
    var a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
    for (var v = a; v <= b + step / 2; v += step) t.push(Math.abs(v) < step / 1e6 ? 0 : v);
    return t;
  }
  function tickLabel(v, g) {
    if (g === 'money' || g === 'invest') {
      var m = v / 1e6;
      return m.toLocaleString('sk-SK', {maximumFractionDigits: 1});
    }
    if (g === 'pct') return (v * 100).toFixed(0) + ' %';
    return v.toLocaleString('sk-SK', {maximumFractionDigits: 2});
  }

  function pctTxt(g) { return (g >= 0 ? '+' : '−') + Math.abs(g * 100).toFixed(1).replace('.', ',') + ' %'; }

  /* výber dvoch období: klik na prvé, klik na druhé -> rast medzi nimi */
  function onPick(i) {
    if (pick.a == null) pick.a = i;
    else if (pick.b == null) { if (i === pick.a) { pick.a = null; } else pick.b = i; }
    else { pick.a = i; pick.b = null; }
    refreshPick();
  }
  function clearPick() { pick.a = null; pick.b = null; refreshPick(); }
  function refreshPick() {
    charts.forEach(function (c) { c.draw(); });
    markPick();
  }
  function markPick() {
    var cells = tableBox.querySelectorAll('[data-i]');
    for (var k = 0; k < cells.length; k++) {
      var i = +cells[k].dataset.i;
      cells[k].classList.toggle('pk', i === pick.a || i === pick.b);
    }
  }

  /* ---------------------------------------------------------- jeden graf */
  function Chart(group) {
    var self = this;
    this.g = group.key;
    this.card = h('div', 'tcard');
    this.card.appendChild(h('h3', 'ttitle', group.title));
    this.chips = h('div', 'chips');
    this.card.appendChild(this.chips);
    this.cmp = h('div', 'cmp');
    this.card.appendChild(this.cmp);
    this.wrap = h('div', 'cwrap');
    this.card.appendChild(this.wrap);
    this.tip = h('div', 'tip');
    this.tip.style.display = 'none';
    this.wrap.appendChild(this.tip);
    this.note = h('div', 'note');
    this.card.appendChild(this.note);
    root.appendChild(this.card);
    window.addEventListener('resize', function () { self.draw(); });
  }
  Chart.prototype.series = function () {
    var d = D[mode], g = this.g;
    return d ? d.series.filter(function (x) { return x.group === g; }) : [];
  };
  Chart.prototype.color = function (id) {
    var all = D.annual ? D.annual.series : D.quarterly.series;
    var ids = all.filter(function (x) { return x.group === this.g; }, this).map(function (x) { return x.id; });
    var i = ids.indexOf(id);
    return COLORS[(i < 0 ? 0 : i) % COLORS.length];
  };
  Chart.prototype.render = function () {
    var self = this, all = this.series();
    if (!all.length) { this.card.style.display = 'none'; return; }
    this.card.style.display = '';
    this.chips.textContent = '';
    all.forEach(function (sr) {
      var on = selected[self.g].has(sr.id);
      var b = h('button', 'chip' + (on ? ' on' : ''));
      b.type = 'button';
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      var key = h('span', 'key');
      key.style.background = self.color(sr.id);
      b.appendChild(key);
      b.appendChild(document.createTextNode(sr.label));
      b.onclick = function () {
        var set = selected[self.g];
        if (set.has(sr.id)) { if (set.size > 1) set.delete(sr.id); }
        else if (set.size < MAXSEL) set.add(sr.id);
        self.render();
      };
      self.chips.appendChild(b);
    });
    this.draw();
  };
  Chart.prototype.renderCmp = function () {
    var d = D[mode], box = this.cmp, self = this;
    box.textContent = '';
    if (!d || pick.a == null) {
      box.style.display = 'none';
      return;
    }
    box.style.display = 'block';
    var all = (this.sel || []);
    if (pick.b == null) {
      box.appendChild(h('span', 'cmpt', 'Od: ' + d.labels[pick.a] +
        ' · klikni na druhé obdobie a uvidíš rast medzi nimi'));
      var x0 = h('button', 'cmpx', 'zrušiť'); x0.type = 'button'; x0.onclick = clearPick;
      box.appendChild(x0);
      return;
    }
    var i0 = Math.min(pick.a, pick.b), i1 = Math.max(pick.a, pick.b), steps = i1 - i0;
    var years = d.lag === 1 ? steps : steps / 4;
    var head = h('div', 'cmph');
    head.appendChild(h('span', 'cmpt', d.labels[i0] + ' → ' + d.labels[i1] +
      ' (' + (d.lag === 1 ? steps + (steps === 1 ? ' rok' : steps < 5 ? ' roky' : ' rokov')
        : steps + (steps === 1 ? ' kvartál' : steps < 5 ? ' kvartály' : ' kvartálov')) + ')'));
    var x = h('button', 'cmpx', 'zrušiť výber'); x.type = 'button'; x.onclick = clearPick;
    head.appendChild(x);
    box.appendChild(head);
    all.forEach(function (sr) {
      var a = sr.values[i0], b = sr.values[i1];
      var row = h('div', 'cmpr');
      var key = h('span', 'key'); key.style.background = self.color(sr.id); row.appendChild(key);
      row.appendChild(h('span', 'cmpn', sr.label));
      row.appendChild(h('span', 'cmpv', fmt(a, sr.group) + ' → ' + fmt(b, sr.group)));
      var res;
      if (a == null || b == null) res = h('strong', null, 'chýbajú údaje');
      else if (sr.group === 'pct') {
        var pp = (b - a) * 100;
        res = Math.abs(pp) < 0.05 ? h('strong', 'muted', '0,0 p. b.') :
          h('strong', pp >= 0 ? 'up' : 'down', (pp >= 0 ? '+' : '−') + Math.abs(pp).toFixed(1).replace('.', ',') + ' p. b.');
      } else if (a > 0) {
        var g = b / a - 1;
        res = h('strong', g >= 0 ? 'up' : 'down', pctTxt(g));
      } else {
        res = h('strong', 'muted', 'zmena v % nejde vypočítať (základ ≤ 0)');
      }
      row.appendChild(res);
      if (a != null && b != null && a > 0 && b > 0 && sr.group !== 'pct' && years >= 1) {
        var cg = Math.pow(b / a, 1 / years) - 1;
        row.appendChild(h('span', 'cmpc', pctTxt(cg) + ' ročne'));
      }
      box.appendChild(row);
    });
  };

  Chart.prototype.draw = function () {
    var self = this, d = D[mode];
    if (!d) return;
    var all = this.series().filter(function (x) { return selected[self.g].has(x.id); });
    if (!all.length) { all = this.series().slice(0, 1); }
    this.sel = all;
    var old = this.wrap.querySelector('svg');
    if (old) this.wrap.removeChild(old);
    var W = Math.max(300, this.wrap.clientWidth || 440), H = 215;
    var L = 50, R = 10, T = 8, B = 28, n = d.labels.length;
    var vals = [];
    all.forEach(function (x) { x.values.forEach(function (v) { if (v != null) vals.push(v); }); });
    var lo = Math.min.apply(null, vals.concat([0])), hi = Math.max.apply(null, vals.concat([0]));
    var ticks = niceTicks(lo, hi); lo = ticks[0]; hi = ticks[ticks.length - 1];
    var y = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    var band = (W - L - R) / n;
    var svg = s('svg', {width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img',
                        'aria-label': this.card.querySelector('h3').textContent});
    ticks.forEach(function (t) {
      svg.appendChild(s('line', {x1: L, x2: W - R, y1: y(t), y2: y(t),
        stroke: t === 0 ? 'var(--axis)' : 'var(--grid)', 'stroke-width': t === 0 ? 1.2 : 1}));
      var tx = s('text', {x: L - 8, y: y(t) + 4, 'text-anchor': 'end', class: 'ax'});
      tx.textContent = tickLabel(t, self.g);
      svg.appendChild(tx);
    });
    var every = band < 30 ? (band < 16 ? 4 : 2) : 1;
    d.labels.forEach(function (lb, i) {
      if (i % every !== (n - 1) % every) return;
      var tx = s('text', {x: L + band * (i + 0.5), y: H - 9, 'text-anchor': 'middle', class: 'ax'});
      tx.textContent = lb;
      svg.appendChild(tx);
    });
    [pick.a, pick.b].forEach(function (pi, k) {
      if (pi == null || pi >= n) return;
      svg.appendChild(s('rect', {x: L + band * pi, y: T, width: band, height: H - T - B,
        fill: 'rgba(79,110,160,.09)'}));
      var tag = s('text', {x: L + band * (pi + 0.5), y: T + 10, 'text-anchor': 'middle', class: 'ax',
        'font-weight': 600, fill: '#6b7a99', 'font-size': 9.5});
      tag.textContent = (pick.a != null && pick.b != null) ? (pi === Math.min(pick.a, pick.b) ? 'Od' : 'Do') : 'Od';
      svg.appendChild(tag);
    });
    var hov = s('rect', {y: T, height: H - T - B, width: band, fill: 'var(--hover)', opacity: 0});
    svg.appendChild(hov);
    var k = all.length;
    if (kind === 'bar') {
      var bw = Math.max(3, Math.min(34, (band * 0.78) / k - 2));
      all.forEach(function (sr, si) {
        var col = self.color(sr.id);
        sr.values.forEach(function (v, i) {
          if (v == null) return;
          var x = L + band * (i + 0.5) - (k * (bw + 2) - 2) / 2 + si * (bw + 2);
          var y0 = y(0), y1 = y(v);
          var top = Math.min(y0, y1), hgt = Math.max(1, Math.abs(y0 - y1));
          svg.appendChild(s('rect', {x: x, y: top, width: bw, height: hgt, fill: col, rx: Math.min(3, bw / 2)}));
        });
      });
    } else {
      all.forEach(function (sr) {
        var col = self.color(sr.id), path = '', pen = false;
        sr.values.forEach(function (v, i) {
          if (v == null) { pen = false; return; }
          path += (pen ? 'L' : 'M') + (L + band * (i + 0.5)).toFixed(1) + ' ' + y(v).toFixed(1);
          pen = true;
        });
        svg.appendChild(s('path', {d: path, fill: 'none', stroke: col, 'stroke-width': 2,
                                   'stroke-linejoin': 'round', 'stroke-linecap': 'round'}));
        sr.values.forEach(function (v, i) {
          if (v == null) return;
          svg.appendChild(s('circle', {cx: L + band * (i + 0.5), cy: y(v), r: n > 12 ? 3 : 4,
            fill: col, stroke: 'var(--surface)', 'stroke-width': 2}));
        });
      });
    }
    var cross = s('line', {y1: T, y2: H - B, stroke: 'var(--muted)', 'stroke-width': 1, opacity: 0,
                           'stroke-dasharray': '3 3'});
    svg.appendChild(cross);
    var hit = s('rect', {x: L, y: 0, width: W - L - R, height: H, fill: 'transparent'});
    svg.appendChild(hit);
    this.wrap.appendChild(svg);
    this.note.textContent = '';

    function at(ev) {
      var r = svg.getBoundingClientRect();
      var x = (ev.clientX - r.left) * (W / r.width);
      return Math.max(0, Math.min(n - 1, Math.floor((x - L) / band)));
    }
    function show(i) {
      hov.setAttribute('x', L + band * i); hov.setAttribute('opacity', 1);
      var cx = L + band * (i + 0.5);
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('opacity', 1);
      self.tip.textContent = '';
      var head = h('div', 'th', d.labels[i]);
      head.appendChild(h('span', 'td', d.dates[i]));
      self.tip.appendChild(head);
      all.forEach(function (sr) {
        var v = sr.values[i];
        var row = h('div', 'tr');
        var key = h('span', 'key'); key.style.background = self.color(sr.id);
        row.appendChild(key);
        var main = h('div', 'tm');
        var line = h('div', 'tl');
        line.appendChild(h('strong', null, fmt(v, sr.group)));
        line.appendChild(h('span', 'tn', ' ' + sr.label));
        main.appendChild(line);
        var prev = i > 0 ? sr.values[i - 1] : null;
        var c1 = change(v, prev, sr.group);
        var yo = i - d.lag >= 0 ? sr.values[i - d.lag] : null;
        var c2 = change(v, yo, sr.group);
        if (d.lag === 1) {
          if (c1) main.appendChild(h('div', 'tc', c1 + '  r/r'));
        } else {
          if (c1) main.appendChild(h('div', 'tc', c1 + '  q/q'));
          if (c2) main.appendChild(h('div', 'tc', c2 + '  r/r'));
        }
        row.appendChild(main);
        self.tip.appendChild(row);
      });
      self.tip.style.display = 'block';
      var tw = self.tip.offsetWidth, px = cx * (self.wrap.clientWidth / W);
      var left = px + 14; if (left + tw > self.wrap.clientWidth - 4) left = px - tw - 14;
      self.tip.style.left = Math.max(4, left) + 'px';
      self.tip.style.top = '4px';
      highlightCol(i);
    }
    function hide() {
      hov.setAttribute('opacity', 0); cross.setAttribute('opacity', 0);
      self.tip.style.display = 'none'; highlightCol(-1);
    }
    hit.addEventListener('pointermove', function (ev) { show(at(ev)); });
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('pointerdown', function (ev) { show(at(ev)); });
    hit.style.cursor = 'pointer';
    hit.addEventListener('click', function (ev) { onPick(at(ev)); });
    this.renderCmp();
  };

  /* -------------------------------------------------------------- tabuľka */
  function buildTable() {
    tableBox.textContent = '';
    var d = D[mode];
    if (!d) return;
    var wrap = h('div', 'tablewrap');
    var t = h('table', 'ttable');
    var thead = h('thead'), hr = h('tr');
    hr.appendChild(h('th', null, mode === 'annual' ? 'Ročné údaje' : 'Kvartálne údaje'));
    d.labels.forEach(function (lb, i) {
      var th = h('th', null, lb); th.dataset.i = i; th.title = d.dates[i]; hr.appendChild(th);
    });
    thead.appendChild(hr); t.appendChild(thead);
    var tb = h('tbody');
    GROUPS.forEach(function (gr) {
      var list = d.series.filter(function (x) { return x.group === gr.key; });
      if (!list.length) return;
      var sec = h('tr', 'sec'), c = h('td', null, gr.title);
      c.colSpan = d.labels.length + 1; sec.appendChild(c); tb.appendChild(sec);
      list.forEach(function (sr) {
        var r = h('tr');
        r.appendChild(h('td', null, sr.label));
        sr.values.forEach(function (v, i) {
          var td = h('td', v != null && v < 0 ? 'neg' : '', fmt(v, sr.group)); td.dataset.i = i; r.appendChild(td);
        });
        tb.appendChild(r);
        var gl = sr.group === 'pct' ? 'zmena (p. b.)' : (d.lag === 1 ? 'zmena r/r' : 'zmena r/r (oproti rovnakému kvartálu)');
        var r2 = h('tr', 'chg');
        r2.appendChild(h('td', null, '   ' + gl));
        sr.values.forEach(function (v, i) {
          var p = i - d.lag >= 0 ? sr.values[i - d.lag] : null;
          var ch = change(v, p, sr.group);
          var td = h('td', null, ch ? ch : '–'); td.dataset.i = i; r2.appendChild(td);
        });
        tb.appendChild(r2);
      });
    });
    t.appendChild(tb); wrap.appendChild(t); tableBox.appendChild(wrap);
    markPick();
    t.addEventListener('pointerover', function (ev) {
      var c = ev.target.closest('[data-i]'); highlightCol(c ? +c.dataset.i : -1);
    });
    t.addEventListener('pointerleave', function () { highlightCol(-1); });
  }
  function highlightCol(i) {
    var cells = tableBox.querySelectorAll('[data-i]');
    for (var k = 0; k < cells.length; k++)
      cells[k].classList.toggle('hl', +cells[k].dataset.i === i);
  }

  /* ------------------------------------------------------ ovládacie prvky */
  function seg(el, opts, get, set) {
    opts.forEach(function (o) {
      var b = h('button', 'segbtn', o[1]); b.type = 'button'; b.dataset.v = o[0];
      b.onclick = function () { set(o[0]); mark(); };
      el.appendChild(b);
    });
    function mark() {
      Array.prototype.forEach.call(el.children, function (b) {
        b.classList.toggle('on', b.dataset.v === get());
      });
    }
    mark();
  }
  var modeBox = document.getElementById('trend-mode');
  var kindBox = document.getElementById('trend-kind');
  var opts = [];
  if (D.annual) opts.push(['annual', 'Ročne']);
  if (D.quarterly) opts.push(['quarterly', 'Kvartálne']);
  seg(modeBox, opts, function () { return mode; }, function (v) {
    mode = v; pick = {a: null, b: null}; charts.forEach(function (c) { c.render(); }); buildTable();
  });
  seg(kindBox, [['bar', 'Stĺpce'], ['line', 'Čiary']], function () { return kind; }, function (v) {
    kind = v; charts.forEach(function (c) { c.draw(); });
  });
  GROUPS.forEach(function (g) { charts.push(new Chart(g)); });
  charts.forEach(function (c) { c.render(); });
  buildTable();
})();
