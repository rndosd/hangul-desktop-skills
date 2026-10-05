# 기입된 여러 문단 표의 행 삭제 — 제한 후보

`safe_rich_row_delete.py`는 기존 일반 표에서 완료된 데이터 행 하나를 삭제한다. 기존 단일 문단 행 편집기를 대체하지 않는다. 병합·중첩/개체/필드/탭/줄바꿈을 가진 대상은 거부한다. 행 복제/새 행 추가나 셀 병합은 이 경로의 범위가 아니다.

각 셀은 1~5개 plain 문단, 문단은 1~20개 서식 run과 plain t 또는 native childless empty run을 허용한다. source/table hash, 정확한 데이터 행과 삭제 이유를 지정한다. 머리행은 보호한다. 표의 rowCnt와 유지 셀의 rowAddr만 바뀌며 나머지 셀·문단·서식/테두리/크기/그림/다른 package member를 전체 비교한다.

```powershell
python -X utf8 -B scripts/safe_rich_row_delete.py inspect source.hwpx --table 43 --output new-inspection.json
python -X utf8 -B scripts/safe_rich_row_delete.py apply source.hwpx new-output.hwpx --request request.json --dry-run
python -X utf8 -B scripts/safe_rich_row_delete.py apply source.hwpx new-output.hwpx --request request.json
```

요청은 `schema=hwpx.rich-row-delete.v1`, inspection의 `source_sha256/table/table_sha256`, 1부터 시작하는 `delete_row`와 `editable_reason`만 담는다. 새 파일만 발행한다. 원본과 대상을 다시 저장하면 inspection부터 새로 만든다. 구조 통과는 native 완료가 아니며 정확한 후보의 실제 한글 쪽을 확인한다.

HWP008: 공개 보고서 46표·6그림 중 두 문단/다중 강조 run을 가진 전략 표의 완료 행 삭제와 새 항목의 기존 행 재활용을 선택했다. 다른 표 44개와 그림 6개, 비대상 본문·바이너리를 보존했다. HWP009에서 4→3→2행 경계를 실제 편집하고 마지막 데이터 행 삭제를 거부했다. 2행 사본의 한글 SaveAs/재열기도 확인했으며 해당 경계만의 PDF 검사는 하지 않았다. 행 추가·가로 병합은 [별도 도구](rich-table-edit.md)를 사용한다. 임의 복합 표의 자동 재설계로 확대하지 않는다.
