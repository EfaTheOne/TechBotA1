# TechBotA1
TechBotA1 is a multi-purpose reconnaissance and attacking program designed for cybersecurity research on AUTHERIZED networks.

### Features
- wifi scan: High-precision airspace scanning. Detects SSID, BSSID, Signal (dBm), Auth (WPA2/WPA3), and Encryption.
- wifi crack [flags]: Multi-mode WPA2-PBKDF2-SHA1 cracker.
- bssid: Low-level BSSID discovery mode.
- gethash local: Rapid extraction of saved WiFi profiles from the host system.
- gethash bssid=... [deauth=...]: Active EAPOL handshake capture engine (Requires Scapy + Admin).
- arpscan: Fast ARP-based host discovery. Maps IP to MAC across the local subnet.
- ping : 64-threaded ICMP sweep (e.g., ping 192.168.1).
- scan [range]: Multi-threaded TCP Port Scanner with service identification.
- banner : Service banner grabber for OS and software version detection.
- sniff [-f bpf] [-d domain]: Deep Packet Dissection Engine. Auto-extracts DNS queries, HTTP headers, and cleartext credentials.
- recon: Unified intelligence report: routing tables, ARP cache, WiFi profiles, and adapter telemetry.
- netstat: Real-time connection monitor showing Local/Remote IPs and PIDs.
- trace : Visual traceroute with geolocation for each hop (City, ISP, Coordinates).
- arpspoof : Man-in-the-Middle engine. Intercepts traffic via ARP cache poisoning.
- dnsspoof : High-speed DNS query interceptor and redirection tool.
- flood : High-throughput UDP stress tester.
- fuzz : Protocol vulnerability tester. Sends malformed TCP/UDP/ICMP packets to crash services.
- shell : Reverse shell listener with built-in payloads for Bash, Python, and PowerShell.
- broadcast : Multi-protocol network-wide notification system (UDP, TCP, NetBIOS, MSG).
- agent : Autonomous AI Hacking Agent (supports Network Recon and Screen Manipulation modes).
- httpvuln : Passive security header auditor (HSTS, CSP, XSS, Cookie security).
- dirbust : Intelligent path discovery for hidden panels (/admin, /config, .env, etc.).
- brute : HTTP Basic Auth credential attacker (16x32 matrix).
- subdomain : DNS-based infrastructure discovery for 70+ common host prefixes.
- dns : Full record interrogation (A, MX, NS, TXT, CNAME, SOA).
- proxy : Stealth proxy server with SSL stripping and BeautifulSoup URL rewriting.
- whois : Consolidated WHOIS, GeoIP, and HTTP header intel.
- lookup : OSINT intelligence aggregator (ISP, ASN, Reverse DNS, Location).
- shadow: Passive vulnerability scanner. Alerts on cleartext creds, weak TLS, and MITM activity.
- hash [type]: 1-second dictionary check for MD5, SHA1, and SHA256.
- hashcat [type]: Advanced CPU-bound cracker with 128-bit parallel chunking and mutation rules.
- hashid : Deterministic algorithm identification + AI cryptographic analysis.
- codec : Universal transcoder (Base64, Hex, ROT13, URL, Hash).
- encrypt : AES-256 (Fernet) file encryption with auto-generated keys.
- decrypt : Multi-vector file decryption.
- bruteforce : Exhaustive key-space verification (lower, alpha, alnum, alnumsym, all).
- app dashboard: Global system telemetry (CPU, RAM, Net utilization).
- app monitor: Live high-frequency performance graphs.
- app topology: Interactive network map with auto-calculated node positions.
- app connections: Filterable list of all active network sockets.
- app nettraffic: Real-time throughput (Up/Down) oscilloscope.
- app sniffer: Wireshark-grade live packet inspection interface with tabbed protocol views.
- app geotarget: Map-based IP geolocation for all active connections.
- app worldmap: Global connectivity visualization showing origin/destination coordinates.
- app chat: Stealth-Comm encrypted messaging app with P2P handshake.
- app entropy: Spectral waveform and spectral density visualizer.
- app portscanner: Visual tool for mapping service orientation on remote hosts.
- app wifiradar: Spatial visualization of nearby access points and signal strength.
- app wificracker: Comprehensive GUI for WPA2 handshake capture and offline cracking.
- app hashcracker: Graphical interface for multi-threaded hash recovery.
- app passwords: Secure viewer for recovered system WiFi password vault.
- app firewall: Live viewer for internal host firewall rules.
- app processes: Modern process manager with resource tracking.
- app hexeditor: Deep binary file viewer and inspector.
app ipinfo: OSINT dashboard for domain and IP intelligence.
app calculator: Scientific/security-focused calculator.
app notes: Persistent notepad with automatic session saving.
app exploits: Database of common exploit techniques and references.
app shadowwalker: Passive vulnerability analysis dashboard with real-time alert logs.
app voice: HUD interface for wake-word AI command and control.
