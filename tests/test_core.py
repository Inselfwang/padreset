"""Tests against a simulated printer; nothing here touches the network."""

import pytest

from padreset import core, store
from padreset.upstream import epc

SERIAL = "XYZW012345"
IDLE = {"status": (4, "Idle (ready to print)"), "serial_number_info": SERIAL}


class FakeEpson(epc.EpsonPrinter):
    """Upstream logic on top of an in-memory EEPROM."""

    def __init__(self, mem, status, model=None, fail_write_at=None, lie_write_at=None):
        super().__init__(model=model, hostname="fake")
        self.mem, self.status = mem, status
        self.fail_write_at, self.lie_write_at = fail_write_at, lie_write_at

    def read_eeprom(self, oid, label=""):
        if isinstance(oid, list):
            return [f"{self.mem.get(int(o), 0):02X}" for o in oid]
        return f"{self.mem.get(int(oid), 0):02X}"

    def write_eeprom(self, oid, value, label="", report=None):
        if oid == self.fail_write_at:
            return False
        if oid != self.lie_write_at:
            self.mem[oid] = value
        return True

    def get_printer_status(self):
        return self.status

    def get_firmware_version(self):
        return "TEST"


def et2500_mem(level_raw=0x12FA):
    mem = {192 + i: ord(c) for i, c in enumerate(SERIAL)}
    mem.update({24: level_raw & 0xFF, 25: (level_raw >> 8) & 0xFF, 30: (level_raw >> 16) & 0xFF,
                28: 0x11, 29: 0x22, 46: 0x50})
    return mem


