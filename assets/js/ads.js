/* ==========================================================
   CarryOS — reklamlar ve reklam engelleyici uyarısı
   Ayarlar assets/js/config.js içinde (adSlots, adblockWall).
   ========================================================== */
(function () {
  "use strict";
  var CFG = window.CARRYOS || {};
  var CLIENT = CFG.adClient || "ca-pub-6968273160398959";
  var SRC = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + CLIENT;
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };

  /* ---------- 1) reklam birimleri ---------- */
  var slots = CFG.adSlots || {};
  $$(".ad[data-ad]").forEach(function (box) {
    var ins = box.querySelector("ins.adsbygoogle");
    var id = slots[box.getAttribute("data-ad")];
    if (!ins || !id) return;                       // slot ID yoksa bu alan hiç görünmez
    ins.setAttribute("data-ad-slot", id);
    // Reklam dolunca çerçeveyi aç, dolmazsa kapalı tut (boş kutu görünmesin)
    var sync = function () {
      var st = ins.getAttribute("data-ad-status");
      box.classList.toggle("on", st === "filled");
    };
    new MutationObserver(sync).observe(ins, { attributes: true, attributeFilter: ["data-ad-status"] });
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {}
  });

  /* ---------- 2) reklam engelleyici algılama ---------- */
  if (CFG.adblockWall === false) return;
  // Arama motoru botlarına ve performans araçlarına uyarı gösterme
  if (/Googlebot|AdsBot|Mediapartners|bingbot|Lighthouse|Chrome-Lighthouse|PTST/i.test(navigator.userAgent)) return;

  var wall = document.getElementById("abWall");
  if (!wall) return;
  var shown = false;

  function baitBlocked() {
    var b = document.createElement("div");
    b.className = "adsbox ad-banner ad-placeholder pub_300x250 text-ad textAd text_ad text_ads text-ads banner_ad";
    b.style.cssText = "position:absolute;left:-9999px;top:-9999px;width:10px;height:10px;pointer-events:none";
    b.innerHTML = "&nbsp;";
    document.body.appendChild(b);
    var cs = window.getComputedStyle(b);
    var hidden = b.offsetHeight === 0 || b.offsetWidth === 0 ||
                 cs.display === "none" || cs.visibility === "hidden";
    b.remove();
    return hidden;
  }

  function probeFailed() {                         // reklam betiğine ulaşılabiliyor mu?
    if (!window.fetch) return Promise.resolve(false);
    return fetch(SRC, { method: "HEAD", mode: "no-cors", cache: "no-store" })
      .then(function () { return false; }, function () { return true; });
  }

  function detect() {
    var bait = baitBlocked();
    if (bait) return Promise.resolve(true);
    if (navigator.onLine === false) return Promise.resolve(false);
    return probeFailed().then(function (failed) {
      var loaded = !!(window.adsbygoogle && window.adsbygoogle.loaded);
      return failed && !loaded;
    });
  }

  function show() {
    if (shown) return;
    shown = true;
    wall.hidden = false;
    document.documentElement.classList.add("ab-lock");
    $$("body > header, body > main, body > footer").forEach(function (el) { el.setAttribute("inert", ""); });
    requestAnimationFrame(function () {
      wall.classList.add("in");
      var btn = document.getElementById("abReload");
      if (btn) btn.focus({ preventScroll: true });
    });
  }

  document.getElementById("abReload").addEventListener("click", function () { location.reload(); });

  // Kullanıcı engelleyiciyi kapatıp sekmeye dönerse sayfayı kendimiz yenileyelim
  function recheck() { if (shown && !baitBlocked()) location.reload(); }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) recheck(); });
  window.addEventListener("focus", recheck);

  // Escape ile kapatılamasın
  wall.addEventListener("keydown", function (e) {
    if (e.key === "Escape") e.preventDefault();
    if (e.key === "Tab") { e.preventDefault(); document.getElementById("abReload").focus(); }
  });

  function run() {
    // Reklam betiğine yüklenmesi için kısa bir süre tanı; yavaş bağlantıda yanlış alarmı önler
    setTimeout(function () {
      detect().then(function (blocked) {
        if (blocked) show();
      });
    }, 1200);
  }
  if (document.readyState === "complete") run();
  else window.addEventListener("load", run);
})();
