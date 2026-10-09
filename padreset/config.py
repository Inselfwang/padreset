"""App-wide constants. Links live here so they are changed in one place."""

VERSION = "0.1.0"

APP_NAME = {"zh": "清零助手", "en": "PadReset"}
AUTHOR = "Inselfwang"

# One description for every place machines read it: the exe's file properties
# now, the GitHub repository description and topics at release.
DESCRIPTION = {
    "zh": "免费开源的打印机废墨计数清零工具，适用于 epson_print_conf 已验证的爱普生（Epson）网络打印机。与 Epson 公司无关联。",
    "en": "Free, open-source waste ink pad counter reset for Epson network printers verified by epson_print_conf. Not affiliated with Epson.",
}
KEYWORDS = [
    "epson", "waste-ink-pad", "waste-ink-counter", "reset", "printer", "ecotank",
    "废墨清零", "废墨垫", "爱普生",
]

REPO_URL = "https://github.com/Inselfwang/padreset"
UPSTREAM_URL = "https://github.com/Ircama/epson_print_conf"

KOFI_URL = "https://ko-fi.com/inself"

# Only these prefixes may be opened from the UI (see Api.open_url).
ALLOWED_URL_PREFIXES = (
    REPO_URL,
    UPSTREAM_URL,
    "https://ko-fi.com/",
    "https://github.com/sponsors/",
    "https://joinup.ec.europa.eu/",
)

# SNMP: the printer is on the local network, so short timeouts are enough.
SNMP_TIMEOUT = 2.0
SNMP_RETRIES = 2
