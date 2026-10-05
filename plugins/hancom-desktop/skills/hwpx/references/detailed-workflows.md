# 이전 상세 경로와 기능별 계약

공통 진입과 우선순위는 현재 SKILL.md를 따른다. 이 참조는 전문 도구의 지원 범위와 기존 검증 계약을 보존한다. 필요한 절만 읽는다.

Plugin setup: use the PC configuration from `${CODEX_HOME}/skills/hwpx/environment.json` (default `${USERPROFILE}/.codex/skills/hwpx/environment.json`) if this plugin cache has no environment.json. Run hancom-setup first when absent.


# HWPX 작업

## 이 PC의 설치 환경

제목 간격·소계 행 묶기 뒤 저장에서 표의 직접 높이가 달라진 경우만 동료 스킬의
[실제 측정 표 높이](../../hwpx-windows-finalize/references/native-measured-table-height.md)를 선택한다.

`environment.json`의 `pythonPath`, `coreStatus`, `pdfCheckStatus`를 먼저 확인한다.
이 후보에 `vendor/hwpx`가 있으면 작성·편집 전에 [후보 라이브러리 선택](candidate-runtime.md)을 따른다. 설치된 라이브러리로 조용히 돌아가지 않는다. PDF 동등성만으로 HWPX 내부 서식 보존을 통과시키지 않는다.
설치 경로나 Python을 이전 PC 경로로 추정하지 않는다. 설정이 없으면 통합 묶음의
`Install-HangulSkills.ps1`로 설치한다. 실제 한글 작업 준비는 동료 스킬의
[PC별 환경](../../hwpx-windows-finalize/references/desktop-environment.md)을 따른다.

요청에 필요한 최소 경로로 편집하고 변경 위험에 맞춰 검증한다.
이 파일이 경로·재시도 정책의 기준이다. 상세 참조의 도구 계약은 유지하되,
일반 경로 권고 때문에 단순 수정을 복합 workflow로 확대하지 않는다.

## 통합된 새 문서·개인용 양식 경로

- 짧은 요청의 새 보고서·계획서는 [보고서 구성·지면 설계](short-prompt-reports.md)를 먼저 적용한다. 사실·제안을 구분하고 실제 한글 전체 쪽 검수를 수행한다.


- 빈 문서에서 생성할 때 [새 문서 설계](new-document-design.md)와 [번호·집계 v2 규칙](new-document-v2.md)을 읽고 `scripts/create_new_document.py`의 prepare → validate → create → audit를 사용한다.
- 번호는 native NUMBER/BULLET 정의로 만든다. 번호 문자·공백 접두어를 본문에 붙이지 않는다. 계층 시작 위치와 줄바꿈 뒤 본문 시작 위치는 구분한다. `autoIndent=1` 구조 검사만으로 실제 이어지는 줄 정렬이 검증됐다고 말하지 않는다. [내어쓰기 검수](hanging-indent-verification.md)를 따른다.

## 자주 쓰는 편집 우선

기입 양식·다단·그림·차트의 지원 판단에는 [복합 편집 확인 범위](complex-edit-lessons.md)를 필요한 경우 읽는다.


일상 보고서 수정은 [자주 쓰는 편집](common-editing.md)의 확인 범위부터 적용한다.
본문·표 셀·빈 양식의 기존 서식을 지키는 편집을 우선하며, 보고서 내용/목차를 고정하지 않는다.
특수 기능은 요청에 필요할 때 선택한다. 지원 목록과 실제 검증 범위를 구분한다.

## 작업 경로

