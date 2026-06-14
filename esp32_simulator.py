"""
Simulasi ESP32 Pabook — esp32_simulator.py
Jalankan: python esp32_simulator.py
Butuh: pip install requests
"""

import requests
import time

SERVER_URL = "https://web-production-34d64b.up.railway.app"

GATES = [
    {"id": "GATE-MASUK-A",  "type": "masuk"},
    {"id": "GATE-KELUAR-A", "type": "keluar"},
]

POLL_INTERVAL = 1.5  # detik


def buka_gate(gate, slot, vehicle):
    print(f"\n  🟢 [{gate['type'].upper()}] GATE BUKA")
    print(f"     Slot   : {slot}")
    print(f"     Kendaraan: {vehicle}")
    print(f"     (simulasi servo 90°)\n")
    # Lapor status ke server
    try:
        requests.post(f"{SERVER_URL}/api/gate/status", json={
            "gate_id": gate["id"],
            "state":   "open",
            "type":    gate["type"],
        }, timeout=3)
    except:
        pass
    time.sleep(3)  # simulasi gate terbuka 3 detik
    tutup_gate(gate)


def tutup_gate(gate):
    print(f"  🔴 [{gate['type'].upper()}] GATE TUTUP (simulasi servo 0°)")
    try:
        requests.post(f"{SERVER_URL}/api/gate/status", json={
            "gate_id": gate["id"],
            "state":   "closed",
            "type":    gate["type"],
        }, timeout=3)
    except:
        pass


def poll(gate):
    try:
        res = requests.get(
            f"{SERVER_URL}/api/gate/poll",
            params={"gate_id": gate["id"]},
            timeout=3
        )
        data = res.json()
        if data.get("has_command"):
            cmd     = data.get("command")
            slot    = data.get("slot",    "?")
            vehicle = data.get("vehicle", "?")
            print(f"  📡 [{gate['type'].upper()}] Perintah: {cmd} | Slot: {slot} | {vehicle}")
            if cmd == "open":
                buka_gate(gate, slot, vehicle)
            elif cmd == "close":
                tutup_gate(gate)
    except requests.exceptions.ConnectionError:
        print("  ⚠️  Tidak bisa konek ke server, coba lagi...")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")


def ping():
    try:
        res  = requests.get(f"{SERVER_URL}/api/ping", timeout=5)
        data = res.json()
        print(f"  ✅ Server OK | Slot: {data['available_slots']}/{data['total_slots']} tersedia")
        return True
    except:
        print("  ❌ Server tidak bisa dihubungi — cek SERVER_URL")
        return False


def main():
    print("=" * 50)
    print("  Pabook ESP32 Simulator")
    print(f"  Server : {SERVER_URL}")
    print(f"  Gates  : {', '.join(g['id'] for g in GATES)}")
    print("=" * 50)

    print("\n  Ping server...")
    if not ping():
        return

    print(f"\n  Polling tiap {POLL_INTERVAL} detik — tekan Ctrl+C untuk stop\n")

    while True:
        for gate in GATES:
            poll(gate)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Simulator dihentikan.")