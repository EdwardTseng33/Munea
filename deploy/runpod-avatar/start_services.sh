#!/bin/bash
# 沐寧 D2b 點火：中繼 + 臉（聲音留本機、鑰匙不出門）
CIP=$(hostname -i | awk '{print $1}')
pkill -f turnserver 2>/dev/null || true
turnserver --daemon --no-cli --listening-port=8443 --listening-ip=0.0.0.0 --relay-ip=$CIP   --min-port=49152 --max-port=49250 --lt-cred-mech --user=munea:${TURN_PASS:?請先 export TURN_PASS} --realm=munea   --no-tls --no-dtls --fingerprint > /root/turn.log 2>&1 || true
pkill -f avatar_cloud_server 2>/dev/null || true
cd /workspace/ditto-talkinghead && LD_LIBRARY_PATH=/opt/cudnn8-pkgs/nvidia/cudnn/lib:$LD_LIBRARY_PATH nohup python -u /root/avatar_cloud_server.py > /root/avatar.log 2>&1 &
sleep 3
(command -v ss >/dev/null && ss -tln | grep 8443 || netstat -tln 2>/dev/null | grep 8443) | head -1
echo "SERVICES KICKED"