| 작업 | 기본 경로 | 참조 |
|---|---|---|
| 읽기·찾기 | 필요한 텍스트/표만 추출·검색 | [api](api.md) |
| 날짜·문구·서식 수정 | 대상 확인 → 지원되는 단건/일괄 편집 | [editing](workflows-editing.md) |
| 분할 run·지정 셀·중복 문구의 정확한 위치 수정 | `selected_text` 진단 → hash-bound 대상 계획 → dry-run/보존 검사 | [선택 텍스트 편집](selected-text-edit.md) |
| 기존 양식의 빈 칸·여러 문단·반복 항목 채우기 | `fill_form` 진단 → 정확한 라벨/인접 소유 셀/개수 검토 → 계획 → dry-run | [라벨 양식 채우기](form-filling.md) |
| 내용의 관계에 맞춘 새 문서/기존 양식 공통 설계 | 에이전트가 관계·표현 선택 → 원자료와 변경/보존 계획 → 지원 연산 → 실제 출력 | [공통 구조 설계](content-structure.md) |
| 기존 양식의 내용 길이·빈 반복 항목 수에 따른 제한 변형 | 허용 범위/보호 표 지정 → 원자적 합성 편집 → 전체 한글 검토 | [기존 양식 변형](form-adaptation.md) |
| 단어·어절 보존 줄바꿈·필요한 문단 자간·긴 표 내용 열 너비 | 선택 문단/열의 hash-bound 편집 → 실제 빈 공간·단어·전체 쪽 검토 | [어절과 긴 표](word-flow.md) |
| 기존 양식의 서식 다면 점검·제한 자간/장평 후보 | 읽기 audit → 명시한 문단 계획 → bounded dry-run → 보존 검사 → native 검토 | [제한 서식 검토](bounded-format-review.md) |
| 줄바꿈·쪽 밀림·반복 상장 | 아래 레이아웃 루프 | [editing](workflows-editing.md) |
| 새 보고서 마지막 쪽에 몇 줄만 넘쳐 여백으로 맞추기 | 요청 시 선택 실행 → 최소 감소 후보의 실제 한글 출력 → 보존/시각 검토 | [선택적 여백 맞춤](auto-margin-fit.md) |
| 새 보고서 쪽 흐름·표 앞뒤 간격·큰 항목 앞 간격·사방 여백 | 선택 설정 → 생성/저장 값 대조 → native 전 페이지 확인 | [쪽 흐름](page-flow.md) |
| 2~3단 병합 머리글 정렬·안 여백·행 높이·전체 반복 | 명시한 최상단 영역 → hash-bound 제한 편집/보존 → native 전체 검토 | [다단 병합 머리글](merged-table-headers.md) |
| 기존 미병합 긴 표의 제목행 반복·CELL/TABLE 나눔·표 바깥 간격·바로 앞 제목의 선택 쪽 나눔 | hash-bound 제한 속성/스타일 편집 → 독립 보존 → 실제 전체 출력 | [기존 표 쪽 흐름](existing-table-flow.md) |
| 표 넘침·여러 쪽 지원 | 지원 경계 확인 → 정적 검사 → native 전체 페이지 검토 | [layout-validation](../../hwpx-windows-finalize/references/layout-validation.md) |
| 합성 개체 배치 계약 점검 | 고정 manifest 기반 읽기 검사 | [object placement](../../hwpx-windows-finalize/references/object-placement-validation.md) |
| 낯선 구조·혼합 블록 편집 | bounded 구조 → query → 일괄 commands | [agent-document](workflows-agent-document.md) |
| 새 보고서 쪽 번호·머리말·꼬리말 | 선택적 새 문서 작성 → native 번호/표지 숨김 → 전체 쪽 검토 | [쪽 요소](report-page-elements.md) |
| 소계·합계행 강조·셀 문단 정렬·값 보존 숫자 표시 | 선택 셀의 hash-bound 서식 → 별도 선/채우기 → 실제 숫자/쪽 경계 검토 | [소계·합계](summary-rows.md) |
| 기존 셀 가로 병합·해제·문단 좌/중앙/우 정렬 | hash-bound 범위 → public 편집/독립 보존 → native 전체 검토 | [셀 병합·정렬](cell-merge-alignment.md) |
| 기존 셀 세로 정렬·안쪽 여백·일반 줄바꿈 | hash-bound 셀 검사 → 배치 속성만 변경/독립 보존 → native 전체 검토 | [셀 안 배치](cell-spacing-wrap.md) |
| 기존 일반 표 행 추가/삭제·셀 너비/높이 | 제한 구조 진단 → hash-bound 요청 → dry-run/독립 보존 비교 → native 저장/출력 | [표 크기 편집](table-layout-edit.md) |
| 일반 복합 생성·편집 | 지원되는 start_workflow / continue_workflow | [autonomous](workflows-autonomous.md) |
| 전문 양식·시험·메일머지·이식 | 전문 도구 유지 | [기능별 참조](task-routing.md) |

