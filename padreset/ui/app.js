(() => {
  "use strict";

  // ------------------------------------------------------------------ icons
  const P = {
    drop: '<path d="M12 2.7c-3.5 4.3-6 7.6-6 10.8a6 6 0 0 0 12 0c0-3.2-2.5-6.5-6-10.8z"/><path d="M9 15a3 3 0 0 0 3 3"/>',
    printer: '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6 14h12v7H6z"/>',
    warn: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    bang: '<path d="M12 6v8"/><path d="M12 18h.01"/>',
    coffee: '<path d="M17 8h1a4 4 0 0 1 0 8h-1"/><path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4z"/><path d="M6 2v2"/><path d="M10 2v2"/><path d="M14 2v2"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    help: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  };
  const svg = (name, size, color = "currentColor", sw = 2) =>
    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name]}</svg>`;

  // ------------------------------------------------------------------ state
  const S = {
    lang: /^zh/i.test(navigator.language) ? "zh" : "en",
    boot: null,
    step: "boot",
    printers: [],
    info: null,
    pad: false,
    stage: 0,
    result: null,
    error: null,
    errorKind: "reset",
    restore: null,
    beforeLevel: null,
    revealSerial: false,
    showReadonly: false,
    manualIp: "",
    manualErr: false,
    modal: null,
  };

  const set = (patch) => { Object.assign(S, patch); render(); };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Templates are trusted HTML; parameters are escaped.
  function t(key, params) {
    const dict = I18N[S.lang] || I18N.zh;
    let s = dict[key] ?? I18N.en[key] ?? key;
    if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined ? esc(params[k]) : m));
    return s;
  }

  const fmtLevel = (x) => {
    if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
    const r = Math.round(Number(x) * 10) / 10;
    return Number.isInteger(r) ? String(r) : r.toFixed(1);
  };
  const fmtTime = (iso) => (iso ? String(iso).replace("T", " ").slice(0, 16) : "");
  const nowIso = () => {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
  };

  const STATUS_ZH = {
    "Error": "错误", "Self Printing": "正在自检打印", "Busy": "忙碌", "Waiting": "等待中",
    "Idle (ready to print)": "空闲", "Paused": "已暂停", "Cleaning": "正在清洗",
    "Factory shipment (not initialized)": "出厂状态（未初始化）", "Shutdown": "正在关机",
    "Nozzle Check": "喷嘴检查", "Charging": "正在充墨",
  };
  const statusText = (s) => (S.lang === "zh" && STATUS_ZH[s]) || s || "";

  // -------------------------------------------------------------------- api
  const api = () => (window.pywebview && window.pywebview.api) || window.MOCK_API;
  async function call(name, ...args) {
    try {
      return await api()[name](...args);
    } catch (e) {
      console.error(name, e);
      return { ok: false, code: "error", params: { detail: String((e && e.message) || e) } };
    }
  }

  // ------------------------------------------------------------------- flow
  async function startScan() {
    set({ step: "scanning", info: null, printers: [], showReadonly: false, modal: null });
    const res = await call("discover");
    const printers = (res && res.printers) || [];
    if (printers.length === 1) return inspect(printers[0].ip);
    set({ step: printers.length ? "pick" : "notfound", printers });
  }

  async function inspect(ip) {
    set({ step: "checking", pad: false, revealSerial: false, showReadonly: false, modal: null, info: S.info && S.info.ip === ip ? S.info : null });
    const info = await call("inspect", ip);
    if (!info || info.code === "error") return set({ step: "failed", error: info, errorKind: "inspect" });
    set({ info, step: info.supported ? "found" : "unsupported" });
  }

  // The printer finishes each step in a fraction of a second. Every step the
  // backend reports stays on screen at least MIN_STEP_MS so the user can see it
  // happen; the steps themselves are real, only their display is held.
  const MIN_STEP_MS = 900;
  let paceChain = Promise.resolve();
  function paced(fn) {
    paceChain = paceChain.then(() => { fn(); return new Promise((r) => setTimeout(r, MIN_STEP_MS)); });
    return paceChain;
  }
  window.onResetProgress = (stage) => { paced(() => set({ stage: Number(stage) || 0 })); };

  async function runSteps(step, request) {
    paceChain = Promise.resolve();
    set({ step, stage: 0, modal: null });
    const res = await request();
    if (res && res.ok) await paced(() => set({ stage: 3 })); // all ticked, briefly
    else await paceChain;
    return res;
  }

  async function startReset() {
    S.beforeLevel = S.info.level;
    const res = await runSteps("resetting", () => call("reset", S.info.serial, S.pad));
    if (res && res.ok) {
      S.info.level = res.after;
      S.info.levels = res.levels;
      return set({ step: "done", result: res, pad: false });
    }
    set({ step: "failed", error: res, errorKind: "reset", pad: false });
  }

  function askRestore(id, level, created) {
    set({ restore: { id, level, created: created || nowIso() }, modal: "restore" });
  }

  async function doRestore() {
    const res = await runSteps("restoring", () => call("restore", S.restore.id, S.info.serial));
    if (res && res.ok) {
      S.info.level = res.after;
      return set({ step: "restored", result: res });
    }
    set({ step: "failed", error: res, errorKind: "restore" });
  }

  function manualConnect() {
    const ip = S.manualIp.trim();
    const ok = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.test(ip) && ip.split(".").every((n) => Number(n) <= 255);
    if (!ok) return set({ manualErr: true });
    S.manualErr = false;
    inspect(ip);
  }

  // The pad help popover opens on hover (CSS) or is pinned by a click. Pinning
  // only toggles a class, so the page is not re-rendered under the mouse.
  function setPadHelp(open) {
    const wrap = document.querySelector(".pad-wrap");
    if (!wrap) return;
    wrap.classList.toggle("help-open", open);
    const btn = wrap.querySelector(".help-btn");
    if (btn) btn.setAttribute("aria-expanded", String(open));
  }

  const actions = {
    donate: () => call("open_url", S.boot.links.kofi),
    link: (d) => call("open_url", d.url),
    help: () => set({ modal: "help" }),
    advanced: () => set({ modal: "advanced" }),
    closeModal: () => set({ modal: null }),
    lang: () => {
      const lang = S.lang === "zh" ? "en" : "zh";
      call("set_lang", lang);
      set({ lang });
    },
    rescan: () => startScan(),
    recheck: () => inspect(S.info.ip),
    pick: (d) => inspect(d.ip),
    manualConnect,
    padHelp: (d, e) => {
      e.preventDefault(); // the button sits inside the checkbox label
      setPadHelp(!document.querySelector(".pad-wrap.help-open"));
    },
    askConfirm: () => { if (S.pad) set({ step: "confirm" }); },
    cancelConfirm: () => set({ step: "found" }),
    startReset,
    undo: () => askRestore(S.result.backup_id, S.result.before, null),
    restoreFromError: () => askRestore(S.error.params.backup_id, S.beforeLevel, null),
    askRestore: (d) => askRestore(d.id, Number(d.level), d.created),
    doRestore,
    proof: () => set({ modal: "proof" }),
    finish: () => inspect(S.info.ip),
    revealSerial: () => set({ revealSerial: !S.revealSerial }),
    readonly: () => set({ showReadonly: !S.showReadonly }),
    request: () => call("open_model_request", S.info.name || "", S.info.firmware || ""),
    openFolder: () => call("open_data_dir"),
  };

  // ----------------------------------------------------------------- pieces
  function header() {
    return `<header>
      <div class="brand">${svg("drop", 26, "var(--accent)")}<span class="brand-name">${t("app.name")}</span><span class="pill-beta">Beta</span></div>
      <nav aria-label="${t("nav.aria")}">
        <button type="button" class="nav-donate" data-action="donate">${svg("coffee", 16)}${t("nav.donate")}</button>
        <button type="button" class="nav-btn" data-action="advanced">${t("nav.advanced")}</button>
        <button type="button" class="nav-btn" data-action="help">${t("nav.help")}</button>
        <button type="button" class="nav-btn nav-lang" data-action="lang" aria-label="${t("nav.lang.aria")}">${t("nav.lang")}</button>
      </nav>
    </header>`;
  }

  function footer() {
    const up = S.boot ? S.boot.links.upstream : "";
    return `<footer>
      ${t("footer.base", { link: "\u0000" }).replace("\u0000", `<button type="button" class="link" data-action="link" data-url="${esc(up)}">epson_print_conf</button>`)} ·
      ${t("footer.free")} · <button type="button" class="link" data-action="donate">${t("footer.coffee")}</button>${S.boot ? ` · v${esc(S.boot.version)}` : ""}
    </footer>`;
  }

  const spinnerBlock = (title, desc) =>
    `<div class="center" role="status"><div class="spinner"></div><div class="title-lg">${title}</div>${desc ? `<div class="desc">${desc}</div>` : ""}</div>`;

  function printerRow({ warn = false, rescan = false } = {}) {
    const i = S.info;
    if (!i) return "";
    let meta = t("printer.meta", { ip: i.ip });
    if (i.serial) {
      const shown = S.revealSerial ? i.serial : i.serial_masked;
      meta += ` · <button type="button" class="serial-btn" data-action="revealSerial" title="${t("printer.reveal")}">${t("printer.serial", { serial: shown })}</button>`;
    }
    return `<div class="printer">
      <div class="printer-icon ${warn ? "warn" : ""}">${svg(warn ? "warn" : "printer", 24, warn ? "var(--amber)" : "var(--accent)")}</div>
      <div class="printer-text"><div class="printer-name">${esc(i.name || i.ip)}</div><div class="printer-meta">${meta}</div></div>
      ${rescan ? `<button type="button" class="icon-btn" data-action="rescan" title="${t("rescan")}" aria-label="${t("rescan")}">${svg("refresh", 18)}</button>` : ""}
    </div>`;
  }

  function checkDesc(c) {
    const p = c.params || {};
    let v;
    if (c.id === "found") v = c.state === "ok" ? "ok" : "fail";
    else if (c.id === "model") v = c.state === "ok" ? (p.serial_checked ? "ok" : "ok_noserial") : p.why;
    else if (c.id === "reading") v = c.state === "ok" ? "ok" : p.why;
    else if (c.id === "idle") v = c.state === "ok" ? (p.locked ? "locked" : "ok") : p.why === "unknown" ? "unknown" : "fail";
    const params = { ...p };
    if (p.level !== undefined) params.level = fmtLevel(p.level);
    if (p.text !== undefined) params.text = statusText(p.text);
    return t(`check.${c.id}.${v}`, params);
  }

  function checksBlock() {
    const list = (S.info && S.info.checks) || [];
    if (!list.length) return "";
    const passed = list.filter((c) => c.state !== "fail").length;
    const items = list.map((c) => {
      const dot = c.state === "ok" ? svg("check", 13, "#FFFFFF", 3.5) : c.state === "warn" ? svg("bang", 13, "#FFFFFF", 3.5) : svg("x", 13, "#FFFFFF", 3.5);
      const titleKey = c.state === "fail" && I18N.zh[`check.${c.id}.title.fail`] ? `check.${c.id}.title.fail` : `check.${c.id}.title`;
      return `<li class="check"><span class="dot ${c.state === "ok" ? "" : c.state}">${dot}</span>
        <span class="check-text"><span class="check-title">${t(titleKey)}</span><span class="check-desc">${checkDesc(c)}</span></span></li>`;
    }).join("");
    return `<section class="checks" aria-labelledby="check-title">
      <div class="checks-head"><h2 id="check-title">${t("check.title")}</h2>
      <span class="checks-count ${passed < list.length ? "bad" : ""}">${t("check.count", { ok: passed, total: list.length })}</span></div>
      <ul>${items}</ul></section>`;
  }

  function levelLook(level) {
    if (level >= 100) return { color: "var(--red)", bg: "var(--red-bg)", key: "level.full" };
    if (level >= 90) return { color: "var(--red)", bg: "var(--red-bg)", key: "level.near" };
    if (level >= 60) return { color: "var(--amber)", bg: "var(--amber-bg)", key: "level.high" };
    if (level < 0.05) return { color: "var(--accent)", bg: "var(--accent-tint)", key: "level.zero" };
    return { color: "var(--accent)", bg: "var(--accent-tint)", key: "level.ok" };
  }

  function meterBlock() {
    const level = S.info && S.info.level;
    if (level === null || level === undefined) return "";
    const look = levelLook(level);
    const width = Math.max(0, Math.min(100, level));
    return `<section class="meter" aria-label="${t("meter.label")}">
      <div class="meter-top">
        <div class="meter-head"><div class="meter-label">${t("meter.label")}</div>
        <div class="meter-num" style="color:${look.color}">${fmtLevel(level)}%</div></div>
        <div class="meter-tag" style="color:${look.color};background:${look.bg}">${t(look.key)}</div>
      </div>
      <div class="bar" aria-hidden="true"><div style="width:${width}%;background:${look.color}"></div></div>
      <div class="small">${t(look.key + ".hint")}</div>
    </section>`;
  }

  function padBlock() {
    return `<div class="pad-block">
      <div class="pad-wrap">
        <label class="pad"><input type="checkbox" id="pad" ${S.pad ? "checked" : ""}>
          <span class="pad-text"><span class="pad-label">${t("pad.label")}</span>
          <span class="small pad-hint">${t("pad.hint")}<button type="button" class="help-btn" data-action="padHelp" aria-expanded="false" aria-controls="pad-help" aria-label="${t("pad.help.aria")}">${svg("help", 17)}</button></span></span>
        </label>
        <div class="popover" id="pad-help" role="note">${t("pad.help.html")}</div>
      </div>
      <button type="button" class="btn btn-primary btn-big" data-action="askConfirm" ${S.pad ? "" : "disabled"}>${t("reset.btn")}</button>
      <div class="tiny">${t("reset.note")}</div>
    </div>`;
  }

  function manualForm() {
    return `<div class="manual">
      <label class="field-label" for="manual-ip">${t("manual.label")}</label>
      <div class="field"><input id="manual-ip" inputmode="decimal" autocomplete="off" spellcheck="false" placeholder="${t("manual.placeholder")}" value="${esc(S.manualIp)}">
      <button type="button" class="btn btn-primary btn-sm" data-action="manualConnect">${t("manual.connect")}</button></div>
      ${S.manualErr ? `<div class="field-err">${t("manual.invalid")}</div>` : ""}
    </div>`;
  }

  function stepsBlock(prefix) {
    const steps = prefix === "rstep"
      ? [["rstep.recheck", "rstep.recheck.desc"], ["rstep.write", "rstep.write.desc"], ["rstep.verify", "rstep.verify.desc"]]
      : [["step.backup", "step.backup.desc"], ["step.write", "step.write.desc"], ["step.verify", "step.verify.desc"]];
    return `<ol class="steps">${steps.map(([k, d], i) => {
      const icon = S.stage > i ? `<span class="step-done">${svg("check", 14, "#FFFFFF", 3.5)}</span>`
        : S.stage === i ? `<span class="spinner sm"></span>` : `<span class="step-pending"></span>`;
      return `<li class="step">${icon}<span class="check-text"><span class="step-title">${t(k)}</span><span class="small">${t(d)}</span></span></li>`;
    }).join("")}</ol>`;
  }

  function donateBlock() {
    return `<div class="donate" id="donate">
      <div class="donate-top"><span class="donate-icon">${svg("coffee", 26, "var(--amber)")}</span>
      <span class="donate-text"><span class="donate-title">${t("donate.title")}</span><span class="donate-body">${t("donate.body")}</span></span></div>
      <button type="button" class="donate-btn" data-action="donate">${svg("coffee", 18)}${t("donate.btn")}</button>
    </div>`;
  }

  const banner = (kind, title, body) => {
    const icon = kind === "ok" ? `<span class="banner-icon">${svg("check", 18, "#FFFFFF", 3)}</span>`
      : kind === "bad" ? `<span class="banner-icon">${svg("x", 18, "#FFFFFF", 3)}</span>` : "";
    return `<div class="banner ${kind}" role="${kind === "ok" ? "status" : "alert"}">${icon}<span class="banner-text"><span class="banner-title">${title}</span><span class="banner-body">${body}</span></span></div>`;
  };

  const confirmBox = (title, bodyHtml, cancelAction, okAction, okLabel, focusCancel) =>
    `<div class="confirm" role="alertdialog" aria-labelledby="confirm-title" aria-describedby="confirm-body">
      <div class="confirm-title" id="confirm-title">${title}</div>
      <div class="confirm-body" id="confirm-body">${bodyHtml}</div>
      <div class="row"><button type="button" class="btn btn-secondary" data-action="${cancelAction}" ${focusCancel ? "data-autofocus" : ""}>${t("cancel")}</button>
      <button type="button" class="btn btn-primary" data-action="${okAction}" ${focusCancel ? "" : "data-autofocus"}>${okLabel}</button></div>
    </div>`;

  function unsupportedKind(i) {
    switch (i.reason) {
      case "unknown_model": case "no_reset_params": return "model";
      case "read_key_failed": case "serial_mismatch": return "params";
      case "read_failed": case "implausible": return "reading";
      case "no_response": return "noresp";
      default: return "busy";
    }
  }

  function readonlyBlock() {
    const i = S.info, st = i.status || {};
    const none = t("ro.none");
    const rows = [
      ["ro.model", i.name || none],
      ["ro.ip", i.ip],
      ["ro.status", st.text ? statusText(st.text) + (st.errcode ? ` · ${st.errcode}` : "") : none],
      ["ro.firmware", i.firmware || none],
      ["ro.level", i.level !== null && i.level !== undefined ? fmtLevel(i.level) + "%" : none],
    ];
    return `<dl class="kv">${rows.map(([k, v]) => `<dt>${t(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  }

  // Evidence that the write happened: every value is read back from the printer.
  function proofText(res) {
    const cells = (res && res.cells) || [];
    if (!cells.length) return "";
    let html = t("proof.summary", { n: cells.length });
    if (cells.every((c) => c.before === c.written)) html += (S.lang === "zh" ? "" : " ") + t("proof.same");
    return html;
  }
  const proofButton = (res) => (res && res.cells && res.cells.length
    ? `<button type="button" class="link proof-link" data-action="proof">${t("proof.toggle")}</button>` : "");

  function proofModal() {
    const cells = (S.result && S.result.cells) || [];
    const rows = cells.map((c) => `<tr><td>${esc(c.addr)}</td><td>${esc(c.before)}</td><td>${esc(c.written)}</td>
      <td>${esc(c.after)} ${c.after === c.written ? `<span class="ok-mark" aria-label="${t("proof.match")}">✓</span>` : ""}</td></tr>`).join("");
    return `<div class="overlay center-v" data-overlay="1"><div class="modal modal-sm" role="dialog" aria-modal="true" aria-labelledby="m-title">
      <h2 id="m-title" class="modal-title">${t("proof.title")}</h2>
      <div class="small">${t("proof.desc")}</div>
      <table class="proof"><thead><tr><th>${t("proof.addr")}</th><th>${t("proof.before")}</th><th>${t("proof.written")}</th><th>${t("proof.after")}</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="small">${proofText(S.result)}</div>
      <div class="row"><button type="button" class="btn btn-primary" data-action="closeModal" data-autofocus>${t("close")}</button></div>
    </div></div>`;
  }

  // ------------------------------------------------------------------ views
  // Each view is either {full} (centred in the card) or {left, right} (two columns).
  function view() {
    const i = S.info;
    switch (S.step) {
      case "boot":
      case "scanning":
        return { full: spinnerBlock(t("scan.title"), t("scan.desc")) };

      case "checking":
        return { full: spinnerBlock(t("checking.title"), t("checking.desc")) };

      case "notfound":
        return { full: `<div class="center">
          <div class="printer-icon warn">${svg("printer", 24, "var(--amber)")}</div>
          <div class="title-lg">${t("notfound.title")}</div><div class="desc">${t("notfound.desc")}</div>
          ${manualForm()}
          <button type="button" class="btn btn-secondary btn-sm" data-action="rescan">${svg("refresh", 16)}${t("rescan")}</button>
        </div>` };

      case "pick":
        return { full: `<div class="pick"><div class="title-md">${t("pick.title", { n: S.printers.length })}</div>
          <div class="list">${S.printers.map((p) => `<button type="button" class="list-item" data-action="pick" data-ip="${esc(p.ip)}">
            ${svg("printer", 22, "var(--accent)")}<span class="grow"><strong>${esc(p.name)}</strong><span class="printer-meta">${esc(p.ip)}</span></span></button>`).join("")}</div>
          <button type="button" class="btn btn-ghost" style="align-self:center" data-action="rescan">${t("rescan")}</button></div>` };

      case "found":
        return { left: printerRow({ rescan: true }) + checksBlock(), right: meterBlock() + padBlock() };

      case "unsupported": {
        const kind = unsupportedKind(i);
        const canRequest = kind === "model" || kind === "params";
        return {
          left: `${printerRow({ warn: true })}
            ${banner("warn", t("unsup.title." + kind), t("unsup.body." + kind))}
            <div class="row stack">
              ${kind !== "noresp" ? `<button type="button" class="btn btn-secondary" data-action="readonly" aria-expanded="${S.showReadonly}">${t("unsup.readonly")}</button>` : ""}
              ${canRequest ? `<button type="button" class="btn btn-primary" data-action="request">${t("unsup.request")}</button>` : ""}
              ${kind === "busy" || kind === "reading" ? `<button type="button" class="btn btn-primary" data-action="recheck">${t("recheck")}</button>` : ""}
            </div>
            <button type="button" class="btn btn-ghost" style="align-self:flex-start" data-action="rescan">${svg("refresh", 16)}${t("rescan")}</button>`,
          right: checksBlock() + (S.showReadonly ? readonlyBlock() : ""),
        };
      }

      case "confirm":
        return {
          left: printerRow() + checksBlock(),
          right: meterBlock() + confirmBox(t("confirm.title"),
            t("confirm.body", { model: i.model, serial: S.revealSerial ? i.serial : i.serial_masked, level: fmtLevel(i.level) }),
            "cancelConfirm", "startReset", t("confirm.ok"), false),
        };

      case "resetting":
        return {
          left: printerRow() + checksBlock(),
          right: `<div class="stack-tight" role="status"><div class="title-md">${t("resetting.title")}</div><div class="small">${t("resetting.desc")}</div></div>${stepsBlock()}`,
        };

      case "done":
        return {
          left: `${printerRow({ rescan: true })}
            ${banner("ok", t("done.title"), t("done.body", { after: fmtLevel(S.result.after), before: fmtLevel(S.result.before) }) + "<br>" + proofText(S.result) + proofButton(S.result))}
            <div class="next"><h3>${t("done.next")}</h3><ol><li>${t("done.step1")}</li><li>${t("done.step2")}</li></ol></div>
            <div class="row"><button type="button" class="btn btn-secondary" data-action="undo">${t("undo")}</button>
            <button type="button" class="btn btn-primary" data-action="finish">${t("finish")}</button></div>`,
          right: meterBlock() + donateBlock(),
        };

      case "failed": {
        const e = S.error || {};
        const p = e.params || {};
        let msg = t("err." + (e.code || "error"), p.detail !== undefined || e.code !== "error" ? p : { detail: "?" });
        if (e.level !== undefined && e.level !== null) msg += "<br>" + t("failed.now", { level: fmtLevel(e.level) });
        const title = S.errorKind === "restore" ? t("restore.failed.title") : t("failed.title");
        const buttons = `<div class="row">${i ? `<button type="button" class="btn btn-secondary" data-action="recheck">${t("retry")}</button>` : `<button type="button" class="btn btn-secondary" data-action="rescan">${t("rescan")}</button>`}
          ${p.backup_id && S.errorKind === "reset" ? `<button type="button" class="btn btn-primary" data-action="restoreFromError">${t("restore.btn")}</button>` : ""}</div>`;
        if (!i) return { full: `<div class="pick">${banner("bad", title, msg)}${buttons}</div>` };
        return { left: printerRow() + banner("bad", title, msg) + buttons, right: meterBlock() || checksBlock() };
      }

      case "restoring":
        return {
          left: printerRow() + checksBlock(),
          right: `<div class="stack-tight" role="status"><div class="title-md">${t("restoring.title")}</div><div class="small">${t("resetting.desc")}</div></div>${stepsBlock("rstep")}`,
        };

      case "restored":
        return {
          left: `${printerRow({ rescan: true })}${banner("ok", t("restored.title"), t("restored.body", { after: fmtLevel(S.result.after) }) + "<br>" + proofText(S.result) + proofButton(S.result))}
            <div class="row"><button type="button" class="btn btn-primary" data-action="finish">${t("finish")}</button></div>`,
          right: meterBlock(),
        };
    }
    return { full: "" };
  }

  function modal() {
    const close = `<button type="button" class="btn btn-ghost btn-sm" data-action="closeModal" data-autofocus>${t("close")}</button>`;
    if (S.modal === "help") {
      return `<div class="overlay" data-overlay="1"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
        <div class="modal-head"><h2 id="m-title">${t("help.title")}</h2>${close}</div>
        <div>${t("help.html", { dir: S.boot ? S.boot.data_dir : "" })}</div></div></div>`;
    }
    if (S.modal === "proof") return proofModal();
    if (S.modal === "restore") {
      const r = S.restore;
      return `<div class="overlay center-v" data-overlay="1"><div class="modal modal-sm" role="alertdialog" aria-modal="true" aria-labelledby="m-title" aria-describedby="m-body">
        <h2 id="m-title" class="modal-title">${t("restore.title")}</h2>
        <div id="m-body" class="confirm-body">${t("restore.body", { level: fmtLevel(r.level), time: fmtTime(r.created) })}</div>
        <div class="small">${t("restore.note")}</div>
        <div class="row"><button type="button" class="btn btn-secondary" data-action="closeModal" data-autofocus>${t("cancel")}</button>
        <button type="button" class="btn btn-primary" data-action="doRestore">${t("restore.ok")}</button></div>
      </div></div>`;
    }
    const i = S.info;
    let backups;
    if (!i || !i.serial) backups = `<p>${t("adv.backups.need")}</p>`;
    else if (!i.backups || !i.backups.length) backups = `<p>${t("adv.backups.none")}</p>`;
    else {
      const canRestore = i.supported;
      backups = `<div class="list backups">${i.backups.map((b) => `<button type="button" class="list-item" data-action="askRestore" data-id="${esc(b.id)}" data-level="${esc(b.level)}" data-created="${esc(b.created)}" ${canRestore ? "" : "disabled"}>
        <span class="grow">${t("adv.backup.item", { time: fmtTime(b.created), level: fmtLevel(b.level) })}</span><span class="list-action">${t("restore.btn")}</span></button>`).join("")}</div>
        ${canRestore ? "" : `<div class="small">${t("adv.backups.blocked")}</div>`}`;
    }
    const links = S.boot ? S.boot.links : {};
    return `<div class="overlay" data-overlay="1"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title">
      <div class="modal-head"><h2 id="m-title">${t("adv.title")}</h2>${close}</div>
      <section><div class="field-label">${t("adv.manual")}</div>${manualForm()}</section><hr>
      <section><div class="field-label">${t("adv.backups")}</div>${backups}</section><hr>
      <section><button type="button" class="btn btn-secondary btn-sm" style="align-self:flex-start" data-action="openFolder">${t("adv.folder")}</button></section><hr>
      <section><div class="field-label">${t("adv.about")}</div>
        <p>${t("adv.version", { version: S.boot ? S.boot.version : "" })} ·
        <button type="button" class="link" data-action="link" data-url="${esc(links.repo)}">${t("adv.source")}</button> ·
        <button type="button" class="link" data-action="link" data-url="${esc(links.license)}">${t("adv.license")}</button></p></section>
    </div></div>`;
  }

  // ----------------------------------------------------------------- render
  function render() {
    document.documentElement.lang = S.lang === "zh" ? "zh-CN" : "en";
    document.title = t("app.name");
    const v = view();
    const main = v.full !== undefined
      ? `<main class="solo">${v.full}</main>`
      : `<main class="split"><div class="pane">${v.left}</div><div class="pane">${v.right}</div></main>`;
    document.getElementById("app").innerHTML =
      `<div class="page"><div class="col">${header()}${main}${footer()}</div></div>`;
    document.getElementById("modal-root").innerHTML = S.modal ? modal() : "";
    const focus = document.querySelector("#modal-root [data-autofocus]") || document.querySelector("main [data-autofocus]");
    if (focus) focus.focus();
  }

  document.addEventListener("click", (e) => {
    if (e.target.dataset && e.target.dataset.overlay) return set({ modal: null });
    const el = e.target.closest("[data-action]");
    if (!e.target.closest(".pad-wrap")) setPadHelp(false);
    if (!el || el.disabled) return;
    const fn = actions[el.dataset.action];
    if (fn) fn(el.dataset, e, el);
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "pad") set({ pad: e.target.checked });
  });
  document.addEventListener("input", (e) => {
    if (e.target.id === "manual-ip") S.manualIp = e.target.value;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (document.querySelector(".pad-wrap.help-open")) return setPadHelp(false);
      if (S.modal) set({ modal: null });
    }
    if (e.key === "Enter" && e.target.id === "manual-ip") manualConnect();
  });

  let started = false;
  async function start() {
    if (started) return;
    started = true;
    const boot = await call("bootstrap");
    S.boot = boot && boot.links ? boot : null;
    if (S.boot && S.boot.lang) S.lang = S.boot.lang;
    startScan();
  }

  render();
  if ((window.pywebview && window.pywebview.api) || window.MOCK_API) start();
  else window.addEventListener("pywebviewready", start, { once: true });
})();
