"""키체인의 봇 토큰으로 chat_id 를 찾아 키체인에 저장한다.

토큰은 키체인 -> 이 프로세스 -> 텔레그램 API 로만 흐른다.
"""
import json
import subprocess
import sys
import urllib.request

import config


def main() -> int:
    token = config._keychain("telegram-bot-token")
    if not token:
        print("[중단] 키체인에 telegram-bot-token 이 없습니다.\n"
              "  security add-generic-password -U -s telegram-bot-token -a pnu -w")
        return 1

    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=20
        ) as r:
            me = json.load(r)
    except Exception as e:
        print(f"[중단] 봇 접속 실패: {e}")
        return 1
    if not me.get("ok"):
        print("[중단] 토큰이 유효하지 않습니다. /revoke 로 재발급 후 다시 저장하세요.")
        return 1
    print(f"봇 확인: @{me['result'].get('username')}")

    wait = "--wait" in sys.argv
    deadline = __import__("time").time() + (300 if wait else 0)
    ups = {"result": []}
    while True:
        try:
            with urllib.request.urlopen(
                f"https://api.telegram.org/bot{token}/getUpdates?timeout=25", timeout=35
            ) as r:
                ups = json.load(r)
        except Exception as e:
            print(f"[경고] getUpdates 실패: {e}")
        if ups.get("result"):
            break
        if __import__("time").time() >= deadline:
            break
        print(f"  대기 중... @{me['result'].get('username')} 에게 메시지를 보내주세요", flush=True)

    chats = {}
    for u in ups.get("result", []):
        msg = u.get("message") or u.get("edited_message") or {}
        ch = msg.get("chat") or {}
        if ch.get("id") is not None:
            name = ch.get("username") or ch.get("first_name") or ch.get("title") or "?"
            chats[str(ch["id"])] = f"{name} ({ch.get('type')})"

    if not chats:
        print("[중단] 대화 기록이 없습니다.\n"
              f"  텔레그램에서 @{me['result'].get('username')} 를 열고 아무 메시지나 보낸 뒤 다시 실행하세요.")
        return 1

    if len(chats) > 1:
        print("여러 대화가 발견됐습니다. 하나를 골라 직접 저장하세요:")
        for cid, who in chats.items():
            print(f"  {cid}  {who}")
        return 1

    cid, who = next(iter(chats.items()))
    print(f"chat_id 발견: {cid}  {who}")
    r = subprocess.run(
        ["security", "add-generic-password", "-U", "-s", "telegram-chat-id",
         "-a", "pnu", "-w", cid],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[중단] 키체인 저장 실패: {r.stderr.strip()}")
        return 1
    print("키체인에 telegram-chat-id 저장 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