경로 우선순위는 이 절이 기준이며 상세 참조는 인자 계약만 보충한다.

1. 읽기는 MCP의 summary map을 우선한다. health는 세션당 한 번 확인한다.
   편집 전 `scripts/diagnose_edit.py source.hwpx --operation ... --find "대상"`으로
   실제 중첩 깊이·대상 유일성·지원 범위를 진단한다. 전체 XML 대신 작은 결과를 읽는다.
2. 한 텍스트 노드에 완전히 포함된 유일한 본문 단건 치환은 MCP 유무와 관계없이 `scripts/safe_replace.py`를 우선한다.
   이 CLI는 위 사전진단을 내부 호출하고 6.3.0 public API·보존 검사 후 새 파일만 내보낸다.
3. 여러 run에 나뉜 문구, 일반/병합 셀의 지정 문단 또는 중복 문구의 지정 위치는
   처음부터 `diagnose_edit.py --operation selected_text`와 `safe_edit.py`의
   inspect → plan → apply --dry-run → apply 경로를 사용한다.
   기존 run·서식 참조를 유지하는 로컬 CLI 구현이며, 대표 3쪽 사례에서 한글 저장·재열기·PDF 전체 검토를 확인했다. 임의 구조의 검증을 뜻하지 않는다.
   텍스트 run에 plain t 하나인 본문/중첩 표 없는 대상 셀만 지원하고,
   새 문구 분배 정책·선택 위치·모든 요청 변경과 비대상 보존을 검토한다.
   기존 replace_text의 BLOCK을 다른 도구로 자동 우회하는 폴백으로 호출하지 않는다.
   자세한 지원/거부 범위와 인자는 위 참조를 따른다.
4. 기존 양식 채우기는 `diagnose_edit.py --operation fill_form --request request.json`과
   `form_fill.py`의 inspect → plan → apply --dry-run → apply 경로를 사용한다.
   현재 0.3.1 로컬 CLI는 정확한 라벨의 right/below 인접 소유 셀과 이미 있는 plain-run 문단만 채운다.
   병합 라벨 경계가 여러 셀에 걸치면 기본적으로 거부한다. 검토한 라벨 내부의 0-based
   target_row_offset(right)/target_column_offset(below)를 명시한 경우만 그 경계 위치를 선택한다.
   라벨 개수·반복 값·선택 문단 수를 정확히 맞추며 하나라도 누락/중복/불명확하면 전체 출력이 거부된다.
   비어 있지 않은 대상은 명시적 allow_replace가 필요하다. 빈 칸은 기존 첫 run에 채운다. 한글이 저장한 자식 없는 서식 run도 제한적으로 지원한다.
   표/행/문단을 자동 생성하거나 native 누름틀을 평문으로 바꾸지 않는다. 모든 요청과 비대상 보존을
   검토하고 native 검증 전에는 실사용 완료로 보고하지 않는다.
   내용 길이/항목 수에 맞춘 기존 양식 변형이 요청되면 [기존 양식 변형](form-adaptation.md)의 별도 form_adapt.py를 사용한다. 기존 필드 입력에 필요한 크기/흐름을 선택 합성하며, 빈 미병합 반복 행만 복제·축소한다. 보호 표/필수 라벨을 보존하고 기입된 반복 행을 삭제하지 않는다. 기존 form_fill의 범위를 일반 행 생성으로 확대하지 않는다.
5. 다른 단건/배치 연산은 해당 구조의 보존 계약이 확인된 MCP를 후보 사본에서 사용한다.
   dry-run/영수증의 실제 지원 인자를 확인한다. 로컬 CLI 가드가 MCP에 주입됐다고 가정하지 않는다.
