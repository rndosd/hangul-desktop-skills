# 기존 긴 표의 제목행 반복·행 나눔·표 간격

`scripts/safe_table_flow.py`는 기존 내용을 다시 쓰지 않고 선택한 표의 쪽 흐름과 바로 앞 표 제목의 연결 속성만 변경한다.
보고서 목차와 내용 형식을 규정하지 않는다. 필요한 기능을 선택하고 실제 한글 출력으로 결정한다.

## 지원 경계

python-hwpx 6.3.0 전용, 평면 **미병합** 표 2~100행·1~12열. 셀당 기존 1~20문단·문단당 1~20 plain run과 native lineBreak tail을 보존한다.
중첩 표·그림·필드·컨트롤·세로 쓰기 셀, 잠금·고정 크기 표, 글자처럼 취급한 표는 거부한다.
본문 직접 문단에 담긴 표만 선택한다. 병합 제목행과 쪽보다 큰 한 행의 정상 출력은 이번 검증에 포함하지 않았다.
글자처럼 취급을 자동 해제하거나 표를 다시 만드는 폴백은 없다.

- `page_break`: CELL(셀 내용의 줄도 다음 쪽으로 이어짐) / TABLE(행/셀 사이에서 나눔).
  TABLE은 행을 통째로 옮기므로 앞쪽의 빈 공간이 더 커질 수 있다. 쪽보다 큰 행을 모두 담는다는 뜻은 아니다.
- `repeat_header`: boolean. True는 반드시 `header_rows:[1]`을 함께 명시한다. 첫 행 셀의 header 표시와 표의 반복 설정을 같이 켠다.
  False는 반복만 끄고 기존 제목 셀 표시를 유지한다. 둘 이상의 병합 제목행은 이 도구의 범위 밖이며 [다단 병합 머리글](merged-table-headers.md)의 별도 검증 경로를 사용한다.
- `outer_spacing_pt`: before/after 중 필요한 면만 0~36pt. outMargin.top/bottom만 바꾸고 좌우 들여쓰기·셀 안 여백·너비·높이·쪽 여백은 유지한다.
- `caption`: 기존 표 바로 앞의 plain 문단을 `expected_text`로 정확히 확인하고 `keep_with_next`를 명시한다.
  필요한 경우 `page_break_before:true`로 그 제목 문단에서 새 쪽을 시작할 수 있다. 문단/컨트롤을 새로 삽입하는 방식이 아니다.
- `anchor_same_page:true`: 자리 차지·문단/단 기준·본문 흐름·겹침 없음인 표에서만 holdAnchorAndSO를 켠다.
  **제목의 고아 배치를 자동 해결하는 옵션으로 사용하지 않는다.** 작은 경계 표에서 이 값과 keepWithNext를 함께 켜도 제목/표/뒤 본문의 순서가 잘못되는 사례가 재현됐다.

## 쪽 경계에서 결정할 것

제목행 반복은 repeatHeader와 첫 행의 제목 셀 표시를 함께 확인한다.
셀 내부 나눔은 긴 설명을 자연스럽게 이어야 할 때, 행 전체 유지는 항목을 한눈에 봐야 할 때 선택한다.
처음부터 모든 표에 한 설정을 강제하지 않는다.

표 제목의 keepWithNext는 조판 부호를 담은 문단과 연결하는 값이며, 떠 있는 표의 실제 첫 행과 같은 쪽이 된다는 보장은 없다.
시험에서 keepWithNext만 적용한 경우와 앵커 연결을 추가한 경우 모두 제목·뒤 문장이 앞쪽, 표가 다음 쪽에 나타났다.
이 두 후보는 COM 저장 성공과 별개로 visual_review_failed로 남겼다.
검토한 표 제목에 명시적 pageBreakBefore를 적용한 후보는 **제목 → 표 → 뒤 문장** 순서를 회복했다.
실제 출력에 문제가 있을 때만 그 위치의 쪽 나눔을 선택하며, 문서 전체 제목에 자동 적용하지 않는다.

