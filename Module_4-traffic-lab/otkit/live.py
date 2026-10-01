"""
Days 1-2: helpers for the LIVE Module 2 (or Module 3) Docker lab.

  otlab live status               is the lab running? which interfaces to capture on?
  otlab live activity             start operator/engineer traffic (OPC UA, Modbus writes, HTTP)
  otlab live capture --minutes 15 record a capture into captures/live/
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import time

from .profile import LAB_ROOT

EXPECTED = ["plc-main-01", "traffic-gen", "scada-hmi-01", "eng-ws-01"]
SUBNETS = {"192.168.1.0/24": "control (L1)", "192.168.2.0/24": "supervisory (L2)", "192.168.3.0/24": "DMZ (L3)"}
ACTIVITY_SCRIPT = os.path.join(LAB_ROOT, "live", "palanca_activity.py")


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def docker_ok():
    if not shutil.which("docker"):
        return False, "Docker is not installed."
    r = _run(["docker", "ps", "--format", "{{.Names}}"])
    if r.returncode:
        return False, r.stderr.strip() or "docker ps failed (are you in the 'docker' group?)"
    return True, r.stdout.split()


def lab_networks():
    """Find the lab's Docker bridge interfaces by subnet (works for Module 2 and Module 3 stacks)."""
    r = _run(["docker", "network", "ls", "-q"])
    if r.returncode:
        return []
    ids = r.stdout.split()
    if not ids:
        return []
    r = _run(["docker", "network", "inspect"] + ids)
    out = []
    for n in json.loads(r.stdout or "[]"):
        for cfg in (n.get("IPAM") or {}).get("Config") or []:
            sn = cfg.get("Subnet")
            if sn in SUBNETS:
                iface = (n.get("Options") or {}).get("com.docker.network.bridge.name") or "br-" + n["Id"][:12]
                out.append({"name": n["Name"], "subnet": sn, "zone": SUBNETS[sn], "iface": iface})
    return sorted(out, key=lambda x: x["subnet"])


def status():
    ok, info = docker_ok()
    if not ok:
        return {"ok": False, "error": info}
    running = set(info)
    nets = lab_networks()
    return {"ok": all(c in running for c in EXPECTED), "running": sorted(running),
            "missing": [c for c in EXPECTED if c not in running], "networks": nets}


def start_activity(minutes, follow=False):
    r = _run(["docker", "cp", ACTIVITY_SCRIPT, "eng-ws-01:/root/palanca_activity.py"])
    if r.returncode:
        raise SystemExit(f"Could not copy the activity script into eng-ws-01: {r.stderr.strip()}\n"
                         f"  Is the Module 2 lab running?  ->  ./otlab live status")
    _run(["docker", "exec", "eng-ws-01", "pkill", "-f", "palanca_activity.py"])
    if follow:
        return subprocess.call(["docker", "exec", "-it", "eng-ws-01", "python3", "/root/palanca_activity.py",
                                "--minutes", str(minutes)])
    r = _run(["docker", "exec", "-d", "eng-ws-01", "sh", "-c",
              f"python3 /root/palanca_activity.py --minutes {minutes} > /root/palanca_activity.log 2>&1"])
    if r.returncode:
        raise SystemExit(r.stderr)
    return 0


def activity_log(lines=40):
    r = _run(["docker", "exec", "eng-ws-01", "tail", "-n", str(lines), "/root/palanca_activity.log"])
    return r.stdout if r.returncode == 0 else r.stderr


def capture(minutes, output=None, where="auto", zones=("control (L1)", "supervisory (L2)")):
    os.makedirs(os.path.join(LAB_ROOT, "captures", "live"), exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    output = output or os.path.join(LAB_ROOT, "captures", "live", f"palanca_live_{stamp}.pcapng")
    secs = int(minutes * 60)
    nets = [n for n in lab_networks() if n["zone"] in zones]
    ok, running = docker_ok()
    if not nets and not (ok and "eng-ws-01" in running):
        raise SystemExit("The live lab is not running, so there is nothing to capture.\n"
                         "  Start it:  cd ../Module_2_Lab_Setup && ./setup.sh      then check:  ./otlab live status")

    if where in ("auto", "host") and nets and shutil.which("dumpcap"):
        cmd = ["dumpcap", "-q"]
        for n in nets:
            cmd += ["-i", n["iface"]]
        cmd += ["-a", f"duration:{secs}", "-w", output]
        print(f"  Capturing on {', '.join(n['iface'] + ' [' + n['zone'] + ']' for n in nets)} for {minutes:g} min ...")
        print("  (Press Ctrl+C to stop early - the file is kept.)")
        p = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
        try:
            _countdown(p, secs)
        except KeyboardInterrupt:
            p.terminate()
            p.wait()
        err = p.stderr.read() if p.stderr else ""
        if p.returncode in (0, None, -15) and os.path.exists(output) and os.path.getsize(output) > 0:
            return output
        if where == "host":
            raise SystemExit(f"dumpcap failed: {err.strip()}\n  Fix: sudo usermod -aG wireshark $USER, then log out and back in.")
        print(f"  Host capture not possible ({err.strip()[:120]}); capturing inside eng-ws-01 instead.")

    # Fallback: capture inside the engineering workstation container
    print(f"  Capturing inside eng-ws-01 (tshark -i any) for {minutes:g} min ...")
    p = subprocess.Popen(["docker", "exec", "eng-ws-01", "tshark", "-q", "-i", "any", "-a", f"duration:{secs}",
                          "-w", "/tmp/otlab_live.pcapng"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        _countdown(p, secs)
    except KeyboardInterrupt:
        _run(["docker", "exec", "eng-ws-01", "pkill", "-INT", "tshark"])
        p.wait()
    r = _run(["docker", "cp", "eng-ws-01:/tmp/otlab_live.pcapng", output])
    if r.returncode:
        raise SystemExit(f"Capture failed: {r.stderr.strip()}")
    print("  Note: a capture from inside eng-ws-01 only shows eng-ws-01's own traffic,\n"
          "        not traffic-gen's polling. The host capture (wireshark group) sees everything.")
    return output


def _countdown(p, secs):
    start = time.time()
    while p.poll() is None:
        left = max(0, secs - int(time.time() - start))
        print(f"\r  {left // 60:02d}:{left % 60:02d} remaining ", end="", flush=True)
        time.sleep(1)
    print("\r  capture finished.          ")
