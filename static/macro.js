/* Makro grafy: výber obdobia, hodnota alebo zmena za 12 mesiacov (tempo), zväčšenie, porovnanie dvoch bodov
   a tabuľka zmien za rôzne obdobia. Čisté SVG, bez knižníc. */
(function () {
  var el = document.getElementById('macrodata');
  if (!el) return;
  var cards = JSON.parse(el.textContent);
  var DAY = 864e5;
  var RANGES = [['1R', 1], ['3R', 3], ['5R', 5], ['10R', 10], ['Všetko', 0]];
  var PERIODS = [['1 mesiac', 30], ['3 mesiace', 91], ['6 mesiacov', 182], ['1 rok', 365], ['3 roky', 1095], ['5 rokov', 1826], ['10 rokov', 3652]];
  var st = {range: 5, mode: 'lvl'};          // spoločné pre všetky grafy

  function num(v, d) { var s = v.toFixed(d == null ? 2 : d); if (/^-0[.,]?0*$/.test(s)) s = s.slice(1); return s.replace('.', ',').replace('-', '−'); }
  function sgn(v, d) { return (v > 0 ? '+' : '') + num(v, d); }
  function h(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function t(d) { return Date.parse(d); }
  function fmtD(d) { return d.slice(8, 10) + '.' + d.slice(5, 7) + '.' + d.slice(0, 4); }

  // hodnota k dátumu (posledná známa najneskôr v ten deň), index v poli
  function idxAt(P, ms) {
    var lo = 0, hi = P.length - 1, r = -1;
    while (lo <= hi) { var m = (lo + hi) >> 1; if (t(P[m][0]) <= ms) { r = m; lo = m + 1; } else hi = m - 1; }
    return r;
  }
  // rada podľa režimu: úroveň alebo zmena za 12 mesiacov (p. b.)
  function series(c) {
    var P = c.points;
    if (st.mode === 'lvl') return P;
    var out = [];
    for (var i = 0; i < P.length; i++) {
      var j = idxAt(P, t(P[i][0]) - 365 * DAY);
      if (j >= 0 && t(P[i][0]) - t(P[j][0]) > 330 * DAY) out.push([P[i][0], P[i][1] - P[j][1]]);
    }
    return out;
  }
  function visible(S) {
    if (!S.length || !st.range) return S;
    var lim = t(S[S.length - 1][0]) - st.range * 365.25 * DAY;
    return S.filter(function (p) { return t(p[0]) >= lim; });
  }
  function unitTxt(c) { return st.mode === 'lvl' ? c.unit : 'p. b.'; }

  function draw(box, c, opt) {
    var S = visible(series(c));
    box.innerHTML = '';
    if (S.length < 2) { box.appendChild(h('div', 'note', 'Na toto obdobie nie je dosť údajov.')); return; }
    var big = opt.big, W = big ? 1000 : 520, H = big ? 430 : 200, ML = 8, MR = big ? 60 : 48, MT = 22, MB = 22;
    var lo = Infinity, hi = -Infinity;
    S.forEach(function (p) { if (p[1] < lo) lo = p[1]; if (p[1] > hi) hi = p[1]; });
    if (st.mode === 'lvl' && lo > 0 && c.id !== 'T10Y2Y') lo = 0;
    if (hi === lo) hi = lo + 1;
    var pad = (hi - lo) * 0.06; hi += pad; if (lo !== 0) lo -= pad;
    var t0 = t(S[0][0]), t1 = t(S[S.length - 1][0]);
    var X = function (d) { return ML + (t(d) - t0) / (t1 - t0) * (W - ML - MR); };
    var Y = function (v) { return MT + (hi - v) / (hi - lo) * (H - MT - MB); };
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" style="display:block;cursor:crosshair">';
    for (var k = 0; k <= 4; k++) {
      var v = lo + (hi - lo) * k / 4, y = Y(v);
      s += '<line x1="' + ML + '" x2="' + (W - MR) + '" y1="' + y + '" y2="' + y + '" stroke="#eee6dc"/>' +
           '<text x="' + (W - MR + 4) + '" y="' + (y + 4) + '" font-size="' + (big ? 12 : 11) + '" fill="#7a6a5a">' + num(v, Math.abs(hi - lo) < 3 ? 2 : 1) + '</text>';
    }
    if (lo < 0 && hi > 0) s += '<line x1="' + ML + '" x2="' + (W - MR) + '" y1="' + Y(0) + '" y2="' + Y(0) + '" stroke="#94a3b8"/>';
    var y0 = new Date(t0).getFullYear(), y1 = new Date(t1).getFullYear(), stepY = Math.max(1, Math.ceil((y1 - y0) / (big ? 12 : 6)));
    for (var yr = y0 + 1; yr <= y1; yr += stepY) {
      var x = X(yr + '-01-01');
      s += '<line x1="' + x + '" x2="' + x + '" y1="' + MT + '" y2="' + (H - MB) + '" stroke="#f3ece4"/>' +
           '<text x="' + x + '" y="' + (H - 6) + '" font-size="11" fill="#7a6a5a" text-anchor="middle">' + yr + '</text>';
    }
    // vyznačený úsek medzi dvoma vybranými bodmi
    var pk = opt.pick;
    if (pk && pk.a != null && pk.b != null) {
      var xa = X(pk.a[0]), xb = X(pk.b[0]);
      s += '<rect x="' + Math.min(xa, xb) + '" y="' + MT + '" width="' + Math.abs(xb - xa) + '" height="' + (H - MT - MB) + '" fill="#c2410c" opacity="0.07"/>';
    }
    var d = S.map(function (p, i) { return (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); }).join('');
    s += '<path d="' + d + '" fill="none" stroke="#c2410c" stroke-width="' + (big ? 2.2 : 1.8) + '"/>';
    [pk && pk.a, pk && pk.b].forEach(function (p) {
      if (p) s += '<circle cx="' + X(p[0]) + '" cy="' + Y(p[1]) + '" r="5" fill="#fff" stroke="#c2410c" stroke-width="2.2"/>';
    });
    s += '<line class="mline" y1="' + MT + '" y2="' + (H - MB) + '" stroke="#475569" stroke-dasharray="3 3" style="display:none"/>' +
         '<circle class="mdot" r="3.5" fill="#c2410c" style="display:none"/>' +
         '<text class="mtxt" font-size="' + (big ? 13 : 12) + '" fill="#1e293b" y="14"></text></svg>';
    box.innerHTML = s;
    var svg = box.firstChild, ln = svg.querySelector('.mline'), dot = svg.querySelector('.mdot'), tx = svg.querySelector('.mtxt');
    function near(e) {
      var r = svg.getBoundingClientRect(), xx = (e.clientX - r.left) / r.width * W;
      var f = Math.min(1, Math.max(0, (xx - ML) / (W - ML - MR)));
      var i = idxAt(S, t0 + f * (t1 - t0));
      if (i < 0) i = 0;
      if (i < S.length - 1 && Math.abs(t(S[i + 1][0]) - (t0 + f * (t1 - t0))) < Math.abs(t(S[i][0]) - (t0 + f * (t1 - t0)))) i++;
      return S[i];
    }
    svg.addEventListener('mousemove', function (e) {
      var p = near(e), px = X(p[0]);
      ln.setAttribute('x1', px); ln.setAttribute('x2', px); ln.style.display = '';
      dot.setAttribute('cx', px); dot.setAttribute('cy', Y(p[1])); dot.style.display = '';
      tx.textContent = fmtD(p[0]) + ': ' + num(p[1]) + ' ' + unitTxt(c);
      tx.setAttribute('x', px > W / 2 ? px - 8 : px + 8); tx.setAttribute('text-anchor', px > W / 2 ? 'end' : 'start');
    });
    svg.addEventListener('mouseleave', function () { ln.style.display = 'none'; dot.style.display = 'none'; tx.textContent = ''; });
    if (opt.onPick) svg.addEventListener('click', function (e) { opt.onPick(near(e)); });
  }

  // text porovnania dvoch bodov: rozdiel, relatívna zmena a tempo za rok
  function cmpText(c, pk) {
    if (!pk || pk.a == null || pk.b == null) return pk && pk.a ? 'Vybraný ' + fmtD(pk.a[0]) + ' (' + num(pk.a[1]) + ' ' + unitTxt(c) + '). Klikni na druhý bod.' : '';
    var a = pk.a, b = pk.b;
    if (t(b[0]) < t(a[0])) { var x = a; a = b; b = x; }
    var yrs = (t(b[0]) - t(a[0])) / (365.25 * DAY), diff = b[1] - a[1];
    var out = fmtD(a[0]) + ' → ' + fmtD(b[0]) + ': ' + num(a[1]) + ' → ' + num(b[1]) + ' ' + unitTxt(c) +
      ' · zmena ' + sgn(diff) + ' p. b.';
    if (a[1] > 0 && b[1] > 0) out += ' (' + sgn((b[1] / a[1] - 1) * 100, 1) + ' %)';
    if (yrs >= 0.25) out += ' · tempo ' + sgn(diff / yrs) + ' p. b. za rok (' + num(yrs, 1) + ' r.)';
    return out;
  }

  // tabuľka zmien za obdobia (k poslednému dátumu)
  function periodTable(c, compact) {
    var S = series(c), last = S[S.length - 1], wrap = h('div', 'tablewrap');
    if (!last) return wrap;
    var tb = h('table', 'plain mtab'), hr = h('tr');
    (compact ? ['Obdobie', 'Zmena', 'Tempo za rok'] : ['Obdobie', 'Vtedy', 'Teraz', 'Zmena', 'Tempo za rok']).forEach(function (x) { hr.appendChild(h('th', null, x)); });
    var th = h('thead'); th.appendChild(hr); tb.appendChild(th);
    var body = h('tbody');
    PERIODS.forEach(function (pr) {
      var j = idxAt(S, t(last[0]) - pr[1] * DAY);
      if (j < 0 || t(last[0]) - t(S[j][0]) < pr[1] * DAY * 0.8) return;
      var diff = last[1] - S[j][1], yrs = pr[1] / 365.25, tr = h('tr');
      tr.appendChild(h('td', null, pr[0]));
      if (!compact) {
        tr.appendChild(h('td', null, num(S[j][1]) + ' (' + fmtD(S[j][0]) + ')'));
        tr.appendChild(h('td', null, num(last[1])));
      }
      var z = h('td', diff < 0 ? 'neg' : null, sgn(diff) + ' p. b.'); tr.appendChild(z);
      tr.appendChild(h('td', null, yrs >= 1 ? sgn(diff / yrs) + ' p. b./rok' : '–'));
      body.appendChild(tr);
    });
    tb.appendChild(body); wrap.appendChild(tb);
    return wrap;
  }

  /* ---------------------------------------------------------------- ovládanie a karty */
  var bar = document.getElementById('macrobar');
  function btns(grp, items, key) {
    grp.innerHTML = '';
    items.forEach(function (it) {
      var b = h('button', st[key] === it[1] ? 'on' : null, it[0]); b.type = 'button';
      b.onclick = function () { st[key] = it[1]; renderAll(); };
      grp.appendChild(b);
    });
  }
  var picks = {};
  function renderCard(c) {
    var box = document.getElementById('mc-' + c.id);
    if (!box || !c.points || c.points.length < 2) return;
    var pk = picks[c.id] || (picks[c.id] = {a: null, b: null});
    var cmp = document.getElementById('mcmp-' + c.id);
    draw(box, c, {pick: pk, onPick: function (p) { pickAdd(pk, p); renderCard(c); }});
    var txt = cmpText(c, pk);
    cmp.textContent = txt; cmp.style.display = txt ? 'block' : 'none';
    if (txt) { var x = h('button', 'cmpx', 'zrušiť'); x.type = 'button'; x.onclick = function () { picks[c.id] = {a: null, b: null}; renderCard(c); };
      cmp.appendChild(document.createTextNode(' ')); cmp.appendChild(x); }
  }
  function pickAdd(pk, p) {
    if (pk.a == null) pk.a = p;
    else if (pk.b == null) { if (p[0] === pk.a[0]) pk.a = null; else pk.b = p; }
    else { pk.a = p; pk.b = null; }
  }
  function renderAll() {
    if (bar) {
      btns(bar.querySelector('[data-g="range"]'), RANGES, 'range');
      btns(bar.querySelector('[data-g="mode"]'), [['Hodnota', 'lvl'], ['Zmena za 12 mesiacov', 'yoy']], 'mode');
    }
    picks = {};
    cards.forEach(renderCard);
  }

  /* ---------------------------------------------------------------- zväčšený graf */
  var modal = document.getElementById('m-modal');
  function openModal(c) {
    modal.textContent = '';
    var box = h('div', 'gmbox'), head = h('div', 'ghead');
    head.appendChild(h('h3', 'gtitle', c.name + (st.mode === 'yoy' ? ' · zmena za 12 mesiacov' : '')));
    var cl = h('button', 'gexp', '✕'); cl.type = 'button'; cl.setAttribute('aria-label', 'Zavrieť'); cl.onclick = closeModal;
    head.appendChild(cl); box.appendChild(head);
    var rg = h('div', 'tgrp'); box.appendChild(rg);
    var cmp = h('div', 'gcmp'); box.appendChild(cmp);
    var host = h('div'); box.appendChild(host);
    box.appendChild(h('div', 'note', 'Prejdi myšou po grafe pre hodnotu v danom dni. Klikni na dva body a ukáže sa zmena medzi nimi aj tempo za rok.'));
    var tbl = h('div'); box.appendChild(tbl);
    modal.appendChild(box); modal.hidden = false; document.body.classList.add('noscroll');
    var pk = {a: null, b: null};
    function redraw() {
      rg.innerHTML = '';
      RANGES.forEach(function (it) {
        var b = h('button', st.range === it[1] ? 'on' : null, it[0]); b.type = 'button';
        b.onclick = function () { st.range = it[1]; pk = {a: null, b: null}; redraw(); renderAll(); };
        rg.appendChild(b);
      });
      draw(host, c, {big: true, pick: pk, onPick: function (p) { pickAdd(pk, p); redraw(); }});
      var txt = cmpText(c, pk);
      cmp.textContent = txt; cmp.style.display = txt ? 'block' : 'none';
      if (txt) { var x = h('button', 'cmpx', 'zrušiť'); x.type = 'button'; x.onclick = function () { pk = {a: null, b: null}; redraw(); };
        cmp.appendChild(document.createTextNode(' ')); cmp.appendChild(x); }
      tbl.innerHTML = ''; tbl.appendChild(h('h3', null, 'Zmena za obdobie (k ' + fmtD(series(c).slice(-1)[0][0]) + ')')); tbl.appendChild(periodTable(c));
    }
    redraw();
    modal.onclick = function (e) { if (e.target === modal) closeModal(); };
  }
  function closeModal() { modal.hidden = true; modal.textContent = ''; document.body.classList.remove('noscroll'); }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && modal && !modal.hidden) closeModal(); });

  cards.forEach(function (c) {
    var b = document.querySelector('[data-expand="' + c.id + '"]');
    if (b) b.onclick = function () { openModal(c); };
    var tb = document.getElementById('mtab-' + c.id);
    if (tb && c.points && c.points.length > 1) tb.appendChild(periodTable(c, true));
  });
  renderAll();
  // tabuľky zmien pod grafmi sa menia s režimom (hodnota / zmena za 12 mesiacov)
  var _ra = renderAll;
  renderAll = function () {
    _ra();
    cards.forEach(function (c) {
      var tb = document.getElementById('mtab-' + c.id);
      if (tb && c.points && c.points.length > 1) { tb.innerHTML = ''; tb.appendChild(periodTable(c, true)); }
    });
  };
  renderAll();
})();
