"""1회 조회용 — GitHub Actions 크론에서 실행된다.

state.json 에 '분반:트랙' 단위로 알림 여부를 남겨, 자리가 계속 열려 있는 동안
매 실행마다 반복 알림하지 않는다. 종료코드 10 = 상태 변경, 0 = 변경 없음.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import config
import notify
import poll

STATE = Path(__file__).parent / "state.json"


def main() -> int:
    notify.require_config()

    prev: dict = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text()).get("had_seat", {})
        except Exception:
            prev = {}
    had = dict(prev)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(locale="ko-KR").new_page()
        pg.goto(config.PAGE_URL, wait_until="domcontentloaded", timeout=90_000)
        pg.wait_for_function(poll.READY_JS, timeout=90_000)
        snap = poll.snapshot(pg)
        b.close()

    if not snap.get("ok"):
        print(f"[오류] 조회 실패: {snap.get('err')}")
        return 1
    if not snap["sections"]:
        print("[경고] 대상 교과목/분반 조회 안 됨")
        return 1

    opened, had, summary = poll.evaluate(snap, had)
    print(f"{time.strftime('%m-%d %H:%M:%S')}  {summary}")

    if opened:
        ok = True
        for title, body, urgent in poll.messages(opened, snap["nm"]):
            used = notify.send(title, body, urgent=urgent)
            if used != ["텔레그램"]:
                ok = False
                print(f"[알림 실패] {used} — {title}")
        desc = "; ".join(f"{o['cls']}/{o['track']} {o['free']}자리" for o in opened)
        if ok:
            for o in opened:
                had[o["key"]] = True
            print(f"*** 알림 발송: {desc}")
        else:
            print(f"[알림 일부 실패] 다음 실행에서 재시도: {desc}")
    else:
        print("여석 없음")

    if had != prev:
        STATE.write_text(json.dumps(
            {"had_seat": had, "updated": time.strftime("%Y-%m-%d %H:%M:%S")},
            ensure_ascii=False, indent=2))
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
