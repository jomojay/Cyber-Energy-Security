# Module 3, Day 4 — Firewall Configuration: Trainee Guide

**Objective:** implement the Palanca FW-OT-01 ruleset —
`firewall-rules-module3.csv`, rules R01 through R12 plus the R99
default-deny baseline — as iptables rules on `fw-ot-01`, the firewall
container sitting between all six network zones. Then prove each rule
does what it's supposed to.

`fw-ot-01` currently boots **wide open**: every zone can reach every
other zone. That's your starting point, not a bug.

## 1. Get in

```bash
docker exec -it fw-ot-01 bash
```

Everything below happens inside that shell, on the `FORWARD` chain
(that's the chain that governs traffic passing *through* this container
between zones — not traffic to/from the container itself).

## 2. The zone → subnet map

The CSV talks about zones by name. iptables needs subnets:

| Zone (as the CSV names it) | Subnet |
|---|---|
| VLAN 10 (Control) | `192.168.1.0/24` |
| VLAN 20 (Supervisory) | `192.168.2.0/24` |
| VLAN 30 (DMZ) | `192.168.3.0/24` |
| VLAN 40 (Management) | `192.168.40.0/24` |
| VLAN 99 (Quarantine) | `192.168.99.0/24` |
| Enterprise | `192.168.50.0/24` |

Tip: export these as shell variables first so your rules read like the
CSV instead of a wall of dotted-decimal:

```bash
CONTROL=192.168.1.0/24
SUPERVISORY=192.168.2.0/24
DMZ=192.168.3.0/24
MANAGEMENT=192.168.40.0/24
QUARANTINE=192.168.99.0/24
ENTERPRISE=192.168.50.0/24
```
(These don't survive if you exit the shell — re-export them if you
reconnect.)

## 3. One rule you're given, before any CSV rule

Add this first, before anything else:

```bash
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
```

This isn't one of R01-R12 — it's what lets **reply** traffic back through
for any connection you *do* allow below. Without it, you'd have to write
a second rule for every single allowed flow just to let its response
back out. It has to go first: iptables reads top-to-bottom and stops at
the first match, so if a later DENY rule for that same pair came first,
it would catch the replies too.

That ordering rule — **specific rules before the deny that would
otherwise catch them, and the broadest rule last** — is the whole game
for the rest of this exercise. Keep it in mind for every example below.

## 4. Four worked examples

These four cover every *shape* of rule in the CSV. Everything else
(R02, R05–R12) is one of these same shapes with a different zone pair
or port — you derive those yourself from the CSV in section 5.

### Example A — R01: a port-based ALLOW, bidirectional

> R01: ALLOW, Supervisory→Control and back, Modbus/TCP, port 502

```bash
iptables -A FORWARD -s "$SUPERVISORY" -d "$CONTROL" -p tcp --dport 502 -m conntrack --ctstate NEW -j ACCEPT
iptables -A FORWARD -s "$CONTROL" -d "$SUPERVISORY" -p tcp --dport 502 -m conntrack --ctstate NEW -j ACCEPT
```
- `-s`/`-d` — source/destination subnet, straight from the zone map above.
- `-p tcp --dport 502` — the CSV's "Protocol/Port" columns become a
  protocol + destination-port match.
- `-m conntrack --ctstate NEW` — only match the *first* packet of a new
  connection; the ESTABLISHED,RELATED rule above already handles
  everything after that.
- "Bidirectional" in the CSV means two rules here, one per direction —
  a firewall rule only ever matches one direction of travel.

### Example B — R03: an ICMP ALLOW

> R03: ALLOW, Supervisory→Control, ICMP (ping)

```bash
iptables -A FORWARD -s "$SUPERVISORY" -d "$CONTROL" -p icmp --icmp-type echo-request -j ACCEPT
```
ICMP has no port — `--icmp-type echo-request` (a ping request specifically,
not every ICMP message type) replaces `--dport` here. The reply (echo-reply)
is handled by the ESTABLISHED,RELATED rule, same as TCP.

### Example C — R04: an explicit pair catch-all DENY

> R04: DENY, Supervisory↔Control, ANY, ANY — catch-all for this pair

```bash
iptables -A FORWARD -s "$SUPERVISORY" -d "$CONTROL" -j DROP
iptables -A FORWARD -s "$CONTROL" -d "$SUPERVISORY" -j DROP
```
No `-p` or `--dport` at all — that's what "ANY/ANY" means: match
everything for this specific pair. **This must come after** Examples A
and B's ACCEPT rules for the same pair, or it would shadow them and
nothing between Supervisory and Control would ever work.

### Example D — R99: the final default-deny (do this LAST)

> R99: DENY, ANY zone → ANY zone — default-deny baseline

```bash
iptables -P FORWARD DROP
```
This isn't a rule appended to the chain — it's the chain's **default
policy**: whatever falls through without matching anything above gets
dropped. Do this only once you've added every ALLOW rule you actually
need. The moment you set this, any zone pair you haven't explicitly
allowed yet — including ones you meant to get to next — stops working.
If that happens: `docker compose restart fw-ot-01` resets you back to
wide-open and you can start again.

