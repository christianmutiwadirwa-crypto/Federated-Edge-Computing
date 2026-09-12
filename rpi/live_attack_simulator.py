import socket
import struct
import time
import random
import argparse
import sys
import os

TARGET_IP = "127.0.0.1"
TARGET_PORT = 9000

def _crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def generate_valid_payload(node_id=1, seq=0) -> bytes:
    magic = 0xABCD
    version = 1
    ts_ms = int(time.time() * 1000)
    # Simulate normal vibration
    floats = [random.gauss(0, 1.0) for _ in range(27)]
    body = struct.pack("<HBBIQfffffffffffffffffffffffffff",
                       magic, version, node_id, seq, ts_ms, *floats)
    crc = _crc16_ccitt(body)
    return body + struct.pack("<H", crc)

def attack_flooding():
    print("[*] Launching Flooding Attack... (Press Ctrl+C to stop)")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((TARGET_IP, TARGET_PORT))
    seq = 0
    try:
        while True:
            s.sendall(generate_valid_payload(node_id=1, seq=seq))
            seq += 1
            time.sleep(0.001)  # 1000 packets per second
    except KeyboardInterrupt:
        s.close()

def attack_slowdos():
    print("[*] Launching SlowDoS Attack... (Press Ctrl+C to stop)")
    # The MLP detects SlowDoS via `window_active_span` and low `packet_rate`.
    # We send valid packets but trickle them at 1.8s intervals (just under the 2s window)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((TARGET_IP, TARGET_PORT))
    seq = 0
    try:
        while True:
            # Use node_id=2 so it goes through the MLP instead of triggering the hybrid override
            payload = generate_valid_payload(node_id=2, seq=seq)
            s.sendall(payload)
            seq += 1
            # The SlowDoS training script used a delay of 5s to 25s between packets.
            # We use 6 seconds to guarantee it creates empty 2-second windows, driving
            # down the overall packet rate to match the SlowDoS detection features!
            time.sleep(6.0)
    except KeyboardInterrupt:
        s.close()

def attack_crc_forged():
    print("[*] Launching CRC Forged Attack... (Press Ctrl+C to stop)")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((TARGET_IP, TARGET_PORT))
    seq = 0
    try:
        while True:
            # The training dataset for CRC Forged spoofed a completely random Node ID on every single packet!
            # This causes the packets to distribute across 256 different windows, keeping the `packet_rate`
            # extremely low so it doesn't get flagged as Flooding, while forcing the model to evaluate the corrupted payload.
            magic = 0xABCD
            version = 1
            node_id = random.randint(3, 255) # Use random Node IDs to match the dataset!
            ts_ms = int(time.time() * 1000)
            floats = [random.uniform(-50, 50) for _ in range(27)]
            
            body = struct.pack("<HBBIQfffffffffffffffffffffffffff",
                               magic, version, node_id, seq, ts_ms, *floats)
            crc = _crc16_ccitt(body)
            payload = body + struct.pack("<H", crc)
            
            s.sendall(payload)
            seq += 1
            time.sleep(0.01) 
    except KeyboardInterrupt:
        s.close()

def attack_malformed():
    print("[*] Launching Malformed Injection... (Press Ctrl+C to stop)")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((TARGET_IP, TARGET_PORT))
    try:
        while True:
            # Send complete garbage bytes
            s.sendall(os.urandom(126) if 'os' in sys.modules else b'\x00' * 126)
            time.sleep(0.1)
    except KeyboardInterrupt:
        s.close()
        
def attack_replay():
    print("[*] Launching Replay / Duplicate Packet Attack... (Press Ctrl+C to stop)")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((TARGET_IP, TARGET_PORT))
    try:
        # Use node_id=2 so it maintains a clean sequence counter without mixing with Node 1
        stolen_packet = generate_valid_payload(node_id=2, seq=42)
        while True:
            # Play it back infinitely. Because the sequence number is 42 every time, 
            # ConnectionStateManager will correctly flag is_duplicate=True!
            s.sendall(stolen_packet)
            time.sleep(0.05)
    except KeyboardInterrupt:
        s.close()

def main():
    parser = argparse.ArgumentParser(description="Live Attack Simulator (Dashboard Testing)")
    parser.add_argument("attack", choices=["flooding", "slowdos", "crcforged", "malformed", "replay"],
                        help="The type of attack to launch against the EdgeNode")
    
    args = parser.parse_args()
    
    try:
        if args.attack == "flooding": attack_flooding()
        elif args.attack == "slowdos": attack_slowdos()
        elif args.attack == "crcforged": attack_crc_forged()
        elif args.attack == "malformed": attack_malformed()
        elif args.attack == "replay": attack_replay()
    except ConnectionRefusedError:
        print("[!] Connection refused. Is the EdgeNode (main.py) running on port 9000?")
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    main()