6. plain 단일 문단 셀의 좌/중앙/우 정렬은 [셀 병합·정렬](cell-merge-alignment.md)의
   별도 제한 CLI를 사용한다. 중첩 표의 정확한 첫 셀 문단의 제한 정렬 변경은 finalize의 `Invoke-HancomCell.ps1` 경로를 사용한다.
   세로 정렬·안쪽 여백·일반 줄바꿈은 [셀 안 배치](cell-spacing-wrap.md)의 별도 `safe_cell_spacing.py` inspect → apply --dry-run → apply 경로를 사용한다.
   이 경로만 plain 여러 문단/run과 native lineBreak 보존을 추가 확인했으며, 문단 정렬/병합 도구의 범위는 확대하지 않는다.
   혼합 테두리·대각선·배경색은 [셀 선·채우기](cell-borders-diagonals.md)의 별도 `safe_cell_decoration.py`를 사용한다. 공유 경계 이웃과 병합 변 전체 범위를 검토하고, 같은 색을 넣을 때 기존 테두리를 보존한다. 대각선 글자 배치는 자동 변경하지 않는다.
   기존 미병합 긴 표의 쪽 흐름·표 앞뒤 간격·바로 앞 제목 연결은 [기존 표 쪽 흐름](existing-table-flow.md)의 `safe_table_flow.py`를 사용한다. keepWithNext나 앵커 설정만으로 떠 있는 표의 제목 유지가 보장되지 않으므로 실제 순서를 확인한다.
   2~3단 가로·세로 병합 머리글의 기존 구조를 유지하는 서식/전체 반복은 [다단 병합 머리글](merged-table-headers.md)의 `safe_table_header.py`를 사용한다. 기존 세로 병합 생성/해제나 본문까지 걸친 병합은 포함하지 않는다.
   소계·합계행의 선택 굵기/셀 정렬과 값 보존 숫자 표시에는 [소계·합계](summary-rows.md)의 `safe_summary_style.py`를 사용한다. 기존 병합/여러 문단을 보존하며 반올림/단위 환산/수식은 제외한다. keepWithNext로 표의 다음 행 유지가 보장되지 않으므로 실제 쪽 경계를 본다.
   각 경로의 범위를 넘으면 보류한다. 도구를 바꿔 같은 거부 연산을 재시도하지 않는다.
7. 작업본의 `audit_form_format.audit_format`은 정렬·행간·여백·들여쓰기·셀 크기/안쪽 여백·병합·번호·
   글꼴/글자 크기/자간/장평 설정을 읽는다. `safe_format.py`는 검토한 문단의 자간/장평만 제한 변경한다.
   단어·어절 단위 줄바꿈과 큰 빈 공간이 생긴 문단의 소폭 자간 후보, 여러 문단을 보존하는 미병합 표 열 재배분은 [어절과 긴 표](word-flow.md)의 별도 검증 경로를 따른다. 자간 효과가 없으면 일괄 축소를 계속하지 않는다.
   자동 맞춤/전역 서식 통일/글자 크기 축소는 구현하지 않았다. 이 경로의 보존 통과도 실제 가독성이나
   수정 필요성의 증거가 아니다. 자세한 지원 한계와 6.3.0 전용 URI 보존 어댑터는 위 참조를 따른다.

공통 금지: 중첩 셀 텍스트 전체 쓰기(`set_table_cell_text`, `fill_cells`, `cell.set_text` 포함)는
하위 내용 손실이 재현돼 현재 지원하지 않는다. 경로가 MCP든 CLI든 이 조건을 먼저 적용한다.
사전진단이 BLOCK이면 쓰기하지 않는다. 미확인 구조는 확인 후 결정하며, raw XML 직접 수정이나
셀 전체 쓰기로 조용히 폴백하지 않는다. 신규 지원은 별도 구현·보존 회귀로 확인해야 한다.

## 편집 루프

1. 원본을 보존하고 별도 후보에서 작업한다. 변경 대상과 보존할 요소를 확인한다.
2. 필요한 범위만 읽어 대상을 확정하고 가능한 한 batch로 편집한다.
   지원되는 dry-run의 diff를 확인한 뒤 commit하고 선언된 영수증을 확인한다.
3. 변경 내용·건수·이름·표·그림 등 관련 보존 조건을 대조한다.
4. 레이아웃 변경이면 실제 한글 렌더 결과를 확인한다. 완료와 미검증을 구분해 전달한다.

### 줄바꿈·쪽 나눔·반복 문서

