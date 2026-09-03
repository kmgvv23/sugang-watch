"""대기조(Actions) 생존 보장.

로컬이 살아 있는 동안 대기조가 항상 떠 있도록 보장한다. 그래야 로컬이 죽는
순간에 이미 대기조가 감시 중이다. Actions 의 schedule 은 몇 시간씩 건너뛰므로
(실측: 이틀간 7회) 크론에만 의존할 수 없다.
"""
import json
import subprocess
import time

WORKFLOW = "standby.yml"
LIVE = {"in_progress", "queued", "requested", "waiting", "pending"}
MIN_INTERVAL = 600      # 확인 간격(초)

_last_check = 0.0


def _gh(args: list[str], timeout: int = 30):
    return subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=timeout)


def ensure(force: bool = False) -> str | None:
    """대기조가 안 돌고 있으면 띄운다. 무슨 일을 했는지 문자열로, 안 했으면 None."""
    global _last_check
    now = time.time()
    if not force and now - _last_check < MIN_INTERVAL:
        return None
    _last_check = now
    try:
        r = _gh(["run", "list", "--workflow", WORKFLOW, "--limit", "3",
                 "--json", "status,conclusion"])
        if r.returncode != 0:
            return None
        runs = json.loads(r.stdout or "[]")
        if any(x.get("status") in LIVE for x in runs):
            return None
        d = _gh(["workflow", "run", WORKFLOW])
        return "대기조 재기동 요청" if d.returncode == 0 else f"대기조 기동 실패: {d.stderr.strip()[:80]}"
    except Exception as e:
        return f"대기조 확인 실패: {e}"
