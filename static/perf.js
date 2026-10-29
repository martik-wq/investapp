/* Graf výkonnosti portfólia a indexov (čisté SVG). Údaje: <script id="perf-data"> */
(function () {
  var el = document.getElementById('perf-data');
  var box = document.getElementById('perf-chart');
  if (!el || !box) return;
  var D = JSON.parse(el.textContent);
  var NS = 'http://www.w3.org/2000/svg';
  var tip = document.getElementById('perf-tip');
  var N = D.dates.length;
  var days = D.dates.map(function (d) { return Date.parse(d + 'T00:00:00Z') / 864e5; });
  var series = [{id: 'portfolio', label: 'Moje portfólio', color: '#2a78d6', width: 2.6, values: D.portfolio, on: true}]
    .concat(D.bench.map(function (b) { return {id: b.id, label: b.label, color: b.color, width: 1.8, values: b.values, on: true}; }));
  var period = 'ytd', s0 = 0, s1 = N - 1;

  function s(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function pct(v, d) {
    if (v == null) return '–';
    return (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(d == null ? 1 : d).replace('.', ',') + ' %';
  }
  function iso(i) { return D.dates[i]; }
  function skDate(i) { var p = D.dates[i].split('-'); return p[2] + '.' + p[1] + '.' + p[0]; }
  function idxAtOrBefore(day) {
    var lo = 0, hi = N - 1, r = 0;
    while (lo <= hi) { var m = (lo + hi) >> 1; if (days[m] <= day) { r = m; lo = m + 1; } else hi = m - 1; }
    return r;
  }
  function addMonths(i, m) {
    var d = new Date(days[i] * 864e5); d.setUTCMonth(d.getUTCMonth() - m);
    return idxAtOrBefore(d.getTime() / 864e5);
  }
  function setPeriod(p) {
    period = p;
    var last = N - 1;
    if (p === 'ytd') {
      var y = new Date(days[last] * 864e5).getUTCFullYear();
      var dec31 = Date.UTC(y - 1, 11, 31) / 864e5;
      s0 = days[0] > dec31 ? 0 : idxAtOrBefore(dec31);
    } else if (p === '1m') s0 = addMonths(last, 1);
    else if (p === '3m') s0 = addMonths(last, 3);
    else if (p === '6m') s0 = addMonths(last, 6);
    else if (p === '1y') s0 = addMonths(last, 12);
    else s0 = 0;
    s1 = last;
    document.querySelectorAll('#perf-periods button').forEach(function (b) { b.classList.toggle('on', b.dataset.p === p); });
    var f = document.getElementById('perf-from'), t = document.getElementById('perf-to');
    f.value = iso(s0); t.value = iso(s1);
    draw();
  }
  function niceTicks(lo, hi) {
    if (lo === hi) hi = lo + 0.01;
    var span = hi - lo, raw = span / 5, p = Math.pow(10, Math.floor(Math.log10(raw)));
    var f = raw / p, step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
    var a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
    for (var v = a; v <= b + step / 2; v += step) t.push(Math.abs(v) < step / 1e6 ? 0 : v);
    return t;
  }
  function rel(sr, i) {
    var b = sr.values[s0], v = sr.values[i];
    if (b == null || v == null || !b) return null;
    return v / b - 1;
  }

  function legend() {
    var lg = document.getElementById('perf-legend');
    lg.textContent = '';
    series.forEach(function (sr) {
      var b = document.createElement('button'); b.type = 'button';
      b.className = 'chip' + (sr.on ? ' on' : '');
      var k = document.createElement('span'); k.className = 'key'; k.style.background = sr.color;
      b.appendChild(k); b.appendChild(document.createTextNode(sr.label));
      b.onclick = function () { sr.on = !sr.on; legend(); draw(); };
      lg.appendChild(b);
    });
  }

  function summary() {
    var parts = [];
    series.forEach(function (sr) {
      if (!sr.on) return;
      parts.push(sr.label + ' ' + pct(rel(sr, s1)));
    });
    var pf = rel(series[0], s1), b1 = series.length > 1 ? series.filter(function (x, i) { return i > 0 && x.on; })[0] : null;
    var txt = skDate(s0) + ' – ' + skDate(s1) + ': ' + parts.join(' · ');
    if (b1 && pf != null && rel(b1, s1) != null) {
      var d = (pf - rel(b1, s1)) * 100;
      txt += ' · rozdiel voči ' + b1.label + ' ' + (d >= 0 ? '+' : '−') + Math.abs(d).toFixed(1).replace('.', ',') + ' p. b.';
    }
    document.getElementById('perf-sum').textContent = txt;
  }

  function draw() {
    var old = box.querySelector('svg'); if (old) box.removeChild(old);
    var W = Math.max(480, box.clientWidth || 900), H = 340, L = 56, R = 16, T = 12, B = 30;
    var vis = series.filter(function (x) { return x.on; });
    var lo = 0, hi = 0;
    for (var i = s0; i <= s1; i++) vis.forEach(function (sr) {
      var r = rel(sr, i); if (r != null) { lo = Math.min(lo, r); hi = Math.max(hi, r); }
    });
    var ticks = niceTicks(lo, hi); lo = ticks[0]; hi = ticks[ticks.length - 1];
    var x0 = days[s0], x1 = days[s1] === days[s0] ? days[s0] + 1 : days[s1];
    var X = function (d) { return L + (d - x0) / (x1 - x0) * (W - L - R); };
    var Y = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    var svg = s('svg', {width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Výkonnosť portfólia a indexov'});
    ticks.forEach(function (t) {
      s('line', {x1: L, x2: W - R, y1: Y(t), y2: Y(t), stroke: t === 0 ? '#9aa3b2' : '#e6e8ec', 'stroke-width': t === 0 ? 1.2 : 1}, svg);
      var tx = s('text', {x: L - 8, y: Y(t) + 4, 'text-anchor': 'end', class: 'ax'}, svg);
      tx.textContent = (t * 100).toFixed(Math.abs(hi - lo) < 0.1 ? 1 : 0).replace('.', ',') + ' %';
    });
    // osi času: asi 6 popisov
    var span = s1 - s0, step = Math.max(1, Math.floor(span / 6));
    for (var j = s0; j <= s1; j += step) {
      var tx2 = s('text', {x: X(days[j]), y: H - 8, 'text-anchor': 'middle', class: 'ax'}, svg);
      var p = D.dates[j].split('-');
      tx2.textContent = span > 400 ? p[1] + '/' + p[0].slice(2) : p[2] + '.' + p[1] + '.';
    }
    vis.forEach(function (sr) {
      var d = '', pen = false;
      for (var i2 = s0; i2 <= s1; i2++) {
        var r = rel(sr, i2);
        if (r == null) { pen = false; continue; }
        d += (pen ? 'L' : 'M') + X(days[i2]).toFixed(1) + ' ' + Y(r).toFixed(1); pen = true;
      }
      s('path', {d: d, fill: 'none', stroke: sr.color, 'stroke-width': sr.width, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
    });
    var cross = s('line', {y1: T, y2: H - B, stroke: '#8a93a3', 'stroke-width': 1, 'stroke-dasharray': '3 3', opacity: 0}, svg);
    var dots = vis.map(function (sr) { return s('circle', {r: 4, fill: sr.color, stroke: '#fff', 'stroke-width': 2, opacity: 0}, svg); });
    var hit = s('rect', {x: L, y: 0, width: W - L - R, height: H, fill: 'transparent'}, svg);
    box.insertBefore(svg, tip);
    function at(ev) {
      var r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) * (W / r.width);
      var day = x0 + (x - L) / (W - L - R) * (x1 - x0);
      return Math.max(s0, Math.min(s1, idxAtOrBefore(day)));
    }
    hit.addEventListener('pointermove', function (ev) {
      var i3 = at(ev), cx = X(days[i3]);
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('opacity', 1);
      tip.textContent = '';
      var h = document.createElement('div'); h.className = 'th'; h.textContent = skDate(i3); tip.appendChild(h);
      vis.forEach(function (sr, k) {
        var r = rel(sr, i3);
        if (r == null) { dots[k].setAttribute('opacity', 0); return; }
        dots[k].setAttribute('cx', cx); dots[k].setAttribute('cy', Y(r)); dots[k].setAttribute('opacity', 1);
        var row = document.createElement('div'); row.className = 'tr';
        var key = document.createElement('span'); key.className = 'key'; key.style.background = sr.color;
        var m = document.createElement('div'); m.className = 'tm';
        var l = document.createElement('div'); l.className = 'tl';
        var st = document.createElement('strong'); st.textContent = pct(r);
        var nm = document.createElement('span'); nm.className = 'tn'; nm.textContent = ' ' + sr.label;
        l.appendChild(st); l.appendChild(nm); m.appendChild(l);
        if (sr.id === 'portfolio' && D.value) {
          var c = document.createElement('div'); c.className = 'tc';
          c.textContent = 'hodnota pozícií ' + D.value[i3].toLocaleString('sk-SK', {maximumFractionDigits: 0}) + ' ' + D.currency;
          m.appendChild(c);
        }
        row.appendChild(key); row.appendChild(m); tip.appendChild(row);
      });
      tip.style.display = 'block';
      var px = cx * (box.clientWidth / W), left = px + 14;
      if (left + tip.offsetWidth > box.clientWidth - 4) left = px - tip.offsetWidth - 14;
      tip.style.left = Math.max(4, left) + 'px'; tip.style.top = '8px';
    });
    hit.addEventListener('pointerleave', function () {
      cross.setAttribute('opacity', 0); dots.forEach(function (d) { d.setAttribute('opacity', 0); }); tip.style.display = 'none';
    });
    summary();
  }

  document.querySelectorAll('#perf-periods button').forEach(function (b) { b.onclick = function () { setPeriod(b.dataset.p); }; });
  document.getElementById('perf-apply').onclick = function () {
    var f = document.getElementById('perf-from').value, t = document.getElementById('perf-to').value;
    if (!f || !t) return;
    var a = idxAtOrBefore(Date.parse(f + 'T00:00:00Z') / 864e5), b = idxAtOrBefore(Date.parse(t + 'T00:00:00Z') / 864e5);
    if (b <= a) return;
    period = 'custom'; s0 = a; s1 = b;
    document.querySelectorAll('#perf-periods button').forEach(function (x) { x.classList.remove('on'); });
    draw();
  };
  legend();
  setPeriod('ytd');
  window.addEventListener('resize', draw);
})();
