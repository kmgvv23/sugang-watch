"""로컬 감시기 생존 신호(heartbeat).

로컬이 살아 있으면 공개 gist 에 현재 unix 시각을 계속 갱신한다.
GitHub Actions 대기조는 이 값을 읽어, 신선하면 침묵하고 오래되면 인수한다.
네트워크가 끊기면 갱신이 실패해 값이 낡으므로 → 자동 페일오버가 된다.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

GIST_ID = (Path(__file__).parent / ".gist_id").read_text().strip()
FILENAME = "heartbeat.txt"
MIN_INTERVAL = 60          # 이 간격보다 자주 보내지 않는다
STALE_SEC = 300            # 이 시간보다 오래되면 '로컬 죽음'으로 본다

_last_sent = 0.0


def beat(force: bool = False) -> bool:
    """생존 신호를 갱신한다. 너무 자주 부르면 무시한다."""
    global _last_sent
    now = time.time()
    if not force and now - _last_sent < MIN_INTERVAL:
        return True
    payload = json.dumps({"files": {FILENAME: {"content": f"{int(now)}\n"}}})
    try:
        r = subprocess.run(
            ["gh", "api", "-X", "PATCH", f"/gists/{GIST_ID}", "--input", "-"],
            input=payload, capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            _last_sent = now
            return True
    except Exception:
        pass
    return False


OWNER = "kmgvv23"
RAW = f"https://gist.githubusercontent.com/{OWNER}/{GIST_ID}/raw/{FILENAME}"


def read(token: str | None = None) -> int | None:
    """마지막 생존 신호 시각. 읽기 실패면 None.

    공개 gist 이므로 인증하지 않는다. Actions 의 GITHUB_TOKEN 은 설치 토큰이라
    gist 스코프가 없어 오히려 401/404 가 난다 (그래서 token 인자는 무시한다).
    raw URL 은 60초 CDN 캐시가 있으므로 캐시 버스터를 붙여 최신값을 받는다.
    """
    cb = int(time.time())
    for url, parse in (
        (f"{RAW}?cb={cb}", lambda b: b.decode().strip()),
        (f"https://api.github.com/gists/{GIST_ID}",
         lambda b: json.loads(b)["files"][FILENAME]["content"].strip()),
    ):
        try:
            req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return int(parse(resp.read()))
        except Exception:
            continue
    return None


def local_alive(token: str | None = None) -> tuple[bool, float | None]:
    """(로컬이 살아있나, 마지막 신호로부터 경과초)"""
    ts = read(token)
    if ts is None:
        return False, None
    age = time.time() - ts
    return age < STALE_SEC, age
