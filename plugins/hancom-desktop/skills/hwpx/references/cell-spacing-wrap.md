# 기존 셀의 세로 정렬·안쪽 여백·일반 줄바꿈

`scripts/safe_cell_spacing.py`는 기존 내용을 다시 쓰지 않고 선택한 셀의 배치 속성만 바꾼다.
내용 구성과 보고서 목차는 규정하지 않는다. 문서에 필요한 경우에만 선택한다.

## 지원 범위

python-hwpx 6.3.0, 평면 표 2~100행·1~12열, 셀마다 기존 1~20문단·문단마다 1~20 run.
여러 글자 서식 run과 native `hp:lineBreak`를 포함한 plain 텍스트를 보존한다.
중첩 표·그림·필드·컨트롤·세로 쓰기가 있는 대상 표는 거부한다.
행·열·표 번호는 1부터 시작한다. 병합된 셀은 정확한 소유 셀(앵커) 주소만 지정한다.

- `vertical_align`: TOP / CENTER / BOTTOM. 글꼴·문단 서식·텍스트는 유지한다.
- `margins_mm`: left/right/top/bottom 중 필요한 면만 명시한다. 각 0~10mm, 사용 가능한 셀 너비 최소 5mm.
  자체 여백이 꺼져 있으면 표의 기본 안 여백을 읽고, 변경하지 않은 면의 유효 값을 유지한 채 자체 여백을 켠다.
- `line_wrap`: BREAK만 지원한다. 기존 ‘한 줄로 입력’(SQUEEZE)을 일반 줄바꿈으로 바꾸거나 이미 BREAK인 셀을 명시할 수 있다.
  보호 셀은 편집하지 않으며 고정 크기 표의 줄바꿈 전환은 거부한다. 자동 글자 축소·임의 내용 삭제는 하지 않는다.

여러 문단/run의 **보존과 배치**를 지원한다. 문단 삽입·삭제나 텍스트 작성 기능을 추가한 것은 아니다.
가로 정렬·병합·해제는 [별도 도구](cell-merge-alignment.md)의 단일 문단 범위를 따른다.

## 실행

Python 경로는 이 PC의 environment.json에서 읽는다. 원본과 다른 새 출력 경로만 사용한다.

```powershell
python -X utf8 scripts/safe_cell_spacing.py inspect source.hwpx --table 1 --output new-inspection.json
python -X utf8 scripts/safe_cell_spacing.py apply source.hwpx candidate.hwpx --request reviewed-request.json --dry-run
python -X utf8 scripts/safe_cell_spacing.py apply source.hwpx candidate.hwpx --request reviewed-request.json
```

```json
{"schema":"hwpx.safe-cell-spacing.v1","source_sha256":"inspect에서 읽은 실제 해시","table":1,"edits":[{"row":2,"column":1,"vertical_align":"TOP"},{"row":3,"column":2,"margins_mm":{"left":5,"top":2}},{"row":4,"column":2,"line_wrap":"BREAK"}]}
```

최대 50개 셀, 중복 대상·알 수 없는 키·오래된 원본 해시는 거부한다.
stdout의 PASS_STRUCTURE / PASS_STRUCTURE_DRY_RUN은 구조 보존 결과이고 native 상태는 pending이다.
표 배치 변경에는 finalize prepare → SaveAs → collect → 실제 전체 쪽 검토 → check를 적용한다.

## 구현과 검증 경계

core의 전용 public setter가 없는 속성에만 별도로 검증한 제한 OXML 속성 어댑터를 사용한다.
public document/table/cell 바인딩으로 대상에 접근하고 vertAlign/lineWrap/hasMargin/cellMargin만 바꾼다.
대상 문단의 줄 캐시는 지워 한글이 다시 조판하게 한다. cell.set_text나 임의 XML 폴백은 없다.
독립 검증은 전체 비대상 패키지·XML, 원래 셀 구조·문단/run·스타일·줄바꿈 뒤 tail까지 비교한다.
독립 verify 호출도 요청의 원본 해시에 묶인다. 이 경로로 다른 도구의 BLOCK을 자동 우회하지 않는다.

2026-10-03 한글 2024 13.0.0.3903 / core 6.3.0에서 편집 8사례와 기준 1사례를
저장·재열기·native PDF 전체 11쪽 검토·strict gate complete로 확인했다.
세로 위치와 여백 이동량을 실제 PDF 경계로 측정했고 가운데 정렬 복원은 기준과 픽셀이 일치했다.
표 기본 여백 상속을 바꾼 3쪽 문서의 표지·마지막 쪽과 쪽 요소도 유지했다.
한 줄 설정으로 긴 글자가 겹치는 부정 대조군은 COM 저장 성공과 별개로 visual_review_failed로 거부했다.
26개 가드/보존 시험은 Python -O에서도 통과했다. fixture는 assets/cell-spacing/source.hwpx에 포함한다.

긴 셀은 일반 줄바꿈에서 실제 출력 행 높이가 늘 수 있다. native 저장본의 cellSz.height가
기존 명목 값으로 남을 수 있으므로 XML 높이만 보고 잘림/쪽 수를 판정하지 않는다.
실제 PDF의 끝 문장·표 다음 본문·글자 겹침·여백과 모든 쪽을 확인한다.
임의 양식, 고정 크기 표, 여러 쪽에 걸친 이 셀 편집은 이 대표 시험만으로 보장하지 않는다.

한글의 [공식 셀 속성 안내](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/table/tableattribute/table%28cellattribute%29.htm)를 참고한다.
PC별 COM·보안 모듈·레지스트리는 이 편집 도구에서 변경하지 않는다.


subList lineWrap=BREAK는 셀 일반 줄바꿈이며 문단의 어절/단어 기준과 다르다. 한글 어절·영문 단어를 지키는 선택 문단 설정과 자간 후보는 [어절과 긴 표](word-flow.md)의 별도 경로다.
