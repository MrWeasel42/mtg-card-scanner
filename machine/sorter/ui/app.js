/* Card Sorter touchscreen app. One page, a few views; it polls /api/state and redraws.
   On the machine's own screen it runs as http://localhost:8080/?kiosk=1 (on-screen keyboard, screen sleep). */
"use strict";
const KIOSK = new URLSearchParams(location.search).has("kiosk");
if (!KIOSK) document.body.classList.add("web");
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = v => v == null ? "—" : "$" + Number(v).toFixed(2);
const api = async (path, body) => {
  const r = await fetch("/api/" + path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  try { return await r.json(); } catch { return { ok: false, error: "Bad answer from the machine" }; }
};
const toast = (t, ms = 2600) => { const el = $("#toast"); el.textContent = t; el.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => el.hidden = true, ms); };
const RUNNING = ["starting", "running", "stopping"];

let S = null;            // last /api/state
let view = "home";       // home | start | run | sessions | session | review | camera | tools | settings
let viewArg = null;
let lastDraw = "";

// --------------------------------------------------------------------------------------------- polling
async function poll() {
  try {
    const s = await (await fetch("/api/state")).json();
    S = s;
    if ((RUNNING.includes(s.state) || ["error", "estop"].includes(s.state)) && !["run", "review", "camera"].includes(view)) go("run");
    if (s.state === "stopped" && view === "home" && s.session) go("run");
    chrome();
    if (["home", "run", "settings"].includes(view)) render();
  } catch { $("#chips").innerHTML = `<span class="chip bad">Machine not answering</span>`; }
  setTimeout(poll, RUNNING.includes(S?.state) ? 700 : 1500);
}

function chrome() {
  const s = S;
  const hwc = s.hw.motors === "ready" ? "ok" : "warn";
  $("#chips").innerHTML = [
    `<span class="chip ${s.pc.online ? "ok" : "warn"}">${s.pc.online ? "● PC: " + esc(s.pc.name) : "○ No PC"}</span>`,
    `<span class="chip ${hwc}">Motors: ${esc(s.hw.motors)}</span>`,
    `<span class="chip">Identify: ${esc(s.identifier)}</span>`,
    s.sim ? `<span class="chip warn">SIMULATION</span>` : "",
  ].join("");
  $("#clock").textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  // alert banner
  const a = s.alert, el = $("#alert");
  document.body.classList.toggle("flash-red", !!a && ["jam", "estop"].includes(a.kind));
  if (!a) { el.hidden = true; } else {
    const red = ["jam", "estop"].includes(a.kind), blue = ["paused"].includes(a.kind);
    el.className = red ? "red" : blue ? "blue" : "orange";
    let btns = "";
    if (a.kind === "jam") btns = `<button data-act="continue">Cleared: carry on</button><button data-act="end">End session</button>`;
    if (a.kind === "estop") btns = `<button data-act="reset">Reset motor board</button>`;
    if (a.kind === "paused") btns = `<button data-act="resume">Resume</button>`;
    const icon = red ? "⛔" : a.kind === "full" ? "📦" : a.kind === "empty" ? "🃏" : a.kind === "nopc" ? "🖥" : "⏸";
    const html = `<span>${icon}</span><span class="grow">${esc(a.text)}</span>${btns}`;
    if (el.dataset.h !== html) { el.innerHTML = html; el.dataset.h = html; }
    el.hidden = false;
    if (red || a.kind === "full") wake();
  }
  // update banner
  const u = s.update, ub = $("#update");
  if (u.available && !RUNNING.includes(s.state)) {
    const h = `<span class="grow">⬆ New version available: ${esc(u.latest)}<span class="muted small"> · ${esc(u.changes.slice(0, 2).join(" · "))}</span></span>
      <button data-act="update" ${u.updating ? "disabled" : ""}>${u.updating ? "Updating…" : "Update now"}</button>`;
    if (ub.dataset.h !== h) { ub.innerHTML = h; ub.dataset.h = h; }
    ub.hidden = false;
  } else ub.hidden = true;
  drawNav();
  // e-stop: whenever anything can move
  $("#estop").hidden = !(RUNNING.includes(s.state) || view === "tools" || s.state === "error");
}

