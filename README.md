# 원문 확인 (PoC)

공모전·청년정책 포털의 **공고 요약**이 주최 측 **원문**과 다른 곳을 7항목으로 찾아 주는 도구입니다.
「엘리스 AI 챌린지 2026」 출품용 PoC입니다. 데모: https://wonmun-check.vercel.app

**시험 결과**(공고 15건, 마감과 자격 30칸 중 원문과 다른 16칸, 엔진 고정 후 1회, [eval/report_test.md](eval/report_test.md)):
원문과 다른 칸 13/16을 찾았고 잘못 경고는 14칸 중 1칸이었습니다. AI가 낸 근거 인용 171개는 코드 검사 전에도 모두 원문과 글자 그대로 같았습니다.
정답표는 도구 코드와 결과를 보지 않은 별도 AI 세션이 원문만 보고 1차로 적었고 사람이 전부 다시 확인하지는 않았습니다.

- 7항목: 마감 일시, 참가 자격, 참가 형태·인원, 시상, 제출물·분량, 실격·감점, 생성형 AI·저작권
- **AI는 찾기만 하고, 판정은 코드가 합니다.** AI(Claude Haiku 5.5)가 항목마다 근거 문장을 글자 그대로 복사해 오면,
  코드가 ① 그 문장이 원문에 정말 있는지 확인하고 ② 날짜·시각·금액을 정규식으로 다시 읽고 ③ 정해 둔 규칙으로 판정합니다.
- 근거가 원문에 없으면 값을 버리고 '확인 필요'로 둡니다. 다른 점을 못 찾으면 "다른 점을 찾지 못함, 원문 확인 권장"이라고 씁니다('일치'라고 쓰지 않음).

## 준비