- 실제 출력의 지정어 분리·빈 쪽·표식 누락/중복은 `hwpx-windows-finalize`의
  [레이아웃 검사](../../hwpx-windows-finalize/references/layout-validation.md)를 읽고 해당 검사기를 쓴다.
  알려진 실패는 재현 사례를 고정하고 수정 후 회귀검사한다. 미검증/미지원 결과를 정상으로 넘기거나
  사용자가 나중에 문제를 발견할 때까지 완료로 처리하지 않는다. 검사 통과와 자동 수정 지원은 별개다.
- 편집 전 코드로 대상 문구 길이·문단/셀 폭·글자 크기·자간·장평·줄 나눔 설정을 읽어
  줄바꿈 위험 후보를 선별하고, 편집 후 의도한 변경과 비대상 내용·서식 보존을 검사한다.
  사전 분석은 위험 추정이지 실제 줄바꿈 판정이 아니다. 현재 도구의 지원 범위를 확인하며,
  미구현·미검증 검사기가 자동 검출을 완료한 것처럼 보고하지 않는다.
- 본문 텍스트나 XML 설정이 같다는 이유로 실제 줄바꿈도 같다고 판정하지 않는다.
  정확한 수정본의 실제 한글 조판으로 확정하며, 확인하지 못했다면 ‘미검증’으로 보고한다.
- 일괄 적용 전에 가장 긴 문구·이름 등 대표 사례로 조판을 시험한다.
  원본의 흐름·개체 위치가 중요하면 원본 사본의 해당 부분에서 시험한다.
- 텍스트 newline을 네이티브 줄바꿈과 같다고 가정하지 않는다.
  의도한 구조와 실제 렌더를 확인한다.
- 넘침·쪽 나눔·빈 문단·개체 위치를 구분해 원인을 고친다.
  글자 크기를 무조건 줄이지 말고 기존 서식을 최대한 보존한다.
- 대표 사례 통과 후 전체 적용한다. 전체 쪽 수·누락·중복을 검사하고 위험에 맞춰 시각 검수한다.
  한 장씩 인쇄하는 반복 문서는 전체 페이지의 넘침·빈 쪽·직인 유무를 확인한다.
- 최종 렌더 증거는 전달할 HWPX에서 출력한 것이어야 한다.
  PDF만 따로 수정했다면 그 사실을 밝히고 수정 HWPX의 검증 증거로 쓰지 않는다.
- PDF 생성은 hwpx-windows-finalize의 「PDF 출력 경로 선택」을 따른다. 사용자의 별도 지정이
  없으면 실제 한글 COM 출력 우선이며, 출력 자체가 막힌 경우에만 computer-use로 전환한다.

## 지연·실패 처리

- 같은 원인의 실패는 최초 시도와 원인에 근거한 재시도 1회까지가 기본이다.
  입력·설정·상태가 바뀌지 않았으면 반복하지 않는다.
- 정상 진행 중인 비동기 작업은 실패로 세지 않는다. 상태/취소 계약을 사용한다.
  응답 없는 호출을 겹쳐 보내거나 개별 읽기 요청을 대량으로 쌓지 않는다.
- 쓰기 응답이 불확실하면 파일·revision·receipt를 확인한다.
  완료 여부를 모른 채 같은 쓰기를 새 요청으로 반복하지 않는다.
- 자동화 연결 실패는 문서 손상의 증거가 아니다. 손상이 확인되지 않으면 재작성하지 않는다.
- 새 한글 창이 열리면 창 목록에서 대상 파일을 다시 선택한다.
  사용자 입력 충돌이 반복되면 화면 조작을 멈추고 필요한 짧은 협조만 요청한다.
- 대체 경로도 막히면 편집 완료/검증 미완료를 구분하고 필요한 다음 확인을 구체적으로 안내한다.

## 유지할 안전 조건

- 원본 덮어쓰기 금지. 중간본은 검수/임시 폴더에 두고 전달 파일을 명확히 한다.
- 학생·직원·개인 문서를 외부 서비스에 보내지 않는다.
- 패키지 통과와 실제 한글 레이아웃 통과를 혼동하지 않는다.
- 지원되지 않는 연산·불완전한 fidelity를 성공으로 포장하지 않는다.
- 도구의 승인, revision/idempotency, openSafety 및 시각 증거 계약을 유지한다.
  [증거 계약](evidence-contract.md)은 해당 도구가 요구할 때 읽는다.
