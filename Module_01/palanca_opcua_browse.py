#!/usr/bin/env python3
"""
palanca_opcua_browse.py — Palanca Gas Plant OPC-UA Client
==========================================================
OCEON Module 1 Lab 4 — OPC-UA Exploration

Connects to the Palanca OPC-UA server (palanca_opcua_server.py),
browses the address space, reads all Generator 1 variables,
and displays security policy information.

Trainees RUN this script and INTERPRET the output.
They do not modify it in Lab 4.
(Module 3 lab adds security policy configuration.)
"""

from opcua import Client, ua
import sys
from datetime import datetime


OPC_ENDPOINT = "opc.tcp://127.0.0.1:4840/palanca"


def print_section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def browse_node(client: Client, node, indent: int = 0):
    """Recursively browse the OPC-UA address space and print node info."""
    prefix = "  " * indent
    try:
        name     = node.get_browse_name().Name
        node_cls = node.get_node_class()
        node_id  = node.nodeid

        if node_cls == ua.NodeClass.Variable:
            try:
                value    = node.get_value()
                datatype = node.get_data_type_as_variant_type()
                access   = node.get_access_level()
                writable = "READ-WRITE" if ua.AccessLevel.CurrentWrite in ua.AccessLevel(access) else "READ-ONLY"
                print(f"{prefix}[VAR] {name:<20} = {str(value):<15} "
                      f"({datatype.name}, {writable})")
            except Exception as e:
                print(f"{prefix}[VAR] {name:<20} = [error reading: {e}]")

        elif node_cls == ua.NodeClass.Object:
            print(f"{prefix}[OBJ] {name}/")
            for child in node.get_children():
                browse_node(client, child, indent + 1)

    except Exception as e:
        print(f"{prefix}[ERR] Cannot browse node: {e}")


def get_security_info(client: Client) -> dict:
    """Extract security policy details from the server."""
    try:
        endpoints = client.get_endpoints()
        info = {
            "endpoint_url": OPC_ENDPOINT,
            "policies": [],
        }
        for ep in endpoints:
            policy = ep.SecurityPolicyUri.split("#")[-1] if "#" in ep.SecurityPolicyUri else ep.SecurityPolicyUri
            mode   = str(ep.SecurityMode).replace("MessageSecurityMode.", "")
            info["policies"].append(f"{policy} / {mode}")
        return info
    except Exception as e:
        return {"endpoint_url": OPC_ENDPOINT, "policies": [f"Error: {e}"]}


def read_gen1_values(client: Client) -> dict:
    """Read all Generator 1 values from the address space."""
    ns = client.get_namespace_index("urn:evolvepower:palanca:scada")
    values = {}

    node_paths = {
        "Frequency":    f"ns={ns};s=Generator1.Frequency",
        "Voltage":      f"ns={ns};s=Generator1.Voltage",
        "OutputPower":  f"ns={ns};s=Generator1.OutputPower",
        "FreqSetpoint": f"ns={ns};s=Generator1.FreqSetpoint",
        "Running":      f"ns={ns};s=Generator1.Running",
        "Fault":        f"ns={ns};s=Generator1.Fault",
        "CBClosed":     f"ns={ns};s=Generator1.CBClosed",
    }

    for name, node_id in node_paths.items():
        try:
            node = client.get_node(node_id)
            values[name] = node.get_value()
        except Exception:
            # Fall back: browse by name
            values[name] = "N/A"

    return values