```bash
git clone https://github.com/ym0506/wonmun-check && cd wonmun-check
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

AI 키는 저장소에 두지 않습니다. 환경변수 `ANTHROPIC_API_KEY`나 키 파일(기본 `~/.config/anthropic/.env`)의 `ANTHROPIC_API_KEY=` 한 줄을 읽습니다.
다른 파일을 쓰려면 `WONMUN_KEY_FILE=/경로/.env`를 지정하세요. 키가 없어도 예시 3건은 볼 수 있습니다.

## 웹 화면 실행

```bash
.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
```

브라우저에서 http://127.0.0.1:8000 을 엽니다.

- **예시 보기**: L07(KISTI DATA·AI 분석 경진대회), L20(밀양 매운맛 쇼츠), Y1(콘진원 우수인재 연계 기업인턴십).
  2026-11-04 공고로 미리 돌려 저장한 결과(`web/examples/*.json`)를 AI 호출 없이 보여 줍니다.
- **직접 확인**: 요약(링커리어 공고 주소, 온통청년 정책 주소, 또는 요약 글 붙여 넣기) + 원문(주소 또는 PDF·HWPX·TXT 파일, 선택).
  1건에 10~30초. 원문을 비우면 포털 페이지 안 '위쪽 칸 ↔ 본문'만 대조합니다.
  - 온통청년 상세 페이지는 요약 칸이 서버 HTML에 비어 있어(자바스크립트로 채움) 읽지 못합니다. 화면 안내대로 칸 글을 붙여 넣어 주세요.
- 행을 누르면 근거 문장이 출처 앞뒤 문맥 안에서 노랗게 표시됩니다. 빨간 항목이 있으면 '포털 오류 신고 문장 복사' 버튼이 나옵니다.

### 설정(환경변수)

| 이름 | 기본값 | 뜻 |
|---|---|---|
| `WONMUN_MODEL` | `claude-haiku-5-5` | AI 모델 |
| `WONMUN_EFFORT` | `low` | AI effort(low·medium·high) |
| `WONMUN_THINKING` | `adaptive` | `disabled`로 생각 끄기(effort high 이하만) |
| `WONMUN_DAILY_LIMIT` | `60` | 직접 확인 하루 전체 횟수(0이면 막음) |
| `WONMUN_IP_DAILY_LIMIT` | `10` | 접속 주소당 하루 횟수 |
| `WONMUN_MAX_SOURCE_CHARS` | `60000` | 출처 하나에서 AI에 보내는 최대 글자 수(넘으면 화면에 적음) |
| `WONMUN_KEY_FILE` | `~/.config/anthropic/.env` | 키 파일 |
| `WONMUN_LEDGER` | `data/api_ledger.jsonl` | 호출 기록(토큰 수만) |

temperature는 설정하지 않습니다. Claude Haiku 5.5와 SDK 2.4.0 기본 API 버전(2026-10-21)은 temperature를 받지 않습니다.

## 시험

```bash
.venv/bin/python -m pytest -q                 # 단위 시험(날짜 읽기, 판정 규칙, 인용 검사, HWPX 등)

# 개발용 표본(11/4 CSV) — 원본 받기(로컬 data/dev_sources/에 저장, git 제외)
.venv/bin/python -m eval.fetch_sources
# 도구 실행(AI 호출, eval/api_calls.jsonl 기준 100회 상한)
.venv/bin/python -m eval.run_tool --run r1
# 규칙만 바꿨을 때: 저장된 AI 출력으로 다시 채점(호출 0)
.venv/bin/python -m eval.run_tool --rescore r1 --run r1c
# 비교군: 같은 모델 1회 질문(--ask는 AI 호출), 규칙만(정규식)
.venv/bin/python -m eval.baseline_chat --ask
.venv/bin/python -m eval.baseline_regex
# 채점 → eval/metrics_dev.md
.venv/bin/python -m eval.score --main r1c --alt r1 r1b --repeat r1c r2c r3c --stage1 s1c
# git에 넣는 결과에서 전화번호·전자우편 가리기(다시 채점한 뒤 꼭 실행)
.venv/bin/python -m eval.redact
# 화면 예시 다시 만들기
.venv/bin/python -m eval.make_examples --run r1c
```

결과 정리: 개발용 표본(규칙을 맞추는 데 쓴 11건) `eval/report_dev.md`, 시험용 표본(엔진 고정 후 15건) `eval/report_test.md`.

## 폴더

```
wonmun/            엔진
  textsrc.py       글자 꺼내기(HTML·PDF·HWPX·TXT), 위치 번호
  portals.py       링커리어 칸/본문 분리, 온통청년 칸 읽기
  fetch.py         주소 한 번 읽기(내부망 차단, 15MB 제한)
  llm.py           AI 근거 찾기(구조화 출력), 호출 기록
  quotes.py        인용 검사(글자 그대로 있는지)
  dates.py         날짜·시각 정규식
  money.py         금액·현금/현물
  judge.py         값 정리와 판정 규칙
  pipeline.py      요청 한 건의 흐름
web/               FastAPI + 정적 화면(외부 CDN 없음), examples/ 저장 예시
eval/              개발용 표본 시험, 비교군, 채점, 결과
tests/             pytest
docs/study/        학습 노트
```

## 생성형 AI 활용 범위(대회 공개용)

- 서비스 안: 7항목 근거 문장 찾기와 짧은 요약(화면에 'AI가 찾은 근거', 'AI 요약'으로 표시). 날짜·금액 읽기와 판정은 코드.
- 개발 과정: 코드·시험·문서 초안 작성에 Claude(코딩 도우미)를 썼습니다.

## 지키는 것

- 키는 저장소에 두지 않고 출력·로그·커밋하지 않습니다. 배포는 아래 Vercel 설정으로 합니다.
- 봇 확인 화면·로그인·403은 우회하지 않고 실패로 알립니다.
- `data/dev_sources/`(받은 원본), `data/runs/`(전체 실행 결과)는 git에 넣지 않습니다.

## 배포(Vercel)

루트 `index.py`가 `web.app`의 `app`을 Vercel에 넘긴다. 설정은 `vercel.json`(함수 최대 60초, 시험·자료 폴더 제외), 올리지 않을 파일은 `.vercelignore`, 파이썬 버전은 `.python-version`(3.14, Vercel이 3.13을 받지 않음). 배포 묶음에는 `requirements.txt`만 들어간다(개발·시험용은 `requirements-dev.txt`).

- 키는 Vercel 환경변수 `ANTHROPIC_API_KEY`로만 넣는다(저장소·파일에 두지 않음).
- Vercel에서는 디스크가 `/tmp`만 쓰기 가능이라 호출 기록이 `/tmp`로 간다. 인스턴스가 바뀌면 지워지므로 하루 호출 제한(`WONMUN_DAILY_LIMIT`, `WONMUN_IP_DAILY_LIMIT`)도 인스턴스마다 따로 센다. 비용 상한은 Anthropic 콘솔의 사용 한도로 건다.
- 접속 주소는 Vercel이 채우는 `x-real-ip`를 쓴다(로컬에서는 헤더를 믿지 않음).
