# 새 표의 여러 쪽 출력과 앞 설명 연결

새로 만든 빈 미병합 표에서만 `scripts/created_report_table.py`의 configure를 내용 기입 전에 호출한다. 이미 채워진 표·기존 사용자 양식·병합 표·중첩 개체에는 자동 적용하지 않는다. 글자처럼 취급한 기존 표를 조용히 해제하지 않는다. 기존 표는 existing-table-flow.md의 제한·실제 검증 경로를 따른다.

```python
from created_report_table import configure
t = doc.add_table(rows, cols, width=47000, height=requested_height)
configure(t, multipage=True, repeat_header=True, page_break='TABLE', before_pt=6, after_pt=8)
# 이 뒤 공개 cell/paragraph/run API로 내용을 넣는다.
```

긴 표에는 글자처럼 취급을 끄고 여러 쪽 흐름을 명시한다. TABLE은 행 전체를 다음 쪽으로 옮기고 CELL은 셀 내용을 쪽 경계에서 이어 쓸 수 있다. 어느 쪽이 알맞은지는 내용과 실제 출력으로 결정한다. 한 행 자체가 쪽보다 큰 경우는 이 검증 범위에 없다. 모든 표에 이 값을 강제하지 않는다. 제목행 반복은 표 속성과 첫 행 셀 표시를 함께 설정한다. 셀 크기·너비·내용·글꼴·쪽 여백은 바꾸지 않는다.

표 앞 설명이 홀로 앞쪽에 남으면 새로 작성하는 그 문단에 `doc.styles.apply_paragraph_format(paragraph_index=..., keep_with_next=True)`를 선택한다. 이번 inline 소형 표에서는 설명과 표가 함께 다음 쪽으로 이동했다. 떠 있는 임의의 기존 표에는 같은 결과를 보장하지 않으며, 필요하면 기존 표 쪽 흐름의 명시적 쪽 나눔 경로를 실제 출력으로 확인한다.

HWP012에서 43행 점검표·5행 고정 큰 행/긴 어절 표·별도29행 행사 운영표를 검증했다. 최초 inline 긴 표는 HWPX 내용과 전후 PDF가 같아도 뒷부분이 출력에서 잘렸다. 수정 뒤 원본의 전체 행/문단·추가 요청 문단, 반복 제목행, 마지막 행과 뒤 본문이 모두 출력됐다. CELL과 TABLE 출력 모두 보존했지만 최종 사례는 행 단위 TABLE을 선택했다. 여러 표와 그림 보고서의 새 표 앞 설명도 함께 이동했다. 이 시험의 큰 행 높이·6/8pt 간격은 시험 선택값이며 모든 보고서의 내용 형식이나 권장 크기를 고정하지 않는다.

한글 COM native 작업은 동시에 실행하지 않는다. 앞 작업의 정상 Quit와 worker 종료를 확인한 뒤 다음 호출을 시작한다. 기존 Hwp 프로세스 보호로 충돌한 호출은 COM/모듈 NOT_CALLED로 기록하며, 프로세스를 강제 종료하거나 보호 조건을 해제하지 않는다.
