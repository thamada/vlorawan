# 仮想LoRaWANデバイス完全実装エミュレーター for TTN

このリポジトリは、**LoRaWAN 1.0.3** の仕様に完全準拠した仮想 LoRaWAN デバイスのエミュレーションを実現しています。Python スクリプトを使用し、OTAA (Over-The-Air Activation) Join 手順の実施、正確なセッションキー (DevAddr, AppSKey, NwkSKey) の導出、仕様どおりの MIC 計算、Cayenne LPP フォーマットのペイロード暗号化、そして TTN のネットワークフロー (Gateway → Network Server → Application Server) を経由する uplink を包括的に実装しています。

---

## 主な特徴

- **LoRaWAN 1.0.3 OTAA Join**  
  - デバイスは Join Request を送信し、TTN からの Join Accept を受け取って OTAA によるネットワーク参加を行います。

- **正確なセッションキー導出**  
  - Join Accept メッセージから取得した **AppNonce**、**NetID**、**DevNonce** を基に、**DevAddr**、**AppSKey**、**NwkSKey** を正しく導出します。

- **仕様どおりの MIC 計算**  
  - LoRaWAN 1.0.3 の仕様に従った手順で、データ送信前にメッセージの整合性検証用 MIC (Message Integrity Code) を計算しています。

- **Cayenne LPP フォーマットのペイロード暗号化**  
  - Cayenne LPP 形式で温度、湿度、GPS、デジタル入力などのセンサーデータを構築し、AppSKey を用いて AES-128 CTR モードで暗号化した上で uplink 送信します。

- **TTN ネットワークフローの再現**  
  - エミュレートされた uplink メッセージは、**TTN Gateway → Network Server → Application Server** という実際のネットワークフローをシミュレートして送信されます。

---

## システム構成とフロー

### 1. OTAA Join プロセス
- **Join Request の作成と送信**  
  - MHDR、JOIN_EUI、DEV_EUI、dev_nonce を連結し、APP_KEY を用いた CMAC により MIC を計算して Join Request メッセージを生成します。  
  - 生成された Join Request は、UDP 経由で TTN の Gateway に送信されます。

- **Join Accept の受信と解析**  
  - UDP Pull Data により Join Accept を待ち、受信した Join Accept メッセージは、APP_KEY を使った AES-128 復号処理により解析されます。  
  - 復号後、Join Accept から AppNonce、NetID、DevAddr を抽出し、セッションが確立されます。

### 2. セッションキーの導出
- **DevAddr, NwkSKey, AppSKey の生成**  
  - OTAA Join のプロセスで取得したパラメータと dev_nonce を用いて、LoRaWAN 仕様に基づいたキー導出処理を実施しています。  
  - これにより、ネットワーク通信で用いるデバイスアドレスと暗号化キーが正しく生成されます。

### 3. MIC 計算
- **データ整合性検証**  
  - uplink メッセージ生成時に、作成した PHYPayload に対して指定のフォーマットでバイト列を構築し、NwkSKey を使用して CMAC を計算。  
  - 計算された MIC がメッセージに付加され、送信先での整合性チェックに利用されます。

### 4. Cayenne LPP ペイロードの暗号化と送信
- **Cayenne LPP 形式によるセンサーデータ生成**  
  - 温度、湿度、GPS 座標、デジタル入力などのデータが Cayenne LPP フォーマットでフレーム化され、バイト列に変換されます。
- **AES-128 CTR モードによる暗号化**  
  - AppSKey を用いて、生成したペイロードが AES-128 CTR モードにより暗号化され、セキュアな uplink メッセージが作成されます。
- **uplink メッセージの送信**  
  - 暗号化された PHYPayload と MIC を含む uplink メッセージは、JSON ラップされた状態で UDP 経由により送信され、TTN の Gateway、Network Server、Application Server を経由してデータが流れます。

---

## 実装のポイント

- **完全な仮想デバイス実装**  
  - 本スクリプトは、LoRaWAN の OTAA Join 手順から始まり、セッションキーの厳密な導出、正しい MIC 計算、Cayenne LPP 形式のペイロードの暗号化、そして実際の TTN ネットワークへの uplink に至る、仮想 LoRaWAN デバイスの完全実装となっています。

- **セキュリティと整合性の確保**  
  - 各処理は LoRaWAN 1.0.3 の仕様に準じており、正当なデバイス認証とデータの整合性検証が行われています。

- **拡張性**  
  - 実運用を想定し、認証情報や接続先サーバー情報は柔軟に変更できるようになっています。実際の TTN 環境に合わせた各種設定へのカスタマイズが容易です。

---

## 実行方法

1. **依存ライブラリのインストール**

   ```bash
   pip install pycryptodome cayennelpp

