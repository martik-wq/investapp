/* Sankey diagram „od tržieb k zisku“ (čisté SVG). Údaje: <script id="flow-data"> */
(function () {
  var el = document.getElementById('flow-data');
  var box = document.getElementById('sankey');
  if (!el || !box) return;
  var D = JSON.parse(el.textContent);
  var NS = 'http://www.w3.org/2000/svg';
  var COL = {rev: '#4f8df5', profit: '#3db07f', cost: '#e8564f'};
  var RIB = {rev: '#bcd0f2', profit: '#b3dcc8', cost: '#efc3c3'};
  var NODE_W = 12;
  var byId = {};
  D.nodes.forEach(function (n, i) { n.idx = i; byId[n.id] = n; });
  var revenue = (byId.revenue || {}).value || 1;
  var tip = document.getElementById('sankey-tip');

  function s(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function money(v) {
    var a = Math.abs(v), sign = v < 0 ? '−' : '';
    if (a >= 1e9) return sign + (a / 1e9).toFixed(1).replace('.', ',') + ' mld.';
    if (a >= 1e6) return sign + (a / 1e6).toFixed(a >= 1e8 ? 0 : 1).replace('.', ',') + ' mil.';
    return sign + Math.round(a / 1e3).toLocaleString('sk-SK') + ' tis.';
  }
  function pct(g) {
    return (g >= 0 ? '+' : '−') + Math.abs(g * 100).toFixed(Math.abs(g) < 0.1 ? 1 : 0).replace('.', ',') + ' %';
  }

  function layout(W, H) {
    var cols = 0;
    D.nodes.forEach(function (n) { cols = Math.max(cols, n.col + 1); });
    var hasStreams = D.nodes.some(function (n) { return n.col === 0 && n.id.indexOf('stream') === 0 || n.id === 'int_income'; });
    var L = hasStreams ? 190 : 40, R = 220, T = 56, B = 14;
    var colNodes = [];
    for (var c = 0; c < cols; c++) {
      colNodes.push(D.nodes.filter(function (n) { return n.col === c; })
        .sort(function (a, b) { return a.ord - b.ord || a.idx - b.idx; }));
    }
    var gapOf = function (c) { return (c === 0 && hasStreams) ? 26 : (c === cols - 1 ? 34 : 54); };
    var k = Infinity;
    colNodes.forEach(function (list, c) {
      if (!list.length) return;
      var sum = list.reduce(function (a, n) { return a + n.value; }, 0);
      var avail = H - T - B - gapOf(c) * (list.length - 1);
      k = Math.min(k, avail / sum);
    });
    var span = (W - L - R - NODE_W) / Math.max(1, cols - 1);
    D.nodes.forEach(function (n) { n.x = L + n.col * span; n.h = Math.max(3, n.value * k); });
    // počiatočné usporiadanie: stĺpec na stred
    colNodes.forEach(function (list, c) {
      var total = list.reduce(function (a, n) { return a + n.h; }, 0) + gapOf(c) * (list.length - 1);
      var y = T + (H - T - B - total) / 2;
      list.forEach(function (n) { n.y = y; y += n.h + gapOf(c); });
    });
    var inL = {}, outL = {};
    D.links.forEach(function (l) {
      (outL[l.s] = outL[l.s] || []).push(l);
      (inL[l.t] = inL[l.t] || []).push(l);
    });
    function resolve(list, c) {
      var g = gapOf(c);
      list.sort(function (a, b) { return a.ord - b.ord || a.y - b.y; });
      for (var i = 1; i < list.length; i++) {
        var need = list[i - 1].y + list[i - 1].h + g;
        if (list[i].y < need) list[i].y = need;
      }
      var over = list.length ? list[list.length - 1].y + list[list.length - 1].h - (H - B) : 0;
      if (over > 0) {
        list[list.length - 1].y -= over;
        for (var j = list.length - 2; j >= 0; j--) {
          var lim = list[j + 1].y - g - list[j].h;
          if (list[j].y > lim) list[j].y = lim;
        }
      }
      if (list.length && list[0].y < T) {
        list[0].y = T;
        for (var m = 1; m < list.length; m++) {
          var nd = list[m - 1].y + list[m - 1].h + g;
          if (list[m].y < nd) list[m].y = nd;
        }
      }
    }
    function pull(n, links, side) {
      var tot = 0, acc = 0;
      links.forEach(function (l) {
        var o = byId[side === 'in' ? l.s : l.t];
        acc += (o.y + o.h / 2) * l.v; tot += l.v;
      });
      return tot ? acc / tot - n.h / 2 : n.y;
    }
    for (var it = 0; it < 8; it++) {
      for (var c1 = 1; c1 < cols; c1++) {
        colNodes[c1].forEach(function (n) { if (inL[n.id]) n.y = pull(n, inL[n.id], 'in'); });
        resolve(colNodes[c1], c1);
      }
      for (var c2 = cols - 2; c2 >= 0; c2--) {
        colNodes[c2].forEach(function (n) { if (outL[n.id]) n.y = (n.y + pull(n, outL[n.id], 'out')) / 2; });
        resolve(colNodes[c2], c2);
      }
    }
    // pozície prepojení na uzloch
    D.nodes.forEach(function (n) {
      var o = (outL[n.id] || []).slice().sort(function (a, b) { return byId[a.t].y - byId[b.t].y; });
      var i = (inL[n.id] || []).slice().sort(function (a, b) { return byId[a.s].y - byId[b.s].y; });
      var offO = 0, offI = 0;
      o.forEach(function (l) { l.h = Math.max(1, l.v * k); l.sy = n.y + offO; offO += l.h; });
      i.forEach(function (l) { l.h = Math.max(1, l.v * k); l.ty = n.y + offI; offI += l.h; });
    });
    return {cols: cols, L: L, R: R, T: T, B: B, hasStreams: hasStreams};
  }

  function label(g, n, geo, W) {
    var lines = [];
    var val = money(n.value);
    var yoy = n.yoy;
    lines.push({t: n.label, w: 700, fs: 13, c: '#1c2430'});
    var l2 = {parts: [{t: val, w: 700, c: '#1c2430'}], fs: 12.5};
    if (yoy != null && D.has_prev) {
      var good = yoy >= 0;
      var col = n.type === 'cost' ? '#6b7585' : (good ? '#1b7a3d' : '#c62828');
      l2.parts.push({t: ' · ' + pct(yoy), w: 700, c: col});
    }
    lines.push(l2);
    if (n.sub) lines.push({t: n.sub, w: 400, fs: 11, c: '#6b7585'});
    var anchor, x, y0;
    var cx = n.x + NODE_W / 2;
    if (n.col === 0 && geo.hasStreams) { anchor = 'end'; x = n.x - 8; y0 = n.y + n.h / 2 - (lines.length - 1) * 7.5; }
    else if (n.col === geo.cols - 1) { anchor = 'start'; x = n.x + NODE_W + 8; y0 = n.y + n.h / 2 - (lines.length - 1) * 7.5; }
    else if (n.col === 0) { anchor = 'start'; x = n.x - 4; y0 = n.y - 6 - (lines.length - 1) * 15; }
    else { anchor = 'middle'; x = cx; y0 = n.y - 6 - (lines.length - 1) * 15; }
    lines.forEach(function (ln, i) {
      var tx = s('text', {x: x, y: y0 + i * (anchor === 'middle' ? 15 : 15) + 4, 'text-anchor': anchor,
        'font-size': ln.fs || 12, class: 'sk-lbl'}, g);
      if (ln.parts) {
        ln.parts.forEach(function (p) {
          var ts = s('tspan', {'font-weight': p.w, fill: p.c}, tx); ts.textContent = p.t;
        });
      } else {
        tx.setAttribute('font-weight', ln.w); tx.setAttribute('fill', ln.c); tx.textContent = ln.t;
      }
      // zúžiť písmo, ak sa text nezmestí
      var avail = anchor === 'end' ? x - 4 : (anchor === 'start' ? W - x - 2 : 170);
      var guard = 0;
      while (tx.getComputedTextLength && tx.getComputedTextLength() > avail && guard++ < 14) {
        var fs = parseFloat(tx.getAttribute('font-size'));
        if (fs > 10) { tx.setAttribute('font-size', fs - 0.5); continue; }
        var t = tx.textContent;
        if (t.length < 6) break;
        tx.textContent = t.slice(0, Math.max(3, t.length - 3)).replace(/\s+$/, '') + '…';
      }
    });
  }

  function showTip(ev, html) {
    tip.textContent = '';
    html.forEach(function (row) {
      var d = document.createElement('div');
      d.className = row.cls || '';
      d.textContent = row.t;
      tip.appendChild(d);
    });
    tip.style.display = 'block';
    var r = box.getBoundingClientRect();
    var x = ev.clientX - r.left + 14, y = ev.clientY - r.top + 12;
    if (x + tip.offsetWidth > r.width - 4) x = ev.clientX - r.left - tip.offsetWidth - 14;
    tip.style.left = Math.max(4, x) + 'px'; tip.style.top = y + 'px';
  }
  function hideTip() { tip.style.display = 'none'; }

  function draw() {
    var old = box.querySelector('svg');
    if (old) box.removeChild(old);
    var W = Math.max(640, box.clientWidth || 900), H = 470;
    D.nodes.forEach(function (n) { delete n.y; });
    var geo = layout(W, H);
    var svg = s('svg', {width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img',
      'aria-label': 'Tok od tržieb k zisku'});
    var gl = s('g', {}, svg), gn = s('g', {}, svg), gt = s('g', {}, svg);
    var linkEls = [];
    D.links.forEach(function (l) {
      var a = byId[l.s], b = byId[l.t];
      var x1 = a.x + NODE_W, x2 = b.x, xm = (x1 + x2) / 2;
      var d = 'M' + x1 + ' ' + l.sy + ' C' + xm + ' ' + l.sy + ',' + xm + ' ' + l.ty + ',' + x2 + ' ' + l.ty +
        ' L' + x2 + ' ' + (l.ty + l.h) + ' C' + xm + ' ' + (l.ty + l.h) + ',' + xm + ' ' + (l.sy + l.h) + ',' + x1 + ' ' + (l.sy + l.h) + ' Z';
      var p = s('path', {d: d, fill: RIB[b.type], 'fill-opacity': 0.85, class: 'sk-link'}, gl);
      p.addEventListener('pointermove', function (ev) {
        p.setAttribute('fill-opacity', 1);
        showTip(ev, [{t: a.label + ' → ' + b.label, cls: 'tt'}, {t: money(l.v) + ' (' + (l.v / revenue * 100).toFixed(1).replace('.', ',') + ' % tržieb)'}]);
      });
      p.addEventListener('pointerleave', function () { p.setAttribute('fill-opacity', 0.85); hideTip(); });
      linkEls.push(p);
    });
    D.nodes.forEach(function (n) {
      var r = s('rect', {x: n.x, y: n.y, width: NODE_W, height: n.h, fill: COL[n.type], rx: 2, class: 'sk-node'}, gn);
      r.addEventListener('pointermove', function (ev) {
        var rows = [{t: n.label, cls: 'tt'}, {t: money(n.value) + ' (' + (n.value / revenue * 100).toFixed(1).replace('.', ',') + ' % tržieb)'}];
        if (n.prev != null && D.has_prev) {
          rows.push({t: 'rok predtým: ' + money(n.prev)});
          if (n.yoy != null) rows.push({t: 'medziročne: ' + pct(n.yoy)});
        }
        showTip(ev, rows);
      });
      r.addEventListener('pointerleave', hideTip);
      label(gt, n, geo, W);
    });
    box.insertBefore(svg, tip);
  }

  // tlačidlá a výber obdobia
  var sel = document.getElementById('flow-period');
  if (sel) sel.addEventListener('change', function () {
    var u = new URL(window.location.href);
    u.searchParams.set('flow', sel.value);
    document.body.classList.add('loading');
    window.location.href = u.toString();
  });
  var tiles = document.getElementById('flow-tiles');
  if (tiles) {
    D.tiles.forEach(function (t, i) {
      var d = document.createElement('div'); d.className = 'ftile';
      var n = document.createElement('div'); n.className = 'fnum'; n.textContent = String(i + 1);
      var l = document.createElement('div'); l.className = 'flabel'; l.textContent = t.label;
      var v = document.createElement('div'); v.className = 'fval ' + (t.good ? 'up' : 'down');
      v.textContent = pct(t.value);
      d.appendChild(n); d.appendChild(l); d.appendChild(v); tiles.appendChild(d);
    });
  }
  draw();
  window.addEventListener('resize', draw);
})();
