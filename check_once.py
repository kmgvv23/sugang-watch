"""1회 조회용 — GitHub Actions 크론에서 실행된다.

state.json 에 분반별 '이미 알림 보냄' 상태를 남겨, 자리가 계속 열려 있는 동안
매 실행마다 반복 알림하지 않는다. 상태가 바뀌면 종료코드로 알려준다(0=변경없음, 10=변경).
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import config
import notify
import watch

STATE = Path(__file__).parent / "state.json"


def main() -> int:
    notify.require_config()

    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text()).get("had_seat", {})
        except Exception:
            prev = {}
    had = {c: bool(prev.get(c, False)) for c in config.WATCH_CLASSES}

    args = {"api": config.API_PATH, "body": config.payload()}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(locale="ko-KR").new_page()
        pg.goto(config.PAGE_URL, wait_until="domcontentloaded", timeout=90_000)
        pg.wait_for_function(watch.READY_JS, timeout=90_000)
        r = pg.evaluate(watch.POLL_JS, args)
        b.close()

    if not r.get("ok"):
        print(f"[오류] 조회 실패: {r.get('err')}")
        return 1

    rows = {x["cls"]: x for x in r["rows"] if x["no"] == config.SUBJ_NO}
    if not rows:
        print("[경고] 대상 교과목 조회 안 됨")
        return 1

    opened, summary = [], []
    for cls in config.WATCH_CLASSES:
        x = rows.get(cls)
        if not x:
            continue
        pa = watch.parse_alloc(x["alloc"])
        if pa is None:
            continue
        cur, cap = pa
        free = cap - cur
        summary.append(f"{cls}:{cur}/{cap}")
        if free > 0:
            if not had[cls]:
                opened.append(f"{cls}분반 {free}자리 ({cur}/{cap})")
        else:
            had[cls] = False

    nm = next(iter(rows.values()))["nm"]
    print(f"{time.strftime('%m-%d %H:%M:%S')}  {' '.join(summary)}")

    changed = False
    if opened:
        used = notify.send(
            f"🚨 자리 났습니다 · {nm}",
            " / ".join(opened) + "  → sugang.pusan.ac.kr 바로 신청",
            urgent=True,
        )
        if used == ["텔레그램"]:
            for o in opened:
                had[o.split("분반")[0]] = True
            changed = True
            print(f"*** 알림 발송: {'; '.join(opened)}")
        else:
            print(f"[알림 실패] {used} — 다음 실행에서 재시도")
    else:
        print("여석 없음")

    new_state = {"had_seat": had, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    old_had = {c: bool(prev.get(c, False)) for c in config.WATCH_CLASSES}
    if had != old_had or changed:
        STATE.write_text(json.dumps(new_state, ensure_ascii=False, indent=2))
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
