// Dev only (index.html?mock=supported&level=78): a fake backend for working on the UI in a browser.
// Scenarios: supported, unsupported, notfound, multi, busy, fail.
(() => {
  const q = new URLSearchParams(location.search);
  const scenario = q.get("mock") || "supported";
  let level = Number(q.get("level") ?? 78.27);
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const SERIAL = "XYZW012345";
  const backups = Array.from({ length: Number(q.get("backups") || 0) }, (_, n) => ({ id: "XYZW012345_mock" + n, created: `2026-10-09T20:${String(59 - n * 6).padStart(2, "0")}:00`, level: n ? 78.3 : 0 }));

  const info = (ip) => {
    if (scenario === "unsupported") {
      return { ip, name: "EPSON ET-2850 Series", model: null, supported: false, reason: "unknown_model",
        checks: [{ id: "found", state: "ok", params: { ip } }, { id: "model", state: "fail", params: { name: "EPSON ET-2850 Series", why: "unknown" } }],
        status: { code: 4, text: "Idle (ready to print)", errcode: null }, level: null, firmware: null, backups: [] };
    }
    const busy = scenario === "busy";
    return {
      ip, name: "EPSON ET-2500 Series", model: "ET-2500", supported: !busy, reason: null,
      serial: SERIAL, serial_masked: "XYZW0•••••", firmware: "BD19IA 19 Oct 2018", level, levels: { main_waste: level },
      status: { code: busy ? 2 : 4, text: busy ? "Busy" : "Idle (ready to print)", errcode: null },
      checks: [
        { id: "found", state: "ok", params: { ip } },
        { id: "model", state: "ok", params: { model: "ET-2500", serial_checked: true } },
        { id: "reading", state: "ok", params: { level } },
        busy ? { id: "idle", state: "fail", params: { text: "Busy", errcode: "" } } : { id: "idle", state: "ok", params: {} },
      ],
      backups: backups.slice(),
    };
  };

  // &auto=help pins the pad help open; &auto=done runs a reset (for headless screenshots).
  const auto = q.get("auto");
  if (auto) {
    const click = (sel) => { const el = document.querySelector(sel); if (el) el.click(); };
    setTimeout(() => {
      if (auto === "help") click(".help-btn");
      if (auto === "advanced") click('[data-action="advanced"]');
      if (auto === "restore") {
        click('[data-action="advanced"]');
        setTimeout(() => click('#modal-root [data-action="askRestore"] .grow'), 100);
      }
      if (auto === "proof") setTimeout(() => click('[data-action="proof"]'), 6000);
      if (auto === "restoring" || auto === "proof") {
        click('[data-action="advanced"]');
        setTimeout(() => click('#modal-root [data-action="askRestore"] .grow'), 100);
        setTimeout(() => click('#modal-root [data-action="doRestore"]'), 200);
      }
      if (auto === "done") {
        click("#pad");
        setTimeout(() => click('[data-action="askConfirm"]'), 100);
        setTimeout(() => click('[data-action="startReset"]'), 200);
      }
    }, 2500);
  }

  window.MOCK_API = {
    async bootstrap() {
      return { lang: q.get("lang") || "zh", version: "0.1.0", data_dir: "C:\\Users\\you\\AppData\\Roaming\\PadReset",
        links: { kofi: "https://ko-fi.com/", repo: "#", upstream: "#", license: "#" } };
    },
    async set_lang() { return true; },
    async discover() {
      await wait(1200);
      if (scenario === "notfound") return { printers: [] };
      if (scenario === "multi") return { printers: [{ ip: "192.168.1.20", name: "EPSON ET-2500 Series" }, { ip: "192.168.1.31", name: "EPSON ET-2850 Series" }] };
      return { printers: [{ ip: "192.168.1.20", name: "EPSON ET-2500 Series" }] };
    },
    async inspect(ip) { await wait(700); return info(ip); },
    async reset(serial, pad) {
      if (!pad) return { ok: false, code: "pad_required", params: {} };
      const before = level;
      for (const s of [0, 1, 2]) { window.onResetProgress(s); await wait(120); } // the real printer is this fast
      const id = "XYZW012345_mock" + backups.length;
      backups.unshift({ id, created: new Date().toISOString().slice(0, 19), level: before });
      if (scenario === "fail") return { ok: false, code: "write_failed", params: { addr: 30, backup_id: id }, level: 41.2 };
      level = 0;
      const plan = [[24, 0], [25, 0], [30, 0], [28, 0], [29, 0], [46, 94]];
      const was = before ? [250, 18, 0, 3, 7, 80] : [0, 0, 0, 0, 0, 94];
      const cells = plan.map(([addr, v], k) => ({ addr, before: was[k], written: v, after: v }));
      return { ok: true, backup_id: id, before, after: 0, levels: { main_waste: 0 }, cells };
    },
    async restore(id) {
      for (const s of [0, 1, 2]) { window.onResetProgress(s); await wait(120); }
      const b = backups.find((x) => x.id === id);
      level = b ? b.level : level;
      const cells = [[24, 0], [25, 0], [30, 0], [28, 0], [29, 0], [46, 94]].map(([addr, v]) => ({ addr, before: v, written: v, after: v }));
      return { ok: true, backup_id: id, after: level, levels: { main_waste: level }, cells };
    },
    async open_url(url) { console.log("open_url", url); return true; },
    async open_model_request(name) { console.log("request", name); return true; },
    async open_data_dir() { return true; },
  };
})();
