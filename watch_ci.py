"""GitHub Actions 대기조 — 로컬이 죽어 있는 동안만 감시한다.

로컬 감시기가 gist 에 생존 신호를 갱신한다. 이 스크립트는 매 회차마다 그 값을 읽어
- 신선하면: 조회만 하고 침묵한다 (로컬이 알리고 있으므로 중복 알림 방지)
- 낡았으면: 감시를 인수해 자리가 나면 텔레그램으로 알린다

한 작업이 최대 약 5.8시간 돌고, 워크플로 concurrency 로 다음 실행이 대기하다가
이어받는다. 로컬처럼 브라우저가 망가지면 통째로 재생성한다.
"""
import os
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

import config
import heartbeat
import notify
import poll

RUN_SEC = int(os.environ.get("RUN_SEC", 5 * 3600 + 40 * 60))   # 약 5.7시간
POLL_SEC = int(os.environ.get("CI_POLL_SEC", 60))
TOKEN = None   # 공개 gist 는 비인증으로 읽는다 (heartbeat.read 주석 참고)


def log(msg: str) -> None:
    print(f"{datetime.now():%m-%d %H:%M:%S}  {msg}", flush=True)


def main() -> int:
    notify.require_config()
    deadline = time.time() + RUN_SEC
    log(f"대기조 시작 · {config.SUBJ_NO} {'/'.join(config.WATCH_CLASSES)}분반 · "
        f"{POLL_SEC}초 주기 · {RUN_SEC // 60}분간")

    had: dict[str, bool] = {}
    taking_over = False
    announced = False

    with sync_playwright() as pw:
        browser = page = None

        def rebuild():
            nonlocal browser, page
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(locale="ko-KR").new_page()
            page.goto(config.PAGE_URL, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_function(poll.READY_JS, timeout=90_000)

        rebuild()

        while time.time() < deadline:
            try:
                alive, age = heartbeat.local_alive(TOKEN)
                snap = poll.snapshot(page)
                if not snap.get("ok") or not snap["sections"]:
                    raise RuntimeError(snap.get("err") or "빈 결과")

                if alive:
                    if taking_over:
                        log(f"로컬 복귀 (신호 {age:.0f}초 전) — 대기 모드로 전환")
                        notify.send("🔄 로컬 감시 복귀",
                                    "맥의 감시기가 살아났습니다. 대기조는 알림을 멈춥니다.")
                        taking_over = False
                        had = {}
                    log(f"대기 (로컬 정상, 신호 {age:.0f}초 전)")
                    time.sleep(POLL_SEC)
                    continue

                if not taking_over:
                    ago = f"{age:.0f}초 전" if age is not None else "읽기 실패"
                    log(f"로컬 신호 낡음({ago}) — 감시 인수")
                    notify.send("📡 대기조가 감시 인수",
                                f"맥의 감시기 신호가 끊겼습니다 (마지막 {ago}).\n"
                                "지금부터 GitHub 서버가 감시합니다.")
                    taking_over = True
                    announced = True

                opened, had, summary = poll.evaluate(snap, had)
                if opened:
                    for title, body, urgent in poll.messages(opened, snap["nm"]):
                        notify.send(title, body, urgent=urgent)
                    for o in opened:
                        had[o["key"]] = True
                    log(f"*** 알림 발송: " +
                        "; ".join(f"{o['cls']}/{o['track']} {o['free']}자리" for o in opened))
                else:
                    log(f"인수 중 · 여석 없음  {summary}")

            except Exception as e:
                log(f"[오류] {e}")
                try:
                    rebuild()
                    log("브라우저 재생성")
                except Exception as e2:
                    log(f"[재생성 실패] {e2}")
                    time.sleep(30)

            time.sleep(POLL_SEC)

    log("대기조 종료 (다음 실행이 이어받음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
