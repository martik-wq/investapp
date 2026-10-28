/* Posúvanie tabuliek ťahaním myšou */
(function () {
  document.querySelectorAll('.tablewrap').forEach(function (w) {
    var down = false, sx = 0, sl = 0, moved = false;
    w.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse' || e.button !== 0) return;
      down = true; moved = false; sx = e.clientX; sl = w.scrollLeft;
    });
    window.addEventListener('pointermove', function (e) {
      if (!down) return;
      var dx = e.clientX - sx;
      if (Math.abs(dx) > 3) { moved = true; w.classList.add('dragging'); }
      if (moved) w.scrollLeft = sl - dx;
    });
    window.addEventListener('pointerup', function () {
      down = false; w.classList.remove('dragging');
    });
  });
  document.addEventListener('submit', function () { document.body.classList.add('loading'); });
  window.addEventListener('pageshow', function () { document.body.classList.remove('loading'); });
  document.querySelectorAll('.nav a, .recent a').forEach(function (a) {
    a.addEventListener('click', function () { document.body.classList.add('loading'); });
  });
})();