// --------------------------------------------------------------------------------------------- navigation
// Every page but Home gets the same top bar: ‹ Back (one level up), ⌂ Home on pages deeper than one level,
// and the page name. No other Back / Done / Cancel buttons on the pages themselves.
let reviewFrom = "session";
function navFor() {
  const busy = S && (RUNNING.includes(S.state) || ["error", "estop"].includes(S.state));
  switch (view) {
    case "home": return null;
    case "run":
      if (busy || !S?.session) return { title: S?.session ? "Sorting" : "Nothing running", back: busy ? null : "home" };
      return { title: "Session stopped", back: "home", backLabel: "‹ Finish later" };
    case "start": return { title: "Start sorting", back: "home" };
    case "sessions": return { title: "Sessions", back: "home" };
    case "session": return { title: "Session", back: "sessions", home: true };
    case "review": return { title: "Review flagged cards", back: reviewFrom, backArg: viewArg, home: true };
    case "camera": return { title: "Camera", back: "home" };
    case "tools": return { title: "Tools", back: "home" };
    case "settings": return { title: "Settings", back: "home" };
  }
  return { title: "", back: "home" };
}
function drawNav() {
  const n = navFor();
  document.body.classList.toggle("sub", !!n);
  if (!n) return;
  const back = n.back === "home" ? `<button class="btn" data-act="nav-home">${n.backLabel || "‹ Back"}</button>`
    : n.back ? `<button class="btn" data-go="${n.back}" ${n.backArg ? `data-arg="${esc(n.backArg)}"` : ""}>‹ Back</button>` : "";
  const html = back + (n.home ? `<button class="btn" data-act="nav-home">⌂ Home</button>` : "") + `<span class="ptitle">${esc(n.title)}</span>`;
  if ($("#nav").dataset.h !== html) { $("#nav").innerHTML = html; $("#nav").dataset.h = html; }
}
function go(v, arg = null) {
  if (v === "review" && view !== "review") reviewFrom = view === "run" ? "run" : "session";
  view = v; viewArg = arg; lastDraw = ""; closeModal(); hideKbd(); render(true); drawNav(); if (S) chrome();
}
function render(force) {
  const html = VIEWS[view]?.();
  if (html === undefined) return;
  if (!force && html === lastDraw) return;
  lastDraw = html;
  const keep = document.activeElement?.id;
  $("#view").innerHTML = html;
  if (keep && $("#" + keep)) $("#" + keep).focus();
  AFTER[view]?.();
}
const AFTER = {};

