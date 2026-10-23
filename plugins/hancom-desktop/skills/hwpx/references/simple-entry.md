# 공통 진입 도구

`SKILL_DIR`는 읽은 SKILL.md가 있는 실제 폴더다. PowerShell의 호출은 다음 형태다.

```powershell
$taskLauncher = Join-Path $taskSkillDir 'scripts/Invoke-HangulTask.ps1'
& $taskLauncher doctor
```

`$taskSkillDir`에 확인한 실제 경로를 넣는다. 로컬 설정이 없으면 현재 `CODEX_HOME/skills`의 environment.json에서 Python을 읽고 포함된 vendor core를 선택한다. 설정이 없으면 hancom-setup으로 준비한다. doctor는 이 경로·해시를 보고하며 쓰기 권한·COM·보안 모듈은 별도 확인이다. 파일 존재는 `Test-Path -LiteralPath (Join-Path $taskSkillDir 'scripts/Invoke-HangulTask.ps1')`로 확인하고 실제 권한 오류 없이 읽기 전용이라 단정하지 않는다.

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

## 새 업무 문서도 기존 서식에서 시작

[서식 선택](template-selection.md) → [원본 기반 작성](source-template-reuse.md)을 따른다. 빈 문서 작성 `new`와 `schema new`는 제거된 명령이다.

## 결과와 수정

exit 0 / PASS_STRUCTURE / PASS_INPUT은 각각 로컬 단계만 뜻한다. native는 NOT_CHECKED로 남는다. BLOCKED의 reason/nextStep를 읽고 입력·지원 범위 오류를 수정한다. 같은 실패를 그대로 반복하지 않는다. 출력·영수증을 덮어쓰지 않는다. 파일 접근 승인창, COM 실패, 보안 모듈 실패는 형제 finalize의 기존 정책대로 별도 처리한다.
