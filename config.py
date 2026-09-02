"""설정. 비밀정보는 하드코딩하지 않는다 (macOS 키체인 -> 환경변수 -> .env 순)."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent

# ---- 감시 대상 ----
SYEAR = "2026"
TERM_GCD = "0020"          # 0010=1학기 0020=2학기 0011/0021=계절
SUBJ_NO = "DB3000932"      # 재무관리 (경영학과 전공필수)
SUBJ_NM_QUERY = "재무관리"  # 조회용 교과목명 (이 이름으로 검색해야 대상이 나옴)
COLL_GRAD_GCD = "0001"     # 0001=대학 0002=대학원 (필수값)
WATCH_CLASSES = ["001", "002", "003"]

# 감시할 트랙. None 이면 모든 트랙(주전공/부전공/일반선택/타대생) 감시.
WATCH_TRACKS = None

# 내 트랙 — 이 칸에 자리가 나면 바로 신청 가능하므로 최우선 긴급 알림.
# 다른 트랙(주전공/일반선택)은 학과에 전화해 변경 요청해야 하므로 일반 알림.
MY_TRACK = "부전공"
DEPT_PHONE = "051-510-1854"   # 경영학과

# 내 트랙에 자리가 나면 수강정정 시스템에 로그인해 분반변경을 자동 시도한다.
# False 로 두면 알림만 보낸다.
AUTO_CHANGE = True

# 선호 순위 (앞이 더 선호). 현재 보유 분반보다 순위가 높은 분반에만 변경을 시도한다.
# 001 월수 10:30 강상훈 / 002 화목 15:00 김진우 / 003 월수 12:00 박희진
PREFERENCE = ["001", "002", "003"]

# 현재 보유 분반 (참고용, 실제 값은 실행 시 시스템에서 읽는다)
CURRENT_CLASS_HINT = "006"

CHANGE_COOLDOWN_SEC = 90   # 같은 분반 재시도 최소 간격
CHANGE_MAX_TRIES = 3       # 같은 분반 최대 시도 횟수

POLL_SEC = 20              # 조회 주기(초). 공용 서버이니 과하게 낮추지 말 것
RELOAD_EVERY = 20 * 60     # CSRF 토큰 갱신용 페이지 재적재 주기(초)

PAGE_URL = "https://onestop.pusan.ac.kr/page?menuCD=000000000000335"
API_PATH = "/ost/cls/atlectmanual/atlectmanual/selectAtlectManual_v2025"


def _keychain(service: str) -> str | None:
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    return out.stdout.strip() or None


def _dotenv() -> dict:
    f = ROOT / ".env"
    if not f.exists():
        return {}
    d = {}
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


_ENV = _dotenv()


def secret(name: str, service: str) -> str:
    v = _keychain(service) or os.environ.get(name) or _ENV.get(name)
    if not v:
        raise SystemExit(
            f"[설정 없음] {name}\n"
            f"  키체인 저장:  security add-generic-password -U -s '{service}' -a pnu -w\n"
            f"  또는 {ROOT}/.env 에  {name}=값"
        )
    return v


def telegram_optional() -> tuple[str, str] | None:
    """설정돼 있으면 (토큰, chat_id), 없으면 None. 없어도 오류를 내지 않는다."""
    t = _keychain("telegram-bot-token") or os.environ.get("TG_TOKEN") or _ENV.get("TG_TOKEN")
    c = _keychain("telegram-chat-id") or os.environ.get("TG_CHAT_ID") or _ENV.get("TG_CHAT_ID")
    return (t, c) if t and c else None


def payload(page_size: int = 200) -> dict:
    return {
        "SCH_SYEAR": SYEAR, "SCH_TERM_GCD": TERM_GCD,
        "SCH_COURSE_COLL_GRAD_GCD": "", "SCH_COLL_GRAD_GCD": COLL_GRAD_GCD,
        "SCH_GRAD_GCD": "", "SCH_COLL_CD": "", "SCH_DEPT_CD": "",
        "SEARCH_GBN": "2", "SCH_SUBJ_GBN": "", "SCH_DETAIL": "",
        "SCH_SUBJ_NM": SUBJ_NM_QUERY, "SCH_PNU_CAPBLTY_GCD": "",
        "SCH_NATIVE_LANG_LECT_GCD": "", "sch_AllOC_CHK": "N",
        "TITLE": "목록", "USER_NM": "", "USER_ID": "",
        "totPage": 1, "totCnt": 0,
        "pageSize": page_size, "pageIndex": 0, "pageGrp": 1,
    }
