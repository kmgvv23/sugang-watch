"""알림 채널 — 텔레그램 전용.

토큰/chat_id 는 macOS 키체인(telegram-bot-token / telegram-chat-id)에서 읽는다.
텔레그램이 유일한 채널이므로, 미설정이면 조용히 넘어가지 않고 즉시 중단한다.
"""
import time
import urllib.parse
import urllib.request

import config

SETUP_HELP = (
    "텔레그램이 설정되지 않았습니다.\n"
    "  1) 텔레그램 @BotFather -> /newbot -> 토큰 받기\n"
    "  2) 만든 봇과 대화 시작 (아무 메시지나 전송)\n"
    "  3) https://api.telegram.org/bot<토큰>/getUpdates 에서 chat.id 확인\n"
    "  4) 저장:\n"
    "     security add-generic-password -U -s telegram-bot-token -a pnu -w\n"
    "     security add-generic-password -U -s telegram-chat-id  -a pnu -w"
)


def require_config() -> tuple[str, str]:
    """시작 시 호출. 설정이 없으면 즉시 종료한다."""
    creds = config.telegram_optional()
    if not creds:
        raise SystemExit("[중단] " + SETUP_HELP)
    return creds


def check_reachable() -> str:
    """봇 토큰이 살아있는지 확인하고 봇 이름을 돌려준다."""
    token, _ = require_config()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=20
        ) as r:
            import json
            j = json.load(r)
            if j.get("ok"):
                return j["result"].get("username", "?")
    except Exception as e:
        raise SystemExit(f"[중단] 텔레그램 봇에 접속할 수 없습니다: {e}\n\n{SETUP_HELP}")
    raise SystemExit("[중단] 텔레그램 토큰이 유효하지 않습니다.\n\n" + SETUP_HELP)


def send(title: str, body: str, urgent: bool = False) -> list[str]:
    """텔레그램으로 발송하고 사용된 채널 목록을 돌려준다."""
    token, chat_id = require_config()
    text = f"{title}\n{body}"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
        # 자리 알림은 무음으로 오면 의미가 없으므로 항상 소리 나게
        "disable_notification": "false",
    }).encode()
    last = "?"
    for attempt in range(3):
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    return ["텔레그램"]
                last = f"HTTP {r.status}"
        except Exception as e:
            last = str(e)
        if attempt < 2:
            time.sleep(2)
    return [f"텔레그램실패({last})"]
