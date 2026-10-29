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

/* Vysvetlivky pri ikonke ⓘ: zobrazia sa hneď pri nabehnutí kurzorom (aj na dotyk/klávesnicu) */
(function () {
  var box = document.createElement('div');
  box.className = 'tipx'; box.setAttribute('role', 'tooltip');
  document.body.appendChild(box);
  function show(el) {
    var t = el.getAttribute('data-tip');
    if (!t) return;
    box.textContent = t; box.style.display = 'block';
    var r = el.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
    var x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    var y = r.bottom + 8;
    if (y + h > window.innerHeight - 8) y = Math.max(8, r.top - h - 8);
    box.style.left = x + 'px'; box.style.top = y + 'px';
  }
  function hide() { box.style.display = 'none'; }
  document.addEventListener('mouseover', function (e) {
    var el = e.target.closest && e.target.closest('.info[data-tip]');
    if (el) show(el); else hide();
  });
  document.addEventListener('focusin', function (e) {
    var el = e.target.closest && e.target.closest('.info[data-tip]');
    if (el) show(el);
  });
  document.addEventListener('focusout', hide);
  window.addEventListener('scroll', hide, true);
})();
