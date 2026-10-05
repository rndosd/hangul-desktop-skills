# 기존 셀의 가로 병합·해제·문단 정렬

`scripts/safe_cell_layout.py`는 기존 일반 표에서 선택한 셀만 바꾸고 원본을 유지한다.
public core merge_cells/split_merged_cell/ensure_paragraph_format을 사용하며 모든 비대상 XML·패키지를 독립 비교한다.
기존 safe_table_layout/form_fill/safe_edit의 BLOCK을 이 도구로 우회하지 않는다. 요청 연산의 별도 진단 경로다.

## 현재 확인한 범위

중첩/그림/필드/컨트롤이 없는 대상 표, 2~100행·1~12열, 셀마다 plain run 하나·문단 하나.
한글이 저장한 childless 빈 run도 지원한다. 다른 표나 대상 밖의 쪽 번호/머리말·꼬리말은 보존한다.

- merge: 같은 행의 연속 2~12개 셀, 병합 전에는 모두 단일 셀이어야 한다.
  왼쪽 셀의 내용을 유지한다. 나머지 셀에 내용이 있거나 서로 서식이 다르면 거부한다.
  채워진 셀 내용을 임의로 버리거나 합칠 순서를 추정하지 않는다.
- unmerge: 정확히 전체 가로 병합 범위를 지정한다. 총 너비를 같은 크기의 셀로 나눈다.
  정확히 나눠지는 HWPUNIT 너비만 지원한다. 원래 병합 전의 서로 다른 너비를 복원하는 기능은 아니다.
  내용은 왼쪽 셀에 남기고 새 셀은 비운다. 셀/문단/글자 서식은 유지한다.
- align: 단일 셀로 구성된 직사각형 선택 범위의 기존 문단을 LEFT/CENTER/RIGHT로 맞춘다.
  원래 paraPr를 복제해 horizontal 값만 바꾸며 글꼴, 들여쓰기, 행간, 여백, 다른 문단을 유지한다.
  여러 문단/run의 가로 정렬, 병합 셀 가로 정렬, 세로 병합·해제는 이 도구의 지원 범위에 없다.
  세로 정렬·안쪽 여백·일반 줄바꿈은 [별도 셀 배치 도구](cell-spacing-wrap.md)에서 제한적으로 지원한다.

split_merged_cell은 새 셀에 기본 paraPr를 주는 동작이 있다.
이 경로는 새 셀의 public para/style 참조를 원래 셀로 복원한다. 새로 생성한 빈 셀의 empty t만
native childless run 형태로 준비한다. 기존 셀 전체 쓰기나 임의 raw XML 편집으로 fallback하지 않는다.
구조 검사는 원본→후보 변경과 비대상 보존을 확인하고 실제 가독성/쪽 흐름은 native에서 확인한다.

## 명령과 요청

행·열·표 번호는 1부터 시작하며 range는 [시작행, 시작열, 끝행, 끝열]이다.
inspect를 읽고 source_sha256을 실제 원본 값으로 넣는다. 새 후보만 게시한다.

```powershell
python -X utf8 scripts/safe_cell_layout.py inspect source.hwpx --table 1 --output new-inspection.json
python -X utf8 scripts/safe_cell_layout.py apply source.hwpx new-candidate.hwpx --request reviewed-request.json --dry-run
python -X utf8 scripts/safe_cell_layout.py apply source.hwpx new-candidate.hwpx --request reviewed-request.json
```

```json
{"schema":"hwpx.safe-cell-layout.v1","source_sha256":"실제 원본 해시","table":1,"operation":"merge","range":[2,1,2,3]}
```

같은 병합 범위의 새 원본 해시와 operation="unmerge"로 해제한다.
정렬 예:

```json
{"schema":"hwpx.safe-cell-layout.v1","source_sha256":"실제 원본 해시","table":1,"operation":"align","range":[3,1,3,3],"alignment":"CENTER"}
```

stdout 영수증의 PASS_STRUCTURE는 후보의 제한 보존 검사이며 native 완료가 아니다.
표 크기/글자 배치가 바뀌므로 prepare → SaveAs → collect → 실제 전체 쪽 검토 → check를 연결한다.

2026-10-03 한글 2024 13.0.0.3903 / core 6.3.0: 한글 저장본 3쪽의 기존 표를 가로 3셀 병합하고
그 저장본을 다시 해제했다. 병합 해제 PDF 전체는 원래 표의 PDF와 픽셀이 일치했다.
센터→왼쪽 복원, 가운데 정렬, 오른쪽 정렬도 각 3쪽 SaveAs·재열기·native PDF·gate complete다.
쪽 번호·머리말·꼬리말·표 앞뒤 문장을 보존했다. 임의 복잡한 표에 대한 검증으로 확대하지 않는다.

가드와 회귀시험은 `scripts/test_frequent_editing.py`, 고정 합성 fixture는 assets에 포함한다.
