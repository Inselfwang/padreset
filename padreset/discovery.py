"""Find Epson printers on the local network.

Same approach as upstream find_printers.py (TCP probe of the printer ports
on the local /24, then an SNMP query for the model), with a thread pool
and short timeouts so a scan takes a few seconds.
"""

import ipaddress
import logging
import socket
from concurrent.futures import ThreadPoolExecutor

from . import config
from .upstream import epc

log = logging.getLogger(__name__)

PRINTER_PORTS = (9100, 515, 631)
TCP_TIMEOUT = 0.6
# A printer in Wi-Fi power save can take a second or more to answer the first
# packet; the quick pass wakes it, the slow pass then catches it.
TCP_TIMEOUT_SLOW = 2.5


def local_ipv4s() -> list:
    """Active local IPv4 addresses, primary route first."""
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 1))  # no packet is sent for UDP connect
            ips.append(sock.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return [
        ip for ip in ips
        if not ip.startswith(("127.", "169.254.")) and ipaddress.ip_address(ip).is_private
    ]


def _port_open(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe(ips, timeout) -> list:
    """The addresses among ips with a printer port open (all pairs in parallel)."""
    pairs = [(ip, port) for ip in ips for port in PRINTER_PORTS]
    if not pairs:
        return []
    with ThreadPoolExecutor(max_workers=256) as pool:
        results = pool.map(lambda pair: _port_open(*pair, timeout), pairs)
        open_ips = {ip for (ip, _), ok in zip(pairs, results) if ok}
    return [ip for ip in ips if ip in open_ips]


def _identify(ips) -> list:
    found = []
    for ip in ips:  # SNMP one at a time: the sync adapter is not thread-safe
        name = snmp_model(ip)
        if name:
            found.append({"ip": ip, "name": name})
    return found


def snmp_model(ip: str) -> str:
    """Model string the printer reports over SNMP, or "" if it does not answer."""
    printer = epc.EpsonPrinter(
        hostname=ip, timeout=config.SNMP_TIMEOUT, retries=1
    )
    try:
        name = printer.get_snmp_info("Model").get("Model", "")
        if "EPSON" in name.upper():
            return name.strip()
        # Some firmware report a generic hrDeviceDescr; the Epson MIB is definitive.
        epson_name = printer.get_snmp_info("Epson Printer Name").get("Epson Printer Name", "")
        if epson_name:
            return ("EPSON " + epson_name).strip()
    except Exception as exc:  # timeouts and malformed answers alike
        log.info("SNMP query to %s failed: %s", ip, exc)
    return ""


def scan(extra_ips=()) -> list:
    """Return [{"ip", "name"}] for every Epson printer found.

    ``extra_ips`` (the printer used last time) skip the TCP probe and are asked
    over SNMP directly, which retries and so tolerates a sleeping printer.
    """
    known = [ip for ip in dict.fromkeys(extra_ips) if ip]
    subnet = []
    for local in local_ipv4s():
        net = ipaddress.ip_network(f"{local}/24", strict=False)
        subnet += [str(h) for h in net.hosts() if str(h) != local and str(h) not in known]
    log.info("Scanning %d addresses (known: %s)", len(subnet), known)

    alive = _probe(subnet, TCP_TIMEOUT)
    log.info("Hosts with printer ports: %s", alive)
    found = _identify(known + alive)
    if not found:
        alive = _probe(known + subnet, TCP_TIMEOUT_SLOW)
        log.info("Slow pass, hosts with printer ports: %s", alive)
        found = _identify(alive)
    return found
