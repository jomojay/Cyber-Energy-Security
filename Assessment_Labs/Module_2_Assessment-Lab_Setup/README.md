# Module 2 Assessment: Lab Kit (instructor only)

Adds an assessment overlay to the existing Palanca Docker lab (the Module 2
lab). Nothing in the practice lab is edited; the overlay is removed with one
script.

## What it changes

| Change | Why |
|---|---|
| New container `rogue-dev` at 192.168.1.99 | The "unfamiliar source" candidates must find (Section B1, B2, B4). It sweeps every PLC, RTU, relay and the VFD with a new connection per poll, 20-register reads and irregular timing, which differs from the legitimate polling master (traffic-gen). |
| `plc-aux-01` reports "Rockwell Automation ControlLogix" | Candidates cannot copy vendor strings from practice notes (Section B3, B4). |
| New container `switch-primer` (shares sw-core-01's network namespace) | Keeps the switch's neighbour (ARP) table populated so the switch output is meaningful (Section B2). |

## Install

1. Copy `docker-compose.assessment.yml`, the `assessment/` folder and the three
   `assessment_*.sh` scripts into the `palanca-lab` folder, next to `docker-compose.yml`.
2. Run `./assessment_setup.sh`. It builds, starts and verifies.
3. Run `./assessment_verify.sh` again 10 minutes before candidates arrive.
4. After the paper run `./assessment_teardown.sh` to restore the practice lab.

## Needs your attention (not tested against a live Docker daemon)

This kit was validated for syntax (compose merge keys, shell, Python) but was
not run against Docker, because no Docker daemon was available where it was
built. Do one full dry run yourself before assessment day:

- Confirm `assessment_verify.sh` passes.
- Run the Section B3 scan as a candidate would and note exactly what
  PLC-AUX-01 returns from the Modbus identification script. The output format
  depends on the pymodbus version in your lab image; the verify script only
  warns if it cannot match "rockwell".
- Confirm the switch output lists 192.168.1.99 and 192.168.1.200 with MAC addresses.

## Notes

- Candidate MAC addresses are Docker generated (02:42 prefix), so an OUI lookup
  cannot identify vendors in this lab. The paper is written with that in mind (Section B2).
- VFD-PUMP-01 (192.168.1.40) is the declared fragile device. The simulators
  do not log connections, so compliance with the "do not scan" rule is judged
  from each candidate's command screenshots.
