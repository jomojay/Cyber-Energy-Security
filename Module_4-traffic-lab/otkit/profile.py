"""
Site profile loading. A profile describes what 'normal' looks like at a
site: asset names, which hosts may write to PLCs, detection thresholds.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LAB_ROOT = os.path.dirname(HERE)
DEFAULT_PROFILE = os.path.join(LAB_ROOT, "profiles", "palanca.json")

DEFAULT_THRESHOLDS = {
    "scan_distinct_ports": 5,
    "scan_window_seconds": 60,
    "enum_distinct_addresses": 8,
    "upload_bytes": 10000,
    "exfil_bytes": 50000,
}


class Profile:
    def __init__(self, data, path=None):
        self.path = path
        self.data = data
        self.site = data.get("site", "Unnamed site")
        self.assets = data.get("assets", [])
        self.by_ip = {a["ip"]: a for a in self.assets}
        self.gateways = set(data.get("gateways", []))
        self.plcs = set(data.get("plcs", []))
        mb = data.get("modbus", {})
        self.approved_masters = set(mb.get("approved_masters", []))
        self.approved_writers = set(mb.get("approved_writers", []))
        self.highest_normal_register = int(mb.get("highest_normal_register", 65535))
        self.approved_programmers = set(data.get("approved_programmers", []))
        self.programming_ports = set(data.get("programming_ports", [102]))
        self.thresholds = dict(DEFAULT_THRESHOLDS, **data.get("thresholds", {}))
        self.window_minutes = float(data.get("window_minutes", 5))

    def name(self, ip):
        """'PLC-MAIN-01' for a known IP, else the IP itself."""
        a = self.by_ip.get(ip)
        return a["name"] if a else ip

    def label(self, ip):
        """'PLC-MAIN-01 (192.168.1.10)' for a known IP, 'UNKNOWN (1.2.3.4)' otherwise."""
        if not isinstance(ip, str) or not ip:
            return "-"
        a = self.by_ip.get(ip)
        if a:
            return f"{a['name']} ({ip})"
        first = ip.split(".", 1)[0]
        if ip.endswith(".255"):
            return f"BROADCAST ({ip})"
        if first.isdigit() and 224 <= int(first) <= 239:
            return f"MULTICAST ({ip})"
        return f"UNKNOWN ({ip})"

    def zone(self, ip):
        a = self.by_ip.get(ip)
        if a:
            return a.get("zone", "?")
        return "Unknown"

    def ip_of(self, name):
        for a in self.assets:
            if a["name"] == name:
                return a["ip"]
        raise KeyError(name)

    def mac_of(self, ip):
        """Deterministic lab MAC for a host (locally administered 02:50:4c = 'PL')."""
        o = [int(x) for x in ip.split(".")]
        return f"02:50:4c:00:{o[2]:02x}:{o[3]:02x}"


def load_profile(path=None):
    path = path or os.environ.get("OTLAB_PROFILE") or DEFAULT_PROFILE
    with open(path) as f:
        return Profile(json.load(f), path)
