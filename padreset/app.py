"""Window and the API the page calls (window.pywebview.api.*)."""

import ctypes
import ipaddress
import locale
import logging
import logging.handlers
import os
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import webview

from . import config, core, discovery, store

log = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent / "ui"
LICENSE_URL = "https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12"


# Landscape, in logical pixels including the title bar. Fits 1366x768 at 100%
# and 1920x1080 at up to 150% scaling with the taskbar shown.
WINDOW_SIZE = (960, 620)


def fit_to_work_area(width, height, margin=24):
    """Shrink the window if the screen's work area (minus taskbar) is smaller."""
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()  # pywebview does this too; makes the rect physical
        rect = wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        scale = user32.GetDpiForSystem() / 96
        work_w = (rect.right - rect.left) / scale
        work_h = (rect.bottom - rect.top) / scale
        return int(min(width, work_w - margin)), int(min(height, work_h - margin))
    except Exception:
        return width, height


def default_lang():
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "zh" if (langid & 0x3FF) == 0x04 else "en"  # LANG_CHINESE
    except Exception:
        loc = (locale.getlocale()[0] or "").lower()
        return "zh" if loc.startswith(("zh", "chinese")) else "en"


class Api:
    """Public methods are callable from JavaScript; keep state in _private attributes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._session = None
        self._window = None
        self._settings = store.load_settings()

    def _guard(self, fn):
        """Run fn; turn exceptions into a result the page can show."""
        try:
            return fn()
        except core.OperationError as exc:
            log.warning("Refused: %s %s", exc.code, exc.params)
            return {"ok": False, "code": exc.code, "params": exc.params, "level": self._current_level()}
        except Exception as exc:
            log.exception("API call failed")
            return {"ok": False, "code": "error", "params": {"detail": str(exc) or type(exc).__name__}}

    def _current_level(self):
        s = self._session
        if not s or not s.printer:
            return None
        return core.overall_level(core._safe(s.printer.get_waste_ink_levels))

    def _progress(self, stage):
        if self._window:
            self._window.evaluate_js(f"window.onResetProgress && window.onResetProgress({int(stage)})")

    def bootstrap(self):
        return {
            "lang": self._settings.get("lang") or default_lang(),
            "version": config.VERSION,
            "data_dir": str(store.data_dir()),
            "links": {
                "kofi": config.KOFI_URL,
                "repo": config.REPO_URL,
                "upstream": config.UPSTREAM_URL,
                "license": LICENSE_URL,
            },
        }

    def set_lang(self, lang):
        if lang in ("zh", "en"):
            self._settings = store.save_settings(lang=lang)
            if self._window:
                self._window.set_title(config.APP_NAME[lang])
        return True

    def discover(self):
        def run():
            with self._lock:
                last = self._settings.get("last_ip")
                return {"printers": discovery.scan([last] if last else [])}
        return self._guard(run)

    def inspect(self, ip):
        def run():
            addr = str(ipaddress.ip_address(str(ip).strip()))
            with self._lock:
                self._session = core.Session(addr)
                result = self._session.inspect()
                log.info(
                    "Inspect %s: %s model=%s supported=%s reason=%s level=%s checks=%s",
                    addr, result.get("name"), result.get("model"), result["supported"],
                    result.get("reason"), result.get("level"),
                    {c["id"]: c["state"] for c in result["checks"]},
                )
                if result.get("name"):
                    self._settings = store.save_settings(last_ip=addr)
                return result
        return self._guard(run)

    def reset(self, serial, pad_confirmed):
        log.info("Reset requested (pad confirmed: %s)", pad_confirmed)

        def run():
            if pad_confirmed is not True:
                return {"ok": False, "code": "pad_required", "params": {}}
            with self._lock:
                if not self._session or not self._session.printer:
                    return {"ok": False, "code": "not_ready", "params": {}}
                return {"ok": True, **self._session.reset(str(serial), progress=self._progress)}
        return self._guard(run)

    def restore(self, backup_id, serial):
        log.info("Restore requested: %s", backup_id)

        def run():
            with self._lock:
                if not self._session or not self._session.printer:
                    return {"ok": False, "code": "not_ready", "params": {}}
                return {"ok": True, **self._session.restore(str(backup_id), str(serial), progress=self._progress)}
        return self._guard(run)

    def open_url(self, url):
        url = str(url)
        if url.startswith(config.ALLOWED_URL_PREFIXES) or url == LICENSE_URL:
            webbrowser.open(url)
            return True
        log.warning("Refused to open %s", url)
        return False

    def open_model_request(self, name, firmware):
        title = f"Model support request: {name}"[:120]
        body = (
            f"Model (SNMP): {name}\nFirmware: {firmware}\n"
            f"App version: {config.VERSION}\n\n"
            "(Please do not post your serial number.)"
        )
        query = urllib.parse.urlencode({"title": title, "body": body, "labels": "model-request"})
        webbrowser.open(f"{config.REPO_URL}/issues/new?{query}")
        return True

    def open_data_dir(self):
        os.startfile(store.data_dir())  # noqa: S606 - Windows only, our own folder
        return True


def setup_logging():
    handler = logging.handlers.RotatingFileHandler(
        store.log_dir() / "padreset.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # pysnmp's sync adapter leaves timeout tasks behind when a dispatcher is
    # dropped; asyncio reports them as errors although nothing is wrong.
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    if not getattr(sys, "frozen", False):
        root.addHandler(logging.StreamHandler())


def main():
    setup_logging()
    log.info("PadReset %s starting", config.VERSION)
    api = Api()
    lang = api.bootstrap()["lang"]
    width, height = fit_to_work_area(*WINDOW_SIZE)
    window = webview.create_window(
        config.APP_NAME[lang],
        url=str(UI_DIR / "index.html"),
        js_api=api,
        width=width,
        height=height,
        min_size=(min(720, width), min(500, height)),
        background_color="#EEF0EC",
        text_select=True,
    )
    api._window = window
    webview.start(debug="--debug" in sys.argv)
