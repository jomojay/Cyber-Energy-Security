# Day 2 — Protocol Analysis Report

**Name:**                    **Date:**                **Capture:**

## 1. Modbus/TCP frame, byte by byte (Section 4.2.2)
Frame No. ____ (request)   Frame No. ____ (matching response)

| Field | Bytes (hex) | Value | Meaning |
|---|---|---|---|
| Transaction ID | | | |
| Protocol ID | | | |
| Length | | | |
| Unit ID | | | |
| Function Code | | | |
| Data | | | |

How do you know the response belongs to the request?

## 2. OPC UA
Session establishment (frame numbers): Hello ___  Acknowledge ___  OpenSecureChannel ___  CreateSession ___  ActivateSession ___
Publish/subscribe exchange (frame numbers): CreateSubscription ___  PublishRequest ___  PublishResponse ___
Screenshots: fig ___

## 3. Communication diagram
(insert results/map_*.png or your own draw.io diagram)

| Master (client) | Slave (server) | Protocol | Interval | Function codes |
|---|---|---|---|---|
| | | | | |

Which device is polled most often? Which communication is NOT periodic?
