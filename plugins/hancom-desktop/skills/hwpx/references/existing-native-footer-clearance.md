# 오른쪽 쪽 번호와 꼬리말 간격

native_footer_clearance_cli.py는 기존 physical RIGHT 꼬리말의 전용 문단 서식 오른쪽 여백만 조정한다. inspect → sourceSha256/binding/rightMarginHwpunit/구체적 이유 → dry-run → apply. 6.3.0 public header.element/mark_dirty의 제한 어댑터이며 raw package writer는 없다. modern 단위 값과 2배 fallback 값의 기존 관계를 유지한다. 공유 문단/스타일에서 쓰는 정의, 다른 정렬/복잡한 머리말·꼬리말은 거부한다. 기존 문구·글자 서식·정렬·서식 ID를 보존한다.

번호 위치와 문서 배치를 바꾸기 전 관련 꼬리말을 조사한다. 여백은 고정 규칙이 아니라 실제 번호 폭·가용 폭을 확인해 명시한다. HWP046은 40pt → 45pt 여백을 사용한 제한 시험이다. 임의 문서의 자동 최적 간격을 보장하지 않는다. 실제 글자 간격·충돌·첫 쪽 표시와 전체 본문 불변 픽셀 검사를 통과해야 한다. 일반/표지 2종의 첫 저장·반복 저장·동일 조합 재편집 활성 구조와 전체 헤더 정의, 실제 12쪽을 확인했다. 원래 HWP045 충돌 실패는 보존됐다.
