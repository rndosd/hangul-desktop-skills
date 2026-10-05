# 기존 책갈피 이름 수정

`scripts/bookmark_rename_cli.py`는 번들 후보 런타임을 선택하고 공개 `InlineObject` 속성 API를 통해 기존 책갈피 이름만 변경한다. root 본문 문단의 단순한 단일 책갈피, 유일한 기존 이름, 새 미사용 이름에 한정한다. 전체 host/binding/hash와 모든 기존 책갈피 이름을 요청에 고정한다.

`inspect SOURCE --name 기존이름 --output binding.json`으로 대상을 읽는다. 요청 JSON에는 `schema: hwpx.bookmark-rename.v1`, `sourceSha256`, 출력 binding인 `bookmark`, `replacement`, 구체적 `editableReason`만 담는다. `apply SOURCE NEW.hwpx --request request.json --dry-run`으로 검사한 뒤 새 파일로 적용한다.

다른 필드의 메타데이터/명령에서 기존 이름을 발견하면 참조 갱신이 별도로 필요하므로 거부한다. 내부 하이퍼링크/상호참조를 함께 고치는 기능으로 확대하지 않는다. 여러 위치의 동명 책갈피, 범위형/복잡한 마커, 셀/주석/머리말 내부 책갈피는 지원하지 않는다. 비대상 package와 조판 캐시에 대한 예외가 없다.

PDF에서 보이지 않는 이름 변경이므로 저장된 HWPX의 이름·host·순서와 활성 의미·전체 header 정의를 읽고, 저장본에서 같은 책갈피 이름을 다시 변경해야 한다. COM 저장 성공이나 PDF 픽셀 동일만으로 합격하지 않는다. native UI의 책갈피 이동은 이 시험에서 확인하지 않았다.

HWP041: native 기존 보고서의 첫 저장·반복 저장·같은 이름 재편집은 모두 활성/전체 header 정의 PASS. 공개 API로 새 책갈피를 추가해 준비한 다른 문서는 첫 저장 시 같은 서식의 run이 합쳐져 예외 없는 활성 구조 FAIL이다. 이름·host·PDF는 유지되고 반복 저장/재편집은 PASS지만 최초 실패는 유지한다. HWP042 변경 없는 원본 저장 대조에서도 같은 run 합치기가 재현됐으며, 이 문서의 plain host·마커 문자 위치·속성은 같았다. 임의 개체 이동을 정상으로 승인하는 규칙이 아니다.