- Windows 실제 한글 검증에는 사용 가능한 hwpx-windows-finalize 스킬을 사용한다.
  파일 검증·실제 열림·인쇄 레이아웃·재저장 검증을 구분한다.

전문 기능은 [기능별 참조](task-routing.md)에서 필요한 항목만 찾아 읽는다.


내용에 맞는 구조를 알아서 선택하라는 요청에는 [공통 구조 설계](content-structure.md)를 읽는다. 에이전트가 내용 관계와 기존 양식 제약을 읽어 문단/항목/표와 필요한 변형을 고른다. 공통 실행기는 판단을 검사·컴파일하며 자연어 모델이 아니다. 고정 목차/표/병합을 강제하지 않고 미지원 구조 변경을 조용히 실행하지 않는다.


새 보고서의 native 그림 캡션·요약 상자·각주/미주·책갈피·웹 링크나 기존 그림의 단일 비공유 PNG/JPEG 데이터 교체에는 [공식 보고서 기능](official-report-features.md)을 읽고 검증된 별도 CLI를 선택한다. 동일 형식·픽셀 크기 교체만 지원하며 기존 임의 개체/목록 구조 편집으로 확대하지 않는다.


기존 보고서의 plain 본문 문단/native 번호·글머리표를 제한적으로 추가·삭제할 때는 [기존 본문 구조 편집](body-structure-edit.md)을 읽고 safe_body_structure.py를 선택한다. 원본 해시/전체 문단 binding과 보호 범위를 지정하고 유지 문단·전체 비대상 package를 대조한다. 셀/control/새 번호 계층 편집이나 다른 helper BLOCK의 우회로 확대하지 않는다.


기존 보고서의 plain 본문 문단/native 번호·글머리표를 제한적으로 추가·삭제할 때는 [기존 본문 구조 편집](body-structure-edit.md)을 읽고 safe_body_structure.py를 선택한다. 원본 해시/전체 문단 binding과 보호 범위를 지정하고 유지 문단·전체 비대상 package를 대조한다. 셀/control/새 번호 계층 편집이나 다른 helper BLOCK의 우회로 확대하지 않는다.


기존 plain 본문에서 여러 글자 서식이 섞인 문단의 수정·추가와 제목 쪽 흐름은 [혼합 서식 본문 편집](mixed-run-body.md)을 읽고 safe_body_structure.py v2를 사용한다. run별 문구를 명시하고 기존 스타일·표/개체·번호 소속을 보존한다. 필요한 제목에만 다음 문단과 연결/새 쪽 시작을 적용하고 실제 한글 쪽 배치를 확인한다.


사용자가 차트를 비슷한 모양으로 새로 만들어도 된다고 허용하면 [파일 방식 차트 재작성](chart-rebuild.md)을 참고한다. 현재 두 계열 묶은 막대 차트의 시험용 후보이며, 실제 한글 검증 전에는 실사용 지원 완료로 안내하지 않는다.


기존 각주·미주의 단일 문단 plain run 문구를 수정할 때는 [기존 주석 문구 편집](existing-note-text.md)과 note_text_cli.py를 사용한다. 주석 전체 setter로 여러 run 서식을 합치지 않고 실제 binding/hash를 고정한다. 저장본 같은 기능 재편집 및 native/전체 정의/쪽 검토는 별도 필수다.


기존 root 본문의 단순 미참조 책갈피 이름 변경은 [기존 책갈피 이름 수정](existing-bookmark-rename.md)과 bookmark_rename_cli.py를 사용한다. field 메타데이터/명령에 기존 이름이 연결되어 있으면 별도 참조 갱신 없이 바꾸지 않는다. 첫 저장 run 변환은 PDF가 같아도 기록하며 저장본 동일 기능 재편집과 비대상/전체 정의 비교를 수행한다.


