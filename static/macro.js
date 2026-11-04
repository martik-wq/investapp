/* Makro grafy: jednoduché SVG čiarové grafy s ukazovateľom hodnoty pod myšou. Bez knižníc. */
(function () {
  var el = document.getElementById('macrodata');
  if (!el) return;
  var cards = JSON.parse(el.textContent);
  function fmt(v) { return v.toFixed(2).replace('.', ','); }
  cards.forEach(function (c) {
    var box = document.getElementById('mc-' + c.id);
    if (!box || !c.points || c.points.length < 2) return;
    var P = c.points, W = 520, H = 190, ML = 8, MR = 46, MT = 8, MB = 20;
    var lo = Infinity, hi = -Infinity;
    P.forEach(function (p) { if (p[1] < lo) lo = p[1]; if (p[1] > hi) hi = p[1]; });
    if (lo > 0 && c.id !== 'T10Y2Y') lo = Math.min(lo, 0);
    if (hi === lo) hi = lo + 1;
    var pad = (hi - lo) * 0.06; hi += pad; if (lo !== 0) lo -= pad;
    var t0 = Date.parse(P[0][0]), t1 = Date.parse(P[P.length - 1][0]);
    var X = function (d) { return ML + (Date.parse(d) - t0) / (t1 - t0) * (W - ML - MR); };
    var Y = function (v) { return MT + (hi - v) / (hi - lo) * (H - MT - MB); };
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" style="display:block">';
    for (var k = 0; k <= 4; k++) {
      var v = lo + (hi - lo) * k / 4, y = Y(v);
      s += '<line x1="' + ML + '" x2="' + (W - MR) + '" y1="' + y + '" y2="' + y + '" stroke="#e5e7eb"/>' +
           '<text x="' + (W - MR + 4) + '" y="' + (y + 4) + '" font-size="11" fill="#64748b">' + fmt(v) + '</text>';
    }
    if (lo < 0 && hi > 0) s += '<line x1="' + ML + '" x2="' + (W - MR) + '" y1="' + Y(0) + '" y2="' + Y(0) + '" stroke="#94a3b8"/>';
    for (var yr = new Date(t0).getFullYear() + 1; yr <= new Date(t1).getFullYear(); yr += 2) {
      var x = X(yr + '-01-01');
      s += '<text x="' + x + '" y="' + (H - 5) + '" font-size="11" fill="#64748b" text-anchor="middle">' + yr + '</text>';
    }
    var d = P.map(function (p, i) { return (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); }).join('');
    s += '<path d="' + d + '" fill="none" stroke="#c2410c" stroke-width="1.8"/>' +
         '<line id="ml-' + c.id + '" y1="' + MT + '" y2="' + (H - MB) + '" stroke="#475569" stroke-dasharray="3 3" style="display:none"/>' +
         '<text id="mt-' + c.id + '" font-size="12" fill="#1e293b" y="16"></text></svg>';
    box.innerHTML = s;
    var svg = box.firstChild;
    svg.addEventListener('mousemove', function (e) {
      var r = svg.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * W;
      var f = Math.min(1, Math.max(0, (x - ML) / (W - ML - MR))), t = t0 + f * (t1 - t0), best = 0, bd = Infinity;
      P.forEach(function (p, i) { var dd = Math.abs(Date.parse(p[0]) - t); if (dd < bd) { bd = dd; best = i; } });
      var px = X(P[best][0]), ln = document.getElementById('ml-' + c.id), tx = document.getElementById('mt-' + c.id);
      ln.setAttribute('x1', px); ln.setAttribute('x2', px); ln.style.display = '';
      tx.textContent = P[best][0] + ': ' + fmt(P[best][1]) + ' ' + c.unit;
      tx.setAttribute('x', px > W / 2 ? px - 8 : px + 8); tx.setAttribute('text-anchor', px > W / 2 ? 'end' : 'start');
    });
    svg.addEventListener('mouseleave', function () {
      document.getElementById('ml-' + c.id).style.display = 'none';
      document.getElementById('mt-' + c.id).textContent = '';
    });
  });
})();
