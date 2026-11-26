/* ==========================================================
   CarryOS — etkileşimler (bağımlılık yok)
   ========================================================== */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var CFG = window.CARRYOS || {};
  var I18N = window.CARRY_I18N;
  var lang = "tr";

  /* ---------- config → bağlantılar ---------- */
  $$("[data-link]").forEach(function (a) {
    var k = a.getAttribute("data-link");
    var url = k === "repo" ? CFG.repoUrl : k === "download" ? CFG.downloadUrl : CFG.releasesUrl;
    if (url) a.setAttribute("href", url);
  });
  if (CFG.version) $("#metaVersion").textContent = CFG.version;
  if (CFG.imageSize) $("#metaSize").textContent = CFG.imageSize;
  if (CFG.sha256) $("#metaSha").textContent = CFG.sha256;
  $("#year").textContent = new Date().getFullYear();

  /* ---------- dil ---------- */
  var statementEl = $("#statement");
  function store() { $$("[data-i18n]").forEach(function (el) { if (el.dataset.tr === undefined) el.dataset.tr = el.innerHTML; }); }
  function setLang(l, save) {
    lang = l; store();
    $$("[data-i18n]").forEach(function (el) {
      var k = el.getAttribute("data-i18n");
      el.innerHTML = l === "en" && I18N.en[k] !== undefined ? I18N.en[k] : el.dataset.tr;
    });
    document.documentElement.lang = l;
    document.title = I18N.meta[l].title;
    var md = $('meta[name="description"]'); if (md) md.setAttribute("content", I18N.meta[l].desc);
    var sp = $$("#langBtn span"); sp[0].classList.toggle("on", l === "tr"); sp[1].classList.toggle("on", l === "en");
    if (save) { try { localStorage.setItem("carryos-lang", l); } catch (e) {} }
    buildStatement(); renderUsb(usbIdx); startTerm(); buildCipher();
    var cb = $("#copyBtn"); if (cb) cb.textContent = I18N.dyn[l].copy;
  }
  $("#langBtn").addEventListener("click", function () { setLang(lang === "tr" ? "en" : "tr", true); });

  /* ---------- nav ---------- */
  var nav = $("#nav"), burger = $("#burger"), links = $("#navLinks");
  burger.addEventListener("click", function () {
    var o = links.classList.toggle("open"); burger.setAttribute("aria-expanded", o);
  });
  $$("a", links).forEach(function (a) { a.addEventListener("click", function () { links.classList.remove("open"); burger.setAttribute("aria-expanded", "false"); }); });
  var bar = $(".progress i"), dunes = $$(".dune");
  var ticking = false;
  function onScroll() {
    var y = window.scrollY || 0, h = document.documentElement.scrollHeight - window.innerHeight;
    nav.classList.toggle("stuck", y > 20);
    bar.style.transform = "scaleX(" + (h > 0 ? Math.min(1, y / h) : 0) + ")";
    if (!reduce && y < window.innerHeight * 1.3) dunes.forEach(function (d) { d.style.transform = "translate3d(0," + (y * parseFloat(d.dataset.speed)) + "px,0)"; });
    updateStatement();
    ticking = false;
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });

  /* ---------- aktif menü ---------- */
  if ("IntersectionObserver" in window) {
    var secs = ["why", "features", "how", "inside", "compat", "faq"].map(function (id) { return document.getElementById(id); });
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) $$("a", links).forEach(function (a) { a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id); });
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    secs.forEach(function (s) { if (s) io.observe(s); });
  }

  /* ---------- reveal ---------- */
  var rv = $$(".rv");
  if ("IntersectionObserver" in window && !reduce) {
    var ro = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); ro.unobserve(e.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    rv.forEach(function (el) { ro.observe(el); });
  } else rv.forEach(function (el) { el.classList.add("in"); });

  /* ---------- hero eğimi ---------- */
  var art = $("#heroArt"), mark = $(".mark");
  if (art && fine && !reduce) {
    var hero = $(".hero");
    hero.addEventListener("mousemove", function (e) {
      var r = hero.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      mark.style.setProperty("--ry", (x * 12) + "deg"); mark.style.setProperty("--rx", (-y * 8) + "deg");
    });
    hero.addEventListener("mouseleave", function () { mark.style.setProperty("--ry", "0deg"); mark.style.setProperty("--rx", "0deg"); });
  }

  /* ---------- manyetik düğmeler ---------- */
  if (fine && !reduce) $$(".magnetic").forEach(function (b) {
    b.addEventListener("mousemove", function (e) {
      var r = b.getBoundingClientRect();
      b.style.transform = "translate(" + ((e.clientX - r.left - r.width / 2) * 0.18) + "px," + ((e.clientY - r.top - r.height / 2) * 0.28) + "px)";
    });
    b.addEventListener("mouseleave", function () { b.style.transform = ""; });
  });

  /* ---------- kart ışığı ---------- */
  $$(".card").forEach(function (c) {
    c.addEventListener("pointermove", function (e) {
      var r = c.getBoundingClientRect();
      c.style.setProperty("--mx", (e.clientX - r.left) + "px"); c.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  });

  /* ---------- manifesto: kelime kelime yanar ---------- */
  var words = [];
  function buildStatement() {
    var t = statementEl.textContent.trim().split(/\s+/);
    statementEl.innerHTML = t.map(function (w) { return '<span class="w">' + w.replace(/</g, "&lt;") + "</span>"; }).join(" ");
    words = $$(".w", statementEl); updateStatement();
  }
  function updateStatement() {
    if (!words.length) return;
    var r = statementEl.getBoundingClientRect(), vh = window.innerHeight;
    var p = (vh * 0.82 - r.top) / (r.height + vh * 0.34);
    p = Math.max(0, Math.min(1, p));
    var n = words.length;
    words.forEach(function (w, i) {
      var a = Math.max(0, Math.min(1, p * (n + 4) - i));
      w.style.opacity = (0.16 + 0.84 * a).toFixed(3);
    });
  }

  /* ---------- şifre çözülme efekti ---------- */
  var cipherEl = $("#cipher"), cipherTimer = null;
  function buildCipher() {
    if (!cipherEl) return;
    clearInterval(cipherTimer);
    var files = I18N.dyn[lang].files, chars = "0123456789abcdef▒░#%&*+=", len = 26;
    var state = 0, tick = 0, hold = 0;
    function rnd(n) { var s = ""; for (var i = 0; i < n; i++) s += chars.charAt(Math.floor(Math.random() * chars.length)); return s; }
    function render() {
      var out = [];
      files.forEach(function (f, i) {
        var pad = Math.max(0, len - f.length);
        var reveal = Math.max(0, Math.min(f.length, Math.floor((tick - i * 3) * 1.2)));
        if (state === 1) out.push("<b>" + f + "</b>");
        else out.push(f.slice(0, reveal).length ? "<b>" + f.slice(0, reveal) + "</b>" + rnd(f.length - reveal) : rnd(f.length));
        if (pad) out[out.length - 1] = out[out.length - 1];
      });
      cipherEl.innerHTML = out.join("\n");
    }
    if (reduce) { state = 1; render(); return; }
    cipherTimer = setInterval(function () {
      if (state === 0) { tick++; render(); if (tick > 36) { state = 1; hold = 0; render(); } }
      else { hold++; if (hold > 38) { state = 0; tick = 0; } }
    }, 60);
  }

  /* ---------- USB bölümleri ---------- */
  var usbIdx = 3, usbDetail = $("#usbDetail"), usbBtns = $$("#usbBar .seg");
  function renderUsb(i) {
    usbIdx = i;
    var d = I18N.dyn[lang].usb[i];
    usbBtns.forEach(function (b, k) { b.classList.toggle("on", k === i); b.setAttribute("aria-selected", k === i); });
    usbDetail.innerHTML = "<div><h3>" + d.n + '</h3><div class="spec">' + d.s + "</div></div><p>" + d.p + "</p>";
  }
  usbBtns.forEach(function (b, k) {
    b.addEventListener("click", function () { renderUsb(k); });
    b.addEventListener("mouseenter", function () { if (fine) renderUsb(k); });
  });

  /* ---------- terminal ---------- */
  var termBody = $("#termBody"), termRun = 0, termStarted = false;
  function startTerm() {
    if (!termBody) return;
    var run = ++termRun, steps = I18N.dyn[lang].term;
    termBody.innerHTML = "";
    if (!termStarted) return;
    var wait = function (ms) { return new Promise(function (r) { setTimeout(r, reduce ? 0 : ms); }); };
    (async function () {
      for (var i = 0; i < steps.length; i++) {
        if (run !== termRun) return;
        var s = steps[i], line = document.createElement("div"); termBody.appendChild(line);
        if (s.t === "cmd") {
          line.innerHTML = '<span class="p">$</span> <span></span><span class="cur"></span>';
          var sp = line.children[1];
          for (var c = 0; c < s.x.length; c++) { if (run !== termRun) return; sp.textContent += s.x[c]; await wait(55); }
          line.removeChild(line.lastChild); await wait(350);
        } else if (s.t === "ask") {
          line.innerHTML = '<span class="p">?</span> ' + s.x + ' <span></span>';
          await wait(450);
          var vs = line.lastChild;
          for (var j = 0; j < s.v.length; j++) { if (run !== termRun) return; vs.textContent += s.v[j]; await wait(65); }
          await wait(250);
        } else if (s.t === "ok") { line.innerHTML = '<span class="ok">✓</span> ' + s.x; await wait(550); }
        else if (s.t === "d") { line.innerHTML = '<span class="d">' + s.x + "</span>"; await wait(400); }
        else if (s.t === "bar") {
          for (var p = 0; p <= 100; p += 4) {
            if (run !== termRun) return;
            var f = Math.round(p / 100 * 26);
            line.innerHTML = '<span class="d">LUKS2 · argon2id</span>  [' + "█".repeat(f) + "░".repeat(26 - f) + "] " + p + "%";
            await wait(45);
          }
          await wait(250);
        } else { line.textContent = s.x; await wait(500); }
      }
      await wait(5200);
      if (run === termRun) startTerm();
    })();
  }
  var termWrap = $("#term");
  if (termWrap && "IntersectionObserver" in window) {
    new IntersectionObserver(function (es, o) {
      es.forEach(function (e) { if (e.isIntersecting) { termStarted = true; startTerm(); o.disconnect(); } });
    }, { threshold: 0.35 }).observe(termWrap);
  } else { termStarted = true; }

  /* ---------- kopyala ---------- */
  var cb = $("#copyBtn");
  if (cb) cb.addEventListener("click", function () {
    var text = $("#codeText").innerText.replace(/^#.*$/gm, "").replace(/\n{2,}/g, "\n").trim();
    var done = function () { cb.textContent = I18N.dyn[lang].copied; setTimeout(function () { cb.textContent = I18N.dyn[lang].copy; }, 1800); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, done);
    else { var ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {} ta.remove(); done(); }
  });

  /* ---------- başlat ---------- */
  var saved = null;
  try { saved = localStorage.getItem("carryos-lang"); } catch (e) {}
  if (!saved && /^en/i.test(navigator.language || "")) saved = "en";
  store();
  if (saved === "en") setLang("en", false); else { buildStatement(); renderUsb(usbIdx); buildCipher(); }
  onScroll();
})();
