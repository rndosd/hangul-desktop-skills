# 여러 문단 표의 행 추가와 가로 병합

한글이 계산한 표 전체 높이까지 최종 파일에 기록해야 하면 구조 편집을 통과한 뒤 [한글 최종 기록](../../hwpx-windows-finalize/references/native-writing.md)을 선택한다. 검토 없이 native 저장본을 원본 대신 발행하지 않는다.

`scripts/safe_rich_table.py`는 python-hwpx 6.3.0 공개 API로 기입된 평면 일반 표를 편집한다. 대상 셀은 1~5개 plain 문단, 각 문단 1~20개 run이다. 병합·중첩 표, 개체·필드·탭·인라인 제어가 있는 대상은 거부한다. 검증된 예시는 비어 있지 않은 텍스트 run이다. 임의 복합 표 재설계나 세로 병합으로 확대하지 않는다.

```powershell
python -X utf8 -B scripts/safe_rich_table.py inspect source.hwpx --table 43 --output new-inspection.json
python -X utf8 -B scripts/safe_rich_table.py apply source.hwpx new-output.hwpx --request request.json --dry-run
python -X utf8 -B scripts/safe_rich_table.py apply source.hwpx new-output.hwpx --request request.json
```

요청 공통 필드는 `schema=hwpx.rich-table.v1`, inspection의 `source_sha256/table/table_sha256`, 1부터 시작하는 데이터 `row`, 구체적인 `editable_reason`이다. 머리행은 보호한다.

- `operation=clone_after`: 선택 행 뒤에 한 행을 복제한다. `cells`는 셀 → 문단 → run의 새 문자열 목록이다. 모든 문단과 run을 지정하며 줄바꿈·탭은 문자열에 넣지 않는다. 셀 크기·테두리·문단·글자 서식을 복제하고 새 문단 ID의 충돌을 막는다.
- `operation=merge_horizontal`: `columns=[1,2]`처럼 인접한 두 열을 지정한다. 왼쪽 셀 서식·테두리를 유지하고 너비를 합친다. 오른쪽 문단과 run 서식을 뒤에 붙여 내용 손실을 막는다. 다른 테두리 정책이 필요하면 별도 작업으로 다룬다.

원본/hash와 실제 API 표의 ID·전체 구조를 결합한다. 패키지 XML 순번과 라이브러리 표 순서가 같다고 가정하지 않는다. 새 출력만 발행하고 비대상 member·본문·행·셀 및 요청한 전체 텍스트/서식을 독립 비교한다. 편집 뒤 한글의 표 전체 높이 재계산은 별도 확인한다. 구조 통과는 native 저장·시각 완료가 아니다.

HWP009: 22쪽 공개 보고서의 가상 사본과 별도 3열 합성 문서에서 행 추가·양쪽 내용 유지 병합, 실제 한글 열기/저장/재열기/PDF를 확인했다. 최초 SaveAs 버전·대체 글꼴 변화와 합성 표 전체 높이 변화는 엄격 보존 미통과로 남겼다. 이후 반복 저장은 활성 의미 및 모든 쪽 픽셀 비교를 통과했다.
