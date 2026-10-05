# 계약 버전 안내

아래 단일-run 템플릿 제한과 header byte-exact 설명은 v1 경로에 해당한다. v2의 명시적 혼합-run 텍스트 수정/추가와 대상 문단 flow 파생 서식은 [혼합 서식 본문 편집](mixed-run-body.md)의 별도 계약을 따른다. v1 요청과 보호 검사는 유지된다.

# 기존 본문 문단·native 목록의 제한 삽입/삭제

내용에 맞게 기존 보고서를 고칠 때 에이전트가 원본과 요청을 읽어 추가·삭제할 위치와 내용을 결정하고, `scripts/safe_body_structure.py`가 정확히 바인딩된 변경만 수행한다. 새 보고서의 의무 목차나 문체를 정하지 않는다. 이 도구 자체는 자연어의 의미나 중복 여부를 판단하지 않는다.

## 지원 범위

- 기존 section의 root-body plain 문단 추가·삭제. 일반 문단과 기존 native NUMBER/BULLET 항목의 기존 스타일을 복제한다.
- 삽입 템플릿은 한 run/한 t의 비어 있지 않은 plain 문단이다. 앵커와 삭제 대상은 plain 텍스트의 여러 run/글자 서식을 허용한다.
- 표·그림·캡션·상자·각주·머리말/꼬리말·책갈피·필드 등 control을 포함한 문단을 삭제하거나 템플릿으로 사용하지 않는다. 별도 control 문단 사이의 plain 영역은 선택할 수 있다.
- 새 문단 ID는 public `insert_paragraphs`가 생성하고 layout cache를 제거한다. 기존 문단은 public `remove`로 삭제한다. XML을 직접 쓰지 않는다.
- 기존 header 정의와 모든 비대상 package 구성원을 byte-exact로, 대상 section의 모든 유지 문단 subtree를 전체 대조한다. 기존 표를 재작성하거나 모든 빈 문단을 청소하지 않는다.

셀 내부/다른 story/구역 편집, 새로운 번호 정의, 목록 단계 변경, native OUTLINE, page/column break 문단의 삽입·삭제, 임의 복합 run 템플릿 복제는 지원하지 않는다. 다른 실행기의 BLOCK를 이 도구로 우회하지 않는다. 이 계약에 맞는 독립 편집 경로를 명시적으로 선택한다.

## 바인딩과 보호

`inspect`는 원본 SHA256과 root 문단별 part/index/id/전체 subtree SHA256/정확한 텍스트, heading type/group/level, plain/template 자격을 출력한다. index나 텍스트만으로 대상을 선택하지 않는다. 원본이 조금이라도 바뀌면 다시 inspect하고 새 요청을 만든다.

요청 schema는 `hwpx.body-structure.v1`이다. 최상위 키는 `schema`, `sourceSha256`, `editableReason`, `protectedSpans`, `operations`만 사용한다. `editableReason`에 사용자 요청의 변경 범위를 구체적으로 기록한다. 출력은 새 .hwpx와 새 `.body-receipt.json` 경로를 사용하며 원본을 덮어쓰지 않는다.

`protectedSpans`는 `{start: binding, end: binding}`의 동일 section 포함 범위 목록이다. 그 안의 plain 문단도 삭제할 수 없고 범위 내부에 끼워 넣을 수 없다. 보호 시작 앞/끝 뒤의 삽입은 가능하다. 보호해야 할 결재란·필수 표기·설명은 에이전트가 원본을 읽고 지정한다. 빈 배열을 허용하므로 지정 누락을 자동으로 발견해 준다고 주장하지 않는다.

operations는 다음 세 가지다.

```json
{"op":"delete","target":{"part":"Contents/section0.xml","index":12,"id":"...","sha256":"...","text":"..."}}
{"op":"insert_after","anchor":{"part":"...","index":0,"id":"...","sha256":"...","text":"..."},"template":{"part":"...","index":0,"id":"...","sha256":"...","text":"..."},"texts":["추가할 실제 내용"]}
{"op":"insert_before","anchor":{"part":"...","index":0,"id":"...","sha256":"...","text":"..."},"template":{"part":"...","index":0,"id":"...","sha256":"...","text":"..."},"texts":["추가할 실제 내용"]}
```

위 값은 설명용이다. 실제 binding 전체를 inspect에서 취한다. 삽입 anchor/template은 삭제 대상과 겹칠 수 없다. anchor와 template은 같은 section을 사용한다. 중복 삭제·동일 삽입 경계·줄바꿈/탭을 포함한 새 텍스트를 거부한다. 1~40 operations, 삽입 하나당 1~20 texts, 전체 변경 100문단까지 제한한다.

## native 번호의 부모 보존

