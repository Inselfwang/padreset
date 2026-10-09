"""Discovery logic with the network replaced by fakes."""

from padreset import discovery


def fake_net(monkeypatch, open_at=None, snmp=None, sleepy=()):
    """open_at: {ip: True}; sleepy ips only answer the slow TCP pass."""
    open_at, snmp = open_at or {}, snmp or {}
    calls = []
    monkeypatch.setattr(discovery, "local_ipv4s", lambda: ["10.0.0.5"])

    def port_open(ip, port, timeout):
        calls.append((ip, timeout))
        if ip in sleepy:
            return timeout >= discovery.TCP_TIMEOUT_SLOW
        return open_at.get(ip, False)

    monkeypatch.setattr(discovery, "_port_open", port_open)
    monkeypatch.setattr(discovery, "snmp_model", lambda ip: snmp.get(ip, ""))
    return calls


def test_finds_printer_in_subnet(monkeypatch):
    fake_net(monkeypatch, open_at={"10.0.0.9": True, "10.0.0.20": True},
             snmp={"10.0.0.9": "EPSON ET-2500 Series"})  # .20 is not an Epson
    assert discovery.scan() == [{"ip": "10.0.0.9", "name": "EPSON ET-2500 Series"}]


def test_known_ip_skips_tcp_probe(monkeypatch):
    calls = fake_net(monkeypatch, snmp={"10.0.0.9": "EPSON ET-2500 Series"})
    assert discovery.scan(["10.0.0.9"]) == [{"ip": "10.0.0.9", "name": "EPSON ET-2500 Series"}]
    assert not any(ip == "10.0.0.9" for ip, _ in calls)


def test_sleeping_printer_found_on_slow_pass(monkeypatch):
    calls = fake_net(monkeypatch, sleepy={"10.0.0.9"}, snmp={"10.0.0.9": "EPSON ET-2500 Series"})
    assert discovery.scan() == [{"ip": "10.0.0.9", "name": "EPSON ET-2500 Series"}]
    assert {t for _, t in calls} == {discovery.TCP_TIMEOUT, discovery.TCP_TIMEOUT_SLOW}


def test_nothing_found(monkeypatch):
    fake_net(monkeypatch)
    assert discovery.scan(["10.0.0.9"]) == []
