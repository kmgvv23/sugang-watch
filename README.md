# 부산대 여석 알림 — DB3000932 재무관리 (001~003분반)

로그인 없이 **onestop 수강편람 조회 API**를 폴링해서, 감시 분반에 여석이 생기는
순간 텔레그램으로 알린다.

## 원리
- 수강편람 화면 표에는 `제한인원`(정원)만 그려지지만, 조회 API 응답에는
  **`ALLOC_RCNT` = "현재인원/정원"** (예: `"48/50"`)이 들어있다 → 여석 = 정원 − 현재인원
- 요청이 RSA 암호화 + CSRF 토큰을 쓰므로, 헤드리스 크롬에 페이지를 띄워두고
  페이지 자신의 `gfn_ajax_request`를 재사용한다 (암호화를 재구현하지 않음)
- 조회 필수값: `SCH_SYEAR`, `SCH_TERM_GCD`, **`SCH_COLL_GRAD_GCD`** (이게 비면 항상 0건)
- 교과목번호로는 검색이 안 되므로 **교과목명("재무관리")으로 조회 후 `SUBJ_NO`로 필터**

## 알림 채널
**텔레그램 전용.** 다른 채널은 쓰지 않는다. 유일한 채널이므로 미설정/토큰 오류면
감시기가 조용히 도는 대신 **시작 시 즉시 중단**한다. 발송 실패 시 3회 재시도하고,
그래도 실패하면 상태를 기록하지 않아 다음 회차에 다시 알린다.

## 설정 (텔레그램)
1. 텔레그램 `@BotFather` → `/newbot` → 토큰 받기
2. 만든 봇과 대화 시작 (아무 메시지나 전송)
3. `https://api.telegram.org/bot<토큰>/getUpdates` 에서 `chat.id` 확인
4. 저장 (값은 프롬프트로 입력됨):

       security add-generic-password -U -s telegram-bot-token -a pnu -w
       security add-generic-password -U -s telegram-chat-id  -a pnu -w

## 실행
    python3 watch.py

- 시작 시 현재 상태를 1회 알리고, 이후 **001/002/003 중 어느 하나라도 여석이
  0 → 1 이상으로 바뀌는 순간** 알린다 (같은 상태 반복 알림 없음. 다시 찼다가 또 나면 다시 알림)
- 종료는 Ctrl+C

### 백그라운드로 계속 돌리기
    cd /Users/kmg/Sugang && nohup python3 watch.py > watch.log 2>&1 &
    tail -f watch.log

## 설정 바꾸기 (`config.py`)
- `WATCH_CLASSES` — 감시할 분반. 현재 `["001","002","003"]`
- `POLL_SEC` — 조회 주기(기본 30초). 공용 서버이니 과하게 낮추지 말 것
- `SUBJ_NO` / `SUBJ_NM_QUERY` — 다른 과목 감시 시 함께 수정
- `SYEAR` / `TERM_GCD` — 학기 바뀌면 수정 (`0010`=1학기, `0020`=2학기)

## 맥이 꺼져 있어도 감시 (GitHub Actions)
`kmgvv23/sugang-watch` (private) 에 올려두고 `.github/workflows/watch.yml` 크론이
**5분마다** `check_once.py` 를 실행한다. 텔레그램 토큰/chat_id 는 리포지토리 시크릿
(`TG_TOKEN`, `TG_CHAT_ID`).

- **크론 간격은 5분이 GitHub 최소값**이고, 부하가 크면 더 늦게 실행될 수 있다
  (실측 10~20분 지연도 발생). 로컬 30초 감시보다 느리다
- 그래서 **둘 다 켜두는 걸 권한다**: 맥이 켜져 있을 때는 `watch.py`(30초),
  꺼져 있을 때는 Actions(5분)가 받는다. 같은 텔레그램으로 오므로 자리가 났을 때
  중복 알림이 올 수 있다 (해로울 건 없다)
- 반복 알림 방지 상태는 `state.json` 에 커밋되어 유지된다
- 수동 실행: `gh workflow run watch.yml` / 로그: `gh run list --workflow=watch.yml`
- 끄려면: `gh workflow disable watch.yml`

## 트랙별(주전공/부전공/일반선택/타대생) 감시
목록 API 는 합계(`ALLOC_RCNT`)만 주지만, **인원 상세 API** 가 트랙별 인원을 준다:

    POST /ost/cls/atlectmanual/atlectmanual/selectAtlectManualPersonnel
    reqData = 목록 API 가 돌려준 행 객체 그대로
    -> {"제한인원":"52/52","주전공본교생교직이수자":"44/44",
        "부전공":"6/6","일반선택":"2/2","타대생":"0/0"}

