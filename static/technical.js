/* Technická analýza: SVG graf s indikátormi (sviečky/čiara, SMA, Bollinger, objem, RSI, MACD). Bez knižníc. */
(function () {
  var el = document.getElementById('techdata');
  if (!el) return;
  var D = JSON.parse(el.textContent), S = D.series, N = S.dates.length;
  var W = 1000, ML = 8, MR = 64;
  var st = {range: 252, type: 'candle', sma20: false, sma50: true, sma200: true, bb: false, vol: true, rsi: true, macd: true};
  var box = document.getElementById('techchart'), info = document.getElementById('techinfo');
  var C = {up: '#15803d', down: '#b91c1c', grid: '#e5e7eb', txt: '#64748b', s20: '#0ea5e9', s50: '#c2410c', s200: '#1e293b', bb: '#94a3b8', macd: '#2563eb', sig: '#c2410c'};

  function fmt(v, d) { return v == null ? '–' : v.toFixed(d == null ? 2 : d).replace('.', ','); }
  function fvol(v) { return v >= 1e9 ? fmt(v / 1e9, 2) + ' mld.' : v >= 1e6 ? fmt(v / 1e6, 1) + ' mil.' : v >= 1e3 ? fmt(v / 1e3, 0) + ' tis.' : fmt(v, 0); }
  function range(i0, i1, arrs) {
    var lo = Infinity, hi = -Infinity;
    arrs.forEach(function (a) { for (var i = i0; i <= i1; i++) { var v = a[i]; if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; } } });
    return [lo, hi];
  }
  function path(a, i0, i1, X, Y) {
    var d = '', pen = false;
    for (var i = i0; i <= i1; i++) {
      if (a[i] == null) { pen = false; continue; }
      d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(a[i]).toFixed(1);
      pen = true;
    }
    return d;
  }
  function render() {
    var i0 = st.range ? Math.max(0, N - st.range) : 0, i1 = N - 1, cnt = i1 - i0 + 1;
    var step = (W - ML - MR) / cnt;
    var X = function (i) { return ML + (i - i0 + 0.5) * step; };
    var panels = [{id: 'price', h: 340}];
    if (st.vol) panels.push({id: 'vol', h: 80});
    if (st.rsi) panels.push({id: 'rsi', h: 110});
    if (st.macd) panels.push({id: 'macd', h: 130});
    var gap = 14, axisH = 22, y = 6, out = '';
    panels.forEach(function (p) { p.y = y; y += p.h + gap; });
    var H = y - gap + axisH;
    out += '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="Cenový graf s indikátormi" style="display:block">';
    panels.forEach(function (p) {
      var Y, lo, hi, g = '';
      if (p.id === 'price') {
        var arrs = [S.high, S.low];
        if (st.sma20) arrs.push(S.sma20); if (st.sma50) arrs.push(S.sma50); if (st.sma200) arrs.push(S.sma200);
        if (st.bb) { arrs.push(S.bb_up); arrs.push(S.bb_lo); }
        var r = range(i0, i1, arrs); var pad = (r[1] - r[0]) * 0.04 || 1; lo = r[0] - pad; hi = r[1] + pad;
      } else if (p.id === 'vol') { lo = 0; hi = range(i0, i1, [S.volume])[1] * 1.1 || 1; }
      else if (p.id === 'rsi') { lo = 0; hi = 100; }
      else { var rm = range(i0, i1, [S.macd, S.macd_sig, S.macd_hist]); var m = Math.max(Math.abs(rm[0]), Math.abs(rm[1])) * 1.1 || 1; lo = -m; hi = m; }
      Y = function (v) { return p.y + p.h - (v - lo) / (hi - lo) * p.h; };
      p.Y = Y; p.lo = lo; p.hi = hi;
      // mriežka a osi
      var ticks = p.id === 'rsi' ? [30, 50, 70] : p.id === 'vol' ? [hi / 1.1 / 2, hi / 1.1] : [0, 1, 2, 3, 4].map(function (k) { return lo + (hi - lo) * k / 4; });
      if (p.id === 'macd') ticks = [lo * 0.8, 0, hi * 0.8];
      ticks.forEach(function (t) {
        out += '<line x1="' + ML + '" x2="' + (W - MR) + '" y1="' + Y(t).toFixed(1) + '" y2="' + Y(t).toFixed(1) + '" stroke="' + C.grid + '"' + ((p.id === 'rsi' && t !== 50) ? ' stroke-dasharray="4 3"' : '') + '/>';
        out += '<text x="' + (W - MR + 6) + '" y="' + (Y(t) + 4).toFixed(1) + '" font-size="11" fill="' + C.txt + '">' + (p.id === 'vol' ? fvol(t) : p.id === 'rsi' ? t : fmt(t, p.id === 'macd' ? 2 : (hi < 20 ? 2 : 1))) + '</text>';
      });
      out += '<text x="' + (ML + 4) + '" y="' + (p.y + 12) + '" font-size="11" fill="' + C.txt + '" font-weight="600">' +
        {price: '', vol: 'Objem', rsi: 'RSI (14)', macd: 'MACD (12, 26, 9)'}[p.id] + '</text>';
      if (p.id === 'price') {
        if (st.bb) {
          var up = '', lw = [];
          for (var i = i0; i <= i1; i++) if (S.bb_up[i] != null) { up += (up ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(S.bb_up[i]).toFixed(1); lw.push([X(i), Y(S.bb_lo[i])]); }
          if (up) {
            var poly = up; for (var k = lw.length - 1; k >= 0; k--) poly += 'L' + lw[k][0].toFixed(1) + ' ' + lw[k][1].toFixed(1);
            out += '<path d="' + poly + 'Z" fill="' + C.bb + '" opacity="0.15"/>';
            out += '<path d="' + path(S.bb_up, i0, i1, X, Y) + '" fill="none" stroke="' + C.bb + '" stroke-width="1"/>';
            out += '<path d="' + path(S.bb_lo, i0, i1, X, Y) + '" fill="none" stroke="' + C.bb + '" stroke-width="1"/>';
          }
        }
        if (st.type === 'line') {
          out += '<path d="' + path(S.close, i0, i1, X, Y) + '" fill="none" stroke="#0f172a" stroke-width="1.6"/>';
        } else {
          var cw = Math.max(1, step * 0.66);
          for (var j = i0; j <= i1; j++) {
            var up_ = S.close[j] >= S.open[j], col = up_ ? C.up : C.down;
            out += '<line x1="' + X(j).toFixed(1) + '" x2="' + X(j).toFixed(1) + '" y1="' + Y(S.high[j]).toFixed(1) + '" y2="' + Y(S.low[j]).toFixed(1) + '" stroke="' + col + '" stroke-width="1"/>';
            var yt = Y(Math.max(S.open[j], S.close[j])), hh = Math.max(1, Math.abs(Y(S.open[j]) - Y(S.close[j])));
            out += '<rect x="' + (X(j) - cw / 2).toFixed(1) + '" y="' + yt.toFixed(1) + '" width="' + cw.toFixed(1) + '" height="' + hh.toFixed(1) + '" fill="' + col + '"/>';
          }
        }
        [['sma20', C.s20], ['sma50', C.s50], ['sma200', C.s200]].forEach(function (m) {
          if (st[m[0]]) out += '<path d="' + path(S[m[0]], i0, i1, X, Y) + '" fill="none" stroke="' + m[1] + '" stroke-width="1.5"/>';
        });
        [['support', C.up], ['resistance', C.down]].forEach(function (lv) {
          (D[lv[0]] || []).forEach(function (v) {
            if (v >= lo && v <= hi) out += '<line x1="' + ML + '" x2="' + (W - MR) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '" stroke="' + lv[1] + '" stroke-dasharray="2 4" opacity="0.55"/>';
          });
        });
      } else if (p.id === 'vol') {
        var bw = Math.max(1, step * 0.7);
        for (var q = i0; q <= i1; q++) out += '<rect x="' + (X(q) - bw / 2).toFixed(1) + '" y="' + Y(S.volume[q]).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + (Y(0) - Y(S.volume[q])).toFixed(1) + '" fill="' + (S.close[q] >= S.open[q] ? C.up : C.down) + '" opacity="0.55"/>';
      } else if (p.id === 'rsi') {
        out += '<path d="' + path(S.rsi, i0, i1, X, Y) + '" fill="none" stroke="#7c3aed" stroke-width="1.4"/>';
      } else {
        var bw2 = Math.max(1, step * 0.7);
        for (var h = i0; h <= i1; h++) if (S.macd_hist[h] != null) {
          var y0 = Y(0), y1 = Y(S.macd_hist[h]);
          out += '<rect x="' + (X(h) - bw2 / 2).toFixed(1) + '" y="' + Math.min(y0, y1).toFixed(1) + '" width="' + bw2.toFixed(1) + '" height="' + Math.max(0.5, Math.abs(y1 - y0)).toFixed(1) + '" fill="' + (S.macd_hist[h] >= 0 ? C.up : C.down) + '" opacity="0.45"/>';
        }
        out += '<path d="' + path(S.macd, i0, i1, X, Y) + '" fill="none" stroke="' + C.macd + '" stroke-width="1.3"/>';
        out += '<path d="' + path(S.macd_sig, i0, i1, X, Y) + '" fill="none" stroke="' + C.sig + '" stroke-width="1.3"/>';
      }
    });
    // dátumy
    var last = panels[panels.length - 1], yy = last.y + last.h + 15;
    for (var t = 0; t <= 5; t++) {
      var ii = Math.min(i1, i0 + Math.round((cnt - 1) * t / 5));
      out += '<text x="' + X(ii).toFixed(1) + '" y="' + yy + '" font-size="11" fill="' + C.txt + '" text-anchor="' + (t === 0 ? 'start' : t === 5 ? 'end' : 'middle') + '">' + S.dates[ii] + '</text>';
    }
    out += '<line id="techx" x1="0" x2="0" y1="6" y2="' + (H - axisH) + '" stroke="#0f172a" stroke-width="0.8" stroke-dasharray="3 3" style="display:none"/>';
    out += '<rect id="techhit" x="' + ML + '" y="0" width="' + (W - ML - MR) + '" height="' + (H - axisH) + '" fill="transparent"/></svg>';
    box.innerHTML = out;
    var hit = document.getElementById('techhit'), xl = document.getElementById('techx'), svg = box.firstChild;
    function at(ev) {
      var r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) / r.width * W;
      var i = Math.max(i0, Math.min(i1, i0 + Math.floor((px - ML) / step)));
      xl.setAttribute('x1', X(i)); xl.setAttribute('x2', X(i)); xl.style.display = '';
      show(i);
    }
    hit.addEventListener('mousemove', at);
    hit.addEventListener('mouseleave', function () { xl.style.display = 'none'; show(N - 1); });
    show(N - 1);
  }
  function show(i) {
    var cur = D.currency ? ' ' + D.currency : '';
    info.innerHTML = '<strong>' + S.dates[i] + '</strong> · O ' + fmt(S.open[i]) + ' · H ' + fmt(S.high[i]) + ' · L ' + fmt(S.low[i]) +
      ' · <strong>Z ' + fmt(S.close[i]) + cur + '</strong> · Obj. ' + fvol(S.volume[i]) +
      (S.sma50[i] != null ? ' · SMA50 ' + fmt(S.sma50[i]) : '') + (S.sma200[i] != null ? ' · SMA200 ' + fmt(S.sma200[i]) : '') +
      (S.rsi[i] != null ? ' · RSI ' + fmt(S.rsi[i], 0) : '') + (S.macd[i] != null ? ' · MACD ' + fmt(S.macd[i]) : '');
  }
  document.querySelectorAll('[data-range]').forEach(function (b) {
    b.addEventListener('click', function () {
      st.range = +b.dataset.range;
      document.querySelectorAll('[data-range]').forEach(function (x) { x.classList.toggle('on', x === b); });
      render();
    });
  });
  document.querySelectorAll('[data-type]').forEach(function (b) {
    b.addEventListener('click', function () {
      st.type = b.dataset.type;
      document.querySelectorAll('[data-type]').forEach(function (x) { x.classList.toggle('on', x === b); });
      render();
    });
  });
  document.querySelectorAll('[data-toggle]').forEach(function (c) {
    c.addEventListener('change', function () { st[c.dataset.toggle] = c.checked; render(); });
  });
  render();
})();
