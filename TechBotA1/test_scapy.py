from scapy.all import sniff, arping, conf
import sys

print(f"Scapy version: {conf.version}")
try:
    print("Testing sniff (timeout 2s)...")
    sniff(count=1, timeout=2)
    print("Sniff OK")
except Exception as e:
    print(f"Sniff FAILED: {e}")

try:
    print("Testing ARPing (timeout 2s)...")
    # Just try to resolve gateway
    arping("192.168.1.1", timeout=2, verbose=0)
    print("ARPing OK")
except Exception as e:
    print(f"ARPing FAILED: {e}")
