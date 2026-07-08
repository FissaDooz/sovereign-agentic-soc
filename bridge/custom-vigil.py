#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
custom-vigil.py - Wazuh -> Vigil bridge (sovereign agentic SOC) - v2 enriched

v2: transmits full context (IP, process, file, user, detailed MITRE mapping,
command line, parent process) so the AI agent can qualify the alert
autonomously, without reporting "missing information".

Location:     /var/ossec/integrations/custom-vigil.py
Permissions:  chown root:wazuh, chmod 750
Invoked by Wazuh as: <script> <alert_file> <api_key> <hook_url>
Dependencies: standard library only.
"""

import json
import sys
import urllib.request
import urllib.error
import urllib.parse

# ------------------------------------------------------------------ config
VIGIL_URL = "http://10.50.10.24:6987/api/ingest/ingest-string"
TIMEOUT = 30


def level_to_severity(level: int) -> str:
    if level >= 14:
        return "critical"
    if level >= 12:
        return "high"
    if level >= 8:
        return "medium"
    return "low"


def level_to_anomaly(level: int) -> float:
    return min(round(level / 15.0, 2), 1.0)


def extract_mitre(rule: dict) -> dict:
    """mitre_predictions {technique_id: score} from rule.mitre."""
    out = {}
    mitre = rule.get("mitre", {})
    ids = mitre.get("id", [])
    if isinstance(ids, str):
        ids = [ids]
    for tid in ids:
        out[tid] = 0.9
    return out


def clean(s):
    """Collapses doubled Windows backslashes from Wazuh logs for readability."""
    if isinstance(s, str):
        return s.replace("\\\\", "\\")
    return s


def build_finding(alert: dict) -> dict:
    rule = alert.get("rule", {})
    agent = alert.get("agent", {})
    data = alert.get("data", {})
    mitre = rule.get("mitre", {})
    level = int(rule.get("level", 0))

    # --- Enriched entity context: everything the agent needs -----------------
    ctx = {
        "host": agent.get("name", "unknown"),
        "host_ip": agent.get("ip", "unknown"),
        "agent_id": agent.get("id"),
        "rule_id": rule.get("id"),
        "rule_description": rule.get("description"),
        "rule_level": level,
        "rule_groups": rule.get("groups", []),
        "mitre_tactics": mitre.get("tactic", []),
        "mitre_techniques": mitre.get("technique", []),
        "mitre_ids": mitre.get("id", []),
        "timestamp": alert.get("timestamp"),
        "log_location": alert.get("location"),
    }

    # --- Windows/Sysmon details (the core of the enrichment) -----------------
    win = {}
    if isinstance(data, dict):
        win = data.get("win", {}).get("eventdata", {}) or {}
        win_system = data.get("win", {}).get("system", {}) or {}
        if win_system.get("eventID"):
            ctx["sysmon_event_id"] = win_system.get("eventID")

    for src_key, dst_key in [
        ("image", "process_image"),
        ("commandLine", "command_line"),
        ("parentImage", "parent_image"),
        ("parentCommandLine", "parent_command_line"),
        ("originalFileName", "original_filename"),
        ("targetFilename", "target_filename"),
        ("user", "user"),
        ("processId", "process_id"),
        ("processGuid", "process_guid"),
        ("parentProcessGuid", "parent_process_guid"),
        ("destinationIp", "destination_ip"),
        ("destinationPort", "destination_port"),
        ("destinationHostname", "destination_hostname"),
        ("sourceIp", "source_ip"),
        ("hashes", "hashes"),
        ("md5", "md5"),
        ("sha256", "sha256"),
        ("ruleName", "sysmon_rule_name"),
        ("utcTime", "event_time"),
    ]:
        if win.get(src_key):
            ctx[dst_key] = clean(win[src_key])

    if alert.get("full_log"):
        ctx["full_log"] = clean(alert["full_log"])[:2000]

    return {
        "finding_id": f"wazuh-{alert.get('id', '')}".replace(".", "-"),
        "timestamp": alert.get("timestamp"),
        "data_source": "wazuh",
        "severity": level_to_severity(level),
        "anomaly_score": level_to_anomaly(level),
        "status": "new",
        "mitre_predictions": extract_mitre(rule),
        "entity_context": ctx,
    }


def log(msg: str):
    try:
        with open("/var/ossec/logs/integrations.log", "a", encoding="utf-8") as f:
            f.write(f"[custom-vigil] {msg}\n")
    except Exception:
        pass
    sys.stderr.write(f"[custom-vigil] {msg}\n")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: custom-vigil.py <alert_file>")

    with open(sys.argv[1], encoding="utf-8", errors="ignore") as f:
        alert = json.load(f)

    finding = build_finding(alert)
    payload = {"findings": [finding]}

    form = urllib.parse.urlencode({
        "data": json.dumps(payload),
        "format": "json",
    }).encode("utf-8")

    req = urllib.request.Request(
        VIGIL_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            log(f"OK {resp.status}: {resp.read().decode('utf-8')[:300]}")
    except urllib.error.HTTPError as e:
        log(f"HTTPError {e.code}: {e.read().decode('utf-8')[:300]}")
    except Exception as e:
        log(f"ERROR: {e}")


if __name__ == "__main__":
    main()
