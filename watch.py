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

import change_section
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
    tries: dict[str, int] = {}       # 분반 -> 변경 시도 횟수
    last_try: dict[str, float] = {}  # 분반 -> 마지막 시도 시각
    held = config.CURRENT_CLASS_HINT # 현재 보유 분반 (변경 성공 시 갱신)


    def rank(cls: str) -> int:
        """선호 순위. 목록에 없으면 최하위."""
        pref = config.PREFERENCE
        return pref.index(cls) if cls in pref else len(pref) + 1

    def try_change(cands: list[str]) -> None:
        """선호 순위가 현재 보유 분반보다 높은 후보에 대해 분반변경을 시도한다."""
        nonlocal held
        better = sorted((c for c in cands if rank(c) < rank(held)), key=rank)
        if not better:
            log(f"자리는 났지만 현재 {held}분반보다 선호 순위가 높지 않음 → 변경 안 함")
            return
        now = time.time()
        for cls in better:
            if tries.get(cls, 0) >= config.CHANGE_MAX_TRIES:
                continue
            if now - last_try.get(cls, 0) < config.CHANGE_COOLDOWN_SEC:
                continue
            tries[cls] = tries.get(cls, 0) + 1
            last_try[cls] = now
            log(f"분반변경 시도 {held} -> {cls} ({tries[cls]}회차)")
            try:
                ok, msg = change_section.run(cls)
            except change_section.Blocked as e:
                notify.send(
                    "⛔ 자동 변경 중단 — 직접 처리 필요",
                    f"{e}\n\n자동 등록 방지는 사람이 처리해야 합니다.\n"
                    f"지금 바로 접속해서 {cls}분반으로 변경하세요.\n"
                    "https://sugang.pusan.ac.kr/",
                    urgent=True,
                )
                log(f"[중단] {e}")
                return
            except Exception as e:
                notify.send(
                    "⚠️ 자동 변경 오류 — 직접 신청 권함",
                    f"{held} -> {cls} 시도 중 오류: {e}\n\nhttps://sugang.pusan.ac.kr/",
                    urgent=True,
                )
                log(f"[변경 오류] {e}")
                continue

            if ok:
                held = cls
                notify.send(
                    f"✅ {cls}분반으로 변경 완료",
                    f"{config.SUBJ_NO} 재무관리\n{msg}\n\n시스템에서 한 번 확인해 주세요.",
                    urgent=True,
                )
                log(f"*** 변경 성공: {msg}")
                return
            log(f"변경 실패: {msg}")
            notify.send(
                f"❌ {cls}분반 자동 변경 실패",
                f"{msg}\n\n자리가 먼저 채워졌을 수 있습니다. "
                f"직접 확인해보세요.\nhttps://sugang.pusan.ac.kr/",
                urgent=True,
            )

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
                    mine_cls = [o["cls"] for o in opened if o["mine"]]
                    if mine_cls and config.AUTO_CHANGE:
                        try_change(mine_cls)

                    ok = True
                    for title, body, urgent in poll.messages(opened, snap["nm"]):
                        used = notify.send(title, body, urgent=urgent)
                        if used != ["텔레그램"]:
                            ok = False
                            log(f"[알림 실패] {used} — {title}")
                    desc = "; ".join(
                        f"{o['cls']}/{o['track']} {o['free']}자리" for o in opened)
                    if ok:
                        for o in opened:
                            had[o["key"]] = True
                        log(f"*** 알림 발송: {desc}")
                    else:
                        log(f"[알림 일부 실패] 다음 회차 재시도: {desc}")
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
