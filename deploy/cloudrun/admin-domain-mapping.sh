#!/usr/bin/env bash
# 沐寧營運後台換網址 admin.munea.net · 一鍵（Cloud Run 網域綁定 · 2026-10-26 Edward 拍板）
#
# 走法：把 admin.munea.net 直接綁在正式大腦 munea-brain 上（Cloud Run「網域對應」）。
#   - 不經 Vercel／Firebase 轉送、不多一跳、不用改官網設定；舊的 run.app 網址照常能用。
#   - 7/11 那份設定單寫「asia-east1 不支援網域綁定」是錯的：Google 的 Cloud Run 地區表把
#     asia-east1 列在支援清單裡（https://cloud.google.com/run/docs/locations）。
#   - 憑證由 Google 自動簽發、自動續期。
#
# 用法（在這台電腦、Git Bash 或 Mac 終端機）：
#   bash deploy/cloudrun/admin-domain-mapping.sh plan     # 只看現況，不動任何東西
#   bash deploy/cloudrun/admin-domain-mapping.sh apply    # 建立綁定，印出要去 GoDaddy 加的 DNS 紀錄
#   bash deploy/cloudrun/admin-domain-mapping.sh status   # DNS／憑證到了沒、網址通了沒
#   bash deploy/cloudrun/admin-domain-mapping.sh remove   # 退回：解除綁定（run.app 網址不受影響）
#
# 前提：
#   1. gcloud 已登入「munea.net 網域驗證過的那個 Google 帳號」（Edward 的；官網 app-site/ 裡的
#      googleaa0c51d3d9781eb5.html 就是那次驗證留下的）。沒登入先跑：gcloud auth login
#   2. 綁的是正式大腦 munea-brain（不是 -staging）。要綁別的服務用 MUNEA_ADMIN_DOMAIN_SERVICE 覆蓋。
set -euo pipefail
cd "$(dirname "$0")/../.."

REGION="asia-east1"
PROJECT="${MUNEA_GCP_PROJECT:-gen-lang-client-0229303523}"
DOMAIN="${MUNEA_ADMIN_DOMAIN:-admin.munea.net}"
SERVICE="${MUNEA_ADMIN_DOMAIN_SERVICE:-munea-brain}"
ROOT_DOMAIN="${DOMAIN#*.}"   # admin.munea.net → munea.net

resolve_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    GCLOUD=(gcloud)
  elif command -v gcloud.cmd >/dev/null 2>&1; then
    GCLOUD=(cmd //c gcloud.cmd)
  else
    echo "⛔ 找不到 gcloud；請先將 Google Cloud SDK 加入 PATH"
    exit 1
  fi
}
gcloud_run() { "${GCLOUD[@]}" "$@"; }
resolve_gcloud

ACTION="${1:-plan}"

say() { printf '\n== %s ==\n' "$1"; }

check_login() {
  local who
  who="$(gcloud_run auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)"
  if [ -z "$who" ]; then
    echo "⛔ gcloud 還沒登入。先跑：gcloud auth login（用 munea.net 驗證過的那個帳號）"
    exit 1
  fi
  echo "gcloud 帳號：$who"
}

check_domain_verified() {
  say "網域驗證（$ROOT_DOMAIN 是不是這個帳號驗證過的）"
  local verified
  verified="$(gcloud_run domains list-user-verified --format='value(id)' 2>/dev/null || true)"
  if printf '%s\n' "$verified" | grep -qx "$ROOT_DOMAIN"; then
    echo "✅ $ROOT_DOMAIN 已驗證"
    return 0
  fi
  echo "⚠ 這個帳號名下沒有 $ROOT_DOMAIN 的驗證紀錄。"
  echo "   解法（擇一）：① 換成驗證過的帳號 gcloud auth login"
  echo "              ② 跑 gcloud domains verify $ROOT_DOMAIN → 會開 Search Console，照指示加一筆 TXT 到 GoDaddy"
  return 1
}

show_mapping() {
  gcloud_run beta run domain-mappings describe --domain "$DOMAIN" --region "$REGION" --project "$PROJECT" \
    --format='yaml(metadata.name,spec.routeName,status.conditions,status.resourceRecords)' 2>/dev/null
}

print_dns() {
  say "要去 GoDaddy（munea.net → DNS）加的紀錄"
  local rows
  rows="$(gcloud_run beta run domain-mappings describe --domain "$DOMAIN" --region "$REGION" --project "$PROJECT" \
    --format='value(status.resourceRecords[].type,status.resourceRecords[].name,status.resourceRecords[].rrdata)' 2>/dev/null || true)"
  if [ -z "$rows" ]; then
    echo "（Google 還沒吐出紀錄，等幾秒再跑 status）"
    return
  fi
  echo "$rows" | awk -F'\t' '{print "  類型 " $1 "   名稱 " ($2==""?"admin":$2) "   值 " $3}'
  echo
  echo "  一般會是一筆：CNAME  admin  →  ghs.googlehosted.com"
  echo "  加完等 DNS 傳播＋Google 簽憑證（通常 15 分鐘內、最慢 24 小時），再跑：bash $0 status"
}

case "$ACTION" in
  plan)
    say "現況（$DOMAIN → $SERVICE @ $REGION / $PROJECT）"
    check_login
    check_domain_verified || true
    if show_mapping; then
      echo "（上面是已存在的綁定）"
    else
      echo "目前沒有綁定。下一步：bash $0 apply"
    fi
    ;;
  apply)
    say "建立綁定 $DOMAIN → $SERVICE"
    check_login
    check_domain_verified
    if show_mapping >/dev/null 2>&1; then
      echo "已經有綁定了，不重建。"
    else
      gcloud_run beta run domain-mappings create --service "$SERVICE" --domain "$DOMAIN" \
        --region "$REGION" --project "$PROJECT" --quiet
      echo "✅ 綁定建立"
    fi
    print_dns
    ;;
  status)
    say "綁定狀態"
    check_login
    show_mapping || { echo "沒有綁定（先跑 apply）"; exit 1; }
    print_dns
    say "實際打打看 https://$DOMAIN/version"
    if curl -fsS --max-time 15 "https://$DOMAIN/version" 2>/dev/null; then
      echo
      echo "✅ 通了。後台網址：https://$DOMAIN/admin.html"
    else
      echo "還沒通（DNS 沒到、或憑證還在簽）。GoDaddy 紀錄加對的話通常 15 分鐘內會好。"
    fi
    ;;
  remove)
    say "解除綁定 $DOMAIN（run.app 網址不受影響）"
    check_login
    gcloud_run beta run domain-mappings delete --domain "$DOMAIN" --region "$REGION" --project "$PROJECT" --quiet
    echo "✅ 已解除。GoDaddy 那筆 CNAME 可以順手刪掉。"
    ;;
  *)
    echo "用法：bash $0 plan|apply|status|remove"; exit 2 ;;
esac
