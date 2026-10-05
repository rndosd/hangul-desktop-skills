# 기존 큰 항목·표 전후 간격

native_report_spacing_cli.py inspect는 원본의 명시된 큰 항목 문구 전체를 받는다. 기존 문단 정의가 이 대상들에만 참조될 때 prev/next를 modern/fallback 관계로 바꾸고 기존 ID를 유지한다. 공유 대상 일부만 선택하면 거부한다. 각 root-body floating 표의 outMargin top/bottom만 바꾸고 좌우/셀 여백·셀크기·번호·본문·나머지 정의를 보존한다. 6.3.0 public header/section.element, mark_dirty/save_to_path 어댑터이며 raw ZIP 작성은 없다.

schema hwpx.native-report-spacing.v1, sourceSha256/binding, majorBeforeHwpunit/majorAfterHwpunit/tableBeforeHwpunit/tableAfterHwpunit, editableReason을 명시하고 dry-run 후 apply한다. 지원은 기존 두 개 이상의 큰 항목·root-body floating0–10표다. 0표는 코드상 허용했으나 이번 실측은1–2표이며 0표 경로는 미검증이다. 12표 예시집은 두 시도 모두 작성 전에 거부했으며 범위를 축소해 성공으로 세지 않았다.

HWP050 standard: 큰 항목16/7pt·표8/10pt 후 저장본에서18/8pt·표10/12pt 재편집, 첫/반복/재편집 활성 구조+전체 정의 PASS. 실제 PDF 간격·전체 내용·모든 쪽을 확인했다. compact도 내부는 PASS지만 마지막 한 줄만 다음 쪽으로 넘어가 FAIL_LAYOUT이다. 다른19행 긴 표는 첫/재편집 저장에서 table.sz.height가 바뀌어 엄격 내부 FAIL이 남는다. 이 기능을 범용 배포 합격으로 처리하지 않는다.

PDF에서 제목 문구가 본문에도 반복될 수 있으므로 원본 글자 크기로 제목을 구분한다. 표머리 문구는 원본 첫 셀에서 읽고 보조 계획에 손으로 적은 문구를 기대값으로 쓰지 않는다. 실제 표 선과 앞/뒤 본문 좌표 및 원본 prev/next 문자로 간격을 측정한다. 문단 쪽 넘침의 본문 누락 검사는 엄격 source chrome 검사와 별도로 실제 쪽을 본다. 문구 확인이 한 줄 고립 문제를 합격시키지 않는다.
