# 소계·합계 행 묶음과 내부 접합 여백

셀 문단 keepWithNext만으로 서로 다른 표 행의 쪽 묶음을 보장하지 않는다. 실제 행 라벨·원본 열 위치를 읽고 모든 쪽을 본다. HWP048 native TableSplitTable은 논리 4열을 3열로 바꾸고 병합/일부 테두리·정의까지 바꾸며 묶음도 실패했다. 그 실패는 유지한다.

summary_row_group_cli.py inspect → schema hwpx.summary-row-group.v2, 원본 sourceSha256/binding, tailRows(2–4), joinGapHwpunit(0–600), editableReason → dry-run → apply. python-hwpx6.3.0 public 문단/표 생성과 기존 행 element 이동 어댑터다. 셀 본문/ID/병합/셀크기/테두리/정의를 새로 만들지 않는다. 원래 표의 행을 작은 inline tail로 옮기고 로컬 rowAddr/행 수/aggregate 높이만 재배치한다. 기존 두 그룹에는 바로 앞 원본 행을 추가해 같은 기능으로 다시 편집한다. vertical merge·중첩·보호·긴 그룹은 거부한다.

새 내부 경계의 앞 표 bottom=joinGapHwpunit, 뒤 표 top=0만 명시 변경하고 원래 표의 바깥 top/bottom과 좌우·셀 내부 여백은 보존한다. HWP048이 복제한 8pt+6pt 외부 여백 때문에 compact 설명문이 두 번째 쪽으로 밀렸다. HWP049은 내부 경계를 0pt로 지정해 원본 한 쪽과 이전 실패 저장본을 한 쪽으로 복구했다. 사용자가 표 사이 여백을 요청하면 별도 간격을 지정하고 실제 쪽수를 확인한다. 서로 독립적인 표의 외부 여백을 임의로 없애는 지침이 아니다.

현재 다섯 입력: 경계 원본/저장본, compact 원본/이전 실패 저장본, 다른 19행·4쪽 긴 표에서 first/repeat/same-group reedit, 모든 기존 셀/병합/전체 정의, 출력 쪽수/묶음·저장 전후 PDF 픽셀·20쪽 실제 검토를 확인했다. compact 둘은 무예외 내부 비교도 모두 PASS. 다른 입력의 표 전체 높이 계산은 특정 두 table ID 직속 sz.height 예외로 별도 판정하고 무예외 FAIL은 유지한다. 모든 한글/버전/표로 일반화하지 않는다.

긴 표 R07 문단은 쪽 사이 머리말·꼬리말이 PDF 추출에 끼어 원본도 전체문구 검사에 실패했다. 기존 HWP030 엄격한 원본 chrome 좌표·문구 검사기로 모든49문단을 별도 재확인했다. 실제 글자 손실/정의 변경을 이 검사로 허용하지 않는다.
