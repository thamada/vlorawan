# -*- coding: utf-8 -*-

# main-otaa.pyをABP用に変更したコード:
# main-otaa.pyでのOTAA Join手順は不要なため、
# 静的に設定された DevAddr、AppSKey、NwkSKey を用いてセッションを開始し、
# 定期的に Cayenne LPPフォーマットのペイロードを暗号化したuplinkをTTNへ送信します。

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
MHDR_UNCONFIRMED_DATA_UP = 0x40
UDP_IP = "au1.cloud.thethings.network"
UDP_PORT = 1700
GATEWAY_EUI = bytes.fromhex("001B1A0000000002")

# -------------------------------
# ABP 用の静的パラメータ
# -------------------------------
# DevEUI (参考情報として使用、ABP では Join は行いません)
DEV_EUI = bytes.fromhex("0123456789ABCDEF")[::-1]  # LSB
# デバイスアドレス（DevAddr）：指定された値をリトルエンディアンに変換
dev_addr = bytes.fromhex("12345678")[::-1]
# アプリケーションセッションキー (AppSKey)
app_skey = bytes.fromhex("0123456789ABCDEF0123456789ABCDEF")
# ネットワークセッションキー (NwkSKey)
nwk_skey = bytes.fromhex("0123456789ABCDEF0123456789ABCDEF")
# -------------------------------

# フレームカウンターの初期化
frame_counter = 0

# UDP ソケットの初期化
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(5.0)

# === Utility Functions ===
def aes_encrypt_block(key, data):
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(data)

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
            "rssi": -129,
            "lsnr": 5.5,
            "size": len(phy_payload),
            "data": base64.b64encode(phy_payload).decode()
        }]
    }
    return json.dumps(rxpk)

def encrypt_payload(payload, key, devaddr, fcnt, direction=0x00):
    """ LoRaWAN 1.0.x FRMPayload を AES-128 CTR モードで暗号化 """
    cipher = AES.new(key, AES.MODE_ECB)
    enc = bytearray()
    k = 1
    for i in range(0, len(payload), 16):
        block = bytes([
            0x01,
            0x00, 0x00, 0x00, 0x00,  # 4 bytes zeros
            direction,
        ]) + devaddr + fcnt.to_bytes(4, 'little') + bytes([0x00, k])
        s = cipher.encrypt(block)
        chunk = payload[i:i+16]
        enc.extend([a ^ b for a, b in zip(chunk, s)])
        k += 1
    return bytes(enc)

def send_uplink():
    global frame_counter
    # Cayenne LPP フレーム作成
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
    # MIC の計算
    mic = calculate_mic(nwk_skey, msg, dev_addr, frame_counter)
    phy_payload = msg + mic

    # UDP 送信用 JSON にラップして送信
    json_payload = wrap_rxpk(phy_payload)
    send_push_data(json_payload)

    print(f"[>] Uplink #{frame_counter} sent.")
    frame_counter += 1

# === ABP Activation ===
def activate_abp():
    print("[+] ABP Activated")
    print(f"[+] DevAddr: {dev_addr[::-1].hex().upper()}")
    print(f"[+] AppSKey: {app_skey.hex().upper()}")
    print(f"[+] NwkSKey: {nwk_skey.hex().upper()}")

if __name__ == "__main__":
    # ABP での静的パラメータを用いて即時アクティベーション
    activate_abp()
    # 定期的に uplink メッセージを送信
    while True:
        send_uplink()
        time.sleep(30)

