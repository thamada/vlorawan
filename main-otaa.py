# -*- coding: utf-8 -*-
import os
import socket
import time
import json
import base64
import random
import struct
from datetime import datetime

from Crypto.Cipher import AES
from Crypto.Hash import CMAC
from cayennelpp import LppFrame

# LoRaWAN 1.0.3 constants
LORAWAN_VERSION = "1.0.3"
MHDR_JOIN_REQUEST = 0x00
MHDR_UNCONFIRMED_DATA_UP = 0x40
JOIN_REQUEST_SIZE = 23
UDP_IP = "au1.cloud.thethings.network"
UDP_PORT = 1700
GATEWAY_EUI = bytes.fromhex("F000000000000001")

# Device credentials (replace with your actual values)
JOIN_EUI = bytes.fromhex("123400000000000F")[::-1]    # LSB
DEV_EUI = bytes.fromhex("0123456789ABCDEF")[::-1]     # LSB
APP_KEY = bytes.fromhex("0123456789ABCDEF0123456789ABCDEF")

# Global session variables (初期化はreset_session()で実施)
dev_nonce = None
app_nonce = None
net_id = None
dev_addr = None
nwk_skey = None
app_skey = None
frame_counter = 0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(5.0)

# === Session Reset Function ===
def reset_session():
    global dev_nonce, app_nonce, net_id, dev_addr, nwk_skey, app_skey, frame_counter
    dev_nonce = os.urandom(2)  # 新たなランダムなNonceを生成
    app_nonce = None
    net_id = None
    dev_addr = None
    nwk_skey = None
    app_skey = None
    frame_counter = 0

# プログラム開始時にセッションをリセット
reset_session()

# === Utility functions ===
def aes_encrypt_block(key, data):
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(data)

def derive_session_key(key, type_byte, appnonce, netid, devnonce):
    block = bytes([type_byte]) + appnonce + netid + devnonce + bytes(7)
    return aes_encrypt_block(key, block)

def cmac_hash(key, msg):
    cobj = CMAC.new(key, ciphermod=AES)
    cobj.update(msg)
    return cobj.digest()[:4]

def calculate_mic(nwk_skey, msg, devaddr, fcnt, direction=0x00):
    b0 = bytes([
        0x49,
        0x00, 0x00, 0x00, 0x00,
        direction,
    ]) + devaddr + fcnt.to_bytes(4, 'little') + bytes([0x00, len(msg)])
    cobj = CMAC.new(nwk_skey, ciphermod=AES)
    cobj.update(b0 + msg)
    return cobj.digest()[:4]

def send_pull_data():
    token = os.urandom(2)
    header = struct.pack('>B2sB8s', 2, token, 2, GATEWAY_EUI)
    sock.sendto(header, (UDP_IP, UDP_PORT))

def send_push_data(payload):
    token = os.urandom(2)
    header = struct.pack('>B2sB8s', 2, token, 0, GATEWAY_EUI)
    sock.sendto(header + payload.encode(), (UDP_IP, UDP_PORT))

def create_join_request():
    global dev_nonce
    # Joinリクエスト送信直前にdev_nonceを再生成
    dev_nonce = os.urandom(2)
    msg = bytes([MHDR_JOIN_REQUEST]) + JOIN_EUI + DEV_EUI + dev_nonce
    mic = cmac_hash(APP_KEY, msg)
    return msg + mic

def wrap_rxpk(phy_payload):
    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    rxpk = {
        "rxpk": [{
            "time": now,
            "tmst": int(time.time() * 1e6) % (2**32),
            "chan": 0,
            "rfch": 0,
            "freq": 923.2,
            "stat": 1,
            "modu": "LORA",
            "datr": "SF7BW125",
            "codr": "4/5",
            "rssi": -30,
            "lsnr": 5.5,
            "size": len(phy_payload),
            "data": base64.b64encode(phy_payload).decode()
        }]
    }
    return json.dumps(rxpk)

def decrypt_join_accept(payload):
    cipher = AES.new(APP_KEY, AES.MODE_ECB)
    mhdr = payload[0:1]
    #decrypted_payload = cipher.decrypt(payload[1:17])
    decrypted_payload = cipher.encrypt(payload[1:17])
    return mhdr + decrypted_payload  # full decrypted join accept

def parse_join_accept(decrypted):
    global app_nonce, net_id, dev_addr
    app_nonce = decrypted[1:4]
    net_id = decrypted[4:7]
    dev_addr = decrypted[7:11]
    print(f"[+] Joined. DevAddr: {dev_addr[::-1].hex().upper()}")

def derive_session_keys():
    global nwk_skey, app_skey
    nwk_skey = derive_session_key(APP_KEY, 0x01, app_nonce, net_id, dev_nonce)
    app_skey = derive_session_key(APP_KEY, 0x02, app_nonce, net_id, dev_nonce)

def encrypt_payload(payload, key, devaddr, fcnt, direction=0x00):
    """ LoRaWAN 1.0.x FRMPayload encryption using AES-128 in CTR mode """
    cipher = AES.new(key, AES.MODE_ECB)
    enc = bytearray()
    k = 1
    for i in range(0, len(payload), 16):
        block = bytes([
            0x01,
            0x00, 0x00, 0x00, 0x00,  # 4 bytes zeros
            direction,               # 0 = uplink
        ]) + devaddr + fcnt.to_bytes(4, 'little') + bytes([0x00, k])
        s = cipher.encrypt(block)
        chunk = payload[i:i+16]
        enc.extend([a ^ b for a, b in zip(chunk, s)])
        k += 1
    return bytes(enc)

def send_uplink():
    global frame_counter
    frame = LppFrame()
    frame.add_temperature(1, round(20.0 + random.uniform(-2, 2), 1))
    frame.add_humidity(2, round(50.0 + random.uniform(-5, 5), 1))
    frame.add_gps(3, 35.6812, 139.7671, 10)  # 東京駅付近
    frame.add_digital_input(4, frame_counter % 256)
    payload = bytes(frame)

    fcnt = frame_counter.to_bytes(2, 'little')
    fctrl = b'\x00'
    fport = b'\x01'

    # FRMPayload を暗号化
    enc_payload = encrypt_payload(payload, app_skey, dev_addr, frame_counter)
    # LoRaWAN PHYPayload 組み立て
    msg = bytes([MHDR_UNCONFIRMED_DATA_UP]) + dev_addr + fctrl + fcnt + fport + enc_payload
    # MIC を計算
    mic = calculate_mic(nwk_skey, msg, dev_addr, frame_counter)
    phy_payload = msg + mic

    # UDP 送信用 JSON にラップして送信
    json_payload = wrap_rxpk(phy_payload)
    send_push_data(json_payload)

    print(f"[>] Uplink #{frame_counter} sent.")
    frame_counter += 1

# === Main Join Procedure ===
join_payload = create_join_request()
json_payload = wrap_rxpk(join_payload)
send_push_data(json_payload)
print("[>] Join Request sent")

# Wait for Join Accept
send_pull_data()
while True:
    try:
        data, _ = sock.recvfrom(1024)
        if data[3] == 0x03:  # PULL_RESP
            resp = json.loads(data[4:].decode())
            txpk = resp.get("txpk", {})
            phy = base64.b64decode(txpk.get("data", ""))
            decrypted = decrypt_join_accept(phy)
            parse_join_accept(decrypted)
            derive_session_keys()
            break
    except socket.timeout:
        print("[!] Timeout waiting for Join Accept, retrying...")
        send_push_data(json_payload)
        send_pull_data()

# === Periodic Uplink ===
while True:
    send_uplink()
    time.sleep(30)

