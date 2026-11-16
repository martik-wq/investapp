/* Našepkávanie firiem: <input data-suggest="go|fill|list">.
   go = po výbere otvorí firmu, fill = vloží ticker do políčka, list = pridá ticker do zoznamu oddeleného čiarkami. */
(function () {
  var URL = (document.querySelector('meta[name="suggest-url"]') || {}).content || '/suggest';
  var GO = (document.querySelector('meta[name="company-url"]') || {}).content || '/company/__';
  var box = document.createElement('div');
  box.className = 'sugg'; box.setAttribute('role', 'listbox'); box.style.display = 'none';
  document.body.appendChild(box);
  var cur = null, items = [], sel = -1, seq = 0, timer = 0;

  function esc(s) { return String(s || '').replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function token(inp) { return inp.dataset.suggest === 'list' ? inp.value.split(/[,;\s]+/).pop() : inp.value; }
  function place() {
    if (!cur) return;
    var r = cur.getBoundingClientRect();
    box.style.left = Math.max(8, r.left) + 'px';
    box.style.top = (r.bottom + 6) + 'px';
    box.style.width = Math.max(r.width, 340) + 'px';
  }
  function hide() { box.style.display = 'none'; items = []; sel = -1; }
  function render(q) {
    if (!items.length) {
      box.innerHTML = q.length >= 2 ? '<div class="sugg-empty">Nič sa nenašlo. Skús iný názov alebo ticker.</div>' : '';
      box.style.display = q.length >= 2 ? 'block' : 'none'; place(); return;
    }
    var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'i');
    box.innerHTML = items.map(function (it, i) {
      return '<div class="sugg-i' + (i === sel ? ' on' : '') + '" data-i="' + i + '" role="option">' +
        '<span class="sugg-s">' + esc(it.symbol) + '</span>' +
        '<span class="sugg-n">' + esc(it.name).replace(re, '<mark>$1</mark>') + '</span>' +
        '<span class="sugg-x">' + esc(it.kind ? it.kind + ' · ' + it.ex : it.ex) + '</span></div>';
    }).join('') + '<div class="sugg-f">↑↓ vybrať · Enter potvrdiť · Esc zavrieť</div>';
    box.style.display = 'block'; place();
  }
  function choose(i) {
    var it = items[i]; if (!it || !cur) return;
    var mode = cur.dataset.suggest;
    if (mode === 'go') {
      document.body.classList.add('loading');
      location.href = GO.replace('__', encodeURIComponent(it.symbol));
    } else if (mode === 'list') {
      var parts = cur.value.split(/[,;\s]+/); parts.pop(); parts = parts.filter(Boolean); parts.push(it.symbol);
      cur.value = parts.join(', ') + ', ';
      cur.focus();
    } else {
      cur.value = it.symbol;
      cur.dispatchEvent(new Event('change'));
      var nxt = cur.form && cur.form.querySelector('input:not([type=hidden]):not([data-suggest])');
      if (nxt) nxt.focus();
    }
    hide();
  }
  function query(inp) {
    var q = token(inp).trim();
    if (q.length < 2) { hide(); return; }
    var my = ++seq;
    // najprv rýchlo bez Yahoo (SEC + moje firmy), potom doplniť s Yahoo
    [0, 1].forEach(function (y) {
      fetch(URL + '?y=' + y + '&q=' + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
        if (my !== seq || cur !== inp) return;
        if (y === 0 && items.length && sel >= 0) return;
        items = d.items || []; if (sel >= items.length) sel = -1;
        render(q);
      }).catch(function () {});
    });
  }
  document.addEventListener('input', function (e) {
    var inp = e.target;
    if (!inp.dataset || !inp.dataset.suggest) return;
    cur = inp; sel = -1;
    clearTimeout(timer); timer = setTimeout(function () { query(inp); }, 160);
  });
  document.addEventListener('keydown', function (e) {
    if (!cur || e.target !== cur || box.style.display === 'none') return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!items.length) return;
      e.preventDefault();
      sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      render(token(cur).trim());
    } else if (e.key === 'Enter' && sel >= 0) {
      e.preventDefault(); choose(sel);
    } else if (e.key === 'Escape') { hide(); }
  });
  box.addEventListener('mousedown', function (e) {
    var el = e.target.closest('.sugg-i'); if (!el) return;
    e.preventDefault(); choose(+el.dataset.i);
  });
  document.addEventListener('focusout', function (e) { if (e.target === cur) setTimeout(hide, 120); });
  window.addEventListener('resize', place);
  window.addEventListener('scroll', place, true);
})();
