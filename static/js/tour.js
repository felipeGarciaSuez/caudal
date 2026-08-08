/* Caudal spotlight tour: highlights real elements in place with a short tip.
   Each page passes its own steps (elements that live on that page), so the tour
   never has to jump between screens. No dependencies. */
(function () {
  "use strict";

  var steps = [], idx = 0, onDone = null, active = false;
  var catcher, hole, tip, tProg, tText, bSkip, bBack, bNext;

  function build() {
    if (catcher) return;
    catcher = el("div", "tour-catch");
    hole = el("div", "tour-hole");
    tip = el("div", "tour-tip");
    tip.innerHTML =
      '<div class="tour-tip-head"><span class="tour-tip-prog"></span></div>' +
      '<div class="tour-tip-text"></div>' +
      '<div class="tour-tip-actions">' +
      '<button type="button" class="tour-skip">Saltar</button>' +
      '<span class="tour-spacer"></span>' +
      '<button type="button" class="tour-back">Atras</button>' +
      '<button type="button" class="btn btn-primary tour-cta"></button>' +
      "</div>";
    document.body.appendChild(catcher);
    document.body.appendChild(hole);
    document.body.appendChild(tip);
    tProg = tip.querySelector(".tour-tip-prog");
    tText = tip.querySelector(".tour-tip-text");
    bSkip = tip.querySelector(".tour-skip");
    bBack = tip.querySelector(".tour-back");
    bNext = tip.querySelector(".tour-cta");
    bSkip.addEventListener("click", finish);
    bBack.addEventListener("click", prev);
    bNext.addEventListener("click", next);
    catcher.addEventListener("click", function (e) { e.stopPropagation(); });
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("keydown", function (e) {
      if (!active) return;
      if (e.key === "Escape") finish();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
    });
  }

  function el(tag, cls) {
    var n = document.createElement(tag);
    n.className = cls;
    return n;
  }

  function target() {
    return document.querySelector(steps[idx].sel);
  }

  function reposition() {
    if (!active) return;
    var t = target();
    if (!t) return;
    var r = t.getBoundingClientRect(), pad = 6;
    hole.style.top = r.top - pad + "px";
    hole.style.left = r.left - pad + "px";
    hole.style.width = r.width + pad * 2 + "px";
    hole.style.height = r.height + pad * 2 + "px";

    var tipH = tip.offsetHeight || 150, tipW = tip.offsetWidth || 300;
    var vh = window.innerHeight, vw = window.innerWidth;
    var top = r.bottom + 12 + tipH < vh ? r.bottom + 12 : r.top - 12 - tipH;
    top = Math.max(8, Math.min(top, vh - 8 - tipH));
    var left = r.left + r.width / 2 - tipW / 2;
    left = Math.max(8, Math.min(left, vw - 8 - tipW));
    tip.style.top = top + "px";
    tip.style.left = left + "px";
  }

  function show(i) {
    idx = i;
    var t = target();
    if (!t) { // element not on this page: skip it gracefully
      if (i < steps.length - 1) return show(i + 1);
      return finish();
    }
    tText.innerHTML = steps[i].text;
    tProg.textContent = i + 1 + " / " + steps.length;
    bBack.style.visibility = i > 0 ? "visible" : "hidden";
    bSkip.style.visibility = i === steps.length - 1 ? "hidden" : "visible";
    bNext.textContent = i === steps.length - 1 ? "Listo" : "Siguiente";
    t.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(reposition, 300);
    bNext.focus();
  }

  function next() { if (idx < steps.length - 1) show(idx + 1); else finish(); }
  function prev() { if (idx > 0) show(idx - 1); }

  function finish() {
    active = false;
    document.body.classList.remove("tour-open");
    if (catcher) { catcher.style.display = hole.style.display = tip.style.display = "none"; }
    if (onDone) { var cb = onDone; onDone = null; cb(); }
  }

  window.CaudalTour = {
    start: function (list, opts) {
      steps = (list || []).slice();
      onDone = (opts && opts.onDone) || null;
      if (!steps.length) return;
      build();
      active = true;
      document.body.classList.add("tour-open");
      catcher.style.display = hole.style.display = tip.style.display = "block";
      show(0);
    },
  };
})();
