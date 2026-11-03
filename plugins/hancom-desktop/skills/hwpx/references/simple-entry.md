# 공통 진입 도구

`SKILL_DIR`는 읽은 SKILL.md가 있는 실제 폴더다. PowerShell의 호출은 다음 형태다.

```powershell
$taskLauncher = Join-Path $taskSkillDir 'scripts/Invoke-HangulTask.ps1'
& $taskLauncher doctor
```

`$taskSkillDir`에 확인한 실제 경로를 넣는다. 로컬 설정이 없으면 현재 `CODEX_HOME/skills`의 environment.json에서 Python을 읽고 포함된 vendor core를 선택한다. 설정이 없으면 저장소 README의 `Install.ps1` 설치를 먼저 안내한다. doctor는 이 경로·해시를 보고하며 쓰기 권한·COM·보안 모듈은 별도 확인이다. 파일 존재는 `Test-Path -LiteralPath (Join-Path $taskSkillDir 'scripts/Invoke-HangulTask.ps1')`로 확인하고 실제 권한 오류 없이 읽기 전용이라 단정하지 않는다.

## 조회 결과를 편집에 이어 쓰기

이 문서의 명령 외에 기존 `scripts/*.py`가 필요하면 `& $taskLauncher tool 스크립트.py 인자...`로 호출한다. 예: `& $taskLauncher tool select_document_block.py --list --summary`. 기존 CLI의 인자·출력·종료 코드를 유지하며 선택된 Python과 vendor를 사용한다. 다른 참조의 `python` 예시는 이 선택된 런타임을 뜻한다. 이미 확인한 환경에서 PATH의 `python`·`py`·Windows 앱 별칭을 다시 탐색할 필요가 없다.

여러 문구나 지정 셀을 바꿀 때는 아래 공통 명령을 쓴다. 기존 `inspect_many`·`make_plan`·`apply_plan`을 연결한 것으로 지원 범위와 보존 검사는 같다. 같은 원본의 조회 결과를 계획에 다시 사용하며 별도 `diagnose`를 앞뒤로 반복하지 않는다.

```powershell
& $taskLauncher inspect source.hwpx --queries queries.json --output targets.json
& $taskLauncher text-plan --inspection targets.json --changes changes.json --output edits.json
& $taskLauncher text source.hwpx result.hwpx --plan edits.json
```

`queries.json`은 기존 [선택 텍스트 조회](selected-text-edit.md)의 배열이다. 예: `[{"find":"기존 제목"},{"find":"기존 일정","table":1,"row":2,"column":1}]`. 조회는 전체 JSON을 파일에 저장하고 화면에는 각 문구의 후보 최대3개·지원 여부·거부 이유·파일 위치만 표시한다. 나머지 후보가 필요할 때만 해당 파일을 읽는다. 지원 가능한 후보가 있다는 것이 모든 일치 위치의 지원을 뜻하지 않는다.

`changes.json`은 조회 순서(0부터)와 검토한 target_id를 명시한다. 여러 변경을 한 계획으로 묶는다.

```json
[{"query":0,"targets":["조회에서 검토한 target_id"],"replace":"새 제목"},
 {"query":1,"targets":["조회에서 검토한 다른 target_id"],"replace":"새 일정"}]
```

단건 또는 다중 조회 파일 모두 받을 수 있다. 다른 원본 revision의 조회 혼합·중복 대상·미지원 대상은 계획을 만들지 않는다. 적용 시 기존 엔진이 현재 해시와 대상, 겹친 편집, 비대상 보존을 다시 확인한다. 이는 필요한 쓰기 가드이며 조회를 새로 반복할 이유는 아니다. 빈 칸 채움·행 추가·정렬처럼 다른 연산은 아래 기존 전용 경로에 묶고, 구조 변경으로 좌표가 달라진 다음 단계만 새 원본에 결합한다.

본문 항목을 추가하거나 복제 가능 여부와 문구 편집 가능 여부가 다른 경우:

```powershell
& $taskLauncher inspect-body source.hwpx --find '필요한 본문' --output body.json
```