기존 HTTPS 웹 링크 주소만 수정할 때는 [기존 하이퍼링크 주소](existing-hyperlink-target.md)와 hyperlink_target_cli.py를 사용한다. name·Command·Path의 일치와 정확한 기존 필드 binding을 고정하며 PDF URI를 화면 픽셀과 별도로 검사한다. 내부 참조/파일/메일/중첩 링크 편집으로 확대하지 않는다.


기존 physical native 머리말/꼬리말의 plain run 문구는 [기존 native story 문구](existing-native-story-text.md)와 native_story_text_cli.py를 사용한다. 전체 story를 새로 만들지 않고 run·ID·폭·쪽 유형·표지 숨김을 보존한다. 본문에 같은 문구가 있어도 머리말로 취급하지 않으며 실제 반복 표시와 동일 기능 재편집을 검증한다.

기존 쪽 설정은 [native 쪽 설정](existing-native-page-settings.md), RIGHT 번호·꼬리말 충돌의 전용 서식 여백 수정은 [꼬리말 간격](existing-native-footer-clearance.md)을 사용한다. PDF 일치·내부 보존·배치 성공을 따로 판정한다.

제목과 떠 있는 작은 표가 다른 쪽으로 갈라진 경우에는 [기존 native 제목/표 연결](existing-native-caption-layout.md)을 확인한다. 이미 맞는 배치에 강제 쪽 나눔을 일괄 적용하지 않는다.

소계·합계 행의 쪽 연결은 [행 묶음 제한 검증](summary-row-group.md)을 확인한다. 분리 표의 내부 경계 여백은 명시 지정하고 원래 바깥 여백을 유지한다. compact 추가 쪽 회귀는 HWP049의 원본·이전 실패 저장본에서 수정됐으며 범용 적용 여부는 모든 실제 쪽과 저장본 재편집으로 확인한다.

기존 큰 항목·표 전후 간격은 [native 간격 검증](native-report-spacing.md)을 확인한다. 간격 값/내부 보존이 맞아도 마지막 한 줄 고립과 긴 표 저장 크기 변경은 별도 실패다.

기존 저장본의 작은 넘침은 [위아래 여백 후보 검증](existing-vertical-margin-fit.md)을 확인한다. native_vertical_fit_cli.py inspect/dry-run/run은 별도 제한 경로다. 생성 영수증 기반 auto_margin_fit을 저장본 재생성에 사용하지 않는다. 선택은 PENDING_VISUAL_REVIEW이며 NO_FIT/환경 차단/원시 수정일 차이를 완료로 숨기지 않는다.

새 문서 첫 저장의 내부 보존 후보는 [새 문서 헤더 준비](fresh-header-serialization.md)를 읽고 제한 환경과 추가되는 보관 스타일을 확인한다.


기존 긴 라벨 설명의 다음 줄 정렬은 [내어쓰기](existing-hanging-explanations.md)를 읽는다. 특정 기존 강제 쪽 나눔·고정 목차 편집은 [보고서 흐름](existing-report-reflow.md)을 읽는다.


길어진 기존 표의 잘림·제목행 반복·앞뒤 간격은 [확장 표 흐름](existing-expanded-table-flow.md)을 읽는다. 배치 변환과 병합 제목 flag 전용 경로를 구분한다.


다른 가로·세로 병합이 섞인 기존 표에서 일부 행 추가/삭제, 동일 라벨 세로 병합, 설명 보존 가로 병합, 두 셀 분할은 [부분 표 구조 편집](mixed-table-structure.md)을 읽는다.


새 행·분할 셀·다중 run의 새 문구를 매핑할 때 [문단 문구 매핑](paragraph-payload.md)을 읽는다. 의도한 전체 문구를 먼저 정하고 서식 조각의 합이 그 문구와 일치하도록 구성한다.


기존 표의 종료 항목 삭제·신규 항목 추가 등 내용에 따른 변경은 [의미별 표 대상 선택](semantic-table-binding.md)를 읽는다. 정확한 전체 셀 키와 새 소스 해시로 작업마다 대상을 다시 찾고 실제 저장본 재편집·긴 내용과 모든 지면을 검수한다.

공개 배포 구성과 확인 범위는 묶음 루트의 INTEGRATION.md를 확인한다. 개인 전용 양식과 과거 PC의 실행 기록은 이 배포본에 포함하지 않는다.
