"""조회 + 여석 판정 공용 모듈 (watch.py / check_once.py 가 함께 쓴다).

수강편람 목록 API로 분반을 찾고, 각 분반마다 인원 상세 API를 호출해
주전공/부전공/일반선택/타대생 트랙별 인원을 얻는다. 트랙은 서로 배타적이므로
'어느 트랙에 자리가 났는지'가 실제 신청 가능 여부를 가른다.
"""
import config

READY_JS = (
    "() => typeof gfn_ajax_request === 'function' "
    "&& !!(window.scwin && scwin.menuInfo && scwin.menuInfo.AUTH_STR)"
)

# 목록 조회 후 대상 분반마다 인원 상세를 이어서 조회한다.
POLL_JS = """
(args) => new Promise(resolve => {
  const call = (url, body) => new Promise(res => {
    let done = false;
    const fin = (v) => { if (!done) { done = true; res(v); } };
    try {
      gfn_ajax_request({url, reqData: body, loading: false,
        success: (data) => fin({ok: true, data}),
        error: (e) => fin({ok: false, err: 'ajax ' + (e && e.status)})});
    } catch (e) { fin({ok: false, err: String(e)}); }
    setTimeout(() => fin({ok: false, err: 'timeout'}), 25000);
  });

  (async () => {
    const list = await call(args.listApi, args.body);
    if (!list.ok) return resolve({ok: false, err: list.err});
    const rows = (list.data || []).filter(r => r.SUBJ_NO === args.subjNo
                                            && args.classes.includes(r.CLASS_NO));
    const out = [];
    for (const r of rows) {
      const p = await call(args.personApi, r);
      out.push({
        cls: r.CLASS_NO, nm: r.SUBJ_NM, subjGcd: r.SUBJ_GCD,
        alloc: r.ALLOC_RCNT, detail: p.ok ? p.data : null,
        detailErr: p.ok ? null : p.err,
      });
    }
    resolve({ok: true, rows: out});
  })().catch(e => resolve({ok: false, err: String(e)}));
})
"""

PERSON_API = "/ost/cls/atlectmanual/atlectmanual/selectAtlectManualPersonnel"

# 인원 상세 응답의 키 -> 표시 이름. 첫 트랙 이름은 과목구분에 따라 달라진다.
_MAIN_LABEL = {"0004": "주전공", "0005": "주전공", "0026": "주전공", "0008": "교직이수자"}


def js_args() -> dict:
    return {
        "listApi": config.API_PATH,
        "personApi": PERSON_API,
        "body": config.payload(),
        "subjNo": config.SUBJ_NO,
        "classes": list(config.WATCH_CLASSES),
    }


def parse_alloc(alloc) -> tuple[int, int] | None:
    """'48/50' -> (48, 50)"""
    try:
        cur, cap = str(alloc).split("/")
        return int(cur.strip()), int(cap.strip())
    except Exception:
        return None


def tracks_of(row: dict) -> dict[str, tuple[int, int]]:
    """분반 1개의 트랙별 (현재인원, 정원). 정원 0인 트랙은 제외."""
    d = row.get("detail") or {}
    main = _MAIN_LABEL.get(str(row.get("subjGcd")), "본교생")
    mapping = [
        (main, "주전공본교생교직이수자"),
        ("부전공", "부전공"),
        ("일반선택", "일반선택"),
        ("타대생", "타대생"),
    ]
    out = {}
    for label, key in mapping:
        pa = parse_alloc(d.get(key))
        if pa and pa[1] > 0:      # 정원 0인 트랙은 애초에 자리가 없다
            out[label] = pa
    return out


def snapshot(page) -> dict:
    """{'ok':bool, 'nm':str, 'sections':{분반:{'total':(cur,cap),'tracks':{...}}}}"""
    r = page.evaluate(POLL_JS, js_args())
    if not r.get("ok"):
        return {"ok": False, "err": r.get("err")}

    sections, nm = {}, config.SUBJ_NO
    for row in r["rows"]:
        nm = row.get("nm") or nm
        total = parse_alloc(row.get("alloc")) or (0, 0)
        sections[row["cls"]] = {
            "total": total,
            "tracks": tracks_of(row),
            "detailErr": row.get("detailErr"),
        }
    return {"ok": True, "nm": nm, "sections": sections}


def wanted(track: str) -> bool:
    """config.WATCH_TRACKS 가 None 이면 모든 트랙, 아니면 해당 트랙만 감시."""
    t = getattr(config, "WATCH_TRACKS", None)
    return True if not t else track in t


def evaluate(snap: dict, had: dict) -> tuple[list[str], dict, str]:
    """(새로 열린 자리 문구들, 갱신된 had, 한줄요약)

    had 키는 '분반:트랙'. 자리가 없어지면 상태를 지워 다음에 다시 알리도록 한다.
    """
    opened, summary = [], []
    for cls in config.WATCH_CLASSES:
        sec = snap["sections"].get(cls)
        if not sec:
            continue
        cur, cap = sec["total"]
        bits = []
        for track, (tcur, tcap) in sec["tracks"].items():
            free = tcap - tcur
            bits.append(f"{track} {tcur}/{tcap}")
            key = f"{cls}:{track}"
            if not wanted(track):
                continue
            if free > 0:
                if not had.get(key):
                    opened.append(f"{cls}분반 {track} {free}자리 ({tcur}/{tcap})")
            else:
                had[key] = False
        if sec.get("detailErr"):
            bits.append(f"상세오류({sec['detailErr']})")
        summary.append(f"{cls} {cur}/{cap}[{' '.join(bits)}]")
    return opened, had, "  ".join(summary)


def key_of(opened_line: str) -> str:
    """'001분반 주전공 1자리 (43/44)' -> '001:주전공'"""
    cls, rest = opened_line.split("분반 ", 1)
    return f"{cls}:{rest.split(' ')[0]}"
