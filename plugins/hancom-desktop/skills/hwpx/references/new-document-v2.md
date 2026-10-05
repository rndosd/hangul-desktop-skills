# 빈 문서 생성 v2: 집계 표와 공백 기준 계층

이 통합판은 같은 짧은 요청으로 빈 문서를 설계한다. 원본 문서·이전 첫 결과·학생 개인정보를 생성 입력에 추가하지 않는다. 자연어의 목적과 사실을 해석하는 단계는 작성 에이전트이며, Python 생성기는 그 구조화된 판단을 검사·작성한다. 아래 규칙은 기존 설계/서식 가이드의 수동 들여쓰기 설명보다 우선한다.

## 목적에 맞는 요약 표

집계·수요조사·수량/예산 대조 보고서에서 **제공된 비교 수치가 둘 이상**이고 빠른 대조가 목적이면, `brief.summary_data`를 선언해 요약 표를 기본 선택한다. 날짜·회차·학년이 있다는 이유만으로 표를 만들지 않는다. 학급별 값이나 응답률·미응답·총계는 요청에 없으면 추정하지 않는다. 불일치 숫자는 그대로 보존하고 확인 사항을 붙인다.

`summary_data`의 `metrics`는 `{label, value, unit, evidence, note?}` 문자열 항목이다. 각 숫자·항목·단위는 연결된 `facts`에 있어야 한다. `presentation`의 기본은 `auto`이며 표로 구체화된다. 문장 중심 안내처럼 비교할 필요가 없거나 사용자가 표를 원하지 않으면 `presentation:text`와 `text_reason`을 명시한다. 표를 넣기 위해 관계없는 숫자를 모으지 않는다.

작성 에이전트는 제목·설명·확인 사항을 문서 목적에 맞게 배치하고, `design.summary_after`에 요약 표를 놓을 블록 id를 지정한다. `prepare`가 제공 수치만으로 요약 표를 삽입한다. 이미 `summary_group:provided_metrics` 표를 직접 설계했다면 그 표를 보존하고 같은 행의 항목/값을 검사한다. 기본 표는 2열 또는 확인 사항이 있는 3열일 뿐 문서 전체의 고정 양식이 아니다. 열 이름·너비·위치는 직접 설계한 표로 달리 정할 수 있다.

필수 사실과 요구 문구가 `재적 79명`처럼 항목/값 셀로 나뉘면 **같은 행**을 공백으로 연결해 검증한다. 다른 행을 합쳐 누락 사실을 충족시키지 않는다. `claims`는 여전히 실제 보이는 부분 문자열을 요구하므로 숫자·단위를 포함한 보이는 셀 문구를 정확히 연결한다. 중요한 확인 질문은 기존 규칙대로 기록한다. 확인 표시 초안이면 진행할 수 있지만 확정본에서는 필요한 답을 받아야 한다.

예: `summary_data={caption:'제공 집계',metrics:[{label:'재적',value:'79',unit:'명',evidence:['enrolled']},{label:'구입 희망',value:'74',unit:'명',evidence:['wants']}],presentation:'auto'}`. facts에는 각각 `재적 79명`, `구입 희망 74명`이라는 요청 유래 문구가 있어야 한다. 표의 확인 사항은 근거가 있는 문구 또는 `[확인 필요: ...]`로 쓴다.

## 번호·글머리표·설명

번호를 붙일 의미상 계층만 0→1→2칸 상당 들여쓰기를 사용한다. 기본 `indent_policy:font_spaces`는 설치된 글꼴 U+0020 폭과 해당 문단의 크기/굵기/장평을 읽어 왼쪽 위치를 계산한다. 공백 문자열을 본문 앞에 붙이지 않는다. 실제 한글 렌더 위치를 검증한 값은 아니다. 번호 모양은 필요할 때 `heading_numbering`의 `1. → 가. → 1)`을 선택한다. 짧은 문서에 3단계를 억지로 만들지 않는다.

`paragraph.list` 또는 `table.list`는 `{kind:number|bullet,level:2|3,group:...}`를 사용하고 기본 경로에서는 `indent_left_mm`를 생략한다. 의미상 독립된 항목은 번호, 짧은 동급 제안은 native 가운데점, 이유·해설·이어서 읽는 문단은 일반 문단으로 둔다. 그룹별 번호 초기화와 자동 내어쓰기는 유지한다. 기존 `bullets` 문자열 접두 경로는 과거 호환용이며 새 설계에서는 사용하지 않는다.