- 첫 트랙 이름은 과목구분(`SUBJ_GCD`)에 따라 다르다:
  `0004/0005/0026`=주전공, `0008`=교직이수자, 그 외=본교생
- 트랙은 **서로 배타적인 칸**이고 합이 정원과 같다 (44+6+2=52).
  즉 주전공 자리가 났는지 부전공 자리가 났는지가 신청 가능 여부를 가른다
- 정원이 0인 트랙(예: 타대생 `0/0`)은 애초에 자리가 없으므로 감시에서 제외한다
- 알림은 **어느 분반의 어느 트랙에 몇 자리**인지까지 알려준다
- `config.WATCH_TRACKS` — `None`이면 모든 트랙, 특정 트랙만 보려면 `["부전공"]`
- `config.MY_TRACK` — 내 트랙(현재 `부전공`). 이 칸에 자리가 나면 바로 신청 가능하므로
  **🔴 긴급 알림**에 교과목번호·분반을 담아 보낸다. 다른 트랙은 학과에 전화해
  변경을 요청해야 하므로 **🟡 일반 알림**에 연락처(`DEPT_PHONE`)를 담는다

## 자동 분반변경 (`change_section.py`)
부전공 칸에 자리가 나면 수강정정 시스템에 로그인해 **분반변경을 자동 시도**한다.
이미 DB3000932 006분반을 보유 중이므로, 새로 신청하는 것이 아니라 **교체**다.

    POST /lecapply/lecapply/saveLecapply   (CLS_CHG_FG='Y', CLS_CHG_CLASS_NO=목표분반)

UI 상으로는 신청내역의 재무관리 행에서 `input[id^=CLS_CHG_CLASS_NO]` 에 목표 분반을
넣고 같은 행의 `.class-change`(변경) 버튼을 누르는 것이다. 서버가 원자적으로
교체하므로 **실패해도 기존 분반이 유지된다**.

### 안전장치
- 대상 교과목은 `SUBJ_NO` 하나, 목표는 `WATCH_CLASSES` 안의 분반만
- **삭제 버튼은 절대 누르지 않는다.** '변경'만 사용
- **자동 등록 방지(캡차) 팝업이 뜨면 즉시 중단하고 사람에게 알린다. 풀지 않는다**
  (`LayerPopup.captcha` 는 공용 레이아웃에 정의만 되어 있고 수강정정 페이지에는
  호출 지점이 없다. 다만 서버가 조건부로 띄울 수 있으므로 매번 확인한다)
- 변경 후 신청내역을 다시 읽어 실제 반영을 확인한다
- `PREFERENCE` 순위가 현재 보유 분반보다 높은 분반에만 시도
- 같은 분반 최대 `CHANGE_MAX_TRIES` 회, 최소 `CHANGE_COOLDOWN_SEC` 간격
- 비밀번호는 키체인 → 브라우저 입력란으로만 흐른다
- `AUTO_CHANGE = False` 로 두면 알림만 보낸다

### 단독 실행
    python3 change_section.py --dry-run 002   # 클릭 직전까지만
    python3 change_section.py 002             # 실제 변경

### 시간표 (2026-2학기, 확정 과목과 충돌 없음)
- 001 월수 10:30 강상훈 / 002 화목 15:00 김진우 / 003 월수 12:00 박희진
- 현재 보유: 006 금 09:30-12:30 김무성
- 확정 과목이 차지한 시간: 월수 13:30·15:00·16:30, 화목 09:00·10:30·16:30, 금 09:30-12:30

수강정정 기간: 2026-09-01 08:00 ~ **2026-09-07 17:00**

조회/판정 로직은 `poll.py` 에 모아 `watch.py`(상시)와 `check_once.py`(크론)가 공유한다.

## 참고
- 알림 채널 조정은 `notify.py`
- 사용하지 않게 된 키체인 항목: `pnu-sugang-id`, `pnu-sugang-pw`
  (sugang 로그인 방식이 불필요해져 폐기. 지우려면
  `security delete-generic-password -s pnu-sugang-id` 등)
- 수강편람은 실시간 반영에 약간의 지연이 있을 수 있다. **대기순번제 대상 과목이면
  그쪽이 더 확실하다** (수강편람 페이지 공지 4번)
