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

/* Aktualizácia aplikácie z GitHubu bez vypínania: tlačidlo v bočnom paneli */
(function () {
  var btn = document.getElementById('updBtn'), msg = document.getElementById('updMsg');
  if (!btn) return;
  var state = 'idle';
  function setMsg(t) { msg.textContent = t || ''; }
  function mark(available) {
    state = available ? 'available' : 'idle';
    btn.textContent = available ? '⬆ Aktualizovať na novú verziu' : '⟳ Skontrolovať aktualizáciu';
    btn.className = available ? 'upd-new' : 'ghost';
  }
  function check(silent) {
    if (!silent) { btn.disabled = true; setMsg('Kontrolujem…'); }
    return fetch('/update/check').then(function (r) { return r.json(); }).then(function (d) {
      btn.disabled = false;
      if (!d.ok) { if (!silent) setMsg('Nepodarilo sa overiť verziu (internet?).'); return; }
      mark(d.available);
      setMsg(d.available ? 'Je dostupná nová verzia.' : (silent ? '' : 'Máš najnovšiu verziu ✓'));
      try { sessionStorage.setItem('investapp_upd_check', String(Date.now())); } catch (e) {}
    }).catch(function () { btn.disabled = false; if (!silent) setMsg('Nepodarilo sa overiť verziu.'); });
  }
  function overlay(text) {
    var o = document.getElementById('updOverlay');
    if (!o) { o = document.createElement('div'); o.id = 'updOverlay'; document.body.appendChild(o); }
    o.textContent = text; o.style.display = 'flex';
  }
  function waitForServer(tries) {
    fetch('/update/ping', {cache: 'no-store'}).then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function () { location.reload(); })
      .catch(function () {
        if (tries <= 0) { overlay('Aplikácia sa nespustila späť. Zatvor okno s aplikáciou a spusti ju znova cez spustit.bat.'); return; }
        setTimeout(function () { waitForServer(tries - 1); }, 1000);
      });
  }
  function apply() {
    overlay('Sťahujem a inštalujem novú verziu… (stránka sa po chvíli sama obnoví)');
    fetch('/update/apply', {method: 'POST'}).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { document.getElementById('updOverlay').style.display = 'none'; setMsg(d.error || 'Aktualizácia sa nepodarila.'); return; }
      overlay('Hotovo. Spúšťam aplikáciu s novou verziou…');
      setTimeout(function () { waitForServer(40); }, d.changed && d.changed.length ? 2500 : 300);
    }).catch(function () {
      /* server sa mohol reštartovať počas odpovede */
      setTimeout(function () { waitForServer(40); }, 2000);
    });
  }
  btn.addEventListener('click', function () { if (state === 'available') apply(); else check(false); });
  try {
    var last = Number(sessionStorage.getItem('investapp_upd_check') || 0);
    if (Date.now() - last > 30 * 60 * 1000) check(true);
  } catch (e) { check(true); }
})();
