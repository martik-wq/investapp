/* Posúvanie tabuliek: ťahanie myšou a tlačidlá ◀ ▶ */
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
  document.querySelectorAll('[data-scroll]').forEach(function (b) {
    b.addEventListener('click', function () {
      var w = document.querySelector('.pane.on .tablewrap') || document.querySelector('.tablewrap');
      if (!w) return;
      w.scrollBy({left: +b.dataset.scroll * Math.max(300, w.clientWidth * 0.7), behavior: 'smooth'});
    });
  });
})();
