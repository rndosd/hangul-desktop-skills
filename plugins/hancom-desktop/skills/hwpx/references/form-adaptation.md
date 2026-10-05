# 내용에 맞춘 기존 양식의 제한 변형

기존 양식의 목적과 필수 항목을 유지하면서 필요한 입력 칸 높이와 빈 반복 영역을 조절할 때 읽는다.
단순 내용 입력이면 기존 form_fill만 사용한다. 보고서 내용·목차·결재 방식이나 표 디자인을 고정하지 않는다.

## 선택과 지원 범위

원본을 읽어 보존할 표와 실제 필수 라벨, 입력 대상, 반복 영역, 변형 허용 범위를 정한다.
사용자가 이미 변형을 허용한 업무 양식은 그 범위에서 진행한다. 고정 제출 양식의 구조 변경 권한은
문서가 편집 가능하다는 이유만으로 추정하지 않는다. 요청이 내용 입력뿐이면 구조를 확대 변경하지 않는다.

`form_adapt.py`는 기존 form_fill·safe_table_layout·safe_table_flow와 새 safe_repeat_rows를
임시 폴더에서 합성하고, 모든 보존 검사가 통과한 최종 후보만 새 파일로 게시한다.

- 기존 빈 칸 입력은 form_fill의 정확한 라벨/인접 소유 셀/기존 문단 계약을 그대로 따른다.
- 반복 영역은 본문 직속 미병합 표, 1개 머리행, 모든 본문 셀이 완전히 빈 상태여야 한다.
  각 셀은 기존 plain 문단 1개와 서식 run 1개이며 plain 빈 t 또는 한글 저장본의 자식 없는 run을 허용한다.
- 빈 반복 행은 명시한 기존 본문 행을 복제하거나 아래쪽의 미사용 빈 행을 줄이고 값을 입력한다.
  새 데이터 행은 1~40개, 열은 1~12개다. 한 값은 XML 유효 단일 문자열 3,000자 이하다.
  공백만 든 원본 행도 빈 행으로 취급하지 않는다. 이미 내용이 있는 반복 영역은 이 경로가 거부한다.
- 높이/너비는 요청한 표의 명시적 값만 바꾸며 기존 크기 도구의 전체 너비 제한을 유지한다.
  긴 입력은 필요한 행 높이를 늘리는 후보부터 본다. 글자 크기나 쪽 여백을 자동으로 줄이지 않는다.
- 항목이 많을 때 기존 표 흐름 도구로 머리행 반복·행 단위 나눔을 선택한다. 업무 내역을 새 쪽에서
  시작하는 것도 선택 사항이다. 제목 연결과 전체 쪽 배치는 실제 출력으로 확정한다.

병합/중첩/보호된 반복 영역, 여러 문단·rich run·필드/누름틀, 기입된 반복 행 삭제,
본문 문단 삽입/삭제, 기존 양식의 범용 자동 맞춤은 포함하지 않는다. 결재란 등 보호 표는 변경 대상에서 제외한다.
다른 경로의 기존 거부를 조용히 우회하는 폴백으로 이 도구를 사용하지 않는다.

## 요청과 재현

Python은 현재 PC environment.json의 pythonPath를 사용한다. 스킬 루트에서 새 출력 경로로 실행한다.

```powershell
python -X utf8 -B scripts/form_adapt.py assets/form-adaptation/source.hwpx new-short.hwpx --request assets/form-adaptation/short-request.json --dry-run
python -X utf8 -B scripts/form_adapt.py assets/form-adaptation/source.hwpx new-short.hwpx --request assets/form-adaptation/short-request.json
python -X utf8 -B -O scripts/test_form_adapt.py
```

합성 source.hwpx와 short/long/many 요청은 재현 자산이다. 실제 업무 문서의 기본 양식이나 높이 규칙으로 사용하지 않는다.
원본 해시가 묶여 있으므로 실제 문서의 구조와 대상 값을 읽고 새 요청을 만든다.

`hwpx.form-adaptation.v1` 필수 키:

