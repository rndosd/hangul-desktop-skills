# 기존 웹 하이퍼링크 주소 편집

`scripts/hyperlink_target_cli.py`는 번들 후보를 선택하고 버전 6.3.0의 공개 InlineObject 이름 setter 및 노출 element의 고정 필드 파라미터를 쓰는 제한 adapter를 실행한다. 원래 field name, Command, Path가 같은 HTTPS 웹 주소를 가리키는 단일 root 본문 링크에 한정한다. 정확한 기존 six-parameter shape와 fieldBegin/fieldEnd pair, host, 표시 문구, source hash를 고정한다.

`inspect SOURCE --ordinal 1 --output binding.json`으로 대상 binding을 읽는다. 요청은 `schema: hwpx.hyperlink-target.v1`, `sourceSha256`, binding인 `hyperlink`, 새 HTTPS URL인 `replacement`, 구체적 `editableReason`만 담는다. `apply SOURCE NEW.hwpx --request request.json --dry-run` 뒤 새 파일로 적용한다.

한글 필드의 name만 바꾸면 PDF의 실제 URI는 옛 Command 주소로 남을 수 있다. 이 도구는 name, Command의 `URL;1;0;0`, Path를 함께 바꾸고 다른 모든 파라미터·표시 글자·서식·field pair·비대상 package를 독립 대조한다. 조판 캐시 예외가 없다. 원본 메타데이터가 이미 불일치하면 추정해 복구하지 않고 거부한다.

현재 내부 책갈피, 파일/메일 링크, 여러/중첩 필드, 셀/주석/머리말 링크, 복잡한 표시 텍스트는 지원하지 않는다. 새 주소의 보안 판단이나 외부 사이트 방문/로그인/다운로드를 이 편집기에 맡기지 않는다. 사용자가 지정한 주소를 저장할 뿐 직접 실행하지 않는다.

PDF 화면이 같아도 URI는 별도다. 실제 한글 첫 저장·반복 저장·같은 링크 주소 재편집 후 HWPX 세 값과 PDF URI를 각각 확인한다. HWP043 두 native 원본에서 예외 없는 활성 의미·전체 header 정의·표시 내용 보존, 다섯 출력 URI 변경, 12쪽 실제 검토를 확인했다. 이름만/Command만 변경한 대조 출력 2건으로 Command 주소가 PDF URI를 결정하는 사례를 재현했다. native UI 링크 클릭이나 모든 링크 형태/전체 strict release를 인증하지 않는다.
