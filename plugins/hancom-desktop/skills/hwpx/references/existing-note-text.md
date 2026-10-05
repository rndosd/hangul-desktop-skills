# 기존 각주·미주 문구 편집

`scripts/note_text_cli.py`는 번들 런타임을 먼저 선택한다. 현재 검증 범위는 기존 각주/미주 하나의 단일 본문 문단, 1~8개 plain text run이다. 번호·앵커·run별 글자 서식은 보존하고 선언한 run의 문구만 교체한다. 여러 본문 문단, 탭/필드/그림이 섞인 주석, 새 주석 생성·삭제·순서/번호 변경은 이 도구의 범위 밖이다.

1. `inspect SOURCE --kind footNote --ordinal 1 --output note-binding.json`으로 실제 대상의 전체 binding을 읽는다. 미주는 `endNote`를 쓴다.
2. 요청 JSON은 `schema: hwpx.note-run-text.v1`, `sourceSha256`, 위 binding인 `note`, `edits: [{run: 1, expected: 기존 문구, replacement: 새 문구}]`, 구체적인 `editableReason`만 담는다. run은 1부터 시작한다. 원본/전체 binding/기존 문구가 다르면 거부한다.
3. `apply SOURCE NEW.hwpx --request request.json --dry-run`으로 비대상 package·번호·앵커·서식 보존을 검사한 뒤 새 경로로 적용한다. 구조 통과는 native 검증 완료가 아니다.
4. 실제 한글 열기→저장/재열기→PDF, 활성 의미·모든 header 정의·전쪽 검토를 별도로 수행한다. 저장본에서 같은 주석 run을 다시 수정하고 같은 검사를 반복한다. 저장본의 새 binding/hash를 읽어 요청한다.

`Note.text` 전체 setter는 혼합 서식 주석의 여러 run을 한 run으로 합칠 수 있다. 이 도구는 공개 `Note.body_paragraph.runs[i].text`만 사용한다. 지정 주석 본문의 조판 캐시 외에는 선언하지 않은 변경을 허용하지 않는다.

HWP040 근거: 기존 보고서의 각주/미주 및 별도 혼합 서식 주석 3사례, 첫 저장·반복 저장·동일 기능 재편집 15 native 작업, 활성 구조와 전체 header 정의 보존, 18쪽 실제 검토. 잘못된 요청 6개 거부와 전체 주석 setter의 혼합 서식 손실 검출을 포함한다. 설치본 교체·native UI 편집·모든 주석 유형 지원이나 전체 strict release를 인증하지 않는다.
