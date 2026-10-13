#!/usr/bin/env python3
"""
OTSafeScanner — starter code for Module 5, Lab Day 3.

This is the skeleton described in Module 5, Section 5.3.1: an
OT-safe Nmap wrapper with hard-coded safety limits (rate limiting,
SIS exclusion) that an analyst cannot accidentally bypass via a
command-line typo. Trainees extend this class on Days 3-4 to add
CVE correlation (Section 5.3.2) and reporting (Section 5.6).

Requires: python-nmap (pip install python-nmap) and nmap installed
on the host. Run against the Module 2 Palanca lab environment.

IMPORTANT: EXCLUDED_IPS below must be updated to match whichever
lab environment you're running against — the addresses shown are
placeholders matching Module 5's own text. Cross-check against your
actual Module 2 asset inventory before running any scan.
"""
import nmap
import json
from datetime import datetime


class OTSafeScanner:
    """OT-safe vulnerability scanner with built-in protections."""

    # Maximum rate (packets per second) — NEVER exceed this
    MAX_RATE = 10

    # OT-safe ports only (no full port scan allowed)
    OT_PORTS = "22,80,102,443,502,4840,20000,44818,47808"

    # Devices that must NEVER be scanned (SIS / safety-critical — update
    # to match your actual lab's asset inventory before running)
    EXCLUDED_IPS = ["192.168.1.50", "192.168.1.51"]

    def __init__(self, scan_id=None):
        self.nm = nmap.PortScanner()
        self.scan_id = scan_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results = []

    def validate_targets(self, targets):
        """Ensure no excluded devices are in the target list."""
        for target in targets:
            if target in self.EXCLUDED_IPS:
                raise ValueError(
                    f"SAFETY VIOLATION: {target} is an excluded/SIS device. "
                    f"Scanning this device is PROHIBITED."
                )

    def _exclude_arg(self):
        """nmap-level exclusion, so excluded devices are never probed even
        when a target is given as a range/CIDR that validate_targets()'s
        exact-match check can't see inside (e.g. 192.168.1.0/24)."""
        return f" --exclude {','.join(self.EXCLUDED_IPS)}" if self.EXCLUDED_IPS else ""

    def host_discovery(self, subnet):
        """Phase 1: ping sweep to identify live hosts."""
        print(f"[{self.scan_id}] Starting host discovery: {subnet}")
        self.nm.scan(hosts=subnet, arguments=f"-sn -T2 --max-rate {self.MAX_RATE}" + self._exclude_arg())

        live_hosts = []
        for host in self.nm.all_hosts():
            if host not in self.EXCLUDED_IPS:
                live_hosts.append(host)
                print(f"  [ALIVE] {host}")
            else:
                print(f"  [SKIPPED - EXCLUDED] {host}")
        return live_hosts

    def port_scan(self, hosts):
        """Phase 2: TCP Connect scan on OT-safe ports only."""
        self.validate_targets(hosts)
        target_str = " ".join(hosts)
        print(f"[{self.scan_id}] Port scanning {len(hosts)} hosts")

        self.nm.scan(
            hosts=target_str,
            ports=self.OT_PORTS,
            arguments=f"-sT -T2 --max-rate {self.MAX_RATE} --max-retries 1" + self._exclude_arg(),
        )

        for host in self.nm.all_hosts():
            for proto in self.nm[host].all_protocols():
                for port in self.nm[host][proto]:
                    state = self.nm[host][proto][port]["state"]
                    self.results.append({
                        "host": host,
                        "port": port,
                        "protocol": proto,
                        "state": state,
                        "service": self.nm[host][proto][port].get("name", ""),
                    })
        return self.results

    def nse_scan(self, hosts, script, port):
        """Phase 3: run a specific NSE script (e.g. modbus-discover, s7-info)."""
        self.validate_targets(hosts)
        target_str = " ".join(hosts)
        print(f"[{self.scan_id}] Running NSE script '{script}' on port {port}")
        self.nm.scan(
            hosts=target_str,
            ports=str(port),
            arguments=f"-sT -T1 --max-rate 5 --script {script}" + self._exclude_arg(),
        )
        nse_results = {}
        for host in self.nm.all_hosts():
            if "tcp" in self.nm[host] and port in self.nm[host]["tcp"]:
                nse_results[host] = self.nm[host]["tcp"][port].get("script", {})
        return nse_results

    def save_results(self, path=None):
        path = path or f"scan_results_{self.scan_id}.json"
        with open(path, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"Results saved to {path}")
        return path


if __name__ == "__main__":
    # Example run against the Module 2 Palanca lab environment.
    # Update the subnet/IPs to match your actual lab deployment.
    scanner = OTSafeScanner()
    hosts = scanner.host_discovery("192.168.1.0/24")
    if hosts:
        scanner.port_scan(hosts)
        scanner.save_results()
    else:
        print("No hosts discovered — confirm the lab environment is running.")