기존 본문 inspect 결과 전체를 저장하고 일치 문단의 `cloneEligibility`와 `directRunTextEdit`를 구분해 보여준다. `--find`는 요약 표시만 좁힌다. 기존 binding은 본문 구조 도구에, 지원 run 후보는 현재 revision의 공개 batch 계약에 연결한다. 후보 표시는 편집·보존 합격이 아니다. 새 내용의 필수 변형이 지원되는지는 선택한 후보에서 먼저 확인하고 그 조회를 실제 편집에 사용한다. 모든 양식·모든 기능을 검사할 필요는 없다.

## 준비된 완성형 계획서 채우기

계획서 작성은 [완성형 3종](template-selection.md#준비된-완성형-계획서) 중 적합한 하나를 고른 뒤 같은 ID의 [조립](#개요로-공문서형-계획서-조립)을 쓴다. fill은 조립이 실패했을 때의 예비다. `SKILL_DIR`는 실제 hwpx 스킬 폴더이며 실행기는 이미 선택한 환경을 재사용한다.

**구역 늘리기·빼기.** 양식 설명(`fill --template`)의 `sections`는 통째로 반복하거나 뺄 수 있는 구역이다(예: 활동 영역 ① 제목·목적·기간·대상·방법·내용). 내용의 영역 수만큼 `{"sections": {"activities": [영역1, 영역2, 영역3]}}`처럼 구역 입력을 영역마다 하나씩 준다. 복사된 구역의 원 숫자는 ①→②→③으로 이어지고, `heading`을 받는 구역은 제목 문구도 바꿀 수 있다. 빈 목록은 구역을 지우며(최소 개수가 0일 때), 구역 입력을 구역 밖 값과 중복해 주면 거부한다. **내용이 양식 칸보다 많으면 버리지 않는다.** 구역으로 늘리거나, 맞는 양식을 고르거나, 구조 편집으로 보완하고, 그래도 넣지 못한 내용은 사용자에게 알린다. 종합사업형은 과제가 요약·성과표와 연결돼 있어 구역 반복을 제공하지 않는다.

```powershell
$planCatalog = Join-Path $taskSkillDir 'assets/document-templates/full-plans.json'
& $taskLauncher fill --catalog $planCatalog --template plan-school
& $taskLauncher fill --catalog $planCatalog --template plan-school --values 계획내용.json --output 운영계획.hwpx
```

조회한 항목명과 반복 목록으로 내용을 채운다. `valueFrom` 연결 위치는 독립 입력이 아니며 제목 등을 중복 작성하지 않는다. 원문 제거·서식 맞춤·표 셀 탐색은 준비 단계에서 끝난 항목만 재사용한다. 고정 칸을 추가하거나 구역을 덜어내려면 같은 원본의 기존 편집 기능을 쓴다. 구역을 생략하는 전용 옵션이 생긴 것은 아니다. 사용자에게 양식 복사를 맡길 필요 없이 fill이 원본을 보존한 새 출력 하나를 만든다. 작성 후 실제 출력 확인은 계속 필요하다.

아래 블록 입력·`--content`·compose는 필요한 표나 부분 구조를 보완할 때 사용한다.

## 개요로 공문서형 계획서 조립

장·절 수가 정해지지 않은 공문서형 계획(Ⅰ. / 1. / 가. / 1) / ○ / - / ‧ / ※, 표 포함)은 한 원본에서 잘라 둔 부품을 개요 순서로 붙이는 `assemble`을 쓴다. 기본 양식은 `plan-official`(교육부 「2027학년도 대학수학능력시험 시행기본계획」 서식, 공공누리 출처표시, 원문 문구 없음)이다.

```powershell
& $taskLauncher assemble --template plan-official --outline 개요.json --output 계획.hwpx --pdf 계획.pdf --run 작업폴더/assemble-run --context host-approved
```

