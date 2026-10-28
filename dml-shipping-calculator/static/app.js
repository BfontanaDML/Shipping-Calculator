/* DML Shipping Calculator - employee screen.
 * Packing, validation and pricing all run on the server (shipping/*.py).
 * This file only manages the form and shows results. */
(function () {
  'use strict';

  var root = document.getElementById('app');
  var API = root.getAttribute('data-api') || 'api/';
  var CFG = null;
  var state = {
    product: null, qtyText: '', service: null,
    qty: null, suggestion: null, rows: [],
    total: '',
    touched: {}
  };
  var suggestToken = 0, quoteToken = 0, suggestTimer = null, quoteTimer = null;

  // ---------- helpers ----------
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'text') n.textContent = v;
      else if (k === 'cls') n.className = v;
      else if (k === 'value') n.value = v;
      else n.setAttribute(k, v === true ? '' : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c !== null && c !== undefined) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return n;
  }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function fmtInt(n) { return Number(n).toLocaleString('en-CA'); }
  function money(v) { return String(v).charAt(0) === '<' ? '< $' + String(v).slice(1) : '$' + v; }
  function product() { return CFG.products.filter(function (p) { return p.id === state.product; })[0] || null; }
  function box(id) { return CFG.boxes.filter(function (b) { return b.id === id; })[0] || null; }
  function service() { return CFG.services.filter(function (s) { return s.id === state.service; })[0] || null; }
  function weightsApply() { var s = service(); return !!(s && s.weights_apply); }
  function post(path, body) {
    return fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return { error: 'Server error (' + r.status + ').' }; }); })
      .catch(function () { return { error: 'Cannot reach the server. Check your connection.' }; });
  }

  // "Not entered yet" messages only appear once the employee has reached that field.
  var MISSING = {
    product: 'Choose a product.', quantity: 'Enter the quantity.', service: 'Choose a UPS service.',
    ups_total_cost: 'Enter the discounted UPS total cost.'
  };
  var INPUTS = { quantity: 'quantity', ups_total_cost: 'ups-total' };
  function showErr(key, msg) {
    var n = document.querySelector('[data-err="' + key + '"]');
    if (!n) return;
    var visible = msg && (MISSING[key] !== msg || state.touched[key]);
    n.textContent = visible ? msg : '';
    if (INPUTS[key]) $(INPUTS[key]).classList.toggle('bad', !!visible);
  }

  // ---------- step 1 ----------
  function segmented(container, name, items) {
    clear(container);
    items.forEach(function (it) {
      var id = name + '-' + it.id;
      container.appendChild(el('span', { cls: 'seg' },
        el('input', { type: 'radio', name: name, id: id, value: it.id }),
        el('label', { 'for': id, text: it.label })));
    });
  }

  // ---------- step 2 ----------
  function rowsFromSuggestion(s) {
    return s.boxes.map(function (b) {
      return { box_id: b.box_id, count: String(b.count), pieces: String(b.pieces_per_box), measured: '' };
    });
  }

  function requestSuggestion() {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(suggestNow, 300);
  }

  function suggestNow() {
    var token = ++suggestToken;
    var had = state.suggestion !== null;
    if (!state.product || !state.qtyText.trim()) {
      state.suggestion = null; state.rows = []; state.qty = null;
      renderBoxes(); scheduleQuote(); return;
    }
    post('suggest', { product_id: state.product, quantity: state.qtyText }).then(function (s) {
      if (token !== suggestToken) return;
      if (s.error) {
        state.suggestion = null; state.rows = []; state.qty = null;
      } else {
        state.suggestion = s; state.qty = s.quantity; state.rows = rowsFromSuggestion(s);
        if (had) clearRates('Boxes changed: get a new UPS Total Cost.');
      }
      renderBoxes(); scheduleQuote();
    });
  }

  function clearRates(note) {
    if (state.total === '') return;
    state.total = '';
    $('ups-total').value = '';
    var n = $('rates-note'); n.textContent = note; n.hidden = false;
  }

  function boxSelect(row, i) {
    var p = product();
    var sel = el('select', { 'data-f': 'box', 'data-i': i, 'aria-label': 'Box size, row ' + (i + 1) });
    p.boxes.forEach(function (a) {
      if (!a.selectable) return; // boxes blocked for this product are not offered
      var b = box(a.box_id);
      var opt = el('option', { value: b.id, text: b.dims_text + (a.auto ? '' : ' (not confirmed)') });
      if (row.box_id === b.id) opt.selected = true;
      sel.appendChild(opt);
    });
    return sel;
  }

  function cellInput(field, i, value, label, cls, mode) {
    return el('input', { type: 'text', inputmode: mode || 'numeric', 'data-f': field, 'data-i': i, cls: 'num ' + (cls || ''),
                         'aria-label': label + ', row ' + (i + 1), autocomplete: 'off', value: value });
  }

  function renderBoxes() {
    var has = !!(CFG && state.suggestion && product());
    $('boxes-area').hidden = !has;
    $('boxes-empty').hidden = has;
    if (!has) return;
    $('boxes').classList.toggle('no-weights', !weightsApply());
    var tb = document.querySelector('#boxes tbody');
    clear(tb);
    state.rows.forEach(function (row, i) {
      var tr = el('tr', { 'data-i': i },
        el('td', { 'data-label': 'Boxes' }, cellInput('count', i, row.count, 'Number of boxes', 'small'),
          el('p', { cls: 'err', 'data-row-err': 'count' })),
        el('td', { 'data-label': 'Box (in)' }, boxSelect(row, i), el('p', { cls: 'err', 'data-row-err': 'box' }), el('p', { cls: 'note' })),
        el('td', { 'data-label': 'Pcs per box' }, cellInput('pieces', i, row.pieces, 'Pieces per box'), el('p', { cls: 'cap' }),
          el('p', { cls: 'err', 'data-row-err': 'pieces' })),
        el('td', { cls: 'wcol dim', 'data-label': 'Dim. weight' }),
        el('td', { 'data-label': 'Measured weight' },
          el('span', { cls: 'with-unit' }, cellInput('measured', i, row.measured, 'Measured weight per box in pounds', '', 'decimal'), el('span', { text: 'lb' })),
          el('p', { cls: 'err', 'data-row-err': 'measured' })),
        el('td', { cls: 'wcol qw', 'data-label': 'Quote weight' }),
        el('td', { cls: 'rm' }, el('button', { type: 'button', cls: 'icon-btn', 'data-act': 'remove', 'data-i': i,
                                           'aria-label': 'Remove row ' + (i + 1), title: 'Remove row', text: '×' })));
      tb.appendChild(tr);
      fillStatic(tr, row);
    });
    $('add-row').hidden = state.rows.length >= CFG.limits.max_box_rows;
    var s = service();
    $('weight-hint').textContent = !s ? 'Choose a UPS service to see weights.' :
      (s.weights_apply ? '' : 'Expedited/Saver: use the billable weight from the UPS quote.');
  }

  function fillStatic(tr, row) {
    var a = product().boxes.filter(function (x) { return x.box_id === row.box_id; })[0];
    var b = box(row.box_id);
    tr.querySelector('.cap').textContent = a && a.capacity ? 'max ' + fmtInt(a.capacity) : '';
    tr.querySelector('.dim').textContent = b ? b.dim_weight_lb + ' lb' : '';
    tr.querySelector('.qw').textContent = '';
  }

  // ---------- quote ----------
  function scheduleQuote() {
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(quoteNow, 200);
  }

  function quoteNow() {
    var token = ++quoteToken;
    var body = {
      product_id: state.product, quantity: state.qtyText, service: state.service,
      rows: state.rows.map(function (r) { return { box_id: r.box_id, count: r.count, pieces: r.pieces, measured_weight_lb: r.measured }; }),
      ups_total_cost: state.total
    };
    post('quote', body).then(function (q) {
      if (token !== quoteToken) return;
      if (q.error) { showResult(null); showErr('packing', q.error); return; }
      applyQuote(q);
    });
  }

  function applyQuote(q) {
    var e = q.errors || {};
    ['product', 'quantity', 'service', 'ups_total_cost', 'packing'].forEach(function (k) { showErr(k, e[k]); });
    var trs = document.querySelectorAll('#boxes tbody tr');
    (q.rows || []).forEach(function (r, i) {
      var tr = trs[i];
      if (!tr) return;
      ['count', 'box', 'pieces', 'measured'].forEach(function (k) {
        var msg = (r.errors || {})[k] || '';
        tr.querySelector('[data-row-err="' + k + '"]').textContent = msg;
        var input = tr.querySelector('[data-f="' + k + '"]');
        if (input) input.classList.toggle('bad', !!msg);
      });
      tr.querySelector('.note').textContent = r.note || '';
      var qw = tr.querySelector('.qw');
      clear(qw);
      if (q.weights_apply && r.quote_weight_lb) {
        tr.querySelector('.dim').textContent = r.dim_weight_lb + ' lb';
        qw.appendChild(el('strong', { text: r.quote_weight_lb + ' lb' }));
        if (r.measured_rounded_lb && r.measured_rounded_lb > r.dim_weight_lb) qw.appendChild(el('span', { cls: 'tiny', text: ' (measured)' }));
      }
    });
    var t = q.totals, tt = $('totals');
    clear(tt);
    if (t && q.quantity) {
      tt.appendChild(el('strong', { text: fmtInt(t.box_count) + (t.box_count === 1 ? ' box' : ' boxes') }));
      tt.appendChild(document.createTextNode(' · ' + fmtInt(t.pieces) + ' of ' + fmtInt(q.quantity) + ' pcs'));
      if (q.weights_apply && t.quote_weight_lb !== null) tt.appendChild(document.createTextNode(' · ' + fmtInt(t.quote_weight_lb) + ' lb quote weight'));
    }
    showResult(q.status === 'complete' ? q.price : null);
  }

  function showResult(price) {
    $('r-total').textContent = price ? money(price.customer_shipping_price) + ' ' + price.currency : '—';
    $('r-piece').textContent = price ? money(price.shipping_price_per_piece) : '—';
    document.querySelector('.results').classList.toggle('ready', !!price);
  }

  // ---------- events ----------
  function touch(k) { state.touched[k] = true; }

  $('product').addEventListener('change', function (e) {
    state.product = e.target.value; touch('product');
    requestSuggestion();
  });
  $('quantity').addEventListener('input', function (e) {
    state.qtyText = e.target.value; touch('product');
    requestSuggestion();
  });
  $('quantity').addEventListener('blur', function () { touch('quantity'); touch('product'); scheduleQuote(); });
  $('service').addEventListener('change', function (e) {
    var had = !!state.service;
    state.service = e.target.value; touch('service');
    if (had) clearRates('Service changed: get a new UPS Total Cost.');
    renderBoxes(); scheduleQuote();
  });
  $('ups-total').addEventListener('input', function (e) {
    state.total = e.target.value; touch('ups_total_cost'); $('rates-note').hidden = true; scheduleQuote();
  });
  $('ups-total').addEventListener('blur', function () {
    touch('ups_total_cost'); touch('service'); touch('quantity'); scheduleQuote();
  });

  var tbody = document.querySelector('#boxes tbody');
  tbody.addEventListener('input', function (e) {
    var f = e.target.getAttribute('data-f'), i = Number(e.target.getAttribute('data-i'));
    if (!f || !state.rows[i]) return;
    if (f === 'count') state.rows[i].count = e.target.value;
    else if (f === 'pieces') state.rows[i].pieces = e.target.value;
    else if (f === 'measured') state.rows[i].measured = e.target.value;
    scheduleQuote();
  });
  tbody.addEventListener('change', function (e) {
    if (e.target.getAttribute('data-f') !== 'box') return;
    var i = Number(e.target.getAttribute('data-i'));
    state.rows[i].box_id = e.target.value;
    fillStatic(e.target.closest('tr'), state.rows[i]);
    scheduleQuote();
  });
  tbody.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act="remove"]');
    if (!b) return;
    state.rows.splice(Number(b.getAttribute('data-i')), 1);
    renderBoxes(); scheduleQuote();
  });
  $('add-row').addEventListener('click', function () {
    var first = product().boxes.filter(function (a) { return a.auto; })
      .sort(function (a, b) { return a.capacity - b.capacity; })[0];
    state.rows.push({ box_id: first.box_id, count: '1', pieces: '', measured: '' });
    renderBoxes(); scheduleQuote();
  });
  $('reset-rows').addEventListener('click', function () {
    if (!state.suggestion) return;
    state.rows = rowsFromSuggestion(state.suggestion);
    renderBoxes(); scheduleQuote();
  });

  // ---------- start ----------
  fetch(API + 'config').then(function (r) { return r.json(); }).then(function (cfg) {
    CFG = cfg;
    segmented($('product'), 'product', cfg.products.map(function (p) { return { id: p.id, label: p.name }; }));
    segmented($('service'), 'service', cfg.services);
    renderBoxes();
  }).catch(function () {
    $('boxes-empty').textContent = 'Cannot load the calculator data. Refresh the page.';
  });
})();