// --------------------------------------------------------------------------------------------- views
const VIEWS = {
  home() {
    if (!S) return "";
    const s = S;
    const last = s.session ? "" : "";
    return `<div class="home">
      <button class="tile gohome" data-go="start"><span class="ico">▶</span><span><div class="t">Start sorting</div>
        <div class="s">${esc(s.settings.lastMode)} · ${s.binsInUse} bins · identifying on ${esc(s.identifier)}</div></span></button>
      <button class="tile" data-go="sessions"><span class="ico">🗂</span><span><div class="t">Sessions</div><div class="s">Review flagged cards, download CSVs</div></span></button>
      <button class="tile" data-go="camera"><span class="ico">📷</span><span><div class="t">Camera</div><div class="s">Live view for focusing</div></span></button>
      <button class="tile" data-go="tools"><span class="ico">🛠</span><span><div class="t">Tools</div><div class="s">Home belt, test doors, bin levels</div></span></button>
      <button class="tile" data-go="settings"><span class="ico">⚙</span><span><div class="t">Settings</div><div class="s">Identify on, prices, screen, updates · ${esc(s.version)}</div></span></button>
    </div>${last}`;
  },

  run() {
    if (!S) return "";
    const s = S, ss = s.session;
    if (!ss) { return `<div class="panel muted">No session is open.</div>`; }
    const lc = s.lastCard;
    const showLast = s.settings.priceShow !== "top", showTop = s.settings.priceShow !== "last";
    const stopped = s.state === "stopped";
    const levels = s.levels || [];
    const counts = ss.binCounts || {};
    const bins = ss.binLabels.map((label, i) => {
      const b = i + 1, lv = levels[i];
      const full = s.alert?.kind === "full" && (s.alert.bins || []).includes(b);
      return `<div class="bin ${b === ss.binsInUse ? "end" : ""} ${full ? "full" : ""} ${lc && lc.bin === b ? "hit" : ""}">
        <div class="n">BIN ${b}${b === ss.binsInUse ? " · END" : ""}</div><div class="c">${counts[b] || 0}</div>
        <div class="l">${esc(label)}</div>${lv != null ? `<div class="lvl" style="width:${lv}%;background:${lv > 85 ? "var(--warn)" : "var(--accent)"}"></div>` : ""}</div>`;
    }).join("");
    const elapsed = ss.started ? Math.max(0, Math.round((Date.now() - new Date(ss.started)) / 60000)) : 0;
    const stats = [
      [ss.cards, "cards"], [s.rate.toFixed(1), "per min"],
      showLast ? [money(lc?.price), "last price"] : [ss.flagged, "flagged"],
      showTop ? [money(ss.top?.price), "highest" + (ss.top ? " · " + esc(ss.top.name) : "")] : [money(ss.total), "total value"],
    ].map(([v, k]) => `<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("");
    const lastHtml = lc ? `
      <div class="photo" style="background-image:url('/api/sessions/${ss.id}/photo/${lc.n}?t=${lc.n}')"></div>
      <div class="name">${esc(lc.name)}</div>
      <div class="muted">${esc(lc.set)} ${lc.setCode ? "· " + esc(lc.setCode) + " #" + esc(lc.number) : ""} ${lc.finish && lc.finish !== "nonfoil" ? "· " + esc(lc.finish) : ""}</div>
      <div class="row"><span class="binbadge ${lc.flagged ? "flag" : ""}">→ Bin ${lc.bin} · ${esc(lc.flagged ? "Flagged: " + (lc.flagReason || "") : lc.binLabel)}</span>
        ${showLast ? `<span class="binbadge">${money(lc.price)}</span>` : ""}</div>`
      : `<div class="photo"></div><div class="name muted">${s.phase === "homing" ? "Homing the belt…" : "Waiting for the first card…"}</div>`;
    const controls = stopped ? `
        <button class="btn big primary" data-go="review" data-arg="${ss.id}" ${ss.toReview ? "" : "disabled"}>⚑ Review flagged (${ss.toReview})</button>
        <button class="btn big" data-act="finish">✓ Finish${ss.mode === "Catalog" ? " & save CSVs" : ""}</button>`
      : s.state === "stopping" ? `<button class="btn big" disabled>Clearing the track…</button>`
      : `<button class="btn big ${s.paused ? "primary" : "warnb"}" data-act="${s.paused ? "resume" : "pause"}">${s.paused ? "▶ Resume" : "⏸ Pause"}</button>
         <button class="btn big danger" data-act="stop">■ Stop session</button>`;
    return `<div class="run">
      <div class="last panel">${lastHtml}</div>
      <div style="display:flex;flex-direction:column;gap:14px;min-height:0">
        <div class="row"><div class="grow"><h1 style="margin:0">${esc(ss.name)}</h1>
          <div class="muted small">${esc(ss.mode)} · ${stopped ? "stopped" : s.paused ? "paused" : s.state} · ${elapsed} min · identifying on ${esc(s.identifier)}${ss.noCard ? ` · ${ss.noCard} empty photos` : ""}</div></div></div>
        <div class="stats">${stats}</div>
        <div class="bins">${bins}</div>
        <div class="controls">${controls}</div>
      </div></div>`;
  },

  start() { return startView(); },
  sessions() { return sessionsView(); },
  session() { return sessionView(); },
  review() { return reviewView(); },
  camera() {
    return `<div style="display:flex;flex-direction:column;height:100%;gap:12px">
      <div class="row"><span class="seg"><button class="${camExp === "auto" ? "on" : ""}" data-act="camexp" data-arg="auto">Auto brightness</button><button class="${camExp === "fixed" ? "on" : ""}" data-act="camexp" data-arg="fixed">As when sorting</button></span>
        <span class="muted small grow">Lens tip to card: 200 mm (7⅞″). Turn the focus ring until the card text is sharp. "As when sorting" is dark without the hood lights.</span></div>
      <img id="camimg" class="cam" alt="camera"></div>`;
  },
  tools() {
    const t = [["home", "⌂ Home the belt", "A fin stops on the scan station"], ["index", "→ Move one station", "Track moves 122 mm"],
      ["feed", "⤓ Feed 50 mm", "Turns the feed roller"], ["doors", "🚪 Test doors", "Each door opens and shuts twice"],
      ["levels", "📏 Bin levels", "Distance to each stack"], ["motors-off", "⏻ Motors off", "Belts turn by hand"]];
    return `<p class="muted" style="margin-top:0">Setup and tests. The red STOP button cuts the motors at once.</p>
      <div class="bins">${t.map(([k, n, d]) => `<button class="tile" style="min-height:130px" data-tool="${k}"><span class="t" style="font-size:22px">${n}</span><span class="s">${d}</span></button>`).join("")}
      <button class="tile" style="min-height:130px" data-act="lights"><span class="t" style="font-size:22px">💡 Lights</span><span class="s">On / off</span></button></div>
      <div id="toolout" class="panel" style="margin-top:14px">Pick a tool.</div>`;
  },
  settings() {
    if (!S) return "";
    const st = S.settings;
    const seg = (key, opts) => `<span class="seg">${opts.map(([v, l]) => `<button class="${String(st[key]) === String(v) ? "on" : ""}" data-set="${key}" data-val="${v}">${l}</button>`).join("")}</span>`;
    const u = S.update;
    return `<div class="list">
      <div class="panel"><h3>Identify cards on</h3>${seg("identifyOn", [["auto", "Auto"], ["pc", "Always PC"], ["machine", "Always machine"]])}
        <p class="muted small">Auto uses your PC when it's on and the machine when it isn't. On-machine identifying is coming in a later update; until then Auto and Machine use the PC when it's on, and cards scanned with no PC are kept and flagged so you can identify them later.</p></div>
      <div class="panel"><h3>Price shown while sorting</h3>${seg("priceShow", [["last", "Last card"], ["top", "Highest so far"], ["both", "Both"]])}</div>
      <div class="panel"><h3>Screen sleep</h3>${seg("sleepMinutes", [[0, "Never"], [5, "5 min"], [10, "10 min"], [30, "30 min"]])}
        <p class="muted small">Never sleeps while sorting. Tap to wake.</p>
        <h3 style="margin-top:12px">Brightness</h3>${seg("brightness", [[30, "Low"], [60, "Medium"], [100, "High"]])}</div>
      <div class="panel"><h3>Software</h3><div class="row"><div class="grow">Version ${esc(S.version)}<div class="muted small">${u.available ? "Update available: " + esc(u.latest) : u.error ? esc(u.error) : "Up to date (checks every 30 min)."}</div></div>
        <button class="btn" data-act="checkupdate">${u.checking ? "Checking…" : "Check now"}</button>
        ${u.available ? `<button class="btn primary" data-act="update">Update now</button>` : ""}</div></div>
      <div class="panel row"><div class="grow">Shut down the Pi before unplugging the machine.</div><button class="btn danger" data-act="shutdown">Shut down</button></div></div>`;
  },
};

// --------------------------------------------------------------------------------------------- start screen
let ST = null;   // {opts, name, mode, setup, labels, src}
async function openStart() {
  const o = await api("setup-options");
  ST = { opts: o, name: o.lastName && false ? o.lastName : o.defaultName, mode: o.lastMode || "Catalog", setup: o.last, src: "last" };
  await relabel();
  render(true);
}
async function relabel() { const r = await api("labels", { setup: ST.setup }); ST.setup = r.setup; ST.labels = r.labels; }
function startView() {
  if (!ST) { openStart(); return `<div class="panel">Loading…</div>`; }
  const o = ST.opts;
  const srcs = [["last", "Last used"]].concat(o.pc ? [["pc", "My PC setup"]] : [])
    .concat(o.saved.map((x, i) => ["saved:" + i, "★ " + x.name]))
    .concat([["Price", "By price"], ["Alphabet", "By letters"], ["Color", "By colour"], ["Rarity", "By rarity"], ["Set", "By set"]]);
  const bins = ST.labels.map((l, i) => {
    const b = i + 1, end = b === ST.setup.binsInUse;
    return `<div class="bin ${end ? "end" : ""}" ${end ? "" : `data-editbin="${b}"`}><div class="n">BIN ${b}${end ? " · END" : " · tap to edit"}</div><div class="l">${esc(l)}</div></div>`;
  }).join("");
  return `<div class="start">
    <div class="panel">
      <div class="field"><h3>Session name</h3><input id="sname" class="input" value="${esc(ST.name)}" data-kbd></div>
      <div class="field"><h3>Mode</h3><span class="seg"><button class="${ST.mode === "Catalog" ? "on" : ""}" data-mode="Catalog">📋 Catalog</button><button class="${ST.mode === "Sort" ? "on" : ""}" data-mode="Sort">🗂 Sort only</button></span>
        <div class="muted small">${ST.mode === "Catalog" ? "Identify, sort, and save ManaBox + Moxfield CSVs." : "Sort into bins; no CSVs."}</div></div>
      <div class="field"><h3>Identifying on</h3><div>${esc(S?.identifier || "")}</div></div>
      <div class="row" style="margin-top:20px"><button class="btn big primary grow" data-act="go">▶ Start</button></div>
    </div>
    <div class="panel">
      <h3>Bins (${ST.setup.binsInUse} on this machine)</h3>
      <div class="srcs" style="margin-bottom:12px">${srcs.map(([k, l]) => `<button class="${ST.src === k ? "on" : ""}" data-src="${k}">${esc(l)}</button>`).join("")}</div>
      <div class="binedit">${bins}</div>
      <div class="row" style="margin-top:12px"><button class="btn small" data-act="savesetup">★ Save these bins as…</button>
        ${ST.src.startsWith("saved:") ? `<button class="btn small danger" data-act="delsetup">Delete this saved setup</button>` : ""}
        <span class="muted small grow">Bins are tried from bin 1; the END bin takes flagged cards and anything no bin takes.</span></div>
    </div></div>`;
}

async function pickSource(k) {
  const o = ST.opts;
  ST.src = k;
  if (k === "last") ST.setup = o.last;
  else if (k === "pc") ST.setup = o.pc;
  else if (k.startsWith("saved:")) ST.setup = o.saved[+k.slice(6)].setup;
  else ST.setup = (await api("preset", { setup: ST.setup, by: k })).setup;
  await relabel(); render(true);
}

function editBin(b) {
  const r = JSON.parse(JSON.stringify(ST.setup.rules[b - 1] || { kind: "Price", name: "", min: null, max: null, colors: [], letters: "", rarities: [], sets: [], types: [] }));
  const o = ST.opts;
  const draw = () => {
    const kinds = o.kinds.map(k => `<button class="${r.kind === k ? "on" : ""}" data-k="${k}">${k === "Anything" ? "Everything" : k}</button>`).join("");
    let body = "";
    if (r.kind === "Price") body = `<div class="row"><div class="field grow"><h3>From $</h3><input id="pmin" class="input" inputmode="decimal" value="${r.min ?? ""}" data-kbd="num" placeholder="no minimum"></div>
        <div class="field grow"><h3>To $</h3><input id="pmax" class="input" inputmode="decimal" value="${r.max ?? ""}" data-kbd="num" placeholder="no maximum"></div></div>`;
    if (r.kind === "Color") body = `<div class="toggles">${o.colors.map(([c, n]) => `<button class="${r.colors.includes(c) ? "on" : ""}" data-t="colors" data-v="${c}">${n}</button>`).join("")}</div>`;
    if (r.kind === "Rarity") body = `<div class="toggles">${o.rarities.map(x => `<button class="${r.rarities.includes(x) ? "on" : ""}" data-t="rarities" data-v="${x}">${x === "special" ? "Special / bonus" : x[0].toUpperCase() + x.slice(1)}</button>`).join("")}</div>`;
    if (r.kind === "Type") body = `<div class="toggles">${o.types.map(x => `<button class="${r.types.includes(x) ? "on" : ""}" data-t="types" data-v="${x}">${x}</button>`).join("")}</div>`;
    if (r.kind === "Letters") body = `<div class="field"><h3>First letters</h3><input id="letters" class="input" value="${esc(r.letters)}" data-kbd placeholder="e.g. A-F, Q   (# = numbers)"></div>`;
    if (r.kind === "Set") body = `<div class="field"><h3>Set codes</h3><input id="sets" class="input" value="${esc(r.sets.join(", "))}" data-kbd placeholder="e.g. MH3, MH2"></div>`;
    if (r.kind === "Anything") body = `<p class="muted">Takes every card that reaches it.</p>`;
    $("#sheet").innerHTML = `<div class="shead"><h1>Bin ${b}</h1><button class="btn" data-b="cancel">✕ Cancel</button></div><div class="toggles" style="margin-bottom:14px">${kinds}</div>${body}
      <div class="field"><h3>Name on the screen (optional)</h3><input id="rname" class="input" value="${esc(r.name)}" data-kbd placeholder="described from the rule"></div>
      <div class="row"><button class="btn primary big grow" data-b="save">Save bin ${b}</button><button class="btn big" data-b="empty">Empty bin</button></div>`;
  };
  const read = () => {
    const v = id => $("#" + id)?.value;
    if (r.kind === "Price") { const lo = parseFloat(v("pmin")), hi = parseFloat(v("pmax")); r.min = isNaN(lo) ? null : lo; r.max = isNaN(hi) ? null : hi; }
    if (r.kind === "Letters") r.letters = v("letters") || "";
    if (r.kind === "Set") r.sets = (v("sets") || "").split(/[ ,;/]+/).filter(Boolean).map(x => x.toUpperCase());
    r.name = v("rname") || "";
  };
  openModal();
  draw();
  $("#sheet").onclick = async e => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.dataset.k) { read(); r.kind = t.dataset.k; draw(); }
    else if (t.dataset.t) { const a = r[t.dataset.t], v = t.dataset.v; const i = a.indexOf(v); i >= 0 ? a.splice(i, 1) : a.push(v); read(); draw(); }
    else if (t.dataset.b === "save" || t.dataset.b === "empty") {
      read();
      const rules = ST.setup.rules.slice(); while (rules.length < 8) rules.push(null);
      rules[b - 1] = t.dataset.b === "empty" ? null : r;
      ST.setup = Object.assign({}, ST.setup, { rules }); ST.src = "custom";
      closeModal(); await relabel(); render(true);
    } else if (t.dataset.b === "cancel") closeModal();
  };
}

// --------------------------------------------------------------------------------------------- sessions
let SL = null, SD = null;
function sessionsView() {
  if (!SL) { api("sessions").then(r => { SL = r.sessions; render(true); }); return `<div class="panel">Loading…</div>`; }
  const items = SL.map(s => {
    const tag = s.state === "finished" ? `<span class="tag ok">finished</span>` : s.state === "running" ? `<span class="tag">running</span>` : `<span class="tag warn">not finished</span>`;
    return `<div class="item" data-go="session" data-arg="${s.id}"><div class="grow"><div style="font-weight:700">${esc(s.name)}</div>
      <div class="muted small">${new Date(s.started).toLocaleString()} · ${esc(s.mode)} · ${s.cards} cards · ${money(s.total)}</div></div>
      ${s.toReview ? `<span class="tag warn">⚑ ${s.toReview} to review</span>` : ""}${tag}</div>`;
  }).join("") || `<div class="panel muted">No sessions yet.</div>`;
  return `<p class="muted small" style="margin-top:0">Download on any phone or PC on your Wi-Fi at <b>http://sorter.local:8080</b>. Your PC app also backs up every finished session automatically.</p>
    <div class="list">${items}</div>`;
}
function sessionView() {
  if (!SD || SD.id !== viewArg) { api("sessions/" + viewArg).then(r => { SD = r.session; render(true); }); return `<div class="panel">Loading…</div>`; }
  const s = SD;
  const bins = s.binLabels.map((l, i) => `<div class="bin ${i + 1 === s.binsInUse ? "end" : ""}"><div class="n">BIN ${i + 1}</div><div class="c">${s.binCounts[i + 1] || 0}</div><div class="l">${esc(l)}</div></div>`).join("");
  const files = (s.exports || []).map(f => `<a class="btn primary" href="/api/sessions/${s.id}/file/${encodeURIComponent(f)}" download>⬇ ${esc(f.split(" - ").pop())}</a>`).join("");
  const isOpen = S?.session?.id === s.id && RUNNING.includes(S.state);
  return `<div class="row" style="margin-bottom:12px"><div class="grow"><h1 style="margin:0">${esc(s.name)}</h1>
      <div class="muted small">${new Date(s.started).toLocaleString()} · ${esc(s.mode)} · ${s.cards} cards · ${s.flagged} flagged · total ${money(s.total)}${s.top ? " · highest " + esc(s.top.name) + " " + money(s.top.price) : ""}</div></div>
      </div>
    <div class="bins" style="margin-bottom:14px">${bins}</div>
    <div class="row">
      <button class="btn big ${s.toReview ? "primary" : ""}" data-go="review" data-arg="${s.id}" ${s.toReview ? "" : "disabled"}>⚑ Review flagged (${s.toReview})</button>
      ${s.state !== "finished" && !isOpen ? `<button class="btn big" data-act="finishsess" data-arg="${s.id}">✓ Finish${s.mode === "Catalog" ? " & save CSVs" : ""}</button>` : ""}
      ${files}<a class="btn" href="/api/sessions/${s.id}/bundle.zip" download>⬇ Everything (.zip)</a>
    </div>
    <div class="row" style="margin-top:14px"><button class="btn small" data-act="rename" data-arg="${s.id}">Rename</button>
      ${isOpen ? "" : `<button class="btn small danger" data-act="delsess" data-arg="${s.id}">Delete session</button>`}</div>`;
}

// --------------------------------------------------------------------------------------------- review
let RV = null;  // {sid, cards, i, finish, condition, extra (search results)}
function reviewView() {
  if (!RV || RV.sid !== viewArg) {
    RV = { sid: viewArg, cards: null, i: 0 };
    api(`sessions/${viewArg}/cards?show=review`).then(r => { RV.cards = r.cards; render(true); });
    return `<div class="panel">Loading…</div>`;
  }
  if (!RV.cards) return `<div class="panel">Loading…</div>`;
  const c = RV.cards[RV.i];
  if (!c) return `<div class="panel"><h1>All flagged cards reviewed ✓</h1><p class="muted">Finish the session to save the CSVs.</p>
      <div class="row"><button class="btn big primary" data-act="${reviewFrom === "run" ? "finish" : "finishsess"}" data-arg="${RV.sid}">✓ Finish & save CSVs</button></div></div>`;
  const cands = (RV.extra || c.candidates || []);
  const finishes = (c.finishes && c.finishes.length ? c.finishes : [{ key: "nonfoil", label: "Non-foil" }, { key: "foil", label: "Foil" }]);
  RV.finish = RV.finish || c.finish; RV.condition = RV.condition || c.condition || "Near Mint";
  const img = x => x.id ? `/api/card-image/${encodeURIComponent(x.id)}` : "";
  return `<div class="review">
    <div class="panel" style="display:flex;flex-direction:column;gap:10px">
      <div class="photo" style="background-image:url('/api/sessions/${RV.sid}/photo/${c.n}')"></div>
      <div class="row"><span class="tag warn">⚑ ${esc(c.flagReason || "flagged")}</span><span class="muted small">card ${c.n} · ${RV.i + 1} of ${RV.cards.length}</span></div>
      <div class="row"><button class="btn small" data-act="rv-prev" ${RV.i ? "" : "disabled"}>‹ Prev</button><button class="btn small" data-act="rv-skip">Skip ›</button>
        <button class="btn small" data-act="rv-reid">↻ Identify again</button></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:12px;min-height:0">
      <h1 style="margin:0">Which printing is it?</h1>
      <div class="row"><input id="rvsearch" class="input grow" placeholder="Not listed? Search a card name…" data-kbd><button class="btn" data-act="rv-search">Search</button></div>
      <div class="cands">${cands.map((x, i) => `<button class="cand ${i === 0 && !RV.extra ? "top" : ""}" data-pick="${i}">
        <div class="img" style="background-image:url('${img(x)}')"></div><div class="nm">${esc(x.name)}</div>
        <div class="st">${esc((x.setCode || "").toUpperCase())} #${esc(x.number)} · ${esc(x.setName || "")}</div></button>`).join("") || `<div class="muted">No suggestions. Search a card name above.</div>`}</div>
      <div class="row"><h3 style="margin:0">Finish</h3><span class="seg">${finishes.map(f => `<button class="${RV.finish === f.key ? "on" : ""}" data-fin="${f.key}">${esc(f.label)}</button>`).join("")}</span>
        <h3 style="margin:0">Condition</h3><span class="seg">${["Near Mint", "Lightly Played", "Moderately Played", "Heavily Played", "Damaged"].map(x => `<button class="${RV.condition === x ? "on" : ""}" data-cond="${x}">${x.split(" ").map(w => w[0]).join("")}</button>`).join("")}</span></div>
      <div class="row"><input id="rvnote" class="input grow" placeholder="Note: how to tell these apart (optional)" data-kbd value="${esc(c.note || "")}">
        <button class="btn danger" data-act="rv-wrong">✗ Not a card / leave out</button></div>
    </div></div>`;
}
async function reviewPick(i) {
  const c = RV.cards[RV.i];
  const list = RV.extra || c.candidates;
  const card = list[i];
  const verdict = !RV.extra && i === 0 ? "ok" : "picked";
  await api(`sessions/${RV.sid}/review`, { n: c.n, verdict, card, finish: RV.finish, condition: RV.condition, note: $("#rvnote")?.value || "" });
  nextReview();
}
function nextReview() { RV.cards.splice(RV.i, 1); RV.extra = null; RV.finish = null; RV.condition = null; if (RV.i >= RV.cards.length) RV.i = Math.max(0, RV.cards.length - 1); if (!RV.cards.length) RV.i = 0; render(true); SD = null; }

// --------------------------------------------------------------------------------------------- camera
let camTimer = null, camExp = "auto";
AFTER.camera = () => {
  api("lights", { on: true });
  const img = $("#camimg");
  const tick = () => {
    if (view !== "camera") { api("lights", { on: false }); return; }
    const n = new Image();
    n.onload = () => { img.src = n.src; camTimer = setTimeout(tick, 150); };
    n.onerror = () => { camTimer = setTimeout(tick, 1500); };
    n.src = "/api/preview.jpg?exp=" + camExp + "&t=" + Date.now();
  };
  clearTimeout(camTimer); tick();
};

// --------------------------------------------------------------------------------------------- actions
document.addEventListener("click", async e => {
  wake();
  const t = e.target.closest("[data-go],[data-act],[data-src],[data-mode],[data-editbin],[data-set],[data-tool],[data-pick],[data-fin],[data-cond]");
  if (!t) return;
  if (t.closest("#sheet") && !t.dataset.go) return;
  const d = t.dataset;
  if (d.go) { if (d.go === "start") ST = null; if (d.go === "sessions") SL = null; if (d.go === "review") RV = null; go(d.go, d.arg); return; }
  if (d.src) return pickSource(d.src);
  if (d.mode) { ST.name = $("#sname").value; ST.mode = d.mode; return render(true); }
  if (d.editbin) { ST.name = $("#sname").value; return editBin(+d.editbin); }
  if (d.set) { const v = isNaN(+d.val) ? d.val : +d.val; await api("settings", { [d.set]: v }); S.settings[d.set] = v; return render(true); }
  if (d.tool) {
    $("#toolout").textContent = "Working…";
    const r = await api("tools/" + d.tool, {});
    $("#toolout").textContent = r.ok ? (r.text || "Done.") : "⚠ " + r.error;
    return;
  }
  if (d.pick) return reviewPick(+d.pick);
  if (d.fin) { RV.finish = d.fin; return render(true); }
  if (d.cond) { RV.condition = d.cond; return render(true); }
  const act = d.act;
  const r = await ACT[act]?.(d.arg, t);
  if (r && r.ok === false && r.error) toast("⚠ " + r.error);
});
let lightsOn = false;
const ACT = {
  go: async () => {
    ST.name = $("#sname").value;
    const r = await api("session/start", { name: ST.name, mode: ST.mode, setup: ST.setup });
    if (r.ok) go("run"); return r;
  },
  pause: () => api("session/pause", {}), resume: () => api("session/resume", {}),
  stop: async () => { if (await confirmBox("Stop the session?", "No more cards are fed. Cards already on the track still go to their bins.", "■ Stop")) return api("session/stop", {}); },
  end: async () => { if (await confirmBox("End the session here?", "Take any cards off the track first. You can still review and finish it.", "End session")) return api("session/stop", {}); },
  continue: () => api("session/continue", {}),
  reset: () => api("reset", {}),
  finish: async () => { const r = await api("session/finish", {}); if (r.ok) { toast(r.exports?.length ? "Saved: " + r.exports.join(", ") : "Session saved."); go("home"); } return r; },
  close: async () => { await api("session/close", {}); go("home"); },
  "nav-home": async () => {   // Home from anywhere; a stopped, unfinished session is left to finish later
    if (S && RUNNING.includes(S.state)) return go("run");
    if (S?.state === "stopped" && S.session) await api("session/close", {});
    go("home");
  },
  camexp: v => { camExp = v; render(true); },
  finishsess: async sid => { const r = await api(`sessions/${sid}/finish`, {}); if (r.ok) { toast("Saved."); SD = null; go("session", sid); } return r; },
  delsess: async sid => { if (await confirmBox("Delete this session?", "Its photos and CSVs are deleted from the machine (your PC backup stays).", "Delete")) { const r = await api(`sessions/${sid}/delete`, {}); SL = null; go("sessions"); return r; } },
  rename: async sid => { const n = await promptBox("Rename session", SD?.name || ""); if (n) { await api(`sessions/${sid}/rename`, { name: n }); SD = null; render(true); } },
  savesetup: async () => { const n = await promptBox("Save these bins as", ""); if (n) { const r = await api("setups/save", { name: n, setup: ST.setup }); ST.opts.saved = r.saved; ST.src = "saved:0"; render(true); toast("Saved."); } },
  delsetup: async () => { const i = +ST.src.slice(6); const r = await api("setups/delete", { name: ST.opts.saved[i].name }); ST.opts.saved = r.saved; ST.src = "custom"; render(true); },
  update: async () => { if (await confirmBox("Update now?", "The machine restarts its software (about 30 seconds).", "Update")) { toast("Updating… the screen comes back by itself.", 8000); return api("update/install", {}); } },
  checkupdate: async () => { await api("update/check", {}); },
  shutdown: async () => { if (await confirmBox("Shut down the Pi?", "Wait 20 seconds after the screen goes dark before unplugging.", "Shut down")) return api("shutdown", {}); },
  lights: async () => { lightsOn = !lightsOn; await api("lights", { on: lightsOn }); $("#toolout").textContent = "Lights " + (lightsOn ? "on" : "off"); },
  "rv-prev": () => { RV.i = Math.max(0, RV.i - 1); RV.extra = null; RV.finish = null; render(true); },
  "rv-skip": () => { RV.i = Math.min(RV.cards.length - 1, RV.i + 1); RV.extra = null; RV.finish = null; render(true); },
  "rv-wrong": async () => { const c = RV.cards[RV.i]; await api(`sessions/${RV.sid}/review`, { n: c.n, verdict: "wrong", note: $("#rvnote")?.value || "" }); nextReview(); },
  "rv-search": async () => { const t = $("#rvsearch").value.trim(); if (!t) return; const r = await api("search", { text: t }); let list = r.cards || []; if (list.length === 1 || (list[0] && list[0].name.toLowerCase() === t.toLowerCase())) list = (await api("printings", { name: list[0].name })).printings; RV.extra = list; render(true); if (!list.length) toast("Nothing found (is the PC on?)"); },
  "rv-reid": async () => { const c = RV.cards[RV.i]; const r = await api(`sessions/${RV.sid}/reidentify`, { n: c.n }); if (r.ok) { if (!r.card.flagged) { toast("Identified: " + (r.card.card?.name || "")); nextReview(); } else { RV.cards[RV.i] = r.card; render(true); } } return r; },
};

// estop
$("#estop").addEventListener("click", e => { e.stopPropagation(); api("estop", {}); toast("EMERGENCY STOP", 4000); });

// --------------------------------------------------------------------------------------------- modal, confirm, prompt
function openModal() { $("#modal").hidden = false; }
function closeModal() { $("#modal").hidden = true; $("#sheet").onclick = null; hideKbd(); }
function confirmBox(title, text, ok) {
  return new Promise(res => {
    openModal();
    $("#sheet").innerHTML = `<div class="shead"><h1>${esc(title)}</h1><button class="btn" data-b="0">✕ Cancel</button></div><p class="muted">${esc(text)}</p><div class="row"><button class="btn big danger grow" data-b="1">${esc(ok)}</button></div>`;
    $("#sheet").onclick = e => { const b = e.target.closest("[data-b]"); if (b) { closeModal(); res(b.dataset.b === "1"); } };
  });
}
function promptBox(title, value) {
  return new Promise(res => {
    openModal();
    $("#sheet").innerHTML = `<div class="shead"><h1>${esc(title)}</h1><button class="btn" data-b="0">✕ Cancel</button></div><input id="pbox" class="input" value="${esc(value)}" data-kbd><div class="row" style="margin-top:14px"><button class="btn big primary grow" data-b="1">OK</button></div>`;
    $("#sheet").onclick = e => { const b = e.target.closest("[data-b]"); if (b) { const v = $("#pbox").value.trim(); closeModal(); res(b.dataset.b === "1" ? v : null); } };
    if (KIOSK) showKbd($("#pbox"));
  });
}

// --------------------------------------------------------------------------------------------- on-screen keyboard (kiosk)
let kbdTarget = null, kbdShift = false, kbdNum = false;
document.addEventListener("focusin", e => { if (KIOSK && e.target.matches("[data-kbd]")) showKbd(e.target); });
function showKbd(el) {
  kbdTarget = el; kbdNum = el.dataset.kbd === "num";
  drawKbd(); $("#kbd").hidden = false;
}
function hideKbd() { $("#kbd").hidden = true; kbdTarget = null; }
function drawKbd() {
  const rows = kbdNum ? [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], [".", "0", "⌫"]]
    : [["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"], ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "⌫"],
       ["a", "s", "d", "f", "g", "h", "j", "k", "l", "'", ","], ["⇧", "z", "x", "c", "v", "b", "n", "m", ".", "#", "&"]];
  const k = x => kbdShift && x.length === 1 ? x.toUpperCase() : x;
  $("#kbd").innerHTML = rows.map(r => `<div class="r">${r.map(x => `<button class="${x === "⇧" || x === "⌫" ? "w" : ""}" data-key="${esc(x)}">${esc(k(x))}</button>`).join("")}</div>`).join("")
    + `<div class="r">${kbdNum ? "" : `<button class="sp" data-key=" ">space</button>`}<button class="w" data-key="clear">Clear</button><button class="w ok" data-key="done">Done</button></div>`;
}
$("#kbd").addEventListener("pointerdown", e => {
  const b = e.target.closest("[data-key]"); if (!b || !kbdTarget) return;
  e.preventDefault();
  const key = b.dataset.key, el = kbdTarget;
  if (key === "done") return hideKbd();
  if (key === "⇧") { kbdShift = !kbdShift; return drawKbd(); }
  if (key === "clear") el.value = "";
  else if (key === "⌫") el.value = el.value.slice(0, -1);
  else { el.value += kbdShift ? key.toUpperCase() : key; if (kbdShift) { kbdShift = false; drawKbd(); } }
  el.dispatchEvent(new Event("input"));
});

// --------------------------------------------------------------------------------------------- screen sleep (kiosk)
let lastTouch = Date.now(), asleep = false;
function wake() { lastTouch = Date.now(); if (asleep) { asleep = false; $("#sleep").hidden = true; api("screen", { on: true }); } }
["pointerdown", "keydown"].forEach(ev => document.addEventListener(ev, () => wake(), true));
$("#sleep").addEventListener("pointerdown", e => { e.stopPropagation(); e.preventDefault(); wake(); });
setInterval(() => {
  if (!KIOSK || !S) return;
  const mins = +S.settings.sleepMinutes;
  if (!mins || RUNNING.includes(S.state) || S.alert) return;
  if (!asleep && Date.now() - lastTouch > mins * 60000) { asleep = true; $("#sleep").hidden = false; api("screen", { on: false }); }
}, 5000);

poll();
render(true);

// --------------------------------------------------------------------------------------------- hide the pointer (kiosk)
// Touch only: no arrow on screen. A plugged-in mouse shows it until 5 s without moving.
if (KIOSK) {
  document.documentElement.classList.add("nocursor");
  let hideTimer = 0;
  addEventListener("pointermove", e => {
    if (e.pointerType !== "mouse") return;
    document.documentElement.classList.remove("nocursor");
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => document.documentElement.classList.add("nocursor"), 5000);
  }, { passive: true });
}
