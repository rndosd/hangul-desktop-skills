# 기존 native 머리말·꼬리말 문구

`scripts/native_story_text_cli.py`는 기존 root body ctrl에 저장된 physical header/footer의 단일 문단, 1~8개 plain text run에 한정해 지정 문구를 수정한다. 공개 Paragraph/Run API를 쓰는 버전 6.3.0 adapter다. 전체 story를 다시 생성하지 않고 선택 run만 수정하며 ID·폭·서식·쪽 유형·숨김·본문 및 비대상 package를 대조한다.

`inspect SOURCE --kind header --ordinal 1 --output binding.json`으로 전체 binding을 읽는다. 꼬리말은 `footer`다. 요청은 `schema: hwpx.native-story-run-text.v1`, `sourceSha256`, `stories: [{binding: inspect결과, edits: [{run: 1, expected: 기존문구, replacement: 새문구}]}]`, 구체적 `editableReason`만 담는다. 최대 6개 기존 story, 각 최대 8개 run이다. `apply SOURCE NEW.hwpx --request request.json --dry-run`을 먼저 수행한다.

native logical/mirror가 동시에 있는 구조, 다중 문단, 필드/자동 쪽 번호/탭/그림이 섞인 story는 이 도구가 지원하지 않는다. 쪽 번호나 새 구역/홀짝 설정 변경으로 확대하지 않는다. 전체 HeaderFooter.text setter는 기존 subList/문단 ID/혼합 서식을 새 내용으로 덮을 수 있으므로 사용하지 않는다.

실제 한글 첫 저장·반복 저장·저장본 같은 run 재편집, 활성 의미 및 모든 header 정의, 반복 표시 쪽·표지 첫 쪽 숨김, 전쪽 검토를 별도 수행한다. 글자가 같다고 본문 제목을 머리말로 분류하지 않는다. PDF 비교에서는 선언한 머리말/꼬리말 영역의 실제 글자 사각형만 대상으로 삼으며 그 밖의 본문 픽셀은 같아야 한다.

HWP044는 일반·표지·혼합 서식 보고서 3종을 시험했다. 검사기의 처음 Pillow 의존성 오류와 표지 제목/머리말 혼동 오류를 보존했고, 설치 추가 없이 표준 Python 픽셀 비교와 영역 제한으로 수정했다. 편집기 구현 자체는 바꾸지 않았으며 실제 native 성공 영수증을 확인하고 빠진 재편집 단계만 수행했다. native UI 편집·모든 story 유형·전체 strict release를 인증하지 않는다.