```json
{"schema":"hwpx.assembly-outline.v1","template":"plan-official",
 "cover":{"title":"학업성취도 평가 시행계획","subtitle":"2027학년도 ○○도 중학교 3학년","date":"2027. 3. 15.","organization":"○○도교육청"},
 "nodes":[{"t":"chapter","text":"평가 개요"},
          {"t":"heading","level":1,"text":"평가의 목적"},
          {"t":"item","text":"성취 수준을 진단함."},{"t":"dash","text":"세부 내용"},{"t":"dot","text":"하위 내용"},{"t":"note","text":"참고 사항"},
          {"t":"table","part":"schedule","rows":[["시행계획 안내","3. 15.(월)",""]]}]}
```

- 번호(Ⅰ. 1. 가. 1))는 개요에서 만든다. 문구에 번호를 넣지 않는다. 절을 빼면 뒤 번호가 당겨진다.
- `cover`의 `title`·`date`는 필수다. `subtitle`(제목 위 작은 줄)·`organization`은 빼면 빈 줄로 남는다.
- `level` 2는 1 아래, 3은 2 아래에만 둔다. 3단계 제목 아래 항목은 원본처럼 한 단계 깊게 들여 쓴다.
- 표 부품: `schedule`(주요 업무·추진 일정·비고 3열, 첫 열 앞에 ` ○ `), `two-column`(구분·내용 2열). `rows`의 한 항목이 표의 반복 묶음 하나이며 1~100개를 넣는다. 묶음의 칸은 왼쪽 위부터 읽는 순서로 manifest `unitCells`개를 적는다(두 부품은 한 줄 묶음이라 열 수와 같다). 칸 하나에 여러 문단이 필요하면 문자열 목록(`["가", "나"]`)을 쓰고 빈 칸은 `""`이다. 제목 행은 선택 `"header":["학년군","주요 활동"]`(`headerCells`개)로 바꾸며, 빼면 부품의 제목을 쓴다. 묶음이 여러 줄(`unitRows`)이고 칸이 합쳐진 표도 같은 방식이며, `repeat`가 false인 표는 묶음 하나만 받는다.
- 장 제목 상자는 제목 길이에 맞춰 넓어진다. 본문 폭을 넘는 제목은 실행 전에 거부한다.
- 문구는 줄바꿈·탭 없이 한 문단씩 넣는다. 빈 문구와 `[항목]` 같은 자리표시 문구는 거부한다.

### 사업형(요약·상세) 조립: `plan-project`

완성형 사업형과 같은 디자인(띠 장 제목 Ⅰ, 번호 탭 1, 네모 번호 과제 제목, □ 소제목, ◦ / - / ⇒ / ※, ◈ 상자)을 길이에 관계없이 조립한다. 표지 다음 쪽에 선택 `summary`(요약 쪽)가 오고, 상세 본문은 새 쪽에서 시작한다. 쪽 번호는 표지 다음 쪽부터 붙는다.

```json
{"schema":"hwpx.assembly-outline.v1","template":"plan-project",
 "cover":{"title":"사업 추진계획","subtitle":"부제","date":"2027. 3.","organization":"○○교육청","department":"담당 부서"},
 "summary":{"title":"사업 추진계획","nodes":[{"t":"chapter","text":"추진 배경"},{"t":"item","text":"요약 문장"},{"t":"point","text":"현재: 상황"},{"t":"arrow","text":"개선: 방향"}]},
 "nodes":[{"t":"chapter","text":"추진 배경"},{"t":"subhead","text":"추진 필요성"},{"t":"item","text":"배경"},
          {"t":"chapter","text":"중점 추진 과제"},{"t":"task","text":"첫째 과제"},{"t":"item","text":"(목표) ..."},{"t":"dash","text":"세부"},
          {"t":"chapter","text":"사업 추진 계획"},{"t":"heading","level":1,"text":"성과 관리"},{"t":"box","text":"핵심 문장"},
          {"t":"table","part":"indicators","rows":[["과제",["지표 1"],["지표 2"]]]}]}
```

