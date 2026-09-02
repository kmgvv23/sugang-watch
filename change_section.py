"""수강정정 시스템에 로그인해 DB3000932 의 분반을 자동 변경한다.

안전장치 (의도적으로 좁게 만듦):
- 대상 교과목은 config.SUBJ_NO 하나뿐. 목표 분반은 config.WATCH_CLASSES 안의 값만
- '변경'(saveLecapply, CLS_CHG_FG=Y)만 사용한다. 삭제 버튼은 절대 누르지 않는다
  → 서버가 원자적으로 교체하므로 실패해도 기존 분반이 유지된다
- 자동 등록 방지(캡차) 팝업이 뜨면 즉시 중단하고 사람에게 알린다. 절대 풀지 않는다
- 변경 후 신청내역을 다시 읽어 실제로 바뀌었는지 확인한다
- 비밀번호는 키체인에서 읽어 브라우저 입력란으로만 전달된다

단독 실행:
    python3 change_section.py --dry-run 002   # 클릭 직전까지만
    python3 change_section.py 002             # 실제 변경
"""
import sys

from playwright.sync_api import sync_playwright

import config

LOGIN_URL = "https://sugang.pusan.ac.kr/"
CAPTCHA_SEL = ".layer-popup.captcha_popup"


class Blocked(Exception):
    """사람이 개입해야 하는 상황 (캡차 등)."""


def _captcha_visible(page) -> bool:
    try:
        for el in page.query_selector_all(CAPTCHA_SEL):
            if el.is_visible():
                return True
        # 클론된 팝업도 확인
        return page.evaluate(
            "() => [...document.querySelectorAll('.layer-popup')]"
            ".some(e => e.offsetParent !== null && /자동 등록 방지/.test(e.innerText||''))"
        )
    except Exception:
        return False


def login(page) -> None:
    sid = config.secret("PNU_ID", "pnu-sugang-id")
    spw = config.secret("PNU_PW", "pnu-sugang-pw")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
    page.fill("#userID", sid)
    page.fill("#userPW", spw)
    page.click("#btnLogin")
    page.wait_for_url(lambda u: "/login" not in u, timeout=60_000)
    page.wait_for_timeout(3_000)
    if _captcha_visible(page):
        raise Blocked("로그인 직후 자동 등록 방지 팝업이 떴습니다")
    # 공지 팝업이 있으면 닫는다
    try:
        for el in page.query_selector_all(".modal_alert_close, .popup_close"):
            if el.is_visible():
                el.click()
                page.wait_for_timeout(400)
    except Exception:
        pass


def current_rows(page) -> list[dict]:
    """신청내역(변경 버튼이 있는 표)에서 교과목번호/분반을 읽는다."""
    return page.evaluate(
        """() => [...document.querySelectorAll('tr')]
             .filter(tr => tr.querySelector('.class-change'))
             .map(tr => {
               const td = [...tr.querySelectorAll('td')].map(x => (x.innerText||'').trim());
               const inp = tr.querySelector("input[id^='CLS_CHG_CLASS_NO']");
               return {subjNo: td[3], classNo: td[4], nm: td[2], inputId: inp ? inp.id : null};
             })"""
    )


def change_to(page, target: str, dry_run: bool = False) -> tuple[bool, str]:
    """(성공여부, 메시지). 이미 목표 분반이면 성공으로 본다."""
    if target not in config.WATCH_CLASSES:
        return False, f"허용되지 않은 목표 분반: {target}"

    rows = current_rows(page)
    mine = [r for r in rows if r["subjNo"] == config.SUBJ_NO]
    if not mine:
        return False, f"신청내역에 {config.SUBJ_NO} 가 없습니다 (분반변경 불가)"
    row = mine[0]
    if row["classNo"] == target:
        return True, f"이미 {target}분반입니다"
    if not row["inputId"]:
        return False, "분반 입력란을 찾지 못했습니다"

    page.fill(f"#{row['inputId']}", target)
    if dry_run:
        return False, f"[모의] {row['classNo']} -> {target} 입력만 완료, 변경 버튼 누르지 않음"

    page.evaluate(
        """(id) => {
             const tr = document.getElementById(id).closest('tr');
             tr.querySelector('.class-change').click();
           }""",
        row["inputId"],
    )
    page.wait_for_timeout(2_500)

    if _captcha_visible(page):
        raise Blocked("변경 시도 중 자동 등록 방지 팝업이 떴습니다 (직접 처리 필요)")

    msg = ""
    for sel in ("#applyTxt", ".layer-popup .message"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                msg = (el.inner_text() or "").strip()
                if msg:
                    break
        except Exception:
            pass

    # 실제로 바뀌었는지 신청내역을 다시 읽어 확인
    page.wait_for_timeout(1_500)
    after = [r for r in current_rows(page) if r["subjNo"] == config.SUBJ_NO]
    now = after[0]["classNo"] if after else "?"
    if now == target:
        return True, f"{row['classNo']} -> {target} 변경 완료. {msg}".strip()
    return False, f"변경 실패 (현재 {now}분반 유지). {msg}".strip()


def run(target: str, dry_run: bool = False) -> tuple[bool, str]:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ko-KR")
        page = ctx.new_page()
        try:
            login(page)
            return change_to(page, target, dry_run=dry_run)
        finally:
            b.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(2)
    try:
        ok, m = run(args[0], dry_run=dry)
    except Blocked as e:
        print(f"[중단] {e}")
        sys.exit(3)
    print(("[성공] " if ok else "[실패] ") + m)
    sys.exit(0 if ok else 1)
