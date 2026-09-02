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

## 알림에 들어가지 않는 것
- **주전공/부전공 등 트랙별 배분 인원**: 수강편람 API에 해당 필드가 없다.
  응답에 있는 인원 정보는 `ALLOC_RCNT`("현재인원/정원") 합계뿐이며,
  `selectAtlectManualPrecaution` 제한사항도 001~003 모두 "없음"으로 온다.
  그 배분은 수강신청 시스템 내부에서만 보이는 것으로 보인다

## 참고
- 알림 채널 조정은 `notify.py`
- 사용하지 않게 된 키체인 항목: `pnu-sugang-id`, `pnu-sugang-pw`
  (sugang 로그인 방식이 불필요해져 폐기. 지우려면
  `security delete-generic-password -s pnu-sugang-id` 등)
- 수강편람은 실시간 반영에 약간의 지연이 있을 수 있다. **대기순번제 대상 과목이면
  그쪽이 더 확실하다** (수강편람 페이지 공지 4번)