## 5. Now you: the remaining rules

Using the CSV and the four patterns above, implement:

**R02, R05, R06, R08, R09, R10** — all the same shape as Example A (a
port-based ALLOW between a zone pair). R09 and R10 name the same source,
destination, and port — that's not a mistake in the CSV, work out why
one rule covers both.

**R07, R11, R12** — the same shape as Example C (an explicit catch-all
DENY for one pair). R11 is the flagship check for today: Enterprise must
never reach Control, on anything.

Once every ALLOW rule you need is in place, finish with **R99** (Example
D) to lock down everything else — every zone pair not explicitly named
above (Control↔DMZ, anything↔Management, anything↔Quarantine, and the
reverse of every one-way rule) should end up denied by this, without you
writing a rule for each of them by hand.

## 6. Test your work

From the *host* (not inside fw-ot-01), after adding each rule or batch of
rules:

```bash
./scripts/test_firewall_rules.sh
```

It attempts the exact traffic each rule should allow or deny and reports
PASS/FAIL, saving results to `logs/firewall_test_results.txt`. Run it as
often as you like — it's read-only against your ruleset, it changes
nothing.

Read the result column, not just PASS/FAIL:
- **CONNECTED** — the attempt succeeded.
- **TIMEOUT** — nothing came back at all. This is what a correct DENY
  looks like (your rules use `DROP`, which is silent).
- **REFUSED** — the packet reached the target and was actively rejected
  *there*, not by your firewall. If you see this on something that's
  supposed to be denied, your firewall let it through and the only
  reason it failed is that nothing was listening.

## 7. Inspecting and fixing your ruleset

```bash
docker exec fw-ot-01 iptables -L FORWARD -v -n --line-numbers
```
Shows every rule in order with a packet/byte hit counter — the fastest
way to see exactly which rule matched (or didn't) for a given test.

```bash
docker exec fw-ot-01 iptables -D FORWARD <line-number>
```
Deletes one rule by its line number from the listing above, if you need
to fix an ordering mistake without starting over.

```bash
docker compose restart fw-ot-01
```
Full reset back to wide-open, no rules. Safe to use any time.

## Deliverable

Once `test_firewall_rules.sh` shows all checks passing:
1. `docker exec fw-ot-01 iptables-save > my_firewall_rules.txt` (run from
   the host) to capture your finished ruleset.
2. Keep `logs/firewall_test_results.txt` from your passing run.
Submit both as your "firewall rule set (as implemented) + test results"
deliverable.

## Advanced task (optional): OT recon through the switch, then prove the firewall's effect

This combines Day 2 (SSH to the switch) and Day 3 (Nmap) skills with what
you just built, and shows something a raw port check doesn't: that
segmentation isn't a blackout — the one path R01 is supposed to leave open
should still work perfectly, even with the rest of the ruleset locked down.

**1. Recon from the switch first, like a real engineer would.**
From `eng-ws-01`:
```bash
ssh admin@sw-core-01
switch> show mac-address-table
switch> show arp
switch> exit
```
This gives you a live host list from the switch's own tables instead of
guessing IPs — the same Day 2 technique, now used to build a target list
for the scan below.

**2. Run an OT-specific Nmap scan against those hosts, with the Modbus NSE script.**
Still from `eng-ws-01`:
```bash
nmap -Pn -p 502 --script modbus-discover 192.168.1.10 192.168.1.11 192.168.1.20 192.168.1.21 192.168.1.30 192.168.1.31 192.168.1.40
```
`modbus-discover` doesn't just report the port open — it queries each
device's Slave ID and returns vendor/product/firmware info, e.g.:
```
Nmap scan report for 192.168.1.10
PORT    STATE SERVICE
502/tcp open  modbus
| modbus-discover:
|   sid 0x1:
|_    Device identification: Siemens S7-1200 PLC-MAIN-01 1.0
```
That should match the vendor strings in the Day 6 asset table exactly —
this is the same information disclosure a real Modbus reconnaissance scan
would surface. Note nmap flags this script `intrusive`, not just
`discovery`: real Modbus devices are often fragile and can misbehave under
scanning, so this kind of scan is never something to run against a live
OT network without explicit authorization.

**3. Run the exact same scan again once your ruleset is finished.**
You should get the *identical* result — full vendor identification,
unchanged. That's R01 doing its job: Supervisory is *supposed* to reach
Control on Modbus/502, and your firewall shouldn't break the traffic it
was designed to allow. Segmentation done right narrows access to exactly
what's needed, not everything.

**4. Now scan a port that isn't part of R01** — e.g. `-p 22,80` instead of
`-p 502` against the same hosts. Before your ruleset existed these came
back `closed` (a real host said no); once your default-deny is in place
they come back `filtered` (nothing answered at all — the packet never got
a reply, dropped by your firewall). That specific difference —
`closed` vs `filtered` — is how you'd tell, from a scan alone, whether a
port is genuinely absent or actively firewalled.