번호는 문자열 접두어를 만들지 않고 원본 native heading 정의와 단계를 유지한다. 같은 group의 부모를 삭제하려면 뒤따르는 깊은 하위 항목도 명시적으로 삭제해야 한다. 기존 자식 앞에 동급 새 부모를 끼워 넣어 그 자식의 소속이 바뀌는 경우도 거부한다. 새 깊은 항목에는 남아 있는 바로 위 단계 부모가 있어야 한다.

이 검사는 native NUMBER의 원래 부모 identity를 비교한다. 일반 설명 문단의 의미상 소속이나 다른 group 사이의 관계는 에이전트가 판단해야 한다. 임의 번호 재시작/계층 재설계까지 지원하는 것으로 확대하지 않는다.

## 실행 및 완료

현재 PC의 installer가 확인한 Python과 skills 경로를 해석해 실행한다. 고정 사용자명/개발 PC 경로를 복사하지 않는다. pinned core 6.3.0와 lxml, 같은 scripts의 `safe_edit.py`, `namespace_literal_guard.py`가 필요하다. 기존 namespace literal 보존 경로만 사용하며 활성 2016 XML을 일반적으로 허용하지 않는다.

```powershell
python -X utf8 -B scripts/safe_body_structure.py inspect source.hwpx --output inspection.json
python -X utf8 -B scripts/safe_body_structure.py apply source.hwpx candidate.hwpx --request request.json --dry-run
python -X utf8 -B scripts/safe_body_structure.py apply source.hwpx candidate.hwpx --request request.json
```

dry-run은 public API로 임시 후보를 실제 만들어 모든 보존 검사를 수행하고 게시하지 않는다. 구조 영수증은 `PASS_STRUCTURE`, native는 `PENDING`이다. 완료로 표시하려면 exact candidate를 hwpx-windows-finalize의 prepare → 실제 한글 SaveAs/재열기/PDF → collect → 독립 보존 대조/전체 쪽 검토 → check 경로로 검증한다. 표나 그림이 뒤쪽으로 이동하는 정상 reflow와 개체/내용 손실을 구분한다. 두 자리 번호의 첫 텍스트와 이어지는 줄, 쪽을 넘긴 긴 문장, 표 전후 여백, 그림과 캡션 위치를 실제 출력으로 본다.

첫 writer→한글 저장의 정규화 문제 자체는 해결되지 않았다. 첫 strict 실패를 보존하고 독립 진단에서 전체 본문·활성 서식·control·표·개체·매체가 같음을 확인한 정확한 native 저장본으로 별도 재검증한다. 아무 차이나 정규화로 간주하거나 strict 기준을 약화하지 않는다. 보안 DLL·등록·권한·승인창 정책을 변경하지 않는다.

## 확인한 사례와 재현 자산

2026-10-04, 한글 2024 13.0.0.3903 / core 6.3.0: 세 개 큰 제목, 동급 항목 12개, 단계별 번호, 표 3개, 요약 상자, native 그림/캡션, 각주와 쪽 번호가 있는 합성 3쪽 보고서에서 세 변경을 확인했다.

1. 일반/동급/하위 문단 4개 삽입, 중복 설명/하위 항목 2개 삭제.
2. 특정 부모와 두 자식의 명시적 삭제, 다른 부모 앞 일반 설명 1개 추가.
3. 긴 하위 항목 8개 추가하여 1)~10), 다음 부모의 1)/2) 재시작, 긴 문장 쪽 넘김과 두 자리 번호 내어쓰기 확인.

원본·변경 3사례 모두 3쪽, 12쪽 전체 실제 검토와 strict complete. 그림과 캡션은 긴 사례에서 함께 3쪽으로 이동했다. 29개 회귀검사를 Python -O에서 통과했다. COM 생성과 보안 모듈 등록은 각각 true로 기록했고 설정 변경은 없다. 이 PC의 성공이 다른 PC의 설치 검증을 대신하지 않는다.

`assets/body-structure/`의 source.hwpx는 정확한 request 해시에 연결된 native 원본이다. 세 request, short-prompts.md, 세 최종 결과를 제공한다. 다른 파일로 바꾸거나 한번 다시 저장한 원본에 기존 request를 적용하지 않는다. 다른 PC는 기존 installer의 Python/core·한글 COM·검증된 보안 모듈 의존성을 먼저 점검하고 새 candidate에 대한 실제 한글 완료 검사를 수행한다. 가상 내용과 서식을 모든 보고서의 기본값으로 쓰지 않는다.

Windows Codex 샌드박스에서 Python TemporaryDirectory의 owner-only ACL 때문에 candidate 생성 전 접근 거부가 발생했다. 기존 권한은 수정하지 않고 출력 부모의 ACL을 상속하는 UUID 이름의 새 일반 임시 폴더를 사용하도록 보완했다. 정확히 생성한 파일과 빈 폴더만 지우며 recursive 정리나 chmod를 수행하지 않는다. 실제 한글/보안 모듈 오류와 구분한다.
