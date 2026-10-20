#!/bin/sh
# AI Usage Hub 에이전트를 macOS 로그인 시 자동 실행(launchd LaunchAgent)으로 등록한다.
#
# 먼저 대시보드 설정 → 기기 관리에서 기기를 등록하고, 안내된 명령으로 ~/.aihub/agent.env 를 만든다.
#
#   cd <저장소>/backend
#   sh collector/install-agent.sh              # 등록하고 바로 시작
#   sh collector/install-agent.sh --uninstall  # 삭제
set -eu

LABEL="com.aihub.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CONFIG="$HOME/.aihub/agent.env"
LOG_DIR="$HOME/.aihub"
DOMAIN="gui/$(id -u)"
BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "삭제했습니다: $LABEL"
  exit 0
fi

if [ "$(uname)" != "Darwin" ]; then
  echo "macOS 전용 스크립트입니다. Windows 는 install-agent.ps1 을 사용하세요." >&2
  exit 1
fi

UV="$(command -v uv || true)"
if [ -z "$UV" ]; then
  echo "uv 를 찾을 수 없습니다. 설치: https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [ ! -f "$CONFIG" ] || ! grep -q '^AIHUB_DEVICE_TOKEN=' "$CONFIG"; then
  echo "$CONFIG 에 기기 토큰이 없습니다. 설정 → 기기 관리의 macOS 안내 명령을 먼저 실행하세요." >&2
  exit 1
fi
chmod 600 "$CONFIG"
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

# launchd 는 PATH 가 최소한이라 uv 를 전체 경로로 지정한다.
# --no-project: 에이전트는 표준 라이브러리만 쓰므로 백엔드 의존성을 설치하지 않는다.
# --python 3.12: 시스템 Python(macOS 기본 3.9 등)이 잡히지 않게 고정한다. 없으면 uv 가 내려받는다.
# 비정상 종료 시에만 60초 간격으로 다시 시작한다.
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$UV</string>
    <string>run</string>
    <string>--no-project</string>
    <string>--python</string>
    <string>3.12</string>
    <string>python</string>
    <string>-m</string>
    <string>collector.agent</string>
  </array>
  <key>WorkingDirectory</key><string>$BACKEND_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/agent.out</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/agent.out</string>
</dict>
</plist>
EOF

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"

echo "등록 완료: 로그인할 때마다 자동으로 실행되며, 지금 바로 시작했습니다."
echo "실행 로그: $LOG_DIR/agent.log"
echo "삭제: sh collector/install-agent.sh --uninstall"