@pytest.fixture
def printer(monkeypatch, tmp_path):
    """Patch the session to talk to a FakeEpson ET-2500; returns its config."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    fake = {"mem": et2500_mem(), "status": dict(IDLE), "name": "EPSON ET-2500 Series", "kw": {}}
    monkeypatch.setattr(core.discovery, "snmp_model", lambda ip: fake["name"])
    monkeypatch.setattr(
        core.Session, "_new_printer",
        lambda self, model=None: FakeEpson(fake["mem"], fake["status"], model=model, **fake["kw"]),
    )
    return fake


# ------------------------------------------------------------------ upstream


def test_reset_plan_matches_upstream_for_every_model():
    """The cells we back up must be exactly the cells upstream writes."""
    checked = 0
    for model in sorted(epc.EpsonPrinter().valid_printers):
        p = epc.EpsonPrinter(model=model, hostname="fake")
        written = []
        p.write_eeprom = lambda oid, value, label="", report=None: written.append((oid, value)) or True
        result = p.reset_waste_ink_levels()
        plan = core.reset_plan(p.parm)
        if result is None:
            assert plan == {}, model
            continue
        assert written == list(plan.items()), model
        checked += 1
    assert checked > 100


def test_match_model():
    valid = epc.EpsonPrinter().valid_printers
    assert core.match_model("EPSON ET-2500 Series", valid) == "ET-2500"
    assert core.match_model("EPSON XYZ-9999 Series", valid) is None
    assert core.match_model("", valid) is None


def test_mask_serial():
    assert core.mask_serial(SERIAL) == "XYZW0•••••"
    assert core.mask_serial(None) == ""


# -------------------------------------------------------------------- checks


def states(result):
    return {c["id"]: c["state"] for c in result["checks"]}


def test_inspect_supported(printer):
    r = core.Session("1.2.3.4").inspect()
    assert r["supported"] is True and r["reason"] is None
    assert r["model"] == "ET-2500" and r["serial"] == SERIAL
    assert states(r) == {"found": "ok", "model": "ok", "reading": "ok", "idle": "ok"}
    assert r["level"] == round(0x12FA / 62.07, 2)


def test_inspect_no_response(printer):
    printer["name"] = ""
    r = core.Session("1.2.3.4").inspect()
    assert not r["supported"] and r["reason"] == "no_response"


def test_inspect_unknown_model(printer):
    printer["name"] = "EPSON XYZ-9999 Series"
    r = core.Session("1.2.3.4").inspect()
    assert not r["supported"] and r["reason"] == "unknown_model"
    assert r["status"]["code"] == 4


def test_inspect_read_key_fails(printer):
    for i in range(10):
        printer["mem"][192 + i] = 0  # serial reads as NULs
    r = core.Session("1.2.3.4").inspect()
    assert not r["supported"] and r["reason"] == "read_key_failed"


def test_inspect_serial_mismatch(printer):
    printer["status"]["serial_number_info"] = "OTHER00001"
    r = core.Session("1.2.3.4").inspect()
    assert not r["supported"] and r["reason"] == "serial_mismatch"


def test_inspect_implausible_reading(printer):
    printer["mem"].update({24: 0xFF, 25: 0xFF, 30: 0xFF})
    r = core.Session("1.2.3.4").inspect()
    assert not r["supported"] and r["reason"] == "implausible"


def test_inspect_busy(printer):
    printer["status"]["status"] = (2, "Busy")
    r = core.Session("1.2.3.4").inspect()
    assert not r["supported"] and states(r)["idle"] == "fail"


def test_inspect_locked_by_waste_counter_is_allowed(printer):
    printer["mem"].update(et2500_mem(int(100.5 * 62.07)))
    printer["status"].update(status=(0, "Error"), errcode="Ink overflow error (Waste ink pad counter overflow)")
    r = core.Session("1.2.3.4").inspect()
    assert r["supported"] is True
    assert r["checks"][-1]["params"] == {"locked": True}


def test_inspect_unknown_status_is_a_warning(printer):
    printer["status"] = {}
    r = core.Session("1.2.3.4").inspect()
    assert r["supported"] is True and states(r)["idle"] == "warn"
    assert r["checks"][1]["params"]["serial_checked"] is False


# ------------------------------------------------------------ reset / restore


def test_reset_backs_up_writes_and_verifies(printer):
    original = dict(printer["mem"])
    s = core.Session("1.2.3.4")
    s.inspect()
    stages = []
    res = s.reset(SERIAL, progress=stages.append)
    assert stages == [0, 1, 2]
    assert res["after"] == 0.0 and res["before"] > 70
    plan = epc.EpsonPrinter(model="ET-2500").parm["raw_waste_reset"]
    assert all(printer["mem"][a] == v for a, v in plan.items())
    assert [(c["addr"], c["before"], c["written"], c["after"]) for c in res["cells"]] == [
        (a, original[a], v, v) for a, v in plan.items()]
    backup = store.load_backup(res["backup_id"])
    assert backup["serial"] == SERIAL and backup["model"] == "ET-2500"
    assert backup["cells"] == {str(a): original[a] for a in plan}

    stages = []
    out = s.restore(res["backup_id"], SERIAL, progress=stages.append)
    assert stages == [0, 1, 2]
    assert printer["mem"] == original
    assert [(c["addr"], c["before"], c["written"], c["after"]) for c in out["cells"]] == [
        (a, v, original[a], original[a]) for a, v in plan.items()]
    assert out["after"] == res["before"]
    assert s.backups()[0]["id"] == res["backup_id"]


def test_reset_refuses_a_different_printer(printer):
    s = core.Session("1.2.3.4")
    s.inspect()
    before = dict(printer["mem"])
    with pytest.raises(core.OperationError) as e:
        s.reset("ZZZZ000000")
    assert e.value.code == "different_printer"
    assert printer["mem"] == before


def test_reset_refuses_when_printer_became_busy(printer):
    s = core.Session("1.2.3.4")
    s.inspect()
    printer["status"]["status"] = (2, "Busy")
    before = dict(printer["mem"])
    with pytest.raises(core.OperationError) as e:
        s.reset(SERIAL)
    assert e.value.code == "recheck_failed"
    assert printer["mem"] == before


def test_reset_write_failure_keeps_backup(printer):
    printer["kw"] = {"fail_write_at": 30}
    s = core.Session("1.2.3.4")
    s.inspect()
    with pytest.raises(core.OperationError) as e:
        s.reset(SERIAL)
    assert e.value.code == "write_failed" and e.value.params["addr"] == 30
    assert store.load_backup(e.value.params["backup_id"])["serial"] == SERIAL


def test_reset_detects_silently_ignored_write(printer):
    printer["kw"] = {"lie_write_at": 24}
    s = core.Session("1.2.3.4")
    s.inspect()
    with pytest.raises(core.OperationError) as e:
        s.reset(SERIAL)
    assert e.value.code == "verify_failed"


def test_restore_rejects_foreign_or_tampered_backup(printer):
    s = core.Session("1.2.3.4")
    s.inspect()
    bad = store.save_backup({"serial": SERIAL, "model": "ET-2500", "cells": {"500": 1}})
    with pytest.raises(core.OperationError) as e:
        s.restore(bad, SERIAL)
    assert e.value.code == "backup_mismatch"
    other = store.save_backup({"serial": "OTHER00001", "model": "ET-2500", "cells": {"24": 1}})
    with pytest.raises(core.OperationError):
        s.restore(other, SERIAL)
