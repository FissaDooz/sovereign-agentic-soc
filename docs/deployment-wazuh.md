# Wazuh Deployment

Wazuh provides endpoint detection for this project: Manager, Indexer, and Dashboard running
all-in-one, plus a Windows agent with Sysmon on the monitored workstation.

## Proxmox host prerequisite (required for the Indexer)

```bash
# on the Proxmox HOST, not inside the LXC (the LXC shares the host kernel)
echo 'vm.max_map_count=262144' > /etc/sysctl.d/99-wazuh.conf
sysctl -p /etc/sysctl.d/99-wazuh.conf
```

Without this, the Indexer (OpenSearch) refuses to start. `vm.max_map_count` is a kernel
parameter, so it has to be set on the Proxmox host rather than inside the LXC, unlike a full VM
where it could be set internally.

## Installation

```bash
apt -y install sudo curl              # sudo is required even when already running as root
curl -sO https://packages.wazuh.com/4.12/wazuh-install.sh
bash ./wazuh-install.sh -a -i         # -a: all-in-one, -i: ignore the resource check
```

Generated credentials:

```bash
tar -O -xf /root/wazuh-install-files.tar wazuh-install-files/wazuh-passwords.txt
```

Dashboard: `https://10.50.10.20` (HTTPS, self-signed certificate, accept the browser warning).

On restart, allow 1-2 minutes for the Indexer to come up; a transient "did not load properly"
message is expected during that window. The `admin` password cannot be changed through the UI
(`Resource 'admin' is reserved`).

## Windows agent

Generated from the dashboard: Agents -> Deploy new agent (OS: Windows, Manager:
`10.50.10.20`). Then, in an elevated PowerShell prompt on the target machine:

```powershell
msiexec.exe /i wazuh-agent.msi /q WAZUH_MANAGER="10.50.10.20" WAZUH_AGENT_NAME="WORKSTATION-01"
NET START WazuhSvc
```

If the agent does not report in despite `Test-NetConnection ... -Port 1514/1515` succeeding,
check the manager address in `ossec.conf` and re-enroll: `agent-auth.exe -m 10.50.10.20`. A
wrong address entered at install time is the usual cause.

## Sysmon (fine-grained telemetry, required)

```powershell
# on the monitored workstation, elevated PowerShell
Invoke-WebRequest "https://download.sysinternals.com/files/Sysmon.zip" -OutFile Sysmon.zip
Expand-Archive Sysmon.zip -DestinationPath Sysmon
Invoke-WebRequest "https://raw.githubusercontent.com/SwiftOnSecurity/sysmon-config/master/sysmonconfig-export.xml" -OutFile sysmonconfig.xml
.\Sysmon\Sysmon64.exe -accepteula -i sysmonconfig.xml
```

Then add to `C:\Program Files (x86)\ossec-agent\ossec.conf`:

```xml
<localfile>
  <location>Microsoft-Windows-Sysmon/Operational</location>
  <log_format>eventchannel</log_format>
</localfile>
```

`Restart-Service WazuhSvc`.

Without Sysmon, Wazuh only sees basic Windows event logs. With it: full command lines, parent
process, network connections, and file hashes, which is what makes the resulting alerts useful
for qualification.

## Alert level calibration

| Level | Example | Forwarded to the bridge |
|---|---|---|
| 7 | CIS checks, rootcheck | No, treated as noise |
| 9 | PowerShell creates a script in Temp | No |
| 12 | Base64-encoded PowerShell | Yes, retained threshold |
| 15 | Executable dropped in a known malware path | Yes, critical |

See [bridge.md](bridge.md) for how level-12+ alerts are forwarded to Vigil.
