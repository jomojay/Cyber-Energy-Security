# Module 3 — Firewall Extension (Day 4)

This is not a new lab environment. It extends Module 2 lab built — Docker `palanca-lab` three additional network segments
and replaces the simplified 3-rule Module 2 ruleset with the full,
11-rule + default-deny Palanca FW-OT-01 ruleset (`firewall-rules-module3.csv`).

This repo contains a complete, working **Docker** build of that
extension (everything alongside this README — `docker-compose.yml`,
`setup.sh`, etc.). If your cohort used the Option C VirtualBox/pfSense
build instead, see that section below; there's no runnable pfSense
config here, just the steps.

## New segments

| VLAN/Zone | Subnet | Notes |
|---|---|---|
| 40 — Management | 192.168.40.0/24 | Switch/firewall management plane |
| 99 — Quarantine | 192.168.99.0/24 | New/untrusted devices pending verification |
| — Enterprise | 192.168.50.0/24 | Added in this Docker build only — see "What's different" below |

## Quick start (Docker build)

```bash
./setup.sh                       # builds, starts, wires cross-zone routing
./teardown.sh                    # stops and removes the lab when done
```

`setup.sh` brings the lab up with `fw-ot-01` **wide open** (no rules) —
that's intentional. This is a hands-on exercise: the infrastructure
(zones, routing, a firewall container sitting between all six of them) is
pre-built and working; implementing the Palanca FW-OT-01 ruleset
(R01-R12 + R99) on top of it is the trainee's job. Hand trainees
`LAB_GUIDE.md` from there.

## Quick start (trainee exercise)

```bash
docker exec -it fw-ot-01 bash    # configure the firewall from in here
./scripts/test_firewall_rules.sh # from the host, anytime — checks progress, saves results to logs/
```

## What's different from the Module 2 Docker lab, and why

Module 2's Docker lab (`Module_2_Lab_Setup/`) has no firewall at all, and
two of its rules can't be expressed in its topology as-is. Three changes
were necessary to make "implement the ruleset and test each rule"
actually achievable here — not just two new networks:

1. **A real firewall, `fw-ot-01`.** Docker doesn't route between separate
   bridge networks by itself — Module 2 only ever crossed zones via
   containers that were directly attached to both. `fw-ot-01` is attached
   to all six zone networks and does real Linux IP forwarding between
   them, and every other container reaches a foreign zone only by a route
   pointing at `fw-ot-01` (see `setup.sh`, step 4) — so its FORWARD chain
   is the only place inter-zone traffic can be filtered. `firewall/
   entrypoint.sh` boots it wide open (FORWARD policy ACCEPT, no rules);
   trainees implement R01-R12 + R99 on that chain themselves, per
   `LAB_GUIDE.md`. `instructor-only/solution_apply_rules.sh` is a
   reference/grading copy of the finished ruleset — **not** run
   automatically by anything, and that whole folder should be stripped
   before handing the repo to a cohort.

   Note on the switch: a real network would do VLAN segmentation on a
   switch and inter-VLAN filtering on a router/firewall with one
   interface per VLAN — that's exactly this topology, just realized as
   one Docker bridge network per VLAN (Docker has no 802.1Q trunking) with
   `fw-ot-01` holding one interface per network, the same shape as the
   pfSense build's OPT3/OPT4 (one interface per VLAN, no separate switch
   device there either). `sw-core-01` is a separate, mostly cosmetic
   device left over from Module 2's Day 2 ARP/MAC exercise — it was never
   doing the actual segmentation, even in Module 2.

2. **The Supervisory↔Control flat network is fixed.** In Module 2,
   `scada-hmi-01/02` and `eng-ws-01` were deliberately dual-homed onto
   both `ot_control` and `ot_supervisory` directly — that *was* the Day 5
   "critical finding". A firewall placed between the zones does nothing
   if traffic already crosses over a direct L2 connection that bypasses
   it entirely, so in this copy those containers (and `historian-01`,
   found the same way during testing) are single-homed on their
   Supervisory/DMZ zone only. R01-R07 govern those boundaries; they're
   only real, enforceable rules once the bypass is gone. Framing: Day 5
   found the flat network, Day 4 here remediates it. `sw-core-01` keeps
   both interfaces — a core switch legitimately terminates two VLANs, and
   it never does IP forwarding between them, so it isn't a bypass path
   the way the HMI/ENG-WS/historian dual-homing was.

