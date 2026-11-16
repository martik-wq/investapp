/* 3D pozadie úvodného pásu: vlniaca sa „dátová krajina“ v perspektíve + žiariaca čiara grafu.
   Čistý canvas bez knižníc. Zastaví sa, keď karta nie je viditeľná, rešpektuje „menej pohybu“. */
(function () {
  var cv = document.getElementById('hero3d');
  if (!cv || !cv.getContext) return;
  var ctx = cv.getContext('2d');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W = 0, H = 0, DPR = Math.min(window.devicePixelRatio || 1, 2);
  var COLS = 46, ROWS = 26, SPACING = 1;
  var t0 = performance.now(), running = true, raf = 0;

  function size() {
    var r = cv.getBoundingClientRect();
    W = r.width; H = r.height;
    cv.width = Math.round(W * DPR); cv.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }

  // výška terénu: zložené vlny (ako trh – trend + cykly)
  function height(x, z, t) {
    return 0.9 * Math.sin(x * 0.32 + t * 0.6) * Math.cos(z * 0.21 - t * 0.4)
         + 0.55 * Math.sin((x + z) * 0.17 + t * 0.9)
         + 0.35 * Math.cos(x * 0.71 - z * 0.33 + t * 1.3)
         + 0.25 * Math.sin(z * 0.9 + t * 0.7);
  }

  // perspektívna projekcia 3D bodu (kamera nad terénom, mierne natočená)
  function proj(x, y, z, yaw) {
    var cx = Math.cos(yaw), sx = Math.sin(yaw);
    var X = x * cx - z * sx, Z = x * sx + z * cx;
    var camY = 3.2, camZ = -6.5, f = Math.min(W, H * 1.6) * 0.9;
    var zz = Z - camZ;
    if (zz < 0.5) return null;
    return [W * 0.5 + (X / zz) * f, H * 0.18 + ((camY - y) / zz) * f * 0.55, zz];
  }

  function frame(now) {
    var t = (now - t0) / 1000 * (reduce ? 0 : 1);
    ctx.clearRect(0, 0, W, H);
    var yaw = Math.sin(t * 0.08) * 0.18 - 0.12;
    var scroll = (t * 0.9) % SPACING;
    var grid = [];
    for (var r = 0; r < ROWS; r++) {
      var row = [];
      var z = r * SPACING - scroll;
      for (var c = 0; c < COLS; c++) {
        var x = (c - COLS / 2) * SPACING * 0.75;
        var y = height(x, z + t * 0.9, t);
        row.push(proj(x, y, z, yaw));
      }
      grid.push(row);
    }
    // čiary terénu – vzadu tenšie a priehľadnejšie
    ctx.lineWidth = 1;
    for (var r2 = ROWS - 1; r2 >= 0; r2--) {
      var depth = r2 / (ROWS - 1);
      var a = 0.55 * (1 - depth) + 0.04;
      ctx.strokeStyle = 'rgba(255,138,61,' + a.toFixed(3) + ')';
      ctx.beginPath();
      var started = false;
      for (var c2 = 0; c2 < COLS; c2++) {
        var p = grid[r2][c2];
        if (!p) { started = false; continue; }
        if (!started) { ctx.moveTo(p[0], p[1]); started = true; } else ctx.lineTo(p[0], p[1]);
      }
      ctx.stroke();
    }
    for (var c3 = 0; c3 < COLS; c3 += 2) {
      ctx.strokeStyle = 'rgba(120,160,255,0.10)';
      ctx.beginPath();
      var st = false;
      for (var r3 = 0; r3 < ROWS; r3++) {
        var q = grid[r3][c3];
        if (!q) { st = false; continue; }
        if (!st) { ctx.moveTo(q[0], q[1]); st = true; } else ctx.lineTo(q[0], q[1]);
      }
      ctx.stroke();
    }
    // body vpredu ako „svetielka“
    for (var r4 = 0; r4 < 6; r4++) {
      for (var c4 = 0; c4 < COLS; c4 += 3) {
        var d = grid[r4][c4];
        if (!d) continue;
        var s = Math.max(0.6, 3.2 / d[2] * 2);
        ctx.fillStyle = 'rgba(255,190,140,' + (0.5 - r4 * 0.07).toFixed(2) + ')';
        ctx.beginPath(); ctx.arc(d[0], d[1], s, 0, 6.283); ctx.fill();
      }
    }
    // žiariaca rastúca čiara grafu
    var n = 90, pts = [];
    for (var i = 0; i < n; i++) {
      var u = i / (n - 1);
      var trend = u * 0.55;
      var noise = 0.06 * Math.sin(u * 23 + t * 1.6) + 0.04 * Math.sin(u * 57 - t * 2.3) + 0.03 * Math.cos(u * 11 + t);
      pts.push([W * (0.05 + u * 0.95), H * (0.78 - trend - noise)]);
    }
    var head = Math.floor(((t * 0.18) % 1.35) * n);
    var grad = ctx.createLinearGradient(0, 0, W, 0);
    grad.addColorStop(0, 'rgba(242,106,46,0)');
    grad.addColorStop(0.5, 'rgba(242,106,46,0.55)');
    grad.addColorStop(1, 'rgba(255,200,150,0.9)');
    ctx.save();
    ctx.shadowColor = 'rgba(242,106,46,0.9)'; ctx.shadowBlur = 16;
    ctx.strokeStyle = grad; ctx.lineWidth = 2.2;
    ctx.beginPath();
    for (var k = 0; k < Math.min(head, n); k++) { if (k === 0) ctx.moveTo(pts[k][0], pts[k][1]); else ctx.lineTo(pts[k][0], pts[k][1]); }
    ctx.stroke();
    if (head > 0 && head <= n) {
      var hp = pts[Math.min(head, n) - 1];
      ctx.fillStyle = '#ffd2b0';
      ctx.beginPath(); ctx.arc(hp[0], hp[1], 3.6, 0, 6.283); ctx.fill();
    }
    ctx.restore();
    if (running && !reduce) raf = requestAnimationFrame(frame);
  }

  size();
  window.addEventListener('resize', function () { size(); if (reduce) frame(performance.now()); });
  document.addEventListener('visibilitychange', function () {
    running = !document.hidden;
    cancelAnimationFrame(raf);
    if (running) raf = requestAnimationFrame(frame);
  });
  raf = requestAnimationFrame(frame);
})();