| 키 | 의미 |
|---|---|
| source_sha256 | 읽고 검토한 원본 SHA256 |
| editable_reason | 허용한 변형 범위의 근거, 비어 있지 않은 단일 줄 |
| preserve_tables | 바꾸지 않을 표의 1-based 번호, 1개 이상 |
| required_labels | 실제 양식의 정확한 필수 셀 라벨, 기존 개수 보존 |
| fields | 기존 form_fill 요청의 fields 목록, 없으면 빈 목록 |
| repeat | 없으면 null, 있으면 아래 반복 영역 |

repeat는 `table`, 모든 열의 `expected_headers`, 기존 본문 `template_row`(머리행 포함 1-based),
`values`(행별 열 문자열 목록)를 정확히 지정한다. fields와 repeat는 서로 다른 명시적 표여야 한다.
선택 `geometry`는 `{table,widths_mm,heights_mm?}` 목록, `flow`는 기존 표 흐름 요청에서
table과 필요한 속성만 담은 목록이다. 각 목록은 최대 4개다. schema/hash는 각 단계에서 실제 후보에 다시 묶는다.
보호 표는 입력·반복·크기·쪽 흐름의 대상이 될 수 없다. fields/repeat 중 실제 편집이 하나 이상 필요하다.

반복 영역만 진단할 때:

```powershell
python -X utf8 -B scripts/safe_repeat_rows.py inspect source.hwpx --table 3 --output new-inspection.json
```

inspect는 읽기 결과이며 지원 승인이나 native 통과가 아니다. 단독 apply 요청은
`hwpx.blank-repeat-rows.v1`과 source_sha256·editable_reason 및 repeat의 4개 키를 사용한다.

## 보존과 완료 판단

행 복제/삭제는 public apply_table_ops, 빈 run 입력은 public run.text setter를 사용한다.
원본과 후보의 모든 비대상 XML/멤버, 머리행·기존 셀 서식/여백/크기, 새 복제 셀의 원본 서식,
문단 ID 충돌을 독립 비교한다. raw XML 직접 쓰기나 셀 전체 쓰기로 폴백하지 않는다.
최종 합성에서도 보호 표 전체, 필수 라벨 개수, 모든 요청 필드/반복 값과 표 목록을 다시 읽어 대조한다.
어느 단계든 실패하면 최종 파일을 게시하지 않는다. dry-run도 실제 후보 생성/재열기/보존 검사를 수행한다.

구조 영수증의 native는 pending이다. 정확한 후보에 finalize의 prepare → 한글 SaveAs/재열기/PDF →
collect → 전체 쪽/차이 검토 → check를 수행한다. COM 성공과 완료 gate는 별도 결과다.
기존 DLL/등록/보안 정책을 사용하며 이 편집 경로에서 설정을 바꾸지 않는다.

2026-10-03, python-hwpx 6.3.0 / 한글 2024 13.0.0.3903 실제 검증:

- 기준 빈 양식 1쪽, 짧은 내용 1쪽, 긴 내용 1쪽, 18항목 양식 3쪽. 4사례 전체 6쪽 strict gate complete.
- 짧은 내용: 빈 반복 3행 → 입력 2행, 목적/검토 높이 8/10mm.
- 긴 내용: 목적/검토 높이 16/16mm → 34/28mm, 글자 크기·폭·쪽 여백 유지.
- 18항목: 결재/기본 정보 뒤 내역을 새 쪽으로 시작, 내역 2쪽 전체에 머리행 반복,
  각 항목 시작/끝이 같은 쪽에 있고 제목은 첫 내역과 함께 표시.
- 결재 표 전체와 필수 라벨 개수, native 활성 서식/셀 테두리/크기/내용 보존 검사 통과.
- 새 가드 33개와 관련 기존 가드 83개를 Python -O에서 통과.

이는 빈 일반 반복 영역을 가진 대표 양식의 확인 범위다. 복잡한 양식의 자동 변형을 모두 해결한 결과는 아니다.


내용의 관계를 판단해 새 문서/기존 양식에 공통으로 적용할 때는 [공통 구조 설계](content-structure.md)를 읽는다. 호환 빈 영역의 머리글 변경·행 조절·명시한 높이·가로 병합을 별도 원자적 실행기로 연결한다. 기존 양식 변형의 제한을 임의 복잡한 양식 전체로 확대하지 않는다.
