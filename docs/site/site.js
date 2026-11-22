// The 3D graph flow: crossfades the views every few seconds; a tab jumps to its view;
// hovering the picture or Pause holds it. With reduced motion it does not advance by itself.
(function () {
  var root = document.getElementById("gflow");
  if (!root) return;
  var tabs = [].slice.call(root.querySelectorAll('[role="tab"]'));
  var imgs = [].slice.call(root.querySelectorAll(".gstage img"));
  var cap = document.getElementById("gcap"), ctl = document.getElementById("gctl");
  var DUR = 6000, i = 0, timer = 0, paused = false, hover = false;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  root.style.setProperty("--dur", DUR / 1000 + "s");
  function show(n) {
    i = (n + imgs.length) % imgs.length;
    if (imgs[(i + 1) % imgs.length]) imgs[(i + 1) % imgs.length].loading = "eager";
    imgs.forEach(function (im, k) {
      im.classList.remove("on");
      if (k === i) { im.loading = "eager"; void im.offsetWidth; im.classList.add("on"); }
    });
    tabs.forEach(function (t, k) {
      t.setAttribute("aria-selected", k === i ? "true" : "false");
      t.tabIndex = k === i ? 0 : -1;
      var bar = t.querySelector(".bar"); bar.style.animation = "none"; void bar.offsetWidth; bar.style.animation = "";
    });
    cap.textContent = imgs[i].getAttribute("data-cap");
    var list = tabs[i].parentNode;
    if (list.scrollWidth > list.clientWidth) list.scrollLeft = tabs[i].offsetLeft - list.offsetLeft - 16;
    schedule();
  }
  function schedule() {
    clearTimeout(timer);
    var hold = paused || hover || reduce;
    root.classList.toggle("paused", hold);
    if (!hold) timer = setTimeout(function () { show(i + 1); }, DUR);
  }
  tabs.forEach(function (t, k) {
    t.addEventListener("click", function () { show(k); });
    t.addEventListener("keydown", function (e) {
      var d = (e.key === "ArrowDown" || e.key === "ArrowRight") ? 1 : (e.key === "ArrowUp" || e.key === "ArrowLeft") ? -1 : 0;
      if (d) { e.preventDefault(); show(k + d); tabs[i].focus(); }
    });
  });
  var stage = document.getElementById("gstage");
  stage.addEventListener("mouseenter", function () { hover = true; schedule(); });
  stage.addEventListener("mouseleave", function () { hover = false; schedule(); });
  ctl.addEventListener("click", function () { paused = !paused; ctl.textContent = paused ? (ctl.dataset.play || "Play") : (ctl.dataset.pause || "Pause"); schedule(); });
  if (reduce) ctl.hidden = true;
  tabs.forEach(function (t, k) { t.tabIndex = k === 0 ? 0 : -1; });
  // start when the section comes into view, so the first view is not missed
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (e) { if (e[0].isIntersecting) { io.disconnect(); show(0); } }, { threshold: 0.3 });
    io.observe(root);
  } else { show(0); }
})();
// Page background: health data points drift, links form between neighbours, and data flows
// run along them as light pulses, denser on the right, away from the headline. Taken from the
// cover of the Tractus-X Community Days deck. A fixed layer behind the whole page, the size of
// the window; it stops while the tab is hidden, and is one still frame when the viewer prefers
// reduced motion.
(function () {
  var canvas = document.getElementById("hero-net");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var W = 1920, H = 1080, LINK = 250, scale = 1;
  var NETLINE = "131,153,168";
  function tone() { NETLINE = document.documentElement.getAttribute("data-theme") === "light" ? "60,80,100" : "131,153,168"; }
  tone(); document.addEventListener("kb-theme", function () { tone(); if (typeof draw === "function") draw(); });
  var COLORS = ["#3d9bff", "#19b39a", "#f5b335", "#a77bd1", "#2471a3", "#148f77"];
  var seed = 7;
  function rnd() { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }
  var nodes = [];
  for (var i = 0; i < 64; i++) {
    var x = rnd() < 0.68 ? 900 + rnd() * 1020 : rnd() * 900;
    nodes.push({ x: x, y: 40 + rnd() * 1000, vx: (rnd() - 0.5) * 0.35, vy: (rnd() - 0.5) * 0.35,
      r: 2.5 + rnd() * 3.5, c: COLORS[Math.floor(rnd() * COLORS.length)], hub: rnd() < 0.12 });
  }
  var pulses = [];
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // dimmer on the left, where the headline is; x / W keeps that on a narrow window too
  function fade(x) { var u = x / W * 1920; return u < 1000 ? 0.25 + 0.75 * (u / 1000) * (u / 1000) : 1; }
  function hexA(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a.toFixed(3) + ")";
  }
  // 1920 units across a wide window; a phone shows 1000 units, so the net keeps its density
  function resize() {
    var w = canvas.clientWidth || window.innerWidth, h = canvas.clientHeight || window.innerHeight;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    scale = w >= 1000 ? w / 1920 : w / 1000;
    var nw = w / scale, nh = h / scale;
    for (var i = 0; i < nodes.length; i++) { nodes[i].x = nodes[i].x / W * nw; nodes[i].y = nodes[i].y / H * nh; }
    W = nw; H = nh;
    ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0);
  }
  function step(dt) {
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      n.x += n.vx * dt; n.y += n.vy * dt;
      if (n.x < 0 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;
    }
    if (pulses.length < 26 && Math.random() < 0.18 * dt) {
      var a = nodes[Math.floor(Math.random() * nodes.length)], best = null, bd = LINK;
      for (var j = 0; j < nodes.length; j++) {
        var b = nodes[j];
        if (b === a) continue;
        var d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < bd && Math.random() < 0.5) { bd = d; best = b; }
      }
      if (best) pulses.push({ a: a, b: best, t: 0, v: 0.008 + Math.random() * 0.01, c: a.c });
    }
    for (var k = pulses.length - 1; k >= 0; k--) {
      pulses[k].t += pulses[k].v * dt;
      if (pulses[k].t >= 1) { pulses[k].b.flash = 1; pulses.splice(k, 1); }
    }
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.lineWidth = 1.4;
    for (var i = 0; i < nodes.length; i++) {
      for (var j = i + 1; j < nodes.length; j++) {
        var a = nodes[i], b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < LINK) {
          ctx.strokeStyle = "rgba(" + NETLINE + "," + ((1 - d / LINK) * 0.32 * fade((a.x + b.x) / 2)).toFixed(3) + ")";
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
    }
    for (var k = 0; k < pulses.length; k++) {
      var p = pulses[k], x = p.a.x + (p.b.x - p.a.x) * p.t, y = p.a.y + (p.b.y - p.a.y) * p.t, f = fade(x);
      var g = ctx.createRadialGradient(x, y, 0, x, y, 16);
      g.addColorStop(0, hexA(p.c, 0.95 * f)); g.addColorStop(1, hexA(p.c, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 16, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = hexA(p.c, 0.55 * f); ctx.lineWidth = 2.5;
      var tt = Math.max(0, p.t - 0.18);
      ctx.beginPath(); ctx.moveTo(p.a.x + (p.b.x - p.a.x) * tt, p.a.y + (p.b.y - p.a.y) * tt); ctx.lineTo(x, y); ctx.stroke();
      ctx.lineWidth = 1.4;
    }
    for (var m = 0; m < nodes.length; m++) {
      var n = nodes[m], fl = n.flash || 0, a2 = (0.55 + 0.45 * fl) * fade(n.x);
      if (n.hub || fl > 0.05) {
        var h = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 6);
        h.addColorStop(0, hexA(n.c, 0.35 * a2 + 0.3 * fl)); h.addColorStop(1, hexA(n.c, 0));
        ctx.fillStyle = h; ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 6, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = hexA(n.c, a2);
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r * (n.hub ? 1.6 : 1) + fl * 3, 0, Math.PI * 2); ctx.fill();
      if (fl) n.flash = Math.max(0, fl - 0.04);
    }
  }
  var running = false, last = 0, raf = 0;
  function frame(ts) {
    if (!running) return;
    var dt = last ? Math.min(3, (ts - last) / 16.7) : 1;
    last = ts; step(dt); draw();
    raf = requestAnimationFrame(frame);
  }
  function sync() {
    if (reduce) { draw(); return; }
    var on = !document.hidden;
    if (on && !running) { running = true; last = 0; raf = requestAnimationFrame(frame); }
    if (!on && running) { running = false; cancelAnimationFrame(raf); }
  }
  resize();
  for (var w = 0; w < 140; w++) step(1);
  draw();
  window.addEventListener("resize", function () { resize(); draw(); });
  document.addEventListener("visibilitychange", sync);
  sync();
})();