- `t`: `chapter`(Ⅰ 띠, 요약 안에서는 Ⅰ. 글자 제목), `heading` level 1(번호 탭 1·2·3, 긴 제목이면 탭이 넓어진다), `task`(네모 번호 과제 제목, 장·탭마다 다시 1부터), `subhead`(□ 소제목, 번호 없음), `point`(① 원 번호 줄, 장마다 1부터), `item`·`dash`·`arrow`·`note`, `box`(◈ 상자), `table`. 요약 안의 `item`·`task`는 요약 쪽 간격의 부품을 쓴다.
- 표 부품: `three-column`(영역·내용·배점 3열, 제목 행은 `header`로 바꾼다), `indicators`(과제 칸이 두 줄에 걸친 2줄 묶음: 칸은 과제·지표 1·지표 2 세 개).

### 학교형·교육사업형 조립: `plan-school`·`plan-education`

완성형 학교형·교육사업형과 같은 디자인(□ 막대 소제목과 ❍ 문단, 번호 탭 1·2·3, 네모 번호 과제 제목, ◦ / -)을 길이에 관계없이 조립한다. 본문은 장 없이 □ 막대(추진 근거·배경·목적·방침 등)로 시작할 수 있고, 첫 `chapter`부터 번호 탭이 붙는다.

```json
{"schema":"hwpx.assembly-outline.v1","template":"plan-school",
 "cover":{"title":"독서 주간 운영계획(안)","organization":"○○초등학교 · 독서교육 담당"},
 "nodes":[{"t":"subhead","text":"추진 근거"},{"t":"lead","text":"근거 문장"},
          {"t":"subhead","text":"추진 목적"},{"t":"lead","text":"목적 1"},{"t":"lead","text":"목적 2"},
          {"t":"chapter","text":"세부 운영 계획"},{"t":"task","text":"운영 개요"},
          {"t":"item","text":"대상: 전교생"},{"t":"item","text":"운영 내용"},{"t":"dash","text":"월요일 | 활동"},
          {"t":"item","text":"추진 절차"},
          {"t":"table","part":"steps","rows":[["준비","운영","공유","평가","담당 / 시기","담당 / 시기","담당 / 시기","담당 / 시기"]]},
          {"t":"task","text":"기대 효과"},{"t":"lead","text":"효과 문장"}]}
```

- `t`: `subhead`(□ 막대 제목), `lead`(❍ 문단), `chapter`(번호 탭 1·2·3, 긴 제목이면 탭이 넓어진다), `task`(네모 번호 과제 제목, 장마다 다시 1부터), `item`(◦), `dash`(-), `table`. "목적: …"처럼 이름표가 붙는 줄은 `item` 문구에 그대로 쓴다.
- `plan-school`: 표지 없이 첫 쪽 머리에 제목 띠와 작성 부서가 온다. `cover`는 `title`(필수)·`organization`. 표 부품 `steps`는 ⇨로 이은 4단계 절차표로 묶음 하나(칸 8개: 단계 4개 → 각 단계의 담당·시기 4개)만 받는다. 쪽 번호는 없다(완성형과 같다).
- `plan-education`: 표지 쪽 다음에 본문이 온다. `cover`는 `title`·`date`(필수), `subtitle`(제목 위 줄), `organization`이며 `title`·`organization`은 본문 첫 쪽 머리에도 함께 들어간다. 표 부품 `targets`는 순·대상·담당·사업·활동·기간·비고 6칸 반복 표다. 쪽 번호는 본문 쪽부터 붙는다.

