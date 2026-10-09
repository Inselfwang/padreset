"""Checks, backup, reset and undo for one printer, on top of epson_print_conf.

Nothing here guesses parameters. A printer can be reset only when
  * its SNMP model string maps to an upstream configuration that has a read
    key, a write key, a waste counter and a reset recipe, and
  * the read key works on this very unit: the serial number read from the
    EEPROM with that key equals the serial the printer reports in its own
    status block, and
  * the waste reading is plausible and the printer is idle.
The same checks run again right before every write.
"""

import logging
import re
import time

from . import config, discovery, store
from .upstream import epc

log = logging.getLogger(__name__)

SERIAL_RE = re.compile(r"[A-Z0-9]{6,20}")
LEVEL_MAX_PLAUSIBLE = 130.0
IDLE_CODES = (3, 4)  # "Waiting", "Idle (ready to print)"
LOCK_ERRORS = ("Ink overflow", "Maintenance request")


class OperationError(Exception):
    """A reset or restore stopped; ``code`` is shown to the user via i18n."""

    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def match_model(name, valid):
    """First model derived from the SNMP name that upstream knows, else None."""
    for cand in epc.get_printer_models(name or ""):
        if cand in valid:
            return cand
    return None


def reset_plan(parm):
    """{address: value} written by EpsonPrinter.reset_waste_ink_levels().

    Mirrors upstream so that exactly these cells are backed up first;
    tests/test_core.py checks the two agree for every model.
    """
    if not parm:
        return {}
    if "raw_waste_reset" in parm:
        return {int(k): int(v) for k, v in parm["raw_waste_reset"].items()}
    plan = {}
    if "main_waste" in parm:
        for oid in parm["main_waste"]["oids"]:
            plan[int(oid)] = 0
        for oid in parm.get("borderless_waste", {}).get("oids", []):
            plan[int(oid)] = 0
    return plan


def mask_serial(serial):
    if not serial:
        return ""
    return serial[:5] + "•" * max(0, len(serial) - 5)


def overall_level(levels):
    """The counter closest to full is the one that locks the printer."""
    return max(levels.values()) if levels else None


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # timeouts, malformed answers
        log.warning("%s failed: %s", getattr(fn, "__name__", fn), exc)
        return None


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _cell_report(before, written, after):
    """Per address: value before, value written, value read back afterwards."""
    return [
        {"addr": a, "before": before.get(a), "written": v, "after": after.get(a)}
        for a, v in written.items()
    ]


