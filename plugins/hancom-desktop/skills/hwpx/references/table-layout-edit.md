# 기존 일반 표: 행 추가·삭제와 셀 크기

`scripts/safe_table_layout.py`는 python-hwpx 6.3.0 public `apply_table_ops`를 호출한다.
직접 XML 쓰기나 표 전체 재작성은 하지 않는다. XML은 대상 진단과 독립 보존 비교에 읽기만 사용한다.
원본 hash에 묶인 요청으로 후보를 새 파일에 게시한다. 기존 출력 경로는 거부한다.

## 현재 지원한 구조

중첩·병합이 없는 직사각형 표, 행 2~100/열 1~12, 셀마다 기존 plain t 하나를 가진 run 한 개와
문단 한 개. 컨트롤·필드·그림·중첩 표·병합·복수 문단/run·빈 childless run은 이 경로에서 거부한다.
다른 표의 병합/결재란 등 비대상 요소는 그대로 보존할 수 있다. 기존 form_fill/safe_edit의
지원 범위를 줄이거나 그 도구에서 거부된 작업을 우회하는 경로가 아니다.

- `insert_after`: 지정한 데이터 행 바로 아래에 한 행을 복제하고, 기존 글자/문단/셀 서식으로
  지정한 각 셀 내용을 넣는다. 머리행을 복제하지 않는다. 새 문단 ID가 충돌하면 출력 거부.
- `delete_row`: 지정 데이터 행 하나만 삭제한다. 머리행 삭제와 마지막 데이터 행 삭제는 거부한다.
- `resize`: 모든 열의 너비를 명시해 전체 표 너비를 유지하며 재분배한다.
  선택한 행 높이는 행 전체 셀에 적용한다. 셀 하나의 모서리만 임의 이동하거나 병합 경계를 바꾸지 않는다.

기존 표 높이의 library `sz.height`는 후보에 이전 값이 남을 수 있다.
시험에서 실제 한글 저장은 변경된 행 높이 합에 맞게 이 개체 높이를 재계산했다.
따라서 native 저장·재열기·PDF 출력과 전체 쪽 확인까지 수행한다.
이 정상 재계산과 비대상 서식/구조 변경을 구분해 읽기 비교하며 gate를 약화하지 않는다.

행 높이를 줄였다고 실제 출력 높이가 반드시 그 값이 되는 것은 아니다.
내용·안쪽 여백·글자 크기 때문에 한글이 더 큰 높이를 필요로 할 수 있다.
현재 native 시험은 높이 확대를 확인했으며, 긴 내용의 축소/자동 맞춤은 아직 확인하지 않았다.
글자 크기를 자동으로 줄이지 않는다.

## 요청과 명령

표와 행 번호는 1부터 시작한다. 머리행은 1번이다. mm 단위를 사용한다.
전체 표 너비를 먼저 inspect로 확인하며 후보 입력의 합을 그 너비에 맞춘다.

```powershell
python -X utf8 scripts/safe_table_layout.py inspect source.hwpx --table 1 --output new-inspection.json
python -X utf8 scripts/safe_table_layout.py apply source.hwpx new-candidate.hwpx --request reviewed-request.json --dry-run
python -X utf8 scripts/safe_table_layout.py apply source.hwpx new-candidate.hwpx --request reviewed-request.json
```

요청 예(세 개의 별도 요청이며 source_sha256은 실제 inspect 값으로 넣는다):

```json
{"schema":"hwpx.safe-table-layout.v1","source_sha256":"검토한 원본 해시","table":1,"operation":"insert_after","row":3,"values":["결과 공유","검토 의견을 정리해 관계 부서에 공유한다."]}
```

```json
{"schema":"hwpx.safe-table-layout.v1","source_sha256":"검토한 원본 해시","table":1,"operation":"delete_row","row":2}
```

```json
{"schema":"hwpx.safe-table-layout.v1","source_sha256":"검토한 원본 해시","table":1,"operation":"resize","widths_mm":[60,110],"heights_mm":{"1":8,"2":12,"3":12,"4":18}}
```

resize 예는 전체 너비 170mm인 표에만 적용할 수 있다. 다른 표에 그 크기를 그대로 강제하지 않는다.
CLI는 JSON 영수증을 stdout으로 출력하며 상태는 native_pending이다.
원본·후보 전체 보존 검사와 finalize의 prepare → SaveAs → collect → 전체 검토 → check를 연결한다.

## 검증 근거

2026-10-03, 한글 2024 13.0.0.3903 / python-hwpx 6.3.0.
기존 한글 저장본의 표 하나를 대상으로 추가/삭제/크기 조절의 독립 후보 세 개를 시험했다.
각각 저장·재열기·3쪽 PDF 출력 및 완료 gate가 complete다.
변경된 쪽을 시각 검토했고 나머지 쪽은 이미 전체를 검토한 원본과 렌더 이미지 해시가 동일했다.
표 밖 내용·나머지 세 표·병합표·결재란·기존 서식을 보존했다.
행 수는 머리행 포함 4→5, 4→3, 4 유지이며 열은 모두 2개다.
열 42.499/127.501mm를 60/110mm로 조절하고 행 높이를 8/12/12/18mm로 확대했다.
긴 문장은 잘림 없이 두 줄로 표시됐다. source→candidate 보존과 candidate→native 보존은 별도 비교했다.

회귀시험 10개: 정상 추가/삭제/크기, dry-run, stale hash, 머리행 삭제 거부,
전체 너비 확대 거부, 병합/중첩 거부, 비대상 손상 게시 거부.
Python 최적화 모드에서도 필수 검사는 제거되지 않으며 10개를 통과했다.

```powershell
python -X utf8 -O scripts/test_safe_table_layout.py
```

이 결과는 제한된 대표 구조의 검증이다. 임의 복잡한 표·긴 다쪽 표·양식 내용에 따른 자동 변형을
지원한다고 확대하지 않는다. 내용별 입력 칸 높이와 빈 반복 영역의 조절은 [기존 양식 변형](form-adaptation.md)의 별도 합성 경로를 따른다. 기존 행 편집 도구의 범위를 넓히지 않으며, 한글 저장본의 자식 없는 빈 run을 복제/채우는 지원은 별도 safe_repeat_rows.py에 한정한다.


여러 plain 문단/run과 기존 목록을 보존하는 미병합 표의 **열 너비만** 재배분은 [어절과 긴 표](word-flow.md)의 별도 safe_table_columns.py 경로를 사용한다. 이 경로는 기존 행 추가/삭제/높이 도구의 범위를 넓히지 않는다. 75→138mm 내용 열로 긴 표의 3→2쪽을 실제 확인했다.

기입된 plain 여러 문단/서식 run 표의 완료 행 하나를 삭제할 때는 [제한 행 삭제 후보](rich-row-delete.md)를 별도로 선택한다. 원래 단일 문단 도구의 거부 범위를 자동 해제하지 않는다.

여러 문단/서식 run 행을 복제해 추가하거나 인접 셀을 양쪽 내용 보존으로 가로 병합할 때는 [여러 문단 표 편집](rich-table-edit.md)을 선택한다. 지원 범위 밖의 병합·제어·중첩 구조는 거부하며 native 검증을 생략하지 않는다.