// The phone menu: the button top left shows and hides the page index. Escape, a chosen link,
// a tap outside or a wider window close it; the section in view is marked current.
(function () {
  var btn = document.querySelector(".menu-btn"), toc = document.getElementById("toc");
  if (!btn || !toc) return;
  btn.hidden = false;
  function set(open, refocus) {
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    toc.hidden = !open;
    if (!open && refocus) btn.focus();
  }
  btn.addEventListener("click", function () { set(toc.hidden); });
  toc.addEventListener("click", function (e) { if (e.target.closest("a")) set(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !toc.hidden) { set(false, true); }
  });
  document.addEventListener("click", function (e) {
    if (!toc.hidden && !toc.contains(e.target) && !btn.contains(e.target)) set(false);
  });
  var wide = window.matchMedia("(min-width: 1221px)");
  (wide.addEventListener ? wide.addEventListener.bind(wide, "change") : wide.addListener.bind(wide))(function (m) { if (m.matches) set(false); });

  if (!("IntersectionObserver" in window)) return;
  var links = [].slice.call(toc.querySelectorAll('li a[href^="#"]'));
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
  var seen = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      links.forEach(function (a) { a.removeAttribute("aria-current"); });
      var a = byId[en.target.id]; if (a) a.setAttribute("aria-current", "true");
    });
  }, { rootMargin: "-45% 0px -50% 0px" });
  Object.keys(byId).forEach(function (id) { var s = document.getElementById(id); if (s) seen.observe(s); });
})();

