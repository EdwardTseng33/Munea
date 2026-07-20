#!/bin/bash
# 沐寧 · 自架視訊中繼站（coturn）開機安裝腳本（GCP VM startup · 2026-07-10 Edward 選 B）
# 用途：手機行動網路連「會動的臉」要靠中繼站轉接；免費公用的不穩→自架一台可靠的。
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y coturn

# 取這台機器的對外 IP（中繼站要對外宣告用）
EXTIP=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip")
INTIP=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip")

cat > /etc/turnserver.conf <<EOF
listening-port=3478
fingerprint
lt-cred-mech
user=muneaturn:munea-turn-a7k2q
realm=munea.turn
external-ip=${EXTIP}
min-port=49160
max-port=49200
no-cli
no-tlsv1
no-tlsv1_1
# 只轉接、不當開放 proxy（防被拿去打別人）
no-multicast-peers
denied-peer-ip=0.0.0.0-0.255.255.255
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
# Allow relay-to-relay traffic on this TURN host while keeping other private peers denied.
allowed-peer-ip=${INTIP}
EOF

# 允許服務啟動
echo "TURNSERVER_ENABLED=1" > /etc/default/coturn
systemctl enable coturn
systemctl restart coturn
echo "coturn started, external-ip=${EXTIP}, internal-ip=${INTIP}" > /var/log/munea-turn-boot.log
