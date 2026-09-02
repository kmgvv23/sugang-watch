"""부산대 수강편람 여석 감시기 → 알림.

로그인 불필요. onestop 수강편람 조회 API 응답의 ALLOC_RCNT("현재인원/정원")를
읽어 감시 대상 분반(001~003) 중 어느 하나라도 여석이 생기는 순간 알린다.
알림 채널은 notify.py 참고 (맥 알림 기본, 텔레그램은 설정 시 자동 병행).

페이지가 요청을 RSA로 암호화하고 CSRF 토큰을 붙이므로, 순수 HTTP 대신
헤드리스 크롬에 페이지를 띄워두고 페이지 자신의 ajax 함수를 재사용한다.
"""
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

import config
import notify

READY_JS = "() => typeof gfn_ajax_request === 'function' && !!(window.scwin && scwin.menuInfo && scwin.menuInfo.AUTH_STR)"

POLL_JS = """
(args) => new Promise(res => {
  let done = false;
  const fin = (v) => { if (!done) { done = true; res(v); } };
  try {
    gfn_ajax_request({
      url: args.api, reqData: args.body, loading: false,
      success: (data) => fin({ok: true, rows: (data || []).map(r => ({
        no: r.SUBJ_NO, cls: r.CLASS_NO, alloc: r.ALLOC_RCNT, nm: r.SUBJ_NM,
      }))}),
      error: (e) => fin({ok: false, err: 'ajax ' + (e && e.status)}),
    });
  } catch (e) { fin({ok: false, err: String(e)}); }
  setTimeout(() => fin({ok: false, err: 'timeout'}), 25000);
})
"""


def log(msg: str) -> None:
    print(f"{datetime.now():%m-%d %H:%M:%S}  {msg}", flush=True)


def parse_alloc(alloc: str) -> tuple[int, int] | None:
    """'48/50' -> (48, 50)"""
    try:
        cur, cap = str(alloc).split("/")
        return int(cur.strip()), int(cap.strip())
    except Exception:
        return None


def main() -> int:
    bot = notify.check_reachable()
    log(f"텔레그램 봇 확인: @{bot}")
    args = {"api": config.API_PATH, "body": config.payload()}

    # 분반별 '여석 있음' 상태. 0 -> 양수로 바뀌는 순간에만 알린다.
    had_seat: dict[str, bool] = {c: False for c in config.WATCH_CLASSES}
    fails = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="ko-KR")
        page = ctx.new_page()

        def load():
            page.goto(config.PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(READY_JS, timeout=60_000)

        load()
        loaded_at = time.time()
        log(f"감시 시작: {config.SUBJ_NO} 분반 {'/'.join(config.WATCH_CLASSES)} · {config.POLL_SEC}초 주기")

        first = True
        while True:
            try:
                if time.time() - loaded_at > config.RELOAD_EVERY:
                    load()
                    loaded_at = time.time()

                r = page.evaluate(POLL_JS, args)
                if not r.get("ok"):
                    raise RuntimeError(r.get("err"))
                fails = 0

                rows = [x for x in r["rows"] if x["no"] == config.SUBJ_NO]
                if not rows:
                    log("[경고] 대상 교과목이 조회되지 않음 (학기 전환/과목명 변경 확인 필요)")

                free_now = {}
                for x in rows:
                    if x["cls"] not in config.WATCH_CLASSES:
                        continue
                    pa = parse_alloc(x["alloc"])
                    if pa is None:
                        continue
                    cur, cap = pa
                    free_now[x["cls"]] = (cap - cur, cur, cap)

                opened, opened_cls = [], []
                for cls in config.WATCH_CLASSES:
                    if cls not in free_now:
                        continue
                    free, cur, cap = free_now[cls]
                    if free > 0:
                        if not had_seat[cls]:
                            opened.append(f"{cls}분반 {free}자리 ({cur}/{cap})")
                            opened_cls.append(cls)
                    else:
                        had_seat[cls] = False

                summary = " ".join(
                    f"{c}:{free_now[c][1]}/{free_now[c][2]}"
                    for c in config.WATCH_CLASSES if c in free_now
                )

                nm = rows[0]["nm"] if rows else config.SUBJ_NO

                if first:
                    used = notify.send(
                        f"감시 시작 · {nm}",
                        f"{config.SUBJ_NO} {'/'.join(config.WATCH_CLASSES)}분반 · 현재 {summary}",
                    )
                    log(f"감시 시작 알림 발송 ({', '.join(used)})")
                    first = False

                if opened:
                    used = notify.send(
                        f"🚨 자리 났습니다 · {nm}",
                        " / ".join(opened) + "  → sugang.pusan.ac.kr 바로 신청",
                        urgent=True,
                    )
                    if used == ["텔레그램"]:
                        # 발송 성공한 분반만 '알림 완료'로 기록
                        for cls in opened_cls:
                            had_seat[cls] = True
                        log(f"*** 알림 발송: {'; '.join(opened)}")
                    else:
                        # 실패하면 상태를 남기지 않아 다음 회차에 다시 시도한다
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
