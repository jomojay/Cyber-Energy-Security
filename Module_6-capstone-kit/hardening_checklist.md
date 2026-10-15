# Palanca SL-2 Hardening Checklist (Module 6, Lab Day 5)

Reference: Module 6, Section 6.5. Apply these measures to the existing
Module 2 Palanca lab environment: the Module 3 firewall lab (Module 2's
topology + FW-OT-01, recommended) or the Option C VirtualBox build.
Check off each item as implemented and record your evidence (command
output, `iptables-save` excerpt, or design note). Items marked
**[auto: check N]** are tested by `verify_hardening.sh` on the Docker lab.
The others need written evidence.

## Firewall Rule Optimisation (6.5.2)
- [ ] Review the Module 3 FW-OT-01 ruleset; remove or narrow any rule
      broader than operationally necessary (e.g. a rule allowing an
      entire /24 when only 2 hosts actually need the access).
      **[auto: checks 3, 4]**
- [ ] Confirm every rule has a documented business justification
      (cross-reference against Module 3's rule table).

## VLAN Restructuring / Microsegmentation (6.5.3)
- [ ] Confirm Control Zone devices are not reachable from Supervisory
      Zone except via the explicitly documented conduit (Module 2
      Lab Day 5's flat-network finding should now be resolved).
      **[auto: check 1]**
- [ ] Split any single large VLAN serving more than one device
      criticality tier into smaller, purpose-specific VLANs.

## Secure Remote Access (6.5.4)
- [ ] Confirm remote/VPN access requires MFA (Module 3, Section 3.3.2).
- [ ] Confirm remote sessions are logged/recorded.

## Endpoint Hardening (6.5.5)
- [ ] Disable unused services/ports on HMI and engineering workstation
      containers/VMs (anything not required for their documented role).
- [ ] Confirm default credentials have been changed on every device
      (Module 2, Section 2.6.3 default-credential check, re-verified).
      **[auto: check 2, SW-CORE-01]**

## Protocol Whitelisting (6.5.6)
- [ ] Confirm the firewall filters by specific Modbus function code
      where supported, not just by port 502 alone. **[auto: check 5]**

## Verification (6.5.7)
- [ ] Run `verify_hardening.sh` and resolve every FAIL before Day 6.
- [ ] Re-run Module 5's OTSafeScanner (Day 6) and confirm the open-port
      count and NSE-discoverable information has measurably decreased
      compared to the pre-hardening Module 5 scan results.