입력 검사가 끝난 뒤 한글을 한 번 열어 표지 부품에 장·제목·항목·표 부품을 차례로 붙이고 저장·재열기·PDF를 만든다. 결과의 `assembly`는 저장본에 자리표시가 남지 않았는지와 요청한 문구·표 행 수를 확인한 값이며, `wrapAlignment`·`pageLayout`은 PDF 배치 경고다. `PASS_NATIVE` 뒤에도 쪽 이미지를 확인한다([preview](#준비된-블록-조합)). 내 양식을 부품으로 등록하는 방법은 저장소의 `tools/build_assembly_template.py`(부품 지도 → 블록 저장 → 자리표시·정규화 → manifest)이며, 등록한 폴더는 `--catalog`로 지정한다.

## 준비된 양식 채우기

현재 기본 목록은 `full-plans.json`의 완성형 계획서 3종이다. 위 fill 호출을 사용한다. 개인 양식은 해당 업무 폴더의 `--catalog`를 명시한다. 과거 블록 ID·합본은 기본 선택에서 제외한다.

## 내용 수정과 표 서식을 함께 적용

다른 양식을 합치거나 내용을 줄여 표 서식 조정이 필요한 adapt 작업에서는, 선택한 주양식과 셀 역할에 맞춘 변경을 `layout` 요청으로 연결한다. 글꼴·정렬을 별도 Python/COM 스크립트로 셀마다 수정할 필요가 없다. 기존 조회에서 확인한 표와 범위를 사용하며 새 전체 진단을 요구하지 않는다.

```powershell
& $taskLauncher text source.hwpx result.hwpx --plan edits.json --layout layout.json
# 이미 내용 편집이 끝났다면:
& $taskLauncher layout edited.hwpx result.hwpx --request layout.json
```

`text --layout`, `batch --layout`, 단독 `layout` 모두 `--dry-run`을 지원한다. 내용+서식 경로는 텍스트 전용 보존 엔진의 임시 후보에 기존 공개 atomic batch를 이어 실행하고 최종 사본 하나만 발행한다. 빈 셀·지정 run·구조 편집도 `batch --request edits.json --layout roles.json`으로 같은 연결을 사용한다. 서식 범위는 내용/구조 변경 후의 표 좌표이며 `expectedRevision`은 편집 전 원본 해시다. 단독 `layout`도 같은 batch를 쓴다. 중간 결과는 비공개 후보이고 전체 성공 때만 최종 파일 하나를 발행한다.

```json
{"schema":"hangul.layout.v1","expectedRevision":"sha256:현재 입력 해시",
 "groups":[
   {"role":"일정 설명","table":1,"range":[2,2,6,2],"fontName":"휴먼명조","alignment":"LEFT","trimEmptyParagraphs":true},
   {"role":"담당","table":1,"range":[2,3,6,3],"fontName":"휴먼명조","alignment":"CENTER","verticalAlignment":"CENTER","trimEmptyParagraphs":true}
 ],
 "rowHeights":[{"table":1,"rows":[6],"heightMm":9}]}
```

표 번호와 `[첫 행, 첫 열, 끝 행, 끝 열]`은 1부터이며 병합 셀의 논리 주소를 쓴다. 병합 셀 일부를 자르는 선택·충돌하는 역할 설정·오래된 해시는 쓰기 전에 거부한다. 행 높이는 세로 병합과 겹치지 않는 행만 지원한다. `fontName`은 문서에 선언된 주양식 글꼴로 지정하며, 아직 없는 글꼴 선언은 기존 `styles.ensure_font` 경로를 사용한다. `fontSizePt`는 필요한 역할에만 지정하고 생략하면 원래 크기·강조를 유지한다. 선·배경·열 너비·병합은 변경하지 않는다.

`trimEmptyParagraphs`는 선택한 내용 있는 셀의 단순 빈 문단만 지운다. 빈 입력 칸·개체/필드/강제 쪽 나눔을 가진 문단은 유지한다. 행 높이는 내용과 기존 미리보기에서 정한 값을 명시하며 자동으로 가장 작은 값으로 줄이지 않는다. `text` 영수증의 `layout_follow_up`과 연결할 때도 해당 셀만 선택한다. 필요한 역할 설정을 실행에 넣는 경로이지 모든 문서에 모든 항목을 검사하는 새 체크리스트가 아니다.

블록을 조합하는 경우 각 블록의 서식 조정까지 끝낸 후 `compose`로 저장·PDF를 한 번 생성한다. 이미 조합한 문서의 피드백 수정에도 같은 `layout`을 쓸 수 있다. 서식이 맞고 내용만 고치는 요청에는 추가할 필요가 없다.

## 단건 문구 치환

```powershell
& $taskLauncher replace report.hwpx result.hwpx --find '정확한 문구' --replace '새 문구'
```

유일한 본문 텍스트 노드 안의 단건만 지원한다. 원본과 다른 신규 출력이 필수다. 내부 safe_replace의 사전진단·public API·전체 보존 검사는 유지된다. BLOCK이면 쓰기하지 않는다. 여러 run/여러 수정/지정 셀/중복 위치는 [선택 텍스트](selected-text-edit.md) 또는 [본문 구조](body-structure-edit.md)의 기존 경로로 처음부터 계획한다. 거부된 연산을 다른 경로로 자동 우회하지 않는다.

## 업무 표 행 삭제·삽입

```powershell
& $taskLauncher schema table
& $taskLauncher table report.hwpx result.hwpx --request task.json
```

task.json은 `schema: hangul.task.v1`, `operation: table`, `headers`(정확한 전체 제목 셀 배열), `reason`(8자 이상 구체적 이유), `operations` 배열이다. 연산은 다음 두 형태만 지원한다.

```json
{"op":"delete","key":{"실행 업무":"삭제할 셀의 완전한 문구"}}
{"op":"insert_after","key":{"실행 업무":"기준 셀의 완전한 문구"},"cells":["단계","새 항목명: 설명 전체","담당","목표일"],"heightHwpunit":2400}
```

key는 해당 제목 열의 완전한 기존 셀 값이다. 순번을 추정하지 않는다. cells는 모든 열 순서의 문자열이다. 사용자 메모가 `항목명: 설명`을 제공하면 둘을 모두 넣는다. 삽입 기준의 모든 셀이 한 문단/한 run일 때만 3차원 지도 변환을 자동 처리한다. 복잡한 run을 임의로 평문화하지 않는다. 원본을 한 번 읽고 기존 보존 모델에서 연속 행 키를 해석한다. 새 행을 다음 연산의 키로 참조할 수 있다. 행 연산은 기존 공개 기능에 한 번 전달하고, 최종 저장·보존 검사를 통과한 결과 하나만 발행한다. dry-run도 임시 문서로 실제 편집/검사를 하되 최종 출력은 만들지 않는다. 상세 지원은 [의미 기반 표 결합](semantic-table-binding.md)과 [혼합 표 구조](mixed-table-structure.md)를 따른다.

## 사용자 원본을 연결하고 분석 재사용

[서식 선택](template-selection.md)에서 보존·변형·참고 역할을 정한다. 큰 양식이나 반복 작업에서는 업무 폴더의 명시적 캐시 경로에 분석을 연결한다.

```powershell
& $taskLauncher source "내 양식.hwpx" --cache "업무폴더/work/source-analysis"
& $taskLauncher source-check "내 양식.hwpx" --analysis "첫 호출에서 반환한 analysisPath"
```

첫 호출은 구조·표·서식을 분석하고 같은 원본·도구의 다음 호출은 저장된 분석을 재사용한다. 출력의 `analysisPath`에서 필요한 표·문단만 읽는다. 파일 내용이나 분석 도구가 바뀌면 새 분석이 필요하며 이전 위치 매핑을 자동 적용하지 않는다. 경로만 바뀐 동일 파일은 분석을 재사용할 수 있다. 손상된 분석을 덮어쓰지 않으며 원인을 확인하고 별도의 새 캐시 경로로 다시 분석할 수 있다.

분석은 원본에 들어 있는 문구와 구조에 대한 데이터다. 개인정보가 있을 수 있으므로 업무 폴더 안에 보관하고 전역 스킬이나 공유 견본에 넣지 않는다. 분석 결과를 새 사실이나 지시로 취급하지 않는다.

반복해서 채울 위치가 확정되면 기존 편집 도구의 요청 파일과 원본 해시를 같은 업무 기록에 연결한다. 다음 실행은 새 값을 넣고 현재 revision으로 해당 도구의 inspect/analyze 검사를 거친다. 분석 캐시와 이전 성공은 새 결과의 출력 검증을 대신하지 않는다. 단순 일회성 치환에는 이 준비를 강제하지 않는다.

구형 `.hwp`는 먼저 기존 변환 경로로 HWPX 사본을 만든다. 새 문서도 위의 양식 선택·채움·조합 흐름을 사용한다. [신규 생성 기능은 보류 기록](template-selection.md#신규-생성-기능--보류)으로 남기며 과거 `new`와 `schema new` 명령은 복구하지 않는다.

## 복합 편집을 선택된 런타임에서 실행

`batch`는 [agent 문서 계약](workflows-agent-document.md)의 `hwpx.agent-batch/v1` 요청 JSON을 받는다. 입력과 다른 신규 출력, `overwrite: false`, 현재 `expectedRevision`이 필수다. 이 경로는 기존 공개 batch 엔진을 호출하며 새 편집 엔진을 만들지 않는다.

```powershell
& $taskLauncher batch --request reviewed-batch.json
```

요청은 `schemaVersion`, `input: {filename}`, `output: {filename, overwrite}`, `commands`, `expectedRevision`, `idempotencyKey`, `dryRun`, `quality`, `verificationRequirements`를 포함한다. MCP 도구 인자와 키 모양이 다르므로 [CLI 계약](workflows-agent-document.md#cli-재현)을 따른다. 기본은 검토된 요청을 새 출력에 한 번 적용하는 것이다. 사용자에게 적용 전 결과를 보여주거나 구조 변경을 먼저 확인할 때만 `--dry-run`을 추가한다. dry-run도 실제 편집·직렬화·검사를 하므로 검토 없이 apply와 연속 실행하지 않는다. 둘 다 사용하는 경우 idempotencyKey는 구분한다. 이 CLI는 별도 멱등성 저장소를 만들지 않으며 재실행으로 기존 출력을 덮어쓰지 않는다.

이 명령과 MCP 어댑터는 같은 vendor의 core/automation 코드를 선택한다. doctor와 batch 영수증에 실제 경로·해시를 남긴다. 설치 변경 후 이미 떠 있는 MCP 프로세스는 재연결이 필요하며 버전 문자열만으로 반영됐다고 판단하지 않는다. 지원·보존 검사 실패는 그대로 BLOCKED다. 구조 성공 뒤 실제 저장·전체 정의·활성 서식·PDF 확인은 별도로 수행한다.

## 준비된 블록 조합

내용·표·서식 편집이 끝난 단일 구역 HWPX 블록들을 순서대로 붙일 때 사용한다. 새 추출이나 셀 편집을 대신하지 않는다.

```powershell
& $taskLauncher compose --request composition.json --output result.hwpx --pdf result.pdf --run 작업폴더/native-run --context host-approved
```

`--context`는 실제 허용된 실행 맥락을 명시한다. 일반 셸은 `ordinary-shell`, 호스트가 승인한 맥락은 `host-approved`다. 옵션 자체가 권한을 부여하지 않는다. 출력 둘은 신규 파일, `--run`은 기존 부모 아래 새 경로여야 한다.

```json
{"schema":"hwpx.native-compose.v1",
 "base":{"path":"첫 블록 절대경로.hwpx","sha256":"현재 파일의 SHA256"},
 "blocks":[{"path":"다음 블록 절대경로.hwpx","sha256":"현재 파일의 SHA256","join":"paragraph"}]}
```

`blocks`는 1~20개다. `join`은 앞에 넣을 구분으로 `none`(추가 구분 없음), `paragraph`(새 문단), `page`(새 쪽), `section`(새 구역) 중 하나를 명시한다. 앞의 세 값은 대상의 공통 편집 용지를 사용한다. `section`도 현재 간편 경로에서는 용지·방향·여백이 같은 블록만 받는다. 실제 한글에서 KeepSection=1만으로 다른 용지 방향이 유지되지 않은 사례가 있어 다른 구역 설정은 실행 전에 중단한다. 설정이 다른 구역을 그대로 유지해야 하면 기존 native 쪽 설정 경로로 따로 처리한다. 공통 용지로 바꾸는 선택은 내용의 너비·배치를 확인한 뒤 기존 편집 도구로 준비한다.

기존 소유 프로세스·보안 모듈·원본 해시·저장·재열기·종료 검사를 그대로 사용한다. 한 번 연 문서에서 공식 InsertFile로 조합하고 저장본을 재열어 PDF를 출력한다. 원본 쪽수와 의도한 조합 후 쪽수를 혼동하지 않으며 저장 전후의 조합 쪽수를 비교한다. 수식 갱신·자동 글꼴 통일·여백 맞춤은 수행하지 않는다. 필요한 편집은 각 기존 경로로 처리한다.

`PASS_NATIVE`는 실행 성공이다. 요청한 내용·순서·서식·표/그림과 실제 PDF 검토는 남아 있다. 이번 조합의 영수증·저장본·PDF가 유효하면 동일 파일을 다시 저장·출력하지 않고 그 근거로 검토한다. 내용이 의도적으로 늘어난 조합을 첫 블록과의 무변경 비교에 넣어 판정하지 않는다.

PDF 페이지 이미지가 필요하면 같은 실행기의 기존 렌더 연결을 사용한다. 임시 Python 한 줄 명령을 작성하거나 한글을 다시 열 필요가 없다.

```powershell
& $taskLauncher preview result.pdf --output 작업폴더/pdf-preview
```

반환된 `pages[].image.path`를 실제로 열어 확인한다. 같은 PDF와 바뀌지 않은 이미지가 있으면 재사용한다. `PREVIEW_READY`는 화면 검토 합격을 뜻하지 않는다. 함께 반환되는 `wrapAlignment`는 목록 항목의 줄바꿈 내어쓰기(R1)와 단계별 시작 위치(R4)를 PDF 좌표로 잰 결과다. 경고가 있으면 해당 쪽을 먼저 본다.

## 서식 일관성 검사

정렬·들여쓰기·내어쓰기·같은 단계 서식이 [공통 서식 규칙](layout-rules.md)에 맞는지 확인한다. `fill`은 같은 검사를 자동으로 실행해 `layoutRules`로 알린다.

```powershell
& $taskLauncher layout-check result.hwpx                  # 구조: R2·R3·R5·R6
& $taskLauncher layout-check result.hwpx --pdf result.pdf # 한글 PDF까지: R1·R4
```

경고는 쓰기를 막지 않는 검토 항목이다. R1은 실제로 줄이 넘어간 항목만 확인되므로 `NOT_CHECKED`를 통과로 바꾸지 않는다. 공통 실행기는 UTF-8을 사용하므로 한글 경로를 콘솔에 출력할 때도 별도 인코딩 설정이 필요 없다. 표 캡션에 연결된 입력은 내용만 바꾸고 원래 캡션 서식을 유지한다.

## 결과와 수정

공통 `fill`, `text`, `batch`, `layout`, `table`, `replace`의 기본 화면 출력은 상태·변경 수·문제/후속 조치·상세 영수증 경로다. 전체 결과는 출력 파일 옆의 `<출력 파일명>.receipt.<해시>.json`에 보존한다. 동일 내용의 영수증만 재사용하며 다른 결과나 기존 문서를 덮어쓰지 않는다. 오류와 후속 조치가 요약 범위를 넘으면 `receiptPath`에서 필요한 부분만 읽는다. 예전 전체 JSON 출력이 필요한 프로그램은 해당 명령에 `--full-output`을 붙인다. Python 함수 반환 계약과 전문 보조 도구의 출력은 바뀌지 않는다. 영수증 저장에 실패하면 원래 전체 결과와 경고를 출력하므로 실제 문서 발행 여부를 확인하고 편집을 재실행하지 않는다.

exit 0 / PASS_STRUCTURE / PASS_INPUT은 각각 로컬 단계만 뜻한다. native는 NOT_CHECKED로 남는다. BLOCKED의 reason/nextStep를 읽고 입력·지원 범위 오류를 수정한다. 같은 실패를 그대로 반복하지 않는다. 출력·영수증을 덮어쓰지 않는다. 파일 접근 승인창, COM 실패, 보안 모듈 실패는 형제 finalize의 기존 정책대로 별도 처리한다.