def main():
    print("=" * 60)
    print(" OCEON Module 1 Lab 4 — Palanca OPC-UA Client")
    print(f" Endpoint: {OPC_ENDPOINT}")
    print(f" Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    client = Client(OPC_ENDPOINT)
    client.set_session_timeout(30000)

    # ── LAB 4 QUESTION 4: Security policy ────────────────────────
    print_section("1. Security Information (Lab 4 Q4)")
    try:
        sec = get_security_info(client)
        print(f"  Endpoint:       {sec['endpoint_url']}")
        print(f"  Security mode:  {sec['policies']}")
        print()
        print("  LAB Q4: Is the security policy 'None' or 'Basic256Sha256'?")
        print("  Write your answer: ___________________________________")
        print("  What does this mean for the security of this connection?")
        print("  Write your answer: ___________________________________")
    except Exception as e:
        print(f"  Cannot retrieve security info before connection: {e}")

    # ── Connect ───────────────────────────────────────────────────
    print_section("2. Connecting to OPC-UA Server")
    try:
        client.connect()
        print(f"  Connected successfully to {OPC_ENDPOINT}")
        print(f"  Session ID: {client.uaclient._uasocket}")
    except Exception as e:
        print(f"  CONNECTION FAILED: {e}")
        print()
        print("  Troubleshooting:")
        print("  1. Is palanca_opcua_server.py running?")
        print("     Run: python3 ~/palanca_labs/module1/scripts/palanca_opcua_server.py")
        print("  2. Check port 4840: ss -an | grep :4840")
        sys.exit(1)

    try:
        # ── LAB 4 QUESTION 3: Browse address space ────────────────
        print_section("3. OPC-UA Address Space (Lab 4 Q3)")
        print("  Browsing PalancaPlatform/ElectricalSystem/...")
        print()

        root = client.get_root_node()
        objects = client.get_objects_node()
        for child in objects.get_children():
            browse_node(client, child, indent=1)

        # ── LAB 4 QUESTION 5: Generator 1 values ─────────────────
        print_section("4. Generator 1 Values (Lab 4 Q5)")
        print("  Reading all Generator1 variables...")
        print()

        ns = client.get_namespace_index("urn:evolvepower:palanca:scada")

        gen1_vars = [
            ("Frequency",    "Hz",  100.0,   "Compare to your Modbus reading in Lab 3"),
            ("Voltage",      "V",   1.0,     "Should match GEN1_VOLTAGE_x10 / 10"),
            ("OutputPower",  "kW",  1.0,     "Active load on the generator"),
            ("FreqSetpoint", "Hz",  1.0,     "This variable is READ-WRITE — why?"),
            ("Running",      "",    None,     "Boolean — True if generator is running"),
            ("Fault",        "",    None,     "Boolean — True if fault condition active"),
            ("CBClosed",     "",    None,     "Boolean — True if circuit breaker is closed"),
        ]

        for var_name, unit, scale, note in gen1_vars:
            try:
                # Try namespace-qualified path first
                path = f"0:Objects/0:Server"
                val = None

                # Browse to find the node
                for child in objects.get_children():
                    try:
                        if child.get_browse_name().Name == "PalancaPlatform":
                            for c2 in child.get_children():
                                if c2.get_browse_name().Name == "ElectricalSystem":
                                    for c3 in c2.get_children():
                                        if c3.get_browse_name().Name == "Generator1":
                                            for c4 in c3.get_children():
                                                if c4.get_browse_name().Name == var_name:
                                                    val = c4.get_value()
                    except Exception:
                        pass

                if val is not None:
                    if scale and scale != 1.0:
                        display = f"{val:.2f} {unit}"
                    elif unit:
                        display = f"{val} {unit}"
                    else:
                        display = str(val)
                    print(f"  Generator1/{var_name:<16} = {display:<20} [{note}]")
                else:
                    print(f"  Generator1/{var_name:<16} = [not found — check server]")
            except Exception as e:
                print(f"  Generator1/{var_name:<16} = [error: {e}]")

        # ── LAB 4 QUESTION 6: Comparison with Modbus ──────────────
        print_section("5. Lab Analysis Questions")
        print()
        print("  Q4: What is the security policy of this connection?")
        print("      Answer: ___________________________________")
        print()
        print("  Q5: Compare Generator1/Frequency above with what")
        print("      palanca_modbus_read.py showed in Lab 3.")
        print("      Are they the same value? Should they be? Why?")
        print("      Answer: ___________________________________")
        print()
        print("  Q6: Generator1/FreqSetpoint is READ-WRITE.")
        print("      If an attacker could connect to this OPC-UA server")
        print("      WITHOUT valid credentials (security policy = None),")
        print("      what could they change? What physical effect would")
        print("      that have on the Palanca generator?")
        print("      Answer: ___________________________________")
        print()
        print("  Q7: How is an attacker's capability here DIFFERENT")
        print("      from what they could do via Modbus?")
        print("      Consider: authentication, audit trail, data model.")
        print("      Answer: ___________________________________")

    finally:
        client.disconnect()
        print(f"\n{'─'*60}")
        print("  OPC-UA session closed.")
        print(f"{'─'*60}")


if __name__ == "__main__":
    main()