// Day and night: without a choice the theme follows the sun where the visitor is (sunrise and
// sunset for the browser's time zone) and changes by itself; the switch stores a choice.
(function () {
  var root = document.documentElement, KEY = "kb-theme";
  var btns = [].slice.call(document.querySelectorAll(".theme-btn"));
  function stored() { try { var s = localStorage.getItem(KEY); return s === "light" || s === "dark" ? s : null; } catch (e) { return null; } }
  // light while the sun is up where the visitor is (kbSunUp comes from the page's head script)
  function byClock() {
    var z = ""; try { z = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) {}
    if (window.kbSunUp) return window.kbSunUp(new Date(), z) ? "light" : "dark";
    var h = new Date().getHours(); return h >= 7 && h < 17 ? "light" : "dark";
  }
  function apply(theme) {
    if (root.getAttribute("data-theme") !== theme) {
      root.setAttribute("data-theme", theme);
      document.dispatchEvent(new Event("kb-theme"));
    }
    btns.forEach(function (b) { b.setAttribute("aria-pressed", theme === "dark" ? "true" : "false"); });
  }
  btns.forEach(function (b) {
    b.hidden = false;
    b.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, next); } catch (e) {}
      apply(next);
    });
  });
  function follow() { if (!stored()) apply(byClock()); }
  apply(stored() || byClock());
  setInterval(follow, 60000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) follow(); });
})();
