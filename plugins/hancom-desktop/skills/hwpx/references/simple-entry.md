# 공통 진입 도구

`SKILL_DIR`는 읽은 SKILL.md가 있는 실제 폴더다. PowerShell의 호출은 다음 형태다.

```powershell
$taskLauncher = Join-Path $taskSkillDir 'scripts/Invoke-HangulTask.ps1'
& $taskLauncher doctor
```

`$taskSkillDir`에 확인한 실제 경로를 넣는다. doctor는 설정·Python·후보 core의 실제 경로/해시를 보고한다. 쓰기 권한, 한글 COM, 보안 모듈은 이 검사만으로 판정하지 않는다. 파일을 찾을 때 작업 폴더 최상위만 보고 스크립트가 없다고 판단하지 말고 `Test-Path -LiteralPath (Join-Path $taskSkillDir 'scripts/Invoke-HangulTask.ps1')`를 사용한다. 실제 권한 오류 없이 읽기 전용이라 단정하지 않는다.

## 단건 문구 치환

```powershell
& $taskLauncher replace report.hwpx result.hwpx --find '정확한 문구' --replace '새 문구'
```

유일한 본문 텍스트 노드 안의 단건만 지원한다. 원본과 다른 신규 출력이 필수다. 내부 safe_replace의 사전진단·public API·전체 보존 검사는 유지된다. BLOCK이면 쓰기하지 않는다. 여러 run/여러 수정/지정 셀/중복 위치는 [선택 텍스트](selected-text-edit.md) 또는 [본문 구조](body-structure-edit.md)의 기존 경로로 처음부터 계획한다. 거부된 연산을 다른 경로로 자동 우회하지 않는다.

## 업무 표 행 삭제·삽입

```powershell
& $taskLauncher schema table
& $taskLauncher table report.hwpx result.hwpx --request task.json --dry-run
& $taskLauncher table report.hwpx result.hwpx --request task.json
```

task.json은 `schema: hangul.task.v1`, `operation: table`, `headers`(정확한 전체 제목 셀 배열), `reason`(8자 이상 구체적 이유), `operations` 배열이다. 연산은 다음 두 형태만 지원한다.

```json
{"op":"delete","key":{"실행 업무":"삭제할 셀의 완전한 문구"}}
{"op":"insert_after","key":{"실행 업무":"기준 셀의 완전한 문구"},"cells":["단계","새 항목명: 설명 전체","담당","목표일"],"heightHwpunit":2400}
```

key는 해당 제목 열의 완전한 기존 셀 값이다. 순번을 추정하지 않는다. cells는 모든 열 순서의 문자열이다. 사용자 메모가 `항목명: 설명`을 제공하면 둘을 모두 넣는다. 삽입 기준의 모든 셀이 한 문단/한 run일 때만 3차원 지도 변환을 자동 처리한다. 복잡한 run을 임의로 평문화하지 않는다. 연산마다 현재 소스 해시와 표/행을 재결합한다. 내부 임시 단계 전체가 보존 검사를 통과한 뒤 최종 파일 하나만 발행한다. dry-run도 임시 문서로 실제 편집/검사를 하되 최종 출력은 만들지 않는다. 상세 지원은 [의미 기반 표 결합](semantic-table-binding.md)과 [혼합 표 구조](mixed-table-structure.md)를 따른다.

## 새 문서

```powershell
& $taskLauncher schema new
& $taskLauncher new result.hwpx --request task.json --dry-run
& $taskLauncher new result.hwpx --request task.json
```

schema new가 실제 지원 입력 예제를 반환한다. 예제를 복사할 때 가상 자리 표시자를 실제 사용자 원자료로 바꾼다. 필수 키는 schema/operation/purpose/audience/kind/title/facts/blocks다. facts는 `id: 정확한 원문 문장` 객체다. 문단의 `facts: [id,...]`는 원문을 그대로 묶어 claims와 evidence를 생성한다. 직접 `text`는 문단 설명·명시한 제안 등에 사용한다. 필수 사실의 재서술이나 새 수치로 바꾸지 않는다. 사실 전부가 결과에 들어가는지 기존 엔진이 검사한다. 중요 미정은 allow_draft와 unknowns의 기존 계약을 따른다.

- heading: type/text/level(1~3). heading에 list를 넣지 않는다.
- paragraph: type과 text 또는 facts 중 하나. 선택 emphasis/list/reason은 기존 엔진 계약 그대로다.
- table: type/headers/rows/reason. rows는 전체 셀 문자열 배열의 배열. 선택 widthWeights/aligns/caption. 입력은 실제 columns/row 객체로 컴파일한다.
- bullets: type/items, 선택 ordered/reason. page_break: type/reason.
- numbered_headings: 번호를 요청했을 때 true. 한글의 실제 3단계 번호 정의를 사용한다. 직접 text에 번호를 붙이지 않는다.
- format: 기존 엔진의 정확한 키만 사용한다. `body_pt`, `line_spacing`, `margins_mm`가 맞는 이름이다. `font_size_pt`, `line_spacing_percent`, `margin_mm`는 거부된다. 비우면 기본 서식이다.

목차·항목 수·표 배치는 작성 에이전트가 내용에 맞게 선택한다. 도구는 고정 목차를 만들지 않는다. 더 복잡한 서식·근거 연결·집계는 [새 문서 설계](new-document-design.md), [번호/집계](new-document-v2.md), [서식](new-document-formatting.md)의 기존 자유 설계 경로를 사용한다. 기존 생성기의 검사를 낮추거나 unsupported 키를 조용히 버리지 않는다.

## 결과와 수정

exit 0 / PASS_STRUCTURE / PASS_INPUT은 각각 로컬 단계만 뜻한다. native는 NOT_CHECKED로 남는다. BLOCKED의 reason/nextStep를 읽고 입력·지원 범위 오류를 수정한다. 같은 실패를 그대로 반복하지 않는다. 출력·영수증을 덮어쓰지 않는다. 파일 접근 승인창, COM 실패, 보안 모듈 실패는 형제 finalize의 기존 정책대로 별도 처리한다.
