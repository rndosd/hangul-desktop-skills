# 명시한 미사용 서식의 보관

PDF가 같아도 한글 저장에서 참조가 없어진 서식 정의가 없어질 수 있다. 사용 중인 구조, 전체 정의, raw 패키지 차이, 실제 재편집을 각각 비교한다. 원본 손실 사례의 ID를 확인했을 때만 후보에서 선택적으로 보관한다.

`scripts/retention_cli.py inspect source.hwpx --kind paragraph|character --id ID [--id ID] --output new-plan.json`으로 해시와 도구, 1–5개 정확한 ID·전체 참조·추가할 이름을 고정한다. `apply source.hwpx --plan new-plan.json --output new-private.hwpx --receipt new-receipt.json`은 그 바인딩을 확인한다. 이미 참조된 정의는 바이트 사본이다. 본문·원래 모든 정의·자산은 유지하고 헤더의 명명 스타일과 개수만 추가한다.

문단은 “보존 문단서식 ID” PARA 스타일, 글자는 “보존 글자서식 ID” CHAR 스타일이다. **문서의 스타일 목록에 항목이 추가된다.** 숨은 본문을 넣거나 미사용 정의를 검사 예외로 삭제하지 않는다. 한국어/영어 이름 충돌, 전체160개 제한, stale source/tools와 기존 출력/receipt는 거부한다. 이름 충돌 시 자동 덮어쓰기·다른 이름 재시도는 하지 않는다.

이 CLI는 public python-hwpx6.3.0 ensure_style와 공개 header.element의 기존 lockForm 보존 어댑터다. COM, DLL, registry 또는 승인은 변경하지 않는다. CLI 성공은 원본·비대상 패키지 검사까지이며, 해당 후보의 실제 한글 저장→재열기→반복 저장 및 PDF 전체 쪽 검토가 별도로 필요하다. 한글 UI 스타일 적용, 다른 PC·빌드와 임의 정의의 자동 보관은 검증 범위가 아니다. 새 이름만 추가했다는 이유로 저장 보존을 통과 처리하지 않는다.

공식 근거: [한글 스타일 도움말](https://help.hancom.com/hoffice130/ko-KR/Hwp/format/style/style.htm)은 PARA/글자 스타일 구분, 영어 이름에 의한 동일 스타일 판정과 최대160개 제한을 설명한다. 이것은 미사용 정의 삭제 원인을 직접 설명하는 공식 문장이 아니며, 보관 효과는 실제 파일 시험으로 확인해야 한다.