3. **An Enterprise zone was added (`ot_enterprise`, `enterprise-ws-01`).**
   R08-R12 — nearly half the ruleset — are written against an "Enterprise"
   zone that Module 2's topology never modeled at all (it only ever had
   Control/Supervisory/DMZ). Without it, those 5 rules would be
   unenforceable and untestable. `enterprise-ws-01` is a minimal endpoint
   container, matching how Management/Quarantine also each got one, so
   every rule has a genuine source or destination to test against, not
   just a network with nothing on it.

## Zones and containers (Docker build)

| Zone | Subnet | Containers |
|---|---|---|
| Control (VLAN 10) | 192.168.1.0/24 | plc-main-01, plc-aux-01, gen1/2-rtu, prot-rel-01/02, vfd-pump-01, traffic-gen, sw-core-01 |
| Supervisory (VLAN 20) | 192.168.2.0/24 | scada-hmi-01/02, eng-ws-01, sw-core-01 |
| DMZ (VLAN 30) | 192.168.3.0/24 | historian-01 |
| Management (VLAN 40) | 192.168.40.0/24 | mgmt-ws-01 — isolated by default-deny |
| Quarantine (VLAN 99) | 192.168.99.0/24 | quarantine-host-01 — isolated by default-deny |
| Enterprise | 192.168.50.0/24 | enterprise-ws-01 — listens on 1433 for R08 |

`fw-ot-01` sits on all six networks at the `.5` address (e.g.
`192.168.1.5`, `192.168.40.5`, ...).

## Rule enforcement, and how it's tested

Every rule in `firewall-rules-module3.csv` should end up as an iptables
rule on `fw-ot-01`'s FORWARD chain — that's the trainee exercise, walked
through step by step in `LAB_GUIDE.md`, which also explains why
enforcement is at L3/L4 (source/dest subnet + protocol/port): the CSV's
"Protocol" column (Modbus, OPC-UA, HTTPS, SQL, VPN) is realized as the
port it rides on, and endpoint containers run plain accept/close **stub**
listeners on exactly those ports rather than full protocol
implementations — a firewall filters by port, not payload, so that's what
it takes to prove a rule allows or denies traffic. R09 and R10 both ride
tcp/443 to the same destination and so collapse to one rule — a real
limitation worth discussing with trainees: a packet filter can't
distinguish an HTTPS dashboard from an HTTPS-tunneled VPN on the same
port.

`scripts/test_firewall_rules.sh` exercises all 11 rules plus the default-
deny baseline (Management/Quarantine isolation, Control↔DMZ, which has no
rule permitting it at all) against *whatever ruleset is currently on
fw-ot-01* and reports PASS/FAIL against the expected allow/deny
behaviour, saving results to `logs/firewall_test_results.txt` — this is
the Day 4 deliverable's "test results" half, and trainees should run it
repeatedly as they build up their ruleset, not just once at the end. It
distinguishes a true firewall block (TIMEOUT, since a correct ruleset
uses silent DROP, not REJECT) from a fast REFUSED, which would mean the
packet actually reached its target and only failed because nothing was
listening — a different and worse finding, since it means the firewall
didn't do the blocking. Several checks deliberately target a port that
genuinely **is** open on the destination for a *different* rule (e.g. R11
targets Control's real 502 Modbus listener; R12 and R07 target
Supervisory's real 443/80 listeners) specifically so a DENY result can
only be explained by the firewall, not by an absent service.


## Troubleshooting (Docker build)

- If a cross-zone test hangs instead of failing fast, that's expected —
  DROP is silent by design; give it the full ~4s timeout.
- `docker exec fw-ot-01 iptables -L FORWARD -v -n --line-numbers` shows
  per-rule packet/byte counters — the clearest way to confirm which rule
  actually matched a given test.
- If cross-zone traffic doesn't reach `fw-ot-01` at all (immediate "no
  route to host" rather than a timeout), re-run `./setup.sh` — step 4
  re-applies every container's route to `fw-ot-01` and is safe to repeat.
- `docker compose logs <service>` — check why a device failed its health
  check, same as the Module 2 lab.
- `docker compose restart fw-ot-01` — resets a trainee's ruleset back to
  wide-open (no rules), if they lock themselves out or want to start over.
