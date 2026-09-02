"""부산대 수강편람 여석 감시기 (상시 실행) → 텔레그램 알림.

로그인 불필요. 목록 API의 ALLOC_RCNT 와 인원 상세 API의 트랙별 인원
(주전공/부전공/일반선택/타대생)을 읽어, 감시 대상 분반·트랙에 자리가
생기는 순간 알린다. 트랙은 배타적이므로 어느 트랙인지까지 알려준다.

요청이 RSA 암호화 + CSRF 토큰을 쓰므로 헤드리스 크롬에 페이지를 띄워두고
페이지 자신의 ajax 함수를 재사용한다.
"""
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

import config
import notify
import poll


def log(msg: str) -> None:
    print(f"{datetime.now():%m-%d %H:%M:%S}  {msg}", flush=True)


def main() -> int:
    bot = notify.check_reachable()
    log(f"텔레그램 봇 확인: @{bot}")

    had: dict[str, bool] = {}
    fails = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()

        def load():
            page.goto(config.PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(poll.READY_JS, timeout=60_000)

        load()
        loaded_at = time.time()
        tracks = getattr(config, "WATCH_TRACKS", None) or ["모든 트랙"]
        log(f"감시 시작: {config.SUBJ_NO} 분반 {'/'.join(config.WATCH_CLASSES)} · "
            f"트랙 {'/'.join(tracks)} · {config.POLL_SEC}초 주기")

        first = True
        while True:
            try:
                if time.time() - loaded_at > config.RELOAD_EVERY:
                    load()
                    loaded_at = time.time()

                snap = poll.snapshot(page)
                if not snap.get("ok"):
                    raise RuntimeError(snap.get("err"))
                if not snap["sections"]:
                    log("[경고] 대상 교과목/분반이 조회되지 않음 (학기 전환 확인 필요)")
                    time.sleep(config.POLL_SEC)
                    continue
                fails = 0

                opened, had, summary = poll.evaluate(snap, had)

                if first:
                    notify.send(
                        f"감시 시작 · {snap['nm']}",
                        f"{config.SUBJ_NO} {'/'.join(config.WATCH_CLASSES)}분반\n"
                        f"감시 트랙: {'/'.join(tracks)}\n{summary}",
                    )
                    log("감시 시작 알림 발송")
                    first = False

                if opened:
                    used = notify.send(
                        f"🚨 자리 났습니다 · {snap['nm']}",
                        "\n".join("· " + o for o in opened)
                        + "\n\n→ sugang.pusan.ac.kr 바로 신청",
                        urgent=True,
                    )
                    if used == ["텔레그램"]:
                        for o in opened:
                            had[poll.key_of(o)] = True
                        log(f"*** 알림 발송: {'; '.join(opened)}")
                    else:
                        log(f"[알림 실패] {used} — 다음 회차 재시도: {'; '.join(opened)}")
                else:
                    log(f"여석 없음  {summary}")

            except KeyboardInterrupt:
                raise
            except Exception as e:
                fails += 1
                log(f"[오류 {fails}] {e}")
                if fails >= 3:
                    try:
                        load()
                        loaded_at = time.time()
                        log("페이지 재적재 완료")
                        fails = 0
                    except Exception as e2:
                        log(f"[재적재 실패] {e2}")
                        time.sleep(30)

            time.sleep(config.POLL_SEC)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("종료")
