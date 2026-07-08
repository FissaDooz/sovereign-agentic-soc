# Wazuh-to-Vigil Bridge

Vigil does not support Wazuh natively; it ships connectors for commercial SIEM/EDR platforms
only. The bridge documented here is the integration work that connects the two, and is the main
original contribution of this project on top of the upstream tools.

## `custom-vigil.py`

Location: `/var/ossec/integrations/custom-vigil.py`, owned `root:wazuh`, mode `750`. No external
dependencies (Python standard library only). It converts a Wazuh alert into a Vigil finding and
posts it to `/api/ingest/ingest-string` (`application/x-www-form-urlencoded`, fields `data` and
`format=json`).

The current version transmits an enriched context so the AI agent can qualify the finding
autonomously rather than reporting missing information: host, source and destination IP,
process and parent process, full command line, target file, user, file hashes, and the MITRE
tactic/technique in plain text (not just the ID). Wazuh alert levels are mapped to Vigil
severities: 14+ maps to `critical`, 12-13 to `high`.

See [bridge/custom-vigil.py](../bridge/custom-vigil.py) for the full script.

## Wiring it into Wazuh (`integratord`)

Inside an `<ossec_config>` block in `/var/ossec/etc/ossec.conf`:

```xml
<integration>
  <name>custom-vigil.py</name>
  <level>12</level>
  <alert_format>json</alert_format>
</integration>
```

`systemctl restart wazuh-manager`.

Two constraints matter here: the script's filename must start with `custom-` (Wazuh's
`integratord` only loads scripts with that prefix), and the `<integration>` block must sit
inside an `<ossec_config>...</ossec_config>` section, not between two separate ones.

See [config/ossec-integration.xml](../config/ossec-integration.xml) for the standalone snippet.

## Validation

After a test attack against the monitored workstation, `[custom-vigil] OK 200` appears on its
own in `/var/ossec/logs/integrations.log`, and the corresponding finding shows up in Vigil
without any manual step. This confirms the level-12 threshold, the `integratord` wiring, and
the ingestion endpoint are all working together correctly.

## Manual test

```bash
/var/ossec/integrations/custom-vigil.py /tmp/test_alert.json
tail -f /var/ossec/logs/integrations.log
```
