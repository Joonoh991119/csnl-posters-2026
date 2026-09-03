/* poster-site runtime. Five small jobs, no framework:
   1) assemble the email address from its parts (no plain address in the repo or the HTML)
   2) announce the publication window in a banner
   3) copy the address
   4) enlarge the poster in place
   5) move between posters with the arrow keys
   With JavaScript off, the poster, supplementary files and references all still work. */
(function () {
  "use strict";

  // ------------------------------------------------------------ 1. email
  function assembleEmail() {
    var nodes = document.querySelectorAll("[data-eu][data-ed]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var addr = el.getAttribute("data-eu") + "@" + el.getAttribute("data-ed");
      if (el.tagName === "A") {
        el.setAttribute("href", "mailto:" + addr);
        el.removeAttribute("aria-disabled");
      }
      var slot = el.querySelector("[data-email-text]");
      if (slot) slot.textContent = addr;
      el.setAttribute("data-addr", addr);
    }
  }

  // ------------------------------------------------------------ 2. publication window
  function parseDate(s) {
    if (!s) return null;
    var m = /^(\d{4})[-.\/](\d{1,2})[-.\/](\d{1,2})$/.exec(String(s).trim());
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3]);
  }

  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function fmt(d) {
    return d.getDate() + " " + MON[d.getMonth()] + " " + d.getFullYear();
  }

  function windowBanner() {
    var cfg = (window.__SITE__ || {}).window || {};
    var el = document.getElementById("window-banner");
    if (!el) return;
    var start = parseDate(cfg.start), end = parseDate(cfg.end);
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var day = 86400000, msg = "";

    if (start && today < start) {
      msg = "Not open yet — this page goes live on " + fmt(start) + ".";
    } else if (end && today > end) {
      msg = "This page closed on " + fmt(end) + ". Please contact the author directly for materials.";
    } else if (end) {
      var left = Math.round((end - today) / day);
      if (left <= 7) msg = "Online until " + fmt(end) + " — " + left + (left === 1 ? " day" : " days") + " left.";
    }
    if (msg) {
      el.textContent = msg;
      el.hidden = false;
    }
  }

  // ------------------------------------------------------------ 3. copy
  function copyButtons() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-copy]");
      if (!btn) return;
      ev.preventDefault();
      var src = document.querySelector(btn.getAttribute("data-copy"));
      var text = src ? (src.getAttribute("data-addr") || src.textContent.trim()) : "";
      if (!text) return;
      var done = function () {
        var old = btn.getAttribute("data-label") || btn.textContent;
        btn.setAttribute("data-label", old);
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = old; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
  }

  // ------------------------------------------------------------ 4. enlarge
  // At a meeting people zoom into one panel of a poster on their phone.
  // Handing them off to a PDF viewer breaks that, so it happens in place.
  function lightbox() {
    var lb = document.getElementById("lightbox");
    var frame = document.querySelector(".poster-frame[data-zoom]");
    if (!lb || !frame) return;
    var img = lb.querySelector("img");
    var stage = lb.querySelector(".stage");
    var scaleBtn = lb.querySelector('[data-lb="scale"]');
    var lastFocus = null;

    function open() {
      lastFocus = document.activeElement;
      img.src = frame.getAttribute("data-zoom");
      lb.classList.add("on");
      document.body.style.overflow = "hidden";
      img.classList.remove("full");
      scaleBtn.textContent = "100%";
      stage.scrollTop = 0;
      lb.querySelector('[data-lb="close"]').focus();
    }
    function close() {
      lb.classList.remove("on");
      document.body.style.overflow = "";
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }
    function toggleScale() {
      var full = img.classList.toggle("full");
      scaleBtn.textContent = full ? "Fit" : "100%";
      if (full) {
        stage.scrollLeft = (stage.scrollWidth - stage.clientWidth) / 2;
      }
    }

    frame.addEventListener("click", open);
    lb.addEventListener("click", function (ev) {
      var act = ev.target.closest("[data-lb]");
      if (act) {
        if (act.getAttribute("data-lb") === "close") close();
        else toggleScale();
        return;
      }
      if (ev.target === stage) close();          // click the backdrop to close
      else if (ev.target === img) toggleScale();
    });
    document.addEventListener("keydown", function (ev) {
      if (!lb.classList.contains("on")) return;
      if (ev.key === "Escape") close();
      if (ev.key === "+" || ev.key === "=") toggleScale();
    });
  }

  // ------------------------------------------------------------ 5. arrow navigation
  function arrowNav() {
    var prev = document.querySelector('.stepper a[aria-label^="Previous"]');
    var next = document.querySelector('.stepper a[aria-label^="Next"]');
    document.addEventListener("keydown", function (ev) {
      var lb = document.getElementById("lightbox");
      if (lb && lb.classList.contains("on")) return;
      if (ev.target && /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) return;
      if (ev.key === "ArrowLeft" && prev) prev.click();
      if (ev.key === "ArrowRight" && next) next.click();
    });
  }

  function boot() {
    assembleEmail(); windowBanner(); copyButtons(); lightbox(); arrowNav();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
