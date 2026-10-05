# 혼합 글자 서식을 보존하는 본문 편집

`safe_body_structure.py`의 `hwpx.body-structure.v2`는 기존 본문에서 굵게·색상·밑줄처럼 여러 run으로 나뉜 문단을 명시적으로 수정하거나 복제하여 추가한다. 원문을 먼저 읽고 사용자의 내용 변경 범위와 새 문구의 강조 위치를 에이전트가 결정한다. 특정 보고서 내용 구성이나 강조 방식은 의무로 정하지 않는다.

## 범위와 중단 조건

- 기존 section의 root-body plain 문단만 대상이다. 1~20개의 run, run마다 childless t 하나인 비어 있지 않은 문단을 사용한다. 기존 native NUMBER/BULLET 정의와 단계는 유지한다.
- `inspect`의 `richTemplate`, `runs`와 완전한 binding을 확인한다. 각 run의 문구를 순서대로 모두 지정한다. 본문을 한 문자열로 합치거나 길이만으로 강조 경계를 추정하지 않는다.
- 기존 run별 charPrIDRef와 문단 서식, 간격, 들여쓰기, 번호를 복제한다. 새 글자 서식을 자동 생성하거나 run 수를 늘리고 줄이지 않는다. 필요한 강조가 원본에 없으면 이 경로로 임의 생성하지 않는다.
- 표/셀/그림/도형/각주/필드/머리말·꼬리말 등 control 또는 다른 story가 포함된 문단을 이 도구로 수정·복제·삭제하지 않는다. 다른 helper의 BLOCK을 우회하지 않는다.
- 원본 SHA256, part/index/id/전체 subtree SHA256/정확한 텍스트 binding, protectedSpans, 원래 native 부모 identity, 충돌 및 제한 검사는 v1과 동일하다. 원본이 다시 저장되면 inspect/request를 새로 만든다.
- 1~40 operations, 삽입 하나에 1~20 문단, 전체 변경 100문단 이하, 한 문단 총 3000자 이하. 줄바꿈·탭·예상 밖 옵션·run 수 불일치·무의미한 변경은 거부한다.

## 요청 예

최상위 키는 `schema`, `sourceSha256`, `editableReason`, `protectedSpans`, `operations`만 사용한다. 아래 selector는 실제 inspect에서 나온 완전한 binding 객체로 대체해야 한다.

```json
{"op":"replace_runs","target":"<binding object>","runs":["검토 의견: ","담당 확인"," / 자료 범위 미정"," / 인계 경로 확인"," - 원본 대조 뒤 결정한다."]}
{"op":"insert_after","anchor":"<binding object>","template":"<binding object>","paragraphs":[{"runs":["후속 검토: ","원본 확보 필요"," / 연락처 미정"," / 적용 전 확인"," - 실제 자료 확인 뒤 진행한다."]}]}
```

다섯 run은 예시일 뿐이다. 실제 template의 run 수와 의미에 맞춰 모두 지정하며 각각의 기존 글자 서식을 사용한다. public `insert_paragraphs`, run `text`, `remove`를 사용한다. raw XML을 써서 문서를 편집하지 않는다.

## 제목과 다음 내용의 쪽 흐름

단독 제목이 표와 갈라진 경우, 전체 여백이나 표 크기를 바꾸기 전에 필요한 제목 문단 하나에 다음 작업을 적용할 수 있다.

```json
{"op":"paragraph_flow","target":"<binding object>","page_break_before":true,"keep_with_next":true}
```

두 키 중 하나 이상, 정확한 boolean만 받는다. 기존 break/control/outline 문단과 보호 범위는 거부한다. public `ensure_paragraph_format(base_para_pr_id=..., break_setting=...)`로 해당 플래그만 바꾼 파생 문단 서식을 만들고 대상 paraPrIDRef만 바꾼다. 기존 공유 정의·번호·다른 header 내용은 구조적으로 같아야 하며 추가 정의는 요청한 플래그 변경 외에 차이가 없어야 한다. 다른 package member는 byte-exact로 확인한다. flow가 없으면 header도 byte-exact다.

`keep_with_next`만으로 모든 표/개체 배치를 보장하지 않는다. 필요한 경우 명시적 쪽 시작을 사용하고 실제 출력에서 제목과 표가 같은 **한글 쪽**에 있는지 확인한다. 모아찍기 PDF 한 장에 같이 있다는 것만으로 통과시키지 않는다. 표 자체의 이동/크기/스타일/분할 정책 변경은 별도 도구의 계약을 따른다.

## 검증과 재현

기존 body-structure-edit.md의 inspect → dry-run → apply → exact candidate의 Windows finalize prepare → SaveAs/재열기/PDF → collect → 독립 보존 비교/모든 쪽 실제 검토 → check 절차를 따른다. `PASS_STRUCTURE`는 한글 완료가 아니다. 편집된 문단은 전체 subtree에서 요청한 run 텍스트/flow 차이만 허용하고, 미편집 문단·표·개체는 전체 subtree로 비교한다. 기존 native 부모 소속은 유지한다.

2026-10-04 한글 2024 13.0.0.3903/core 6.3.0에서 전라남도 공개 결과보고서(표 16개) 복사본과 합성 복합 문서로 검증했다. 공식 자료의 수치는 바꾸지 않고 가상 검토 메모 추가/표현 수정 및 제목 단독 쪽 문제를 교정했다. 원본·결과 총 19개 실제 PDF 인쇄면(모아찍기 포함)을 모두 검토했으며 strict 완료 검사, 독립 내용·서식·표/개체 비교, PDF의 굵은 glyph/파란색/실제 밑줄 선 및 제목/표 한글 쪽 좌표를 확인했다. 기존 29개+새 25개 회귀검사 54개를 Python -O에서 통과했다.

최초 원본 SaveAs에서는 빈 substFont 참조와 중복 pageNum 정리 때문에 strict 실패가 있었다. 실패 기록은 유지했다. 원본 OpenOnly/저장/재저장 6인쇄면의 pixel, 모든 내용, 활성 서식(추가 LTR 기본값 외 동일), 유실 control 차이를 독립 비교한 뒤 정확한 native 저장 복사본으로 새 검증을 수행했다. 최초 strict 실패 자체를 해결했다고 주장하지 않는다. 재검사 중 PowerShell worker AuthorizationManager 시작 오류가 한 번 있었고, 정책 변경 없이 새 검증 경로/승인된 실행 맥락에서 같은 candidate가 성공했다. COM 생성과 모듈 등록을 구분한다.

`assets/mixed-runs/`의 합성 source.hwpx, request.json, result.hwpx와 짧은 프롬프트는 공개 보고서 데이터가 필요 없는 재현 자산이다. 요청은 원본 SHA에 묶여 있다. 다른 PC는 설치기의 현재 runtime/core/한글 COM/검증된 공식 DLL 환경 점검과 해당 PC의 native 출력 검사를 다시 수행한다. 이 PC의 통과는 다른 PC의 설치 성공을 보장하지 않는다. 레지스트리·ACL·실행/보안 정책·DLL·승인창 처리 변경은 이 기능에 포함하지 않는다.
