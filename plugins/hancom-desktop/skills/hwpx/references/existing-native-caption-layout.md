# 제목과 떠 있는 표의 쪽 연결

기존 safe_table_flow의 keepWithNext만으로 제목/표가 같은 쪽에 나온다고 보장할 수 없다. 실제 출력에서 제목과 첫 표머리의 쪽·좌표를 읽는다. 원래 분리된 작은 표를 이미 표가 시작하던 쪽에 붙이는 경우에 한해 제목 앞 쪽 나눔을 명시하고, 정상 문단 기준 자리 차지 표의 앵커와 개체 연결을 유지한다. 이미 함께 있는 제목에는 불필요한 강제 쪽 나눔을 넣지 않는다.

native_caption_layout_cli.py inspect → sourceSha256/binding/breakBeforeCaption/captionAfterHwpunit/이유 → dry-run → apply. 기존 제목 문단 스타일이 전용인 경우만 수정하고 공유 참조면 거부한다. 기존 ID를 유지해 불필요한 서식 복제/이전 정의 삭제를 피한다. 6.3.0 public header.element/mark_dirty와 table.element/mark_dirty 제한 어댑터이다. 미병합 root-body floating 2–20행 표, 바로 앞 plain 제목, 기존 modern/fallback margin 관계만 지원한다.

HWP047: 원래 분리 입력, 그 native 저장본, 별도 이미 맞는 floating compact 입력에서 첫 저장·반복 저장·같은 제목 배치 재편집(6pt → 9pt 간격), 활성 구조·전체 헤더 정의·모든 원문·저장 전후 픽셀·실제 12쪽 PASS. 별도 inline 표 입력은 작성 전 거부했고 유지했다. 이 검증은 표 전체를 한 쪽에 고정하는 기능이 아니다. CELL 나눔을 유지하며 제목과 첫 행의 관계를 검사한다. 여러 쪽 긴 표·병합·공유 스타일·중첩 캡션은 미검증이다.

공식 도움말: [표 위치](https://help.hancom.com/hoffice130/ko-KR/Hwp/table/tableattribute/table(position).htm), [여러 쪽 지원](https://help.hancom.com/hoffice130/ko-KR/Hwp/table/tableattribute/table(table).htm). 공식 글자처럼 취급된 표의 여러 쪽 제한을 따른다. 이번 수리는 그 속성을 바꾸는 폴백을 쓰지 않는다. 특정 XML 속성과 native 동작의 대응은 이번 실측 근거다.
