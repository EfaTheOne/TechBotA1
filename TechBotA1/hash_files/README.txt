╔══════════════════════════════════════════════════════════════════╗
║  TECHBOT A1 — WiFi Hash Files Directory                        ║
╚══════════════════════════════════════════════════════════════════╝

Drop your .hc22000 hash files here!

The WiFiCracker app will automatically detect all hash files
placed in this folder. When you launch the app, you can select
which hash file to crack from a built-in file browser.

SUPPORTED FORMATS:
  • .hc22000  — Hashcat 22000 format (WPA/WPA2 PMKID & MIC)
  • .cap      — Packet capture files (will attempt conversion)
  • .pcap     — Packet capture files (will attempt conversion)
  • .txt      — Plain hash text files

HOW TO USE:
  1. Copy or drag-and-drop hash files into this folder
  2. Launch WiFiCracker:  techbot app wificracker
  3. Go to the "Cracker" tab
  4. Select your hash file from the "HASH FILES" panel
  5. Click "⚡ AUTO ATTACK" to begin cracking

GENERATING HASH FILES:
  • Use the Sniffer app's Handshake tab to capture WPA handshakes
  • Use hcxpcapngtool to convert .cap files to .hc22000 format
  • Use 'techbot gethash' command to auto-capture hashes