class Session:
    """One printer, from inspection to reset or restore.

    Not thread-safe; the API layer serialises calls.
    """

    def __init__(self, ip):
        self.ip = ip
        self.name = None
        self.model = None
        self.printer = None
        self.serial = None
        self.firmware = None
        self.plan = {}
        self.levels = None

    def _new_printer(self, model=None):
        return epc.EpsonPrinter(
            model=model,
            hostname=self.ip,
            timeout=config.SNMP_TIMEOUT,
            retries=config.SNMP_RETRIES,
        )

    # ---------------------------------------------------------------- checks

    def inspect(self):
        """Read-only. Run every check and return what the UI shows."""
        checks = []
        out = {
            "ip": self.ip, "name": None, "model": None,
            "supported": False, "reason": None, "checks": checks,
            "levels": None, "level": None, "serial": None,
            "serial_masked": None, "firmware": None, "status": None,
            "backups": [],
        }
        self.printer = None

        name = discovery.snmp_model(self.ip)
        if not name:
            out["reason"] = "no_response"
            checks.append({"id": "found", "state": "fail", "params": {"ip": self.ip}})
            return out
        self.name = out["name"] = name
        checks.append({"id": "found", "state": "ok", "params": {"ip": self.ip}})

        base = self._new_printer()
        model = match_model(name, base.valid_printers)
        if not model:
            out["reason"] = "unknown_model"
            checks.append({"id": "model", "state": "fail", "params": {"name": name, "why": "unknown"}})
            out["status"] = self._status_summary(_safe(base.get_printer_status))
            return out

        printer = self._new_printer(model)
        parm = printer.parm
        plan = reset_plan(parm)
        out["model"] = model
        if not plan or "write_key" not in parm or "main_waste" not in parm:
            out["reason"] = "no_reset_params"
            checks.append({"id": "model", "state": "fail", "params": {"model": model, "why": "no_params"}})
            out["status"] = self._status_summary(_safe(printer.get_printer_status))
            return out

        status = _safe(printer.get_printer_status) or {}
        out["status"] = self._status_summary(status)
        serial = _safe(printer.get_serial_number)
        status_serial = status.get("serial_number_info")
        out["firmware"] = _safe(printer.get_firmware_version)

        if not isinstance(serial, str) or not SERIAL_RE.fullmatch(serial):
            out["reason"] = "read_key_failed"
            checks.append({"id": "model", "state": "fail", "params": {"model": model, "why": "read_key"}})
            return out
        if status_serial and status_serial != serial:
            out["reason"] = "serial_mismatch"
            checks.append({"id": "model", "state": "fail", "params": {"model": model, "why": "serial_mismatch"}})
            return out
        out["serial"] = serial
        out["serial_masked"] = mask_serial(serial)
        checks.append({
            "id": "model", "state": "ok",
            "params": {"model": model, "serial_checked": bool(status_serial)},
        })

        levels = _safe(printer.get_waste_ink_levels)
        level = overall_level(levels)
        if level is None:
            out["reason"] = "read_failed"
            checks.append({"id": "reading", "state": "fail", "params": {"why": "no_data"}})
        elif level < 0 or level > LEVEL_MAX_PLAUSIBLE:
            out["reason"] = "implausible"
            checks.append({"id": "reading", "state": "fail", "params": {"level": level, "why": "range"}})
        else:
            locked = any(e in (status.get("errcode") or "") for e in LOCK_ERRORS)
            if locked and level < 90:
                checks.append({"id": "reading", "state": "warn", "params": {"level": level, "why": "lock_low"}})
            else:
                checks.append({"id": "reading", "state": "ok", "params": {"level": level}})
        out["levels"], out["level"] = levels, level

        checks.append(self._idle_check(status))

        out["supported"] = not any(c["state"] == "fail" for c in checks)
        if out["supported"]:
            out["reason"] = None
        self.model, self.printer, self.serial = model, printer, serial
        self.firmware, self.plan, self.levels = out["firmware"], plan, levels
        out["backups"] = self.backups()
        return out

    @staticmethod
    def _status_summary(status):
        if not status:
            return None
        code, text = status.get("status") or (None, None)
        return {"code": code, "text": text, "errcode": status.get("errcode")}

    @staticmethod
    def _idle_check(status):
        if not status or "status" not in status:
            return {"id": "idle", "state": "warn", "params": {"why": "unknown"}}
        code, text = status["status"]
        errcode = status.get("errcode") or ""
        if code in IDLE_CODES:
            return {"id": "idle", "state": "ok", "params": {}}
        if code == 0 and any(e in errcode for e in LOCK_ERRORS):
            return {"id": "idle", "state": "ok", "params": {"locked": True}}
        return {"id": "idle", "state": "fail", "params": {"text": text, "errcode": errcode}}

    def backups(self):
        if not self.serial:
            return []
        return [
            {"id": b["id"], "created": b.get("created"), "level": overall_level(b.get("levels"))}
            for b in store.list_backups(self.serial)
        ]

    def _recheck(self, expected_serial):
        """Run every check again; refuse to write unless all still pass."""
        fresh = self.inspect()
        if fresh.get("serial") and fresh["serial"] != expected_serial:
            raise OperationError("different_printer")
        if not fresh["supported"]:
            raise OperationError("recheck_failed", checks=fresh["checks"])
        return fresh

    # ----------------------------------------------------------------- write

    def _write_cells(self, cells, label):
        """Write {address: value}; each write is read back by upstream."""
        for addr, value in cells.items():
            try:
                ok = self.printer.write_eeprom(addr, value, label=label)
            except Exception as exc:
                log.error("write %s=%s raised %s", addr, value, exc)
                ok = False
            if not ok:
                raise OperationError("write_failed", addr=addr)

    def _read_cells(self, addrs, label):
        values = _safe(self.printer.read_eeprom_many, list(addrs), label=label)
        if not values or values == [None]:
            return None
        return {a: int(v, 16) for a, v in zip(addrs, values)}

    def reset(self, expected_serial, progress=lambda stage: None):
        """Back up, write the reset values, read back. Returns a result dict."""
        progress(0)
        fresh = self._recheck(expected_serial)
        addrs = list(self.plan)
        before = self._read_cells(addrs, "padreset_backup")
        if before is None:
            raise OperationError("backup_read_failed")
        backup_id = store.save_backup({
            "created": _now(),
            "app_version": config.VERSION,
            "ip": self.ip, "name": self.name, "model": self.model,
            "serial": self.serial, "firmware": self.firmware,
            "levels": fresh["levels"],
            "cells": {str(a): v for a, v in before.items()},
        })
        log.info("Backup %s: %s", backup_id, before)

        progress(1)
        try:
            self._write_cells(self.plan, "padreset_reset")
        except OperationError as exc:
            exc.params["backup_id"] = backup_id
            raise

        progress(2)
        after = self._read_cells(addrs, "padreset_verify")
        if after is None or any(after[a] != v for a, v in self.plan.items()):
            raise OperationError("verify_failed", backup_id=backup_id)
        levels = _safe(self.printer.get_waste_ink_levels)
        log.info("Reset done: wrote %s, read back %s, levels now %s", self.plan, after, levels)
        return {
            "backup_id": backup_id,
            "before": overall_level(fresh["levels"]),
            "after": overall_level(levels),
            "levels": levels,
            "cells": _cell_report(before, self.plan, after),
        }

    def restore(self, backup_id, expected_serial, progress=lambda stage: None):
        """Write the cells of a backup back to the same printer."""
        progress(0)
        rec = store.load_backup(backup_id)
        if rec.get("serial") != expected_serial or rec.get("model") != self.model:
            raise OperationError("backup_mismatch")
        cells = {int(a): int(v) for a, v in rec["cells"].items()}
        if not set(cells) <= set(self.plan) or not all(0 <= v <= 255 for v in cells.values()):
            raise OperationError("backup_mismatch")
        self._recheck(expected_serial)
        current = self._read_cells(list(cells), "padreset_current")
        if current is None:
            raise OperationError("backup_read_failed")
        progress(1)
        self._write_cells(cells, "padreset_restore")
        progress(2)
        after = self._read_cells(list(cells), "padreset_verify")
        if after is None or after != cells:
            raise OperationError("verify_failed", backup_id=backup_id)
        levels = _safe(self.printer.get_waste_ink_levels)
        log.info("Restored %s: was %s, wrote %s, read back %s, levels now %s",
                 backup_id, current, cells, after, levels)
        return {
            "backup_id": backup_id,
            "after": overall_level(levels),
            "levels": levels,
            "cells": _cell_report(current, cells, after),
        }