몇 줄만 넘치는 경우 표 바깥의 과한 간격을 먼저 살펴본다. 이번 사례는 앞뒤 36pt에서 앞 6pt·뒤 8pt로 바꾸어 2쪽을 1쪽으로 줄였다.
글꼴·셀 크기·사방 쪽 여백과 내용은 그대로였다. 이 값은 통제 시험이지 모든 문서의 권장 간격이나 자동 한 쪽 맞춤 규칙이 아니다.
간격을 조금 바꾸어도 중간 행의 나눔 위치가 달라질 수 있으므로 마지막 쪽만 보지 말고 전체 표를 검토한다.
기존 양식의 범용 자동 쪽 여백 맞춤은 추가하지 않았다.

## 실행

Python은 현재 PC environment.json의 pythonPath를 사용한다. table 번호는 1부터 시작한다.

```powershell
python -X utf8 scripts/safe_table_flow.py inspect source.hwpx --table 1 --output new-inspection.json
python -X utf8 scripts/safe_table_flow.py apply source.hwpx candidate.hwpx --request reviewed-request.json --dry-run
python -X utf8 scripts/safe_table_flow.py apply source.hwpx candidate.hwpx --request reviewed-request.json
```

```json
{
  "schema":"hwpx.safe-table-flow.v1",
  "source_sha256":"inspect에서 읽은 실제 SHA256",
  "table":1,
  "page_break":"TABLE",
  "repeat_header":true,
  "header_rows":[1],
  "outer_spacing_pt":{"before":6,"after":8}
}
```

제목 위치도 검토한 별도 요청 예시:

```json
{"schema":"hwpx.safe-table-flow.v1","source_sha256":"실제 SHA256","table":1,"caption":{"expected_text":"정확한 기존 표 제목","keep_with_next":true,"page_break_before":true}}
```

원본/기존 출력을 덮어쓰지 않는다. 요청 원본 해시·알 수 없는 키·값 범위를 검사한다.
PASS_STRUCTURE는 의도한 속성/비대상 보존 통과이며 native는 pending이다.
전달 후보에 finalize prepare → SaveAs → collect → 실제 모든 쪽 검토 → check를 적용한다.
각 항목 시작/끝·제목행 반복 횟수, 표 제목과 첫 행의 쪽, 표 뒤 문장의 순서/간격·잘림·쪽 요소를 대조한다.

## 구현과 실제 검증

전용 public 표 흐름 setter가 없는 core 6.3.0에 별도 검증한 제한 속성 어댑터를 사용한다.
public document/table 바인딩으로 pageBreak/repeatHeader, 지정 첫 행 header, outMargin.top/bottom과 명시한 anchor flag만 바꾼다.
제목은 public ensure_paragraph_format으로 기존 문단 정의를 복제하고 참조만 바꾼다.
독립 검사는 예상 전체 section, 기존 공유 header 정의와 허용한 신규 정의, 비대상 패키지 바이트까지 비교한다.
셀 전체 쓰기나 자동 XML 폴백은 없고 글꼴/내용/셀 크기/쪽 여백/머리말/쪽 번호를 바꾸지 않는다.

2026-10-03 한글 2024 13.0.0.3903 / core 6.3.0에서 기존 native 원본의 편집 7종·기준 2종, 전체 **29쪽**을 저장·재열기·PDF 출력·전체 시각 검토·strict gate complete로 확인했다.
진단 부정 사례 3종·6쪽은 visual_review_failed로 거부했다. 실제 18행 TABLE 나눔, 표가 있는 모든 쪽의 제목행,
표 뒤 간격 증가 6pt, 2→1쪽 감소, 명시한 제목 쪽 나눔에 따른 순서 회복을 측정했다. 비대상 부록은 픽셀이 일치했다.
37개 가드/보존 시험이 Python -O에서도 통과했다. assets/table-flow/source.hwpx와 caption.hwpx는 합성 회귀 fixture이다.
임의 복잡한 양식·여러 행 병합 제목·세로 병합·한 쪽보다 큰 한 행·특정 프린터까지 확인했다는 뜻은 아니다.

[한컴 여러 쪽 지원 안내](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/table/tableattribute/table%28table%29.htm),
[한컴 표 위치·조판 부호 안내](https://help.hancom.com/hoffice130/ko-KR/Hwp/table/tableattribute/table%28position%29.htm).
보안 DLL·레지스트리·실행 정책은 이 편집 도구에서 변경하지 않는다.
