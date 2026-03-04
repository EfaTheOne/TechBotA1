"""
EliteSnifferEngine v2.0 — Wireshark-Grade Packet Analysis Engine
──────────────────────────────────────────────────────────────────
Deep packet dissection, URL/domain tracking, display filters,
protocol statistics, flow tracking, and PCAP export.
Only requires: scapy
"""

import threading
import datetime
import os
import re
import time
import struct
import collections
from collections import defaultdict, OrderedDict, deque

try:
    import scapy.all as scapy
    from scapy.layers.inet import IP, TCP, UDP, ICMP
    from scapy.layers.l2 import Ether, ARP
    from scapy.layers.dns import DNS, DNSQR, DNSRR
    from scapy.packet import Raw
    from scapy.utils import wrpcap
    from scapy.config import conf
    SCAPY_OK = True
except ImportError:
    SCAPY_OK = False

# Dot11/EAPOL — separate import so WiFi layer failures don't break the engine
HAS_DOT11 = False
HAS_EAPOL = False
try:
    from scapy.layers.dot11 import Dot11, Dot11Beacon, Dot11Auth, Dot11AssoReq
    HAS_DOT11 = True
except Exception:
    Dot11 = None
try:
    from scapy.layers.eap import EAPOL
    HAS_EAPOL = True
except Exception:
    try:
        from scapy.all import EAPOL
        HAS_EAPOL = True
    except Exception:
        EAPOL = None


# ═══════════════════════════════════════════════════
# TLS SNI Extraction (manual parse — no extra deps)
# ═══════════════════════════════════════════════════

def extract_tls_sni(raw_bytes):
    """Extract Server Name Indication from a TLS ClientHello."""
    try:
        if len(raw_bytes) < 6:
            return None
        # TLS record: type 0x16 (handshake), version, length
        if raw_bytes[0] != 0x16:
            return None
        # Handshake type 0x01 = ClientHello
        if raw_bytes[5] != 0x01:
            return None

        # Parse ClientHello
        offset = 5 + 4  # skip handshake header
        if offset + 2 > len(raw_bytes):
            return None
        # Skip client version (2) + random (32)
        offset += 2 + 32
        # Skip session ID
        if offset + 1 > len(raw_bytes):
            return None
        sid_len = raw_bytes[offset]
        offset += 1 + sid_len
        # Skip cipher suites
        if offset + 2 > len(raw_bytes):
            return None
        cs_len = struct.unpack("!H", raw_bytes[offset:offset + 2])[0]
        offset += 2 + cs_len
        # Skip compression methods
        if offset + 1 > len(raw_bytes):
            return None
        cm_len = raw_bytes[offset]
        offset += 1 + cm_len
        # Extensions
        if offset + 2 > len(raw_bytes):
            return None
        ext_len = struct.unpack("!H", raw_bytes[offset:offset + 2])[0]
        offset += 2
        ext_end = offset + ext_len

        while offset + 4 <= ext_end and offset + 4 <= len(raw_bytes):
            ext_type = struct.unpack("!H", raw_bytes[offset:offset + 2])[0]
            ext_data_len = struct.unpack("!H", raw_bytes[offset + 2:offset + 4])[0]
            offset += 4
            if ext_type == 0x0000:  # SNI extension
                # SNI list length (2), type (1), name length (2), name
                if offset + 5 <= len(raw_bytes):
                    name_len = struct.unpack("!H", raw_bytes[offset + 3:offset + 5])[0]
                    if offset + 5 + name_len <= len(raw_bytes):
                        return raw_bytes[offset + 5:offset + 5 + name_len].decode('ascii', errors='ignore')
                return None
            offset += ext_data_len
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════
# Display Filter Parser
# ═══════════════════════════════════════════════════

class DisplayFilter:
    """Wireshark-style display filter engine.

    Supports:
        protocol filters:  tcp, udp, dns, http, tls, arp, icmp
        field filters:     ip.src == x, ip.dst == x, tcp.port == 80
                           dns.query contains google
                           http.url contains youtube
                           http.host == example.com
        logical:           and, or, not
        bare strings:      any text → matches against info/src/dst
    """

    def __init__(self, expression=""):
        self.expression = expression.strip()

    def matches(self, pkt_info):
        """Check if a packet info dict matches this filter."""
        if not self.expression:
            return True
        try:
            return self._eval(self.expression, pkt_info)
        except Exception:
            return True  # On parse error, show all

    def _eval(self, expr, p):
        expr = expr.strip()
        if not expr:
            return True

        # Handle 'or'
        or_parts = self._split_logical(expr, ' or ')
        if len(or_parts) > 1:
            return any(self._eval(part, p) for part in or_parts)

        # Handle 'and'
        and_parts = self._split_logical(expr, ' and ')
        if len(and_parts) > 1:
            return all(self._eval(part, p) for part in and_parts)

        # Handle 'not'
        if expr.startswith('not ') or expr.startswith('!'):
            inner = expr[4:] if expr.startswith('not ') else expr[1:]
            return not self._eval(inner.strip(), p)

        # Handle parentheses
        if expr.startswith('(') and expr.endswith(')'):
            return self._eval(expr[1:-1], p)

        # Handle comparison: field == value, field != value, field contains value
        for op in [' contains ', ' == ', ' != ', ' >= ', ' <= ', ' > ', ' < ']:
            if op in expr.lower():
                idx = expr.lower().index(op)
                field = expr[:idx].strip().lower()
                value = expr[idx + len(op):].strip().strip('"').strip("'")
                return self._compare(field, op.strip(), value, p)

        # Bare protocol name
        proto_lower = expr.lower()
        pkt_proto = p.get("proto", "").lower()
        if proto_lower in ("tcp", "udp", "dns", "http", "tls", "arp", "icmp", "ip", "raw"):
            if proto_lower == "ip":
                return p.get("src", "???") != "???"
            return pkt_proto == proto_lower

        # Bare text search — match against info, src, dst, urls
        search = expr.lower()
        searchable = f"{p.get('info', '')} {p.get('src', '')} {p.get('dst', '')} {' '.join(p.get('urls', []))} {' '.join(p.get('domains', []))}".lower()
        return search in searchable

    def _compare(self, field, op, value, p):
        # Resolve field value
        actual = self._resolve_field(field, p)
        if actual is None:
            return False

        if op == 'contains':
            return value.lower() in str(actual).lower()
        elif op == '==':
            return str(actual).lower() == value.lower()
        elif op == '!=':
            return str(actual).lower() != value.lower()
        try:
            a, b = float(actual), float(value)
            if op == '>': return a > b
            if op == '<': return a < b
            if op == '>=': return a >= b
            if op == '<=': return a <= b
        except (ValueError, TypeError):
            pass
        return False

    def _resolve_field(self, field, p):
        field_map = {
            'ip.src': p.get('src'),
            'ip.dst': p.get('dst'),
            'src': p.get('src'),
            'dst': p.get('dst'),
            'protocol': p.get('proto'),
            'proto': p.get('proto'),
            'tcp.srcport': p.get('sport'),
            'tcp.dstport': p.get('dport'),
            'tcp.port': p.get('sport') or p.get('dport'),
            'udp.srcport': p.get('sport'),
            'udp.dstport': p.get('dport'),
            'udp.port': p.get('sport') or p.get('dport'),
            'port': p.get('sport') or p.get('dport'),
            'len': p.get('len'),
            'length': p.get('len'),
            'info': p.get('info'),
            'dns.query': ' '.join(p.get('domains', [])),
            'dns.name': ' '.join(p.get('domains', [])),
            'http.url': ' '.join(p.get('urls', [])),
            'http.host': p.get('http_host', ''),
            'http.method': p.get('http_method', ''),
            'tls.sni': p.get('tls_sni', ''),
            'tcp.flags': p.get('tcp_flags_str', ''),
        }
        return field_map.get(field)

    def _split_logical(self, expr, keyword):
        """Split on keyword but respect parentheses."""
        parts = []
        depth = 0
        current = ""
        i = 0
        kw_lower = keyword.lower()
        while i < len(expr):
            if expr[i] == '(':
                depth += 1
            elif expr[i] == ')':
                depth -= 1
            if depth == 0 and expr[i:i + len(keyword)].lower() == kw_lower:
                parts.append(current)
                current = ""
                i += len(keyword)
                continue
            current += expr[i]
            i += 1
        parts.append(current)
        return parts if len(parts) > 1 else [expr]