사용자가 지정한 `brief.format.heading_layout`은 자동 위치보다 우선한다. 항목에도 명시적 위치가 필요하면 사용자가 지정한 `brief.format.indent_policy:explicit`와 각 `list.indent_left_mm`를 기록한다. 에이전트가 임의로 고른 6mm는 기본 규칙을 덮어쓸 수 없다. 미지원 글꼴/비영 자간에서 측정이 불확실하면 오류를 설명하고 명시적인 위치를 받아야 하며 다른 글꼴로 바꾸지 않는다.

같은 ‘1칸’도 글꼴·크기에 따라 다르다. 이 컴퓨터의 11pt·장평 100·자간 0 맑은 고딕은 1칸 약 387 HWPUNIT, 2칸 약 773 HWPUNIT이며 함초롬바탕은 각각 330/660이다. 서로 다른 제목 크기에는 그 크기로 계산한다. 번호 너비와 줄 바꿈 뒤의 실제 정렬은 native 확인 항목이다.

## 실행과 보존

```powershell
$taskCodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$pythonExe = (Get-Content -Raw -LiteralPath (Join-Path $taskCodexRoot 'skills/hwpx/environment.json') | ConvertFrom-Json).pythonPath
& $pythonExe -X utf8 scripts/create_new_document.py prepare --brief brief.json --design design.json --prepared-design prepared-design.json
& $pythonExe -X utf8 scripts/create_new_document.py validate --brief brief.json --design prepared-design.json
& $pythonExe -X utf8 scripts/create_new_document.py create --brief brief.json --design prepared-design.json --output improved.hwpx
```

`prepare`는 별도 JSON 파일을 배타적으로 작성하며 기존 파일을 덮어쓰지 않는다. 생성 후 그 HWPX와 입력을 다시 고쳐 첫 결과처럼 제시하지 않는다. 새 판은 별도 이름으로 보존한다. 요약 표의 기본 정렬은 머리글 가운데·값 오른쪽·설명 왼쪽, 셀 안 여백 좌우 1.5mm/위아래 1mm, 줄 간격 140%다. 명시한 사용자/작성 서식은 우선한다. 표 경계·쪽 나눔은 native 미검증이다.

이 경로는 설치·등록·보안 변경·외부 업로드·COM 재시도를 수행하지 않는다. COM 기능 자체는 기존 스킬에 유지하며, native 미검증을 구조 검사 통과와 구별해 보고한다.

## 사실·대상 범위의 검토 보완

요청이 작업 순서를 주었다고 해서 단계별 참여 대상·자격·제외 범위까지 확정된 것으로 해석하지 않는다. ‘대표 학년을 고르고 추가 과제를 한다’만으로 ‘선정 학년의 학생만 과제를 한다’고 좁히지 않는다. 중요한 범위가 미정이면 먼저 질문하고, 확인 표시 초안이 허용되면 대상 범위를 확정하지 않는 문장으로 쓴다. 운영 제안은 해당 문장에 제안임을 표시한다. 제작 보조 기록의 가정이나 문서 끝의 포괄적인 확인 목록만으로 본문 단정을 정당화하지 않는다.

작성 단계에서 미정 범위가 쓰이는 블록을 파악해 `brief.unknowns` 항목에 `block_ids:[...]`를 선언한다. 각 블록에도 정확한 `[확인 필요: 항목]` 표시를 두어야 하며 `validate`는 누락을 `UNKNOWN_NOT_MARKED_AT_USE`로 거부한다. 이 계약은 작성자가 선언한 범위의 검사이며 자연어에서 모든 미정 사실을 자동 발견하거나 표시가 붙은 모든 문장을 의미적으로 보증하지 않는다. 본문을 원 요청과 대조하는 단계는 유지한다.

집계에서 값의 산술 차이와 원인을 구별한다. 74+2와 79가 다르더라도 조사 범주가 전체를 빠짐없이 나눈다는 근거가 없으면 차이를 ‘미응답 3명’으로 쓰지 않는다. 제공 값과 이미 요구된 확인 표시를 보존한다. 별도 산술 대조 설명은 내부 검토 제안으로 추가할 수 있으나, 짧은 요청에서 요구되지 않은 설명의 생략을 사실 왜곡으로 단정하지 않는다.
