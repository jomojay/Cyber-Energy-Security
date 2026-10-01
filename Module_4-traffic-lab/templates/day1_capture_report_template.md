# Day 1 — Annotated Wireshark Capture Report

**Name:**                    **Date:**
**Capture file:** captures/live/________________   **Duration:** ____ min   **Packets:** ______

## 1. How I captured
Interface(s) used: ______________   (from `./otlab live status`)
Was `./otlab live activity` running during the capture?  Yes / No

## 2. Display filters
| Filter | Packets displayed | What I see (1 sentence) | Screenshot |
|---|---|---|---|
| `modbus` | | | fig 1 |
| `opcua` | | | fig 2 |
| `tcp.port==502` | | | fig 3 |
| `tcp.port==4840` | | | fig 4 |

Why do `modbus` and `tcp.port==502` show different numbers?

## 3. Colouring rule for Modbus writes
Name: ________   Filter: ______________________   Colour: ______
Screenshot of a highlighted write (fig 5). Which device sent it? ______ Which register? ______

## 4. Other observations
(protocols you did not expect, devices you could not identify …)