# ═══════════════════════════════════════════════════
# Protocol Statistics Tracker
# ═══════════════════════════════════════════════════

class ProtocolStats:
    """Real-time protocol statistics aggregator."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proto_counts = defaultdict(int)
        self.proto_bytes = defaultdict(int)
        self.ip_src_counts = defaultdict(int)
        self.ip_dst_counts = defaultdict(int)
        self.total_packets = 0
        self.total_bytes = 0
        self.start_time = None
        self.domains_seen = OrderedDict()   # domain → count
        self.urls_seen = OrderedDict()      # url → count

    def record(self, pkt_info):
        with self.lock:
            if self.start_time is None:
                self.start_time = time.time()
            proto = pkt_info.get("proto", "RAW")
            plen = pkt_info.get("len", 0)
            self.proto_counts[proto] += 1
            self.proto_bytes[proto] += plen
            self.total_packets += 1
            self.total_bytes += plen

            src = pkt_info.get("src", "???")
            dst = pkt_info.get("dst", "???")
            if src != "???":
                self.ip_src_counts[src] += 1
            if dst != "???":
                self.ip_dst_counts[dst] += 1

            for d in pkt_info.get("domains", []):
                self.domains_seen[d] = self.domains_seen.get(d, 0) + 1
            for u in pkt_info.get("urls", []):
                self.urls_seen[u] = self.urls_seen.get(u, 0) + 1

    def get_snapshot(self):
        with self.lock:
            elapsed = time.time() - self.start_time if self.start_time else 0
            pps = self.total_packets / elapsed if elapsed > 0 else 0
            bps = self.total_bytes / elapsed if elapsed > 0 else 0
            top_domains = sorted(self.domains_seen.items(), key=lambda x: -x[1])[:20]
            top_urls = sorted(self.urls_seen.items(), key=lambda x: -x[1])[:20]
            top_src = sorted(self.ip_src_counts.items(), key=lambda x: -x[1])[:10]
            top_dst = sorted(self.ip_dst_counts.items(), key=lambda x: -x[1])[:10]
            return {
                "proto_counts": dict(self.proto_counts),
                "proto_bytes": dict(self.proto_bytes),
                "total_packets": self.total_packets,
                "total_bytes": self.total_bytes,
                "elapsed": elapsed,
                "pps": pps,
                "bps": bps,
                "top_domains": top_domains,
                "top_urls": top_urls,
                "top_src": top_src,
                "top_dst": top_dst,
            }

    def reset(self):
        with self.lock:
            self.proto_counts.clear()
            self.proto_bytes.clear()
            self.ip_src_counts.clear()
            self.ip_dst_counts.clear()
            self.total_packets = 0
            self.total_bytes = 0
            self.start_time = None
            self.domains_seen.clear()
            self.urls_seen.clear()


# ═══════════════════════════════════════════════════
# TCP Flow / Connection Tracker
# ═══════════════════════════════════════════════════

class FlowTracker:
    """Track TCP/UDP connections and their states."""

    def __init__(self):
        self.lock = threading.Lock()
        self.flows = {}  # (src, dst, sport, dport, proto) → flow_info

    def record(self, pkt_info):
        src = pkt_info.get("src", "???")
        dst = pkt_info.get("dst", "???")
        sport = pkt_info.get("sport", 0)
        dport = pkt_info.get("dport", 0)
        proto = pkt_info.get("proto", "RAW")

        if proto not in ("TCP", "UDP", "HTTP", "TLS", "DNS"):
            return

        # Normalize flow key (lower IP first for bidirectional)
        if (src, sport) > (dst, dport):
            key = (dst, src, dport, sport, proto)
        else:
            key = (src, dst, sport, dport, proto)

        with self.lock:
            if key not in self.flows:
                self.flows[key] = {
                    "src": src, "dst": dst, "sport": sport, "dport": dport,
                    "proto": proto, "packets": 0, "bytes": 0,
                    "start": pkt_info.get("time", ""),
                    "last": pkt_info.get("time", ""),
                    "state": "ACTIVE",
                }
            flow = self.flows[key]
            flow["packets"] += 1
            flow["bytes"] += pkt_info.get("len", 0)
            flow["last"] = pkt_info.get("time", "")

            # TCP state tracking
            flags = pkt_info.get("tcp_flags", 0)
            if flags:
                if flags & 0x02:  # SYN
                    flow["state"] = "SYN_SENT"
                if flags & 0x12 == 0x12:  # SYN-ACK
                    flow["state"] = "ESTABLISHED"
                if flags & 0x01:  # FIN
                    flow["state"] = "CLOSING"
                if flags & 0x04:  # RST
                    flow["state"] = "RESET"

    def get_flows(self):
        with self.lock:
            return list(self.flows.values())

    def reset(self):
        with self.lock:
            self.flows.clear()


# ═══════════════════════════════════════════════════
# WPA 4-Way Handshake Tracker
# ═══════════════════════════════════════════════════

class HandshakeTracker:
    """Track WPA/WPA2 4-way EAPOL handshakes and extract hash data."""

    def __init__(self):
        self.lock = threading.Lock()
        # bssid → {"messages": {1:pkt,2:pkt,3:pkt,4:pkt}, "client": mac, "packets": [raw], ...}
        self.handshakes = {}  # bssid → handshake_info
        self.eapol_log = []   # all EAPOL events for display

    def record_eapol(self, pkt, pkt_info):
        """Analyze an EAPOL packet and track handshake progress."""
        try:
            # Get raw EAPOL-Key bytes from pkt_info (already parsed by dissect)
            # or try to extract from the packet directly
            raw_load = b''
            if HAS_EAPOL and EAPOL is not None and pkt.haslayer(EAPOL):
                eapol_layer = pkt[EAPOL]
                raw_load = bytes(eapol_layer.payload) if eapol_layer.payload else bytes(eapol_layer)[4:]
            elif pkt.haslayer(Ether) and pkt[Ether].type == 0x888E:
                full_raw = bytes(pkt[Ether].payload)
                raw_load = full_raw[4:] if len(full_raw) > 4 else b''
            elif pkt.haslayer(Raw):
                raw_load = bytes(pkt[Raw].load)
                if len(raw_load) > 4 and raw_load[1] == 3:
                    raw_load = raw_load[4:]
                else:
                    raw_load = b''

            # Determine BSSID and client
            bssid = pkt_info.get('eapol_bssid', None) or pkt_info.get('dst', 'unknown')
            client = pkt_info.get('src', 'unknown')

            if HAS_DOT11 and Dot11 is not None and pkt.haslayer(Dot11):
                dot11 = pkt[Dot11]
                bssid = dot11.addr3 if dot11.addr3 else dot11.addr2
                if dot11.addr1 and dot11.addr1 != bssid:
                    client = dot11.addr1
                elif dot11.addr2 and dot11.addr2 != bssid:
                    client = dot11.addr2
            elif pkt.haslayer(Ether):
                bssid = pkt[Ether].dst
                client = pkt[Ether].src

            bssid = bssid.lower() if bssid else 'unknown'
            client = client.lower() if client else 'unknown'

            # Parse EAPOL Key frame to determine message number
            msg_num = self._detect_message_num(raw_load)

            # Extract key data
            anonce = None
            snonce = None
            mic = None

            if len(raw_load) >= 76:
                nonce_offset = 13
                nonce = raw_load[nonce_offset:nonce_offset + 32]
                mic_offset = 77
                if len(raw_load) > mic_offset + 16:
                    mic = raw_load[mic_offset:mic_offset + 16]

                if msg_num == 1:
                    anonce = nonce
                elif msg_num == 2:
                    snonce = nonce
                elif msg_num == 3:
                    anonce = nonce

            with self.lock:
                if bssid not in self.handshakes:
                    self.handshakes[bssid] = {
                        "bssid": bssid,
                        "client": client,
                        "messages": {},
                        "packets": [],
                        "anonce": None,
                        "snonce": None,
                        "mic": None,
                        "complete": False,
                        "time": pkt_info.get("time", ""),
                    }

                hs = self.handshakes[bssid]
                if client != 'unknown':
                    hs["client"] = client
                hs["messages"][msg_num] = pkt
                hs["packets"].append(pkt)
                hs["time"] = pkt_info.get("time", "")

                if anonce:
                    hs["anonce"] = anonce.hex()
                if snonce:
                    hs["snonce"] = snonce.hex()
                if mic and msg_num == 2:
                    hs["mic"] = mic.hex()

                # Complete if we have M1+M2 (enough for cracking)
                if 1 in hs["messages"] and 2 in hs["messages"]:
                    hs["complete"] = True

                event = {
                    "time": pkt_info.get("time", ""),
                    "bssid": bssid,
                    "client": client,
                    "msg_num": msg_num,
                    "has_nonce": anonce is not None or snonce is not None,
                    "has_mic": mic is not None,
                    "complete": hs["complete"],
                    "total_msgs": len(hs["messages"]),
                }
                self.eapol_log.append(event)
                return event

        except Exception as e:
            self.eapol_log.append({
                "time": pkt_info.get("time", ""), "bssid": "error", "client": "",
                "msg_num": 0, "has_nonce": False, "has_mic": False,
                "complete": False, "total_msgs": 0, "error": str(e),
            })
        return None

    def _detect_message_num(self, key_data):
        """Detect which of the 4 EAPOL-Key messages this is."""
        if len(key_data) < 6:
            return 0
        try:
            key_info = struct.unpack('!H', key_data[1:3])[0]
        except struct.error:
            return 0

        has_ack = bool(key_info & 0x0080)
        has_mic = bool(key_info & 0x0100)
        has_secure = bool(key_info & 0x0200)
        has_install = bool(key_info & 0x0040)

        if has_ack and not has_mic:
            return 1
        if not has_ack and has_mic and not has_secure:
            return 2
        if has_ack and has_mic and has_install:
            return 3
        if not has_ack and has_mic and has_secure:
            return 4
        if has_ack and has_mic:
            return 3
        if has_mic:
            return 2
        return 0

    def get_handshakes(self):
        """Return a list of all tracked handshakes."""
        with self.lock:
            return [dict(v, packets_count=len(v['packets'])) for v in self.handshakes.values()]

    def get_log(self):
        """Return the EAPOL event log."""
        with self.lock:
            return list(self.eapol_log)

    def export_handshake(self, bssid, storage_path="captures"):
        """Export captured handshake packets to a .cap file for hashcat/aircrack."""
        bssid = bssid.lower()
        with self.lock:
            hs = self.handshakes.get(bssid)
            if not hs or not hs["packets"]:
                return None, 0
            pkts = list(hs["packets"])

        safe_bssid = bssid.replace(':', '')
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = os.path.join(storage_path, f"handshake_{safe_bssid}_{ts}.cap")
        wrpcap(fname, pkts)
        return fname, len(pkts)

    def get_hash_string(self, bssid):
        """Generate hash info summary for the captured handshake."""
        bssid = bssid.lower()
        with self.lock:
            hs = self.handshakes.get(bssid)
            if not hs:
                return None

            lines = []
            lines.append(f"BSSID:    {hs['bssid']}")
            lines.append(f"Client:   {hs['client']}")
            lines.append(f"Messages: {sorted(hs['messages'].keys())}")
            lines.append(f"Complete: {'YES ✓' if hs['complete'] else 'Waiting...'}")
            if hs.get('anonce'):
                lines.append(f"ANonce:   {hs['anonce']}")
            if hs.get('snonce'):
                lines.append(f"SNonce:   {hs['snonce']}")
            if hs.get('mic'):
                lines.append(f"MIC:      {hs['mic']}")
            if hs['complete']:
                lines.append("")
                lines.append("Hash can be cracked with:")
                safe = bssid.replace(':', '')
                lines.append(f"  hashcat -m 22000 handshake_{safe}_*.cap wordlist.txt")
                lines.append(f"  aircrack-ng -w wordlist.txt handshake_{safe}_*.cap")
            return "\n".join(lines)

    def reset(self):
        with self.lock:
            self.handshakes.clear()
            self.eapol_log.clear()


# ═══════════════════════════════════════════════════
# Main Sniffer Engine
# ═══════════════════════════════════════════════════

TCP_FLAGS_MAP = {
    'F': 0x01, 'S': 0x02, 'R': 0x04, 'P': 0x08,
    'A': 0x10, 'U': 0x20, 'E': 0x40, 'C': 0x80,
}

def tcp_flags_to_str(flags):
    """Convert TCP flags int to human-readable string like [SYN, ACK]."""
    names = []
    flag_names = [
        (0x02, "SYN"), (0x10, "ACK"), (0x01, "FIN"), (0x04, "RST"),
        (0x08, "PSH"), (0x20, "URG"), (0x40, "ECE"), (0x80, "CWR"),
    ]
    for mask, name in flag_names:
        if flags & mask:
            names.append(name)
    return ", ".join(names) if names else "NONE"


class EliteSnifferEngine:
    """Wireshark-grade packet capture and analysis engine."""

    def __init__(self, interface=None, storage_path="captures"):
        self.interface = interface
        self.storage_path = storage_path
        self.is_running = False
        self.stop_event = threading.Event()
        self.stats = ProtocolStats()
        self.flows = FlowTracker()
        self.handshakes = HandshakeTracker()
        self.raw_packets = []       # raw scapy packets for PCAP export
        self.raw_lock = threading.Lock()
        self.max_raw = 50000        # max packets to keep in memory
        self._sniff_thread = None

        if not os.path.exists(storage_path):
            os.makedirs(storage_path)

    def start_capture(self, callback, bpf_filter=None):
        """Start sniffing in a background thread. callback(pkt_info_dict) per packet."""
        if self.is_running:
            return
        self.is_running = True
        self.stop_event.clear()
        self.stats.reset()
        self.flows.reset()
        self.handshakes.reset()
        with self.raw_lock:
            self.raw_packets.clear()

        iface = self.interface
        if not iface:
            try:
                iface = conf.iface
            except Exception:
                iface = None

        def _sniff_worker():
            try:
                def _handler(pkt):
                    if self.stop_event.is_set():
                        return
                    info = self.dissect(pkt)
                    # Store raw
                    with self.raw_lock:
                        if len(self.raw_packets) < self.max_raw:
                            self.raw_packets.append(pkt)
                    # Track stats & flows
                    self.stats.record(info)
                    self.flows.record(info)
                    # Notify UI
                    callback(info)

                scapy.sniff(
                    iface=iface,
                    prn=_handler,
                    filter=bpf_filter if bpf_filter else None,
                    store=0,
                    stop_filter=lambda x: self.stop_event.is_set()
                )
            except Exception as e:
                callback({"error": str(e), "proto": "ERROR", "src": "ENGINE", "dst": "UI",
                          "time": datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
                          "len": 0, "info": f"Capture error: {e}", "domains": [], "urls": []})
            finally:
                self.is_running = False

        self._sniff_thread = threading.Thread(target=_sniff_worker, daemon=True)
        self._sniff_thread.start()

    def stop_capture(self):
        """Stop the capture."""
        self.stop_event.set()
        self.is_running = False

    def export_pcap(self, filename=None):
        """Export captured packets to a PCAP file."""
        if not filename:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.storage_path, f"capture_{ts}.pcap")
        with self.raw_lock:
            pkts = list(self.raw_packets)
        if pkts:
            wrpcap(filename, pkts)
        return filename, len(pkts)

    def dissect(self, pkt):
        """Deep packet dissection — returns a rich info dictionary."""
        info = {
            "raw": pkt,
            "time": datetime.datetime.fromtimestamp(pkt.time).strftime('%H:%M:%S.%f')[:-3],
            "src": "???",
            "dst": "???",
            "proto": "RAW",
            "len": len(pkt),
            "info": pkt.summary(),
            "sport": None,
            "dport": None,
            "tcp_flags": 0,
            "tcp_flags_str": "",
            "domains": [],
            "urls": [],
            "http_host": "",
            "http_method": "",
            "tls_sni": "",
            "layers": [],
        }

        # ── Layer 2: Ethernet ──
        if pkt.haslayer(Ether):
            info["layers"].append({
                "name": "Ethernet II",
                "fields": [
                    ("Source MAC", pkt[Ether].src),
                    ("Destination MAC", pkt[Ether].dst),
                    ("Type", hex(pkt[Ether].type)),
                ]
            })

        # ── Layer 2: ARP ──
        if pkt.haslayer(ARP):
            arp = pkt[ARP]
            info["proto"] = "ARP"
            info["src"] = arp.psrc
            info["dst"] = arp.pdst
            op_str = "Request" if arp.op == 1 else "Reply" if arp.op == 2 else str(arp.op)
            info["info"] = f"ARP {op_str}: Who has {arp.pdst}? Tell {arp.psrc}" if arp.op == 1 else f"ARP {op_str}: {arp.psrc} is at {arp.hwsrc}"
            info["layers"].append({
                "name": "ARP",
                "fields": [
                    ("Operation", op_str),
                    ("Sender MAC", arp.hwsrc),
                    ("Sender IP", arp.psrc),
                    ("Target MAC", arp.hwdst),
                    ("Target IP", arp.pdst),
                ]
            })
            return info

        # ── Layer 3: IP ──
        if pkt.haslayer(IP):
            ip = pkt[IP]
            info["src"] = ip.src
            info["dst"] = ip.dst
            info["proto"] = "IP"
            info["layers"].append({
                "name": "Internet Protocol v4",
                "fields": [
                    ("Source", ip.src),
                    ("Destination", ip.dst),
                    ("Version", ip.version),
                    ("Header Length", ip.ihl * 4),
                    ("TTL", ip.ttl),
                    ("Protocol", ip.proto),
                    ("Total Length", ip.len),
                    ("Identification", hex(ip.id)),
                    ("Flags", ip.flags),
                    ("Fragment Offset", ip.frag),
                ]
            })

        # ── Layer 4: TCP ──
        if pkt.haslayer(TCP):
            tcp = pkt[TCP]
            info["proto"] = "TCP"
            info["sport"] = tcp.sport
            info["dport"] = tcp.dport
            info["tcp_flags"] = int(tcp.flags)
            flags_str = tcp_flags_to_str(int(tcp.flags))
            info["tcp_flags_str"] = flags_str
            info["info"] = f"{tcp.sport} → {tcp.dport} [{flags_str}] Seq={tcp.seq} Ack={tcp.ack} Win={tcp.window}"
            info["layers"].append({
                "name": "Transmission Control Protocol",
                "fields": [
                    ("Source Port", tcp.sport),
                    ("Destination Port", tcp.dport),
                    ("Sequence Number", tcp.seq),
                    ("Acknowledgment Number", tcp.ack),
                    ("Flags", f"0x{int(tcp.flags):03x} [{flags_str}]"),
                    ("Window Size", tcp.window),
                    ("Checksum", hex(tcp.chksum) if tcp.chksum else "N/A"),
                    ("Urgent Pointer", tcp.urgptr),
                ]
            })

            # ── Application layer detection on TCP ──
            if pkt.haslayer(Raw):
                raw_data = bytes(pkt[Raw].load)

                # HTTP Detection
                try:
                    text = raw_data[:2000].decode('utf-8', errors='ignore')
                    http_methods = ["GET ", "POST ", "PUT ", "DELETE ", "HEAD ", "OPTIONS ", "PATCH "]
                    for method in http_methods:
                        if text.startswith(method):
                            info["proto"] = "HTTP"
                            lines = text.split('\r\n')
                            request_line = lines[0]
                            info["http_method"] = method.strip()
                            info["info"] = request_line

                            # Extract host and URL
                            path = request_line.split(' ')[1] if len(request_line.split(' ')) > 1 else "/"
                            host = ""
                            header_fields = []
                            for line in lines[1:]:
                                if ':' in line:
                                    k, v = line.split(':', 1)
                                    header_fields.append((k.strip(), v.strip()))
                                    if k.strip().lower() == 'host':
                                        host = v.strip()
                                        info["http_host"] = host

                            if host:
                                full_url = f"http://{host}{path}"
                                info["urls"].append(full_url)
                                info["domains"].append(host)
                                info["info"] = f"{method.strip()} {full_url}"

                            info["layers"].append({
                                "name": f"Hypertext Transfer Protocol ({method.strip()})",
                                "fields": [("Request", request_line)] + header_fields[:15]
                            })
                            break

                    # HTTP Response
                    if text.startswith("HTTP/"):
                        info["proto"] = "HTTP"
                        lines = text.split('\r\n')
                        info["info"] = lines[0]
                        header_fields = []
                        for line in lines[1:]:
                            if ':' in line:
                                k, v = line.split(':', 1)
                                header_fields.append((k.strip(), v.strip()))
                            elif line == '':
                                break
                        info["layers"].append({
                            "name": "Hypertext Transfer Protocol (Response)",
                            "fields": [("Status", lines[0])] + header_fields[:15]
                        })
                except Exception:
                    pass

                # TLS/SSL Detection (ClientHello with SNI)
                if info["proto"] == "TCP" and len(raw_data) > 5 and raw_data[0] == 0x16:
                    sni = extract_tls_sni(raw_data)
                    if sni:
                        info["proto"] = "TLS"
                        info["tls_sni"] = sni
                        info["domains"].append(sni)
                        info["info"] = f"Client Hello → {sni}"
                        info["layers"].append({
                            "name": "Transport Layer Security",
                            "fields": [
                                ("Record Type", "Handshake (0x16)"),
                                ("Handshake Type", "Client Hello"),
                                ("Server Name (SNI)", sni),
                            ]
                        })
                    elif raw_data[0] == 0x16:
                        info["proto"] = "TLS"
                        # Check for other handshake types
                        hs_type = raw_data[5] if len(raw_data) > 5 else 0
                        hs_names = {2: "Server Hello", 11: "Certificate", 12: "Server Key Exchange",
                                    14: "Server Hello Done", 16: "Client Key Exchange"}
                        hs_name = hs_names.get(hs_type, f"Type {hs_type}")
                        info["info"] = f"TLS Handshake: {hs_name}"
                        info["layers"].append({
                            "name": "Transport Layer Security",
                            "fields": [
                                ("Record Type", "Handshake (0x16)"),
                                ("Handshake Type", hs_name),
                            ]
                        })

                # TLS Application Data
                if info["proto"] == "TCP" and len(raw_data) > 5 and raw_data[0] == 0x17:
                    info["proto"] = "TLS"
                    info["info"] = f"TLS Application Data ({len(raw_data)} bytes)"
                    info["layers"].append({
                        "name": "Transport Layer Security",
                        "fields": [
                            ("Record Type", "Application Data (0x17)"),
                            ("Length", len(raw_data)),
                        ]
                    })

        # ── Layer 4: UDP ──
        elif pkt.haslayer(UDP):
            udp = pkt[UDP]
            info["proto"] = "UDP"
            info["sport"] = udp.sport
            info["dport"] = udp.dport
            info["info"] = f"{udp.sport} → {udp.dport} Len={udp.len}"
            info["layers"].append({
                "name": "User Datagram Protocol",
                "fields": [
                    ("Source Port", udp.sport),
                    ("Destination Port", udp.dport),
                    ("Length", udp.len),
                    ("Checksum", hex(udp.chksum) if udp.chksum else "N/A"),
                ]
            })

            # ── DNS ──
            if pkt.haslayer(DNS):
                dns = pkt[DNS]
                info["proto"] = "DNS"
                dns_fields = [("Transaction ID", hex(dns.id)), ("Flags", hex(dns.qr))]

                if dns.qr == 0 and pkt.haslayer(DNSQR):
                    # DNS Query
                    qname = pkt[DNSQR].qname.decode(errors='ignore').rstrip('.')
                    qtype_map = {1: "A", 28: "AAAA", 5: "CNAME", 15: "MX", 2: "NS",
                                 12: "PTR", 6: "SOA", 16: "TXT", 33: "SRV", 255: "ANY"}
                    qtype = qtype_map.get(pkt[DNSQR].qtype, str(pkt[DNSQR].qtype))
                    info["info"] = f"Query: {qname} ({qtype})"
                    info["domains"].append(qname)
                    dns_fields.extend([("Query Name", qname), ("Query Type", qtype)])

                elif dns.qr == 1:
                    # DNS Response
                    answers = []
                    if pkt.haslayer(DNSQR):
                        qname = pkt[DNSQR].qname.decode(errors='ignore').rstrip('.')
                        info["domains"].append(qname)
                        dns_fields.append(("Query Name", qname))

                    # Parse answers
                    for i in range(dns.ancount):
                        try:
                            rr = dns.an[i] if hasattr(dns, 'an') and dns.an else None
                            if rr and hasattr(rr, 'rdata'):
                                rdata = str(rr.rdata)
                                answers.append(rdata)
                                dns_fields.append((f"Answer {i + 1}", f"{rr.rrname.decode(errors='ignore')} → {rdata}"))
                        except Exception:
                            break

                    if answers:
                        info["info"] = f"Response: {', '.join(answers[:3])}"
                        if len(answers) > 3:
                            info["info"] += f" (+{len(answers) - 3} more)"
                    else:
                        info["info"] = f"Response: {dns.ancount} answers"

                info["layers"].append({"name": "Domain Name System", "fields": dns_fields})

        # ── ICMP ──
        elif pkt.haslayer(ICMP):
            icmp = pkt[ICMP]
            info["proto"] = "ICMP"
            type_names = {0: "Echo Reply", 3: "Destination Unreachable", 5: "Redirect",
                          8: "Echo Request", 11: "Time Exceeded"}
            type_name = type_names.get(icmp.type, f"Type {icmp.type}")
            info["info"] = f"ICMP {type_name} (type={icmp.type}, code={icmp.code})"
            info["layers"].append({
                "name": "Internet Control Message Protocol",
                "fields": [
                    ("Type", f"{icmp.type} ({type_name})"),
                    ("Code", icmp.code),
                    ("Checksum", hex(icmp.chksum) if icmp.chksum else "N/A"),
                ]
            })

        # ── EAPOL (WPA Handshake) ──
        # Detection method 1: scapy auto-dissects EAPOL layer
        is_eapol = False
        eapol_raw_bytes = b''
        if HAS_EAPOL and EAPOL is not None and pkt.haslayer(EAPOL):
            is_eapol = True
        # Detection method 2: Check EtherType 0x888E (EAPOL over Ethernet — Windows)
        elif pkt.haslayer(Ether) and pkt[Ether].type == 0x888E:
            is_eapol = True
        # Detection method 3: Scan raw bytes for EAPOL signature
        elif pkt.haslayer(Raw):
            raw_check = bytes(pkt[Raw].load)
            # EAPOL version(1) + type(1) + length(2) — type 3 = EAPOL-Key
            if len(raw_check) > 4 and raw_check[0] in (1, 2, 3) and raw_check[1] == 3:
                is_eapol = True
                eapol_raw_bytes = raw_check

        if is_eapol:
            info["proto"] = "EAPOL"

            # Get EAPOL payload bytes
            if HAS_EAPOL and EAPOL is not None and pkt.haslayer(EAPOL):
                eapol_layer = pkt[EAPOL]
                eapol_raw_bytes = bytes(eapol_layer.payload) if eapol_layer.payload else bytes(eapol_layer)[4:]
                eapol_version = eapol_layer.version
            else:
                # Manual parse: skip Ether header (14 bytes) if present
                if pkt.haslayer(Ether) and pkt[Ether].type == 0x888E:
                    full_raw = bytes(pkt[Ether].payload)
                    eapol_version = full_raw[0] if len(full_raw) > 0 else 0
                    eapol_raw_bytes = full_raw[4:] if len(full_raw) > 4 else b''  # skip EAPOL header
                else:
                    eapol_version = eapol_raw_bytes[0] if eapol_raw_bytes else 0
                    eapol_raw_bytes = eapol_raw_bytes[4:] if len(eapol_raw_bytes) > 4 else b''

            # Determine BSSID and client
            eapol_bssid = "unknown"
            eapol_client = "unknown"

            if HAS_DOT11 and Dot11 is not None and pkt.haslayer(Dot11):
                dot11 = pkt[Dot11]
                eapol_bssid = dot11.addr3 or dot11.addr2 or "unknown"
                if dot11.addr1 and dot11.addr1 != eapol_bssid:
                    eapol_client = dot11.addr1
                elif dot11.addr2 and dot11.addr2 != eapol_bssid:
                    eapol_client = dot11.addr2
                info["src"] = dot11.addr2 or info["src"]
                info["dst"] = dot11.addr1 or info["dst"]
            elif pkt.haslayer(Ether):
                # On Windows/wired: Ether src = sender, dst = receiver
                eapol_bssid = pkt[Ether].dst
                eapol_client = pkt[Ether].src
                info["src"] = pkt[Ether].src
                info["dst"] = pkt[Ether].dst

            # Determine message number from EAPOL-Key data
            msg_num = self.handshakes._detect_message_num(eapol_raw_bytes) if eapol_raw_bytes else 0
            info["info"] = f"EAPOL Key Message {msg_num}/4 — BSSID: {eapol_bssid}"
            info["eapol_msg"] = msg_num
            info["eapol_bssid"] = eapol_bssid

            eapol_fields = [
                ("Type", f"EAPOL-Key (Message {msg_num}/4)"),
                ("BSSID", eapol_bssid),
                ("Client", eapol_client),
                ("Version", eapol_version),
                ("Payload Length", len(eapol_raw_bytes)),
            ]

            # Extract nonce if available
            if len(eapol_raw_bytes) >= 45:
                nonce = eapol_raw_bytes[13:45]
                nonce_name = "ANonce" if msg_num in (1, 3) else "SNonce" if msg_num == 2 else "Nonce"
                eapol_fields.append((nonce_name, nonce.hex()))

            if len(eapol_raw_bytes) > 93:
                mic = eapol_raw_bytes[77:93]
                if any(b != 0 for b in mic):
                    eapol_fields.append(("MIC", mic.hex()))

            info["layers"].append({
                "name": "IEEE 802.1X (EAPOL) — WPA 4-Way Handshake",
                "fields": eapol_fields
            })

            # Track the handshake
            self.handshakes.record_eapol(pkt, info)

        # ── Raw payload layer ──
        if pkt.haslayer(Raw):
            raw_data = bytes(pkt[Raw].load)
            payload_preview = raw_data[:64].decode('ascii', errors='replace')
            info["layers"].append({
                "name": f"Data ({len(raw_data)} bytes)",
                "fields": [
                    ("Length", len(raw_data)),
                    ("Preview", payload_preview),
                ]
            })

        return info

    def get_detail_text(self, pkt_info):
        """Format the layers list into a human-readable dissection string."""
        lines = []
        for layer in pkt_info.get("layers", []):
            lines.append(f"▼ {layer['name']}")
            for fname, fval in layer.get("fields", []):
                lines.append(f"    {fname}: {fval}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def get_hex_dump(data):
        """Format binary data as a classic hex/ASCII dump."""
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            lines.append(f"{i:06x}  {hex_part:<48}  │{ascii_part}│")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════
# SHADOW WALKER — Passive Vulnerability Analysis Engine
# ═══════════════════════════════════════════════════

class ShadowWalkerEngine:
    """
    Passive network vulnerability scanner.
    Analyzes every packet from EliteSnifferEngine for security issues.
    Cross-platform: Windows + Linux.
    """

    # Severity levels
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"

    # Well-known cleartext ports
    CLEARTEXT_PORTS = {
        21: "FTP", 23: "Telnet", 25: "SMTP", 80: "HTTP",
        110: "POP3", 143: "IMAP", 161: "SNMP", 389: "LDAP",
        513: "rlogin", 514: "rsh", 8080: "HTTP-Alt", 8000: "HTTP-Dev",
        1080: "SOCKS", 3128: "Proxy", 5900: "VNC",
    }

    # Suspicious TLDs / known-bad domain fragments for C2 detection
    SUSPICIOUS_TLDS = {
        ".xyz", ".top", ".tk", ".pw", ".cc", ".su", ".ru.com",
        ".cn.com", ".bid", ".click", ".download", ".gdn",
        ".racing", ".review", ".stream", ".win", ".loan",
    }

    SUSPICIOUS_DOMAIN_FRAGS = {
        "malware", "c2", "botnet", "evil", "exploit", "phish",
        "payload", "dropper", "ransomware", "backdoor", "trojan",
        "keylogger", "rat", "miner", "cryptojack",
    }

    def __init__(self):
        self.lock = threading.Lock()
        self.alerts = []            # List of alert dicts
        self.alert_count = 0
        self.severity_counts = {self.CRITICAL: 0, self.HIGH: 0, self.MEDIUM: 0, self.LOW: 0, self.INFO: 0}

        # Tracking state for stateful detections
        self._arp_table = {}        # ip → set(mac) for ARP spoofing detection
        self._port_scan_tracker = {}  # src_ip → {dst_ip: set(ports)} for port scan detection
        self._port_scan_threshold = 15  # ports from same src to same dst = scan
        self._dns_query_sizes = collections.defaultdict(lambda: collections.deque(maxlen=50)) 
        self._dns_tunnel_threshold = 5  # consecutive large DNS queries
        self._seen_cred_hashes = set()  # Prevent duplicate credential alerts
        self._cleartext_sessions = {}  # (src,dst,port) → timestamp
        self.start_time = None
        self.total_packets_analyzed = 0

        # Optimization: pre-calculate regex or patterns if any
        self._cookie_pattern = re.compile(r"(session|token|auth|jwt)", re.IGNORECASE)

    def reset(self):
        with self.lock:
            self.alerts.clear()
            self.alert_count = 0
            self.severity_counts = {self.CRITICAL: 0, self.HIGH: 0, self.MEDIUM: 0, self.LOW: 0, self.INFO: 0}
            self._arp_table.clear()
            self._port_scan_tracker.clear()
            self._dns_query_sizes.clear()
            self._seen_cred_hashes.clear()
            self._cleartext_sessions.clear()
            self.start_time = None
            self.total_packets_analyzed = 0

    def _add_alert(self, severity, category, title, detail, src="", dst="", proto="", raw_evidence="", exploit=""):
        """Thread-safe alert insertion with exploit suggestion."""
        alert = {
            "id": self.alert_count,
            "time": datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
            "severity": severity,
            "category": category,
            "title": title,
            "detail": detail,
            "src": src,
            "dst": dst,
            "proto": proto,
            "evidence": str(raw_evidence)[:512],
            "exploit": exploit
        }
        with self.lock:
            self.alerts.append(alert)
            self.alert_count += 1
            self.severity_counts[severity] = self.severity_counts.get(severity, 0) + 1
        return alert

    def get_alerts(self, severity_filter=None, limit=500):
        """Return alerts, optionally filtered by severity."""
        with self.lock:
            result = list(self.alerts)
        if severity_filter:
            result = [a for a in result if a["severity"] == severity_filter]
        return result[-limit:]

    def get_stats(self):
        """Return current scanner statistics."""
        with self.lock:
            elapsed = (datetime.datetime.now() - self.start_time).total_seconds() if self.start_time else 0
            return {
                "total_analyzed": self.total_packets_analyzed,
                "total_alerts": self.alert_count,
                "severity": dict(self.severity_counts),
                "elapsed": elapsed,
                "rate": self.total_packets_analyzed / elapsed if elapsed > 0 else 0,
            }

    def analyze(self, pkt_info):
        """
        Main entry point. Analyze a dissected packet dict from EliteSnifferEngine.
        Call this from the capture callback to get real-time vulnerability detection.
        Returns a list of new alerts generated for this packet (may be empty).
        """
        if self.start_time is None:
            self.start_time = datetime.datetime.now()

        self.total_packets_analyzed += 1
        new_alerts = []

        proto = pkt_info.get("proto", "RAW")
        src = pkt_info.get("src", "")
        dst = pkt_info.get("dst", "")
        sport = pkt_info.get("sport", 0) or 0
        dport = pkt_info.get("dport", 0) or 0
        info = pkt_info.get("info", "")
        domains = pkt_info.get("domains", [])
        urls = pkt_info.get("urls", [])
        layers = pkt_info.get("layers", [])
        pkt_len = pkt_info.get("len", 0)

        # Optimization: Only calculate raw_text if protocols might need it
        raw_text = ""
        if proto in ("HTTP", "TCP", "FTP", "POP3", "IMAP", "SMTP", "Telnet"):
            for layer in layers:
                for fname, fval in layer.get("fields", []):
                    if fname == "Preview":
                        raw_text = str(fval)
                        break
                if raw_text: break

        # 1. CLEARTEXT CREDENTIAL HARVESTING
        if proto in ("HTTP", "TCP"):
            new_alerts.extend(self._check_credentials(pkt_info, raw_text, src, dst, sport, dport))

        # 2. UNENCRYPTED COOKIE DETECTION
        if proto == "HTTP":
            new_alerts.extend(self._check_cookies(pkt_info, raw_text, src, dst))

        # 3. CLEARTEXT PROTOCOL USAGE
        if proto == "TCP" and dport in self.CLEARTEXT_PORTS:
            new_alerts.extend(self._check_cleartext_service(src, dst, dport))

        # 4. WEAK / DEPRECATED TLS DETECTION
        if proto == "TLS":
            new_alerts.extend(self._check_tls(pkt_info, src, dst))

        # 5. ARP SPOOFING DETECTION
        if proto == "ARP":
            new_alerts.extend(self._check_arp_spoof(pkt_info, src, dst))

        # 6. SUSPICIOUS DNS (C2, Tunneling, Exfil)
        if proto == "DNS" and domains:
            new_alerts.extend(self._check_dns(pkt_info, domains, src, dst, pkt_len))

        # 6.1 WEB VULNERABILITY DETECTION
        if urls:
            new_alerts.extend(self._check_web_vulnerabilities(urls, src, dst))

        # 7. PORT SCAN DETECTION
        if proto == "TCP":
            flags = pkt_info.get("tcp_flags", 0)
            if flags & 0x02 and not (flags & 0x10):  # SYN only
                new_alerts.extend(self._check_port_scan(src, dst, dport))

        # 8. LARGE DATA EXFILTRATION DETECTION
        if pkt_len > 10000 and proto in ("TCP", "HTTP", "UDP"):
            new_alerts.extend(self._check_exfiltration(src, dst, proto, pkt_len))

        # 9. EAPOL / DEAUTH FLOOD DETECTION
        if proto == "EAPOL":
            a = self._add_alert(
                self.HIGH, "WIRELESS", "EAPOL Handshake Detected",
                "WPA 4-way handshake activity detected. Someone may be performing a deauth/capture attack.",
                src=src, dst=dst, proto=proto, raw_evidence=info,
                exploit=f"techbot gethash bssid={src}"
            )
            new_alerts.append(a)

        return new_alerts

    # ── Detection Modules ──

    def _check_credentials(self, pkt_info, raw_text, src, dst, sport, dport):
        """Detect cleartext credentials in FTP, Telnet, HTTP Basic Auth, POP3, IMAP, SMTP."""
        alerts = []
        text_lower = raw_text.lower()

        # HTTP Basic Auth (base64 encoded but trivially decoded)
        info_str = pkt_info.get("info", "")
        for layer in pkt_info.get("layers", []):
            for fname, fval in layer.get("fields", []):
                fval_str = str(fval)
                if "authorization" in str(fname).lower() and "basic" in fval_str.lower():
                    cred_hash = hash(fval_str)
                    if cred_hash not in self._seen_cred_hashes:
                        self._seen_cred_hashes.add(cred_hash)
                        decoded = ""
                        try:
                            import base64
                            b64_part = fval_str.split("Basic ")[-1].strip()
                            decoded = base64.b64decode(b64_part).decode(errors='ignore')
                        except Exception:
                            decoded = fval_str
                        a = self._add_alert(
                            self.CRITICAL, "CREDENTIALS",
                            "HTTP Basic Auth Credentials (Cleartext)",
                            f"Intercepted HTTP Basic Auth credentials in cleartext.\n"
                            f"Decoded: {decoded}\nHeader: {fval_str}",
                            src=src, dst=dst, proto="HTTP", raw_evidence=fval_str,
                            exploit=f"techbot brute {src}"
                        )
                        alerts.append(a)

        # FTP USER/PASS
        if dport == 21 or sport == 21:
            if "user " in text_lower or "pass " in text_lower:
                cred_hash = hash(raw_text.strip())
                if cred_hash not in self._seen_cred_hashes:
                    self._seen_cred_hashes.add(cred_hash)
                    a = self._add_alert(
                        self.CRITICAL, "CREDENTIALS",
                        "FTP Credentials (Cleartext)",
                        f"FTP login credentials transmitted in cleartext.\nPayload: {raw_text.strip()[:200]}",
                        src=src, dst=dst, proto="FTP", raw_evidence=raw_text[:200],
                        exploit=f"techbot brute {dst}"
                    )
                    alerts.append(a)

        # Telnet
        if dport == 23 or sport == 23:
            if "login:" in text_lower or "password:" in text_lower or len(raw_text.strip()) > 2:
                cred_hash = hash(f"telnet-{src}-{dst}")
                if cred_hash not in self._seen_cred_hashes:
                    self._seen_cred_hashes.add(cred_hash)
                    a = self._add_alert(
                        self.CRITICAL, "CREDENTIALS",
                        "Telnet Session Detected (Cleartext)",
                        f"Active Telnet session detected. All data transmits in cleartext.\n"
                        f"Any credentials typed are fully visible to interceptors.",
                        src=src, dst=dst, proto="Telnet", raw_evidence=raw_text[:200],
                        exploit=f"techbot brute {dst}"
                    )
                    alerts.append(a)

        # POP3 / IMAP
        if dport in (110, 143) or sport in (110, 143):
            mail_proto = "POP3" if dport == 110 or sport == 110 else "IMAP"
            if "user " in text_lower or "login " in text_lower or "pass " in text_lower:
                cred_hash = hash(f"{mail_proto}-{src}-{dst}")
                if cred_hash not in self._seen_cred_hashes:
                    self._seen_cred_hashes.add(cred_hash)
                    a = self._add_alert(
                        self.CRITICAL, "CREDENTIALS",
                        f"{mail_proto} Credentials (Cleartext)",
                        f"Email login credentials sent over unencrypted {mail_proto}.\n"
                        f"Payload: {raw_text.strip()[:200]}",
                        src=src, dst=dst, proto=mail_proto, raw_evidence=raw_text[:200],
                        exploit=f"techbot brute {dst}"
                    )
                    alerts.append(a)

        # SMTP Auth
        if dport == 25 or sport == 25:
            if "auth " in text_lower or "ehlo" in text_lower:
                cred_hash = hash(f"smtp-{src}-{dst}")
                if cred_hash not in self._seen_cred_hashes:
                    self._seen_cred_hashes.add(cred_hash)
                    a = self._add_alert(
                        self.HIGH, "CREDENTIALS",
                        "SMTP Session Detected (Cleartext)",
                        "Unencrypted SMTP session detected. Email content and credentials may be visible.",
                        src=src, dst=dst, proto="SMTP", raw_evidence=raw_text[:200],
                        exploit=f"techbot brute {dst}"
                    )
                    alerts.append(a)

        return alerts

    def _check_cookies(self, pkt_info, raw_text, src, dst):
        """Detect HTTP cookies transmitted without encryption."""
        alerts = []
        for layer in pkt_info.get("layers", []):
            for fname, fval in layer.get("fields", []):
                fname_lower = str(fname).lower()
                fval_str = str(fval)
                if fname_lower == "cookie" or fname_lower == "set-cookie":
                    sensitive_flags = []
                    fval_lower = fval_str.lower()
                    if "session" in fval_lower or "token" in fval_lower or "auth" in fval_lower or "jwt" in fval_lower:
                        sensitive_flags.append("Contains session/auth tokens")
                    if "secure" not in fval_lower:
                        sensitive_flags.append("Missing 'Secure' flag")
                    if "httponly" not in fval_lower:
                        sensitive_flags.append("Missing 'HttpOnly' flag")

                    severity = self.HIGH if sensitive_flags else self.MEDIUM
                    cookie_hash = hash(fval_str[:100])
                    if cookie_hash not in self._seen_cred_hashes:
                        self._seen_cred_hashes.add(cookie_hash)
                        a = self._add_alert(
                            severity, "COOKIES",
                            "Unencrypted HTTP Cookie Detected",
                            f"Cookie transmitted over cleartext HTTP.\n"
                            f"Issues: {', '.join(sensitive_flags) if sensitive_flags else 'Unencrypted transport'}\n"
                            f"Cookie: {fval_str[:300]}",
                            src=src, dst=dst, proto="HTTP",
                            raw_evidence=fval_str[:300],
                            exploit=f"techbot brute {dst}"
                        )
                        alerts.append(a)
        return alerts

    def _check_cleartext_service(self, src, dst, dport):
        """Alert on connections to well-known cleartext services."""
        alerts = []
        session_key = (src, dst, dport)
        if session_key not in self._cleartext_sessions:
            self._cleartext_sessions[session_key] = True
            service = self.CLEARTEXT_PORTS.get(dport, f"Port {dport}")
            severity = self.HIGH if dport in (21, 23, 110, 143, 389) else self.MEDIUM
            a = self._add_alert(
                severity, "CLEARTEXT",
                f"Cleartext {service} Connection Detected",
                f"Connection to {service} (port {dport}) uses NO encryption.\n"
                f"All data including credentials is transmitted in plaintext.\n"
                f"Recommendation: Use the encrypted alternative (SFTP, SSH, HTTPS, etc.)",
                src=src, dst=dst, proto=service,
                exploit=f"techbot fuzz {dst}"
            )
            alerts.append(a)
        return alerts

    def _check_tls(self, pkt_info, src, dst):
        """Detect weak or deprecated TLS versions."""
        alerts = []
        raw_pkt = pkt_info.get("raw", None)
        if raw_pkt is None:
            return alerts

        try:
            if raw_pkt.haslayer(Raw):
                raw_data = bytes(raw_pkt[Raw].load)
                # TLS record header: content_type(1) + version(2) + length(2)
                if len(raw_data) >= 5 and raw_data[0] == 0x16:  # Handshake
                    major = raw_data[1]
                    minor = raw_data[2]
                    version_name = ""
                    severity = None

                    if major == 3 and minor == 0:
                        version_name = "SSLv3.0"
                        severity = self.CRITICAL
                    elif major == 3 and minor == 1:
                        version_name = "TLS 1.0"
                        severity = self.HIGH
                    elif major == 3 and minor == 2:
                        version_name = "TLS 1.1"
                        severity = self.MEDIUM

                    if severity:
                        tls_hash = hash(f"tls-{src}-{dst}-{version_name}")
                        if tls_hash not in self._seen_cred_hashes:
                            self._seen_cred_hashes.add(tls_hash)
                            a = self._add_alert(
                                severity, "TLS",
                                f"Deprecated {version_name} Detected",
                                f"Connection using {version_name} which is cryptographically weak.\n"
                                f"Known vulnerabilities: POODLE, BEAST, CRIME attacks.\n"
                                f"Recommendation: Upgrade to TLS 1.2 or TLS 1.3.",
                                src=src, dst=dst, proto="TLS",
                                raw_evidence=f"Version bytes: {major}.{minor}"
                            )
                            alerts.append(a)
        except Exception:
            pass
        return alerts

    def _check_arp_spoof(self, pkt_info, src, dst):
        """Detect ARP cache poisoning by tracking IP-to-MAC mappings."""
        alerts = []
        # Extract MAC from layers
        sender_mac = ""
        sender_ip = src
        for layer in pkt_info.get("layers", []):
            if layer.get("name") == "ARP":
                for fname, fval in layer.get("fields", []):
                    if fname == "Sender MAC":
                        sender_mac = str(fval)
                    elif fname == "Sender IP":
                        sender_ip = str(fval)

        if sender_ip and sender_mac:
            if sender_ip in self._arp_table:
                known_macs = self._arp_table[sender_ip]
                if sender_mac not in known_macs:
                    # IP was previously associated with a different MAC!
                    old_macs = ", ".join(known_macs)
                    a = self._add_alert(
                        self.CRITICAL, "ARP SPOOF",
                        f"ARP Spoofing Detected — {sender_ip}",
                        f"IP address {sender_ip} is now associated with MAC {sender_mac},\n"
                        f"but was previously seen with MAC(s): {old_macs}.\n"
                        f"This is a strong indicator of an active ARP poisoning / MITM attack.\n"
                        f"Recommendation: Investigate immediately. Use static ARP entries.",
                        src=sender_ip, dst=dst, proto="ARP",
                        raw_evidence=f"Old: {old_macs} → New: {sender_mac}",
                        exploit=f"techbot arpspoof {sender_ip} {dst}"
                    )
                    alerts.append(a)
                    known_macs.add(sender_mac)
            else:
                self._arp_table[sender_ip] = {sender_mac}

        return alerts

    def _check_dns(self, pkt_info, domains, src, dst, pkt_len):
        """Detect suspicious DNS: C2 domains, DNS tunneling, data exfiltration."""
        alerts = []

        for domain in domains:
            domain_lower = domain.lower()

            # Check against suspicious TLDs
            for tld in self.SUSPICIOUS_TLDS:
                if domain_lower.endswith(tld):
                    a = self._add_alert(
                        self.MEDIUM, "DNS",
                        f"Suspicious TLD: {domain}",
                        f"DNS query to domain with suspicious TLD ({tld}).\n"
                        f"These TLDs are commonly associated with malware, phishing, and C2 infrastructure.",
                        src=src, dst=dst, proto="DNS", raw_evidence=domain
                    )
                    alerts.append(a)
                    break

            # Check for known-bad domain fragments
            for frag in self.SUSPICIOUS_DOMAIN_FRAGS:
                if frag in domain_lower:
                    a = self._add_alert(
                        self.HIGH, "DNS",
                        f"Suspicious Domain: {domain}",
                        f"DNS query contains known malicious keyword '{frag}'.\n"
                        f"Possible C2, malware callback, or phishing infrastructure.",
                        src=src, dst=dst, proto="DNS", raw_evidence=domain
                    )
                    alerts.append(a)
                    break

            # DNS Tunneling detection: very long subdomain labels
            labels = domain_lower.split(".")
            long_labels = [l for l in labels if len(l) > 40]
            if long_labels:
                a = self._add_alert(
                    self.HIGH, "DNS TUNNEL",
                    f"Possible DNS Tunneling: {domain[:60]}...",
                    f"DNS query has unusually long subdomain labels (>{40} chars).\n"
                    f"This is a classic indicator of DNS tunneling / data exfiltration.\n"
                    f"Tools: iodine, dnscat2, dns2tcp.",
                    src=src, dst=dst, proto="DNS", raw_evidence=domain,
                    exploit=f"techbot dnsspoof {domain} 127.0.0.1"
                )
                alerts.append(a)

            # DNS query frequency anomaly (many large queries from same source)
            self._dns_query_sizes[src].append(len(domain))
            q_sizes = list(self._dns_query_sizes[src])
            recent_large = sum(1 for s in q_sizes[-10:] if s > 30)
            if recent_large >= self._dns_tunnel_threshold:
                tunnel_hash = hash(f"dnstunnel-{src}")
                if tunnel_hash not in self._seen_cred_hashes:
                    self._seen_cred_hashes.add(tunnel_hash)
                    a = self._add_alert(
                        self.HIGH, "DNS TUNNEL",
                        f"DNS Tunneling Pattern from {src}",
                        f"Source {src} has sent {recent_large} large DNS queries in the last 10 packets.\n"
                        f"Average query length: {sum(q_sizes[-10:]) / 10:.0f} chars.\n"
                        f"This strongly suggests DNS tunneling for data exfiltration.",
                        src=src, dst=dst, proto="DNS"
                    )
                    alerts.append(a)

        return alerts

    def _check_web_vulnerabilities(self, urls, src, dst):
        """Detect SQLi, XSS, and other web attack patterns in URLs."""
        alerts = []
        sqli_patterns = [r"(' OR '1'='1)", r"(-- )", r"(union select)", r"(select @@version)"]
        xss_patterns = [r"(<script>)", r"(alert\()", r"(onerror=)", r"(javascript:)"]
        
        for url in urls:
            url_lower = url.lower()
            for pattern in sqli_patterns:
                if re.search(pattern, url_lower):
                    a = self._add_alert(
                        self.HIGH, "WEB VULN", "Possible SQL Injection Pattern",
                        f"Detected SQL injection pattern in URL.\nPattern: {pattern}\nURL: {url}",
                        src=src, dst=dst, proto="HTTP", raw_evidence=url,
                        exploit=f"techbot fuzz {dst}"
                    )
                    alerts.append(a)
                    break
            
            for pattern in xss_patterns:
                if re.search(pattern, url_lower):
                    a = self._add_alert(
                        self.HIGH, "WEB VULN", "Possible XSS Pattern",
                        f"Detected Cross-Site Scripting (XSS) pattern in URL.\nPattern: {pattern}\nURL: {url}",
                        src=src, dst=dst, proto="HTTP", raw_evidence=url,
                        exploit=f"techbot brute {dst}"
                    )
                    alerts.append(a)
                    break
        return alerts

    def _check_port_scan(self, src, dst, dport):
        """Detect port scanning by tracking SYN packets from same source."""
        alerts = []
        if src not in self._port_scan_tracker:
            self._port_scan_tracker[src] = {}
        if dst not in self._port_scan_tracker[src]:
            self._port_scan_tracker[src][dst] = set()

        self._port_scan_tracker[src][dst].add(dport)
        port_count = len(self._port_scan_tracker[src][dst])

        # Alert at threshold crossings
        if port_count == self._port_scan_threshold:
            a = self._add_alert(
                self.HIGH, "PORT SCAN",
                f"Port Scan Detected: {src} → {dst}",
                f"Source {src} has sent SYN packets to {port_count} different ports on {dst}.\n"
                f"Ports probed: {sorted(list(self._port_scan_tracker[src][dst]))[:20]}\n"
                f"This is a strong indicator of host reconnaissance / service enumeration.",
                src=src, dst=dst, proto="TCP",
                exploit=f"techbot flood {src} 80"
            )
            alerts.append(a)
        elif port_count > 0 and port_count % 50 == 0:
            a = self._add_alert(
                self.CRITICAL, "PORT SCAN",
                f"Aggressive Port Scan: {src} → {dst} ({port_count} ports)",
                f"Massive port scan in progress. {port_count} unique ports probed.\n"
                f"This may indicate an automated scanner like Nmap, Masscan, or similar.",
                src=src, dst=dst, proto="TCP"
            )
            alerts.append(a)

        return alerts

    def _check_exfiltration(self, src, dst, proto, pkt_len):
        """Flag unusually large data transfers that could indicate exfiltration."""
        alerts = []
        exfil_hash = hash(f"exfil-{src}-{dst}-{pkt_len // 5000}")
        if exfil_hash not in self._seen_cred_hashes:
            self._seen_cred_hashes.add(exfil_hash)
            size_kb = pkt_len / 1024
            severity = self.MEDIUM if pkt_len < 50000 else self.HIGH
            a = self._add_alert(
                severity, "DATA EXFIL",
                f"Large Data Transfer: {size_kb:.1f} KB",
                f"Unusually large packet ({size_kb:.1f} KB) from {src} to {dst}.\n"
                f"Protocol: {proto}.\n"
                f"Large transfers to external IPs may indicate data exfiltration.",
                src=src, dst=dst, proto=proto
            )
            alerts.append(a)
        return alerts


# ═══════════════════════════════════════════════════
# Standalone test
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    if not SCAPY_OK:
        print("Scapy not installed. Run: pip install scapy")
        exit(1)

    engine = EliteSnifferEngine()
    print("Starting 10-second test capture...")

    def cb(p):
        proto = p.get("proto", "?")
        src = p.get("src", "?")
        dst = p.get("dst", "?")
        info = p.get("info", "")
        domains = p.get("domains", [])
        urls = p.get("urls", [])
        line = f"[{proto:^5}] {src} → {dst} | {info}"
        if domains:
            line += f"  DOMAIN: {', '.join(domains)}"
        if urls:
            line += f"  URL: {', '.join(urls)}"
        print(line)

    engine.start_capture(cb)
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        pass
    engine.stop_capture()

    snap = engine.stats.get_snapshot()
    print(f"\n── Stats ──")
    print(f"Total: {snap['total_packets']} packets, {snap['total_bytes']} bytes")
    print(f"Rate: {snap['pps']:.1f} pkt/s, {snap['bps']:.0f} B/s")
    print(f"Protocols: {snap['proto_counts']}")
    if snap['top_domains']:
        print(f"Top Domains: {snap['top_domains'][:5]}")

    fname, count = engine.export_pcap()
    print(f"Exported {count} packets to {fname}")
