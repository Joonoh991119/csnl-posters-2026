/* poster-site — 런타임은 세 가지 일만 한다.
   1) 이메일 주소를 조각에서 조립한다 (저장소에 평문 주소를 두지 않는다)
   2) 게시기간 상태를 배너로 알린다
   3) 주소 복사
   자바스크립트가 꺼져 있어도 포스터 PDF·서플·레퍼런스는 전부 보인다. */
(function () {
  "use strict";

  // ------------------------------------------------------------ 1. 이메일
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

  // ------------------------------------------------------------ 2. 게시기간
  function parseDate(s) {
    if (!s) return null;
    var m = /^(\d{4})[-.\/](\d{1,2})[-.\/](\d{1,2})$/.exec(String(s).trim());
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3]);
  }

  function fmt(d) {
    return d.getFullYear() + "." + String(d.getMonth() + 1).padStart(2, "0") + "." +
      String(d.getDate()).padStart(2, "0");
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
      msg = "게시 준비 중입니다 · " + fmt(start) + " 공개 예정";
    } else if (end && today > end) {
      msg = "게시 기간이 끝난 페이지입니다 (" + fmt(end) + " 종료). 자료가 필요하면 저자에게 직접 문의해 주세요.";
    } else if (end) {
      var left = Math.round((end - today) / day);
      if (left <= 7) msg = "게시 종료까지 D-" + left + " · " + fmt(end) + " 까지 열려 있습니다";
    }
    if (msg) {
      el.textContent = msg;
      el.hidden = false;
    }
  }

  // ------------------------------------------------------------ 3. 복사
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
        btn.textContent = "복사됨";
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

  // ------------------------------------------------------------ 4. 포스터 확대
  // 학회장에서 사람들은 휴대폰으로 포스터의 그림 한 칸을 확대해 본다.
  // PDF 뷰어로 넘기면 그 흐름이 끊기므로, 같은 페이지에서 바로 키운다.
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
      scaleBtn.textContent = full ? "맞춤" : "100%";
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
      if (ev.target === stage) close();          // 배경을 누르면 닫힌다
      else if (ev.target === img) toggleScale();
    });
    document.addEventListener("keydown", function (ev) {
      if (!lb.classList.contains("on")) return;
      if (ev.key === "Escape") close();
      if (ev.key === "+" || ev.key === "=") toggleScale();
    });
  }

  // ------------------------------------------------------------ 5. 좌우 이동
  function arrowNav() {
    var prev = document.querySelector('.stepper a[aria-label^="이전"]');
    var next = document.querySelector('.stepper a[aria-label^="다음"]');
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
