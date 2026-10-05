# 다단 병합 머리글

내용과 목차를 고정하지 않는 선택 기능이다. 큰 범주의 열 묶음이 필요한 표에서만 2~3단 머리글을 사용한다.
`scripts/safe_table_header.py`는 기존 병합을 그대로 두고 머리글 서식과 전체 제목행 반복만 변경한다.
기존 셀을 재병합하거나 본문을 다시 작성하는 도구가 아니다.

## 경계와 대상

python-hwpx 6.3.0, 직접 본문 문단의 정상 떠 있는 표, TABLE 행 단위 나눔, 2~100행·1~12열.
머리글은 맨 위의 연속 1~3행을 `header_rows:[1,2]` 또는 `[1,2,3]`으로 명시한다.
가로·세로 병합은 모두 선언한 머리글 안에서 끝나야 하며, 본문은 미병합 plain 셀이어야 한다.
본문까지 걸친 병합, 머리글 밖의 기존 제목 셀 표시, 보호/고정 표·셀, 글자처럼 취급한 표,
중첩 표·그림·필드·컨트롤·세로 쓰기 셀은 거부한다. 다른 기존 도구의 BLOCK을 우회하지 않는다.
셀당 1~20 plain 문단·문단당 1~20 run과 native lineBreak tail을 보존한다.

- `repeat_header`: boolean. 지정 영역의 모든 **소유 셀** header 표시와 표 repeatHeader를 함께 설정한다. 세로 병합으로 가려진 좌표에 새 셀을 만들지 않는다.
- `alignment`: LEFT/CENTER/RIGHT. 기존 문단 서식을 public ensure_paragraph_format으로 복제하고 가로 정렬만 바꾼다.
- `vertical_align`: TOP/CENTER/BOTTOM. 지정 머리글 소유 셀 안쪽 세로 정렬만 바꾼다.
- `margins_mm`: left/right/top/bottom 중 명시한 면만 0~10mm. 나머지는 기존 유효 여백을 유지한다. 사용 가능 너비 5mm 이상 필요.
- `row_heights_mm`: 머리글 행별 5~30mm. 세로 병합 셀의 높이는 걸친 행들의 HWPUNIT 합으로 정한다. 너비/병합 span/본문 높이는 유지하며 사용 가능 높이 3mm 이상 필요.

값은 의무 기본값이 아니다. 문구 길이에 따라 여백·높이를 선택하고 한글이 실제로 확장한 크기·쪽 이동을 검토한다.
이 도구는 표 전체 높이 값을 강제로 맞추거나 글자를 자동 축소하지 않는다.

## 실행

현재 PC environment.json의 pythonPath를 사용한다. table/행/열은 1부터 시작한다.

```powershell
python -X utf8 scripts/safe_table_header.py inspect source.hwpx --table 1 --output new-inspection.json
python -X utf8 scripts/safe_table_header.py apply source.hwpx candidate.hwpx --request reviewed-request.json --dry-run
python -X utf8 scripts/safe_table_header.py apply source.hwpx candidate.hwpx --request reviewed-request.json
```

```json
{"schema":"hwpx.safe-table-header.v1","source_sha256":"inspect의 실제 SHA256","table":1,"header_rows":[1,2,3],"repeat_header":true,"alignment":"CENTER","vertical_align":"CENTER","margins_mm":{"left":1.5,"right":1.5,"top":1.5,"bottom":1.5},"row_heights_mm":[10,10,10]}
```

반복만 켜려면 정렬/여백/높이를 생략한다. 머리글 문구는 [선택 텍스트 편집](selected-text-edit.md)의
safe_edit.py inspect(table,row,column) → 정확한 target_id 계획 → dry-run → apply로 별도 편집한다.
병합 영역의 소유 셀과 고유 문단을 지정하며 셀 전체 재쓰기를 하지 않는다.

새 표는 create_new_document.compose의 새 문서 단계에서 public table.merge_cells를 사용할 수 있다.
먼저 병합으로 덮일 새 셀의 내용이 비어 있는지, 열 묶음이 논리적으로 맞는지 확인한다.
이는 기존 세로 병합 생성/해제의 지원 확대가 아니다. 표준 생성 audit가 병합 후 구조를 검증했다고
주장하지 말고 실제 소유 셀·완전한 grid·문구 수·본문/테두리·전체 출력을 별도 확인한다.
assets/merged-headers/two.hwpx와 three.hwpx는 실제 한글로 저장한 **합성 회귀 원본**이다.

## 보존과 출력 판정

public document/table/cell 바인딩과 set_size, ensure_paragraph_format을 사용한다.
제목 표시·셀 여백·세로 정렬은 별도 검증한 제한 속성 어댑터이며 임의 XML 폴백이 아니다.
예상 전체 section과 실제 section, 기존 공유 스타일와 허용한 신규 정렬 정의,
비대상 패키지 바이트를 독립 비교한다. 머리글 선택 문단의 line cache만 무효화할 수 있다.
본문 셀과 캐시, 모든 문구/run/tail/컨트롤, cellAddr/cellSpan/너비/테두리/배경/비대상 스타일은 유지한다.
출력은 신규 경로에만 만들고 원본 SHA256을 재확인한다. PASS_STRUCTURE의 native는 pending이다.

finalize prepare → SaveAs → 재열기/PDF → collect → **실제 모든 쪽 검토** → check를 수행한다.
모든 표 쪽에서 상위 묶음과 하위 열 제목의 수를 대조한다. 본문 고유 항목은 정확히 한 번이어야 한다.
실제 PDF 테두리 좌표에서 머리글 전체 높이를 측정하고 글자 잘림·겹침·병합선·표 뒤 문장·쪽 요소를 확인한다.
COM 생성/모듈 등록/열기·저장 성공은 구조 보존과 시각 완료를 대신하지 않는다.

2026-10-03 한글 2024 13.0.0.3903/core 6.3.0에서 새 가로·세로 병합 기준 2종과
기존 편집 5종(2단/3단 반복, 정렬·여백·높이, 3단 상위 문구 한 곳 변경), 총 **14쪽**이 strict gate complete.
2단 전체 20mm/3단 전체 30mm가 실제 다음 쪽에서도 유지됐다. 모든 R01~R24 본문 항목은 정확히 한 번,
기존 셀 span/크기/문구/run/테두리/활성 서식과 머리말·꼬리말·쪽 번호가 보존됐다.
43개 가드/보존 시험은 Python -O에서도 통과했다. 임의 기존 복잡한 표나 기존 세로 재병합까지 검증한 것은 아니다.
기존 safe_table_flow.py의 미병합 가드는 그대로 유지한다. 보안 DLL/레지스트리/권한/실행 정책 변경은 없다.

[한컴 제목 줄 반복 안내](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/table/tableattribute/table%28table%29.htm),
[한컴 셀 속성 안내](https://help.hancom.com/hoffice/multi/ko_kr/hwp/table/tableattribute/table%28cellattribute%29.htm).
