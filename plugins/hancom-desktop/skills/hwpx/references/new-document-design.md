# 빈 문서 설계·생성

이 통합판의 집계 표와 번호·항목 들여쓰기는 [v2 규칙](new-document-v2.md)을 우선 적용한다. 수동 `indent_left_mm` 예시는 사용자 명시 서식의 예외 또는 과거 호환 경로다.

번호·계층·여백·자간·표 서식까지 설계할 때 [서식 설계 보완](new-document-formatting.md)을 함께 읽는다.

이 경로는 사용자가 기존 파일 없이 새 계획서·안내문·보고서 등 작성을 요청할 때 사용한다. 정해진 양식명에서 템플릿을 고르지 않는다. 대화에서 읽는 사람, 목적, 전달할 내용, 필요한 행동을 파악한 후 적절한 구성과 서식을 작성 에이전트가 설계한다. 실행기는 설계를 HWPX로 만들고 검증하며 자연어를 독립적으로 해석하는 모델은 아니다.

내용의 관계와 표현 선택을 기존 양식 편집에도 공유할 때는 [공통 구조 설계](content-structure.md)를 따른다. 원자료·관계·선택 이유를 보존하고 지원되는 공통 계획을 이 작성 경로로 컴파일한다. 복잡한 새 문서의 자유로운 설계는 기존 경로를 유지한다.

## 대화에서 설계까지

1. 사용자 요청을 `brief.json`에 보존한다. `purpose`, `audience`, `kind`, `facts`, `requirements`, `unknowns`, `format`, `allow_draft`를 사용한다. 이미 받은 정보는 다시 묻지 않는다. 종류를 명시하지 않아도 목적에서 합리적으로 추론할 수 있으면 그 선택을 기록한다.
2. 중요한 정보만 한 번에 질문한다. 문서 목적 자체, 필수 내용·근거, 안내문의 실제 일시·장소·신청 방법처럼 결과를 바꾸는 내용이 부족하면 질문한다. 명시적으로 초안을 허용하면 `[확인 필요: 일시]` 같은 표시로 작성한다. 실제 정보처럼 보이는 임의 날짜·금액·이름을 채우지 않는다. 보고서의 실적은 결과 근거가 없으면 성과로 쓰지 않는다. 서식 취향·담당자처럼 생략 가능한 사항은 반복 질문하지 않는다.
3. `intake` 결과를 활용하되 질문 목록을 기계적으로 모두 사용자에게 보여 주지 않는다. 계획서의 목표·실행·자원·평가, 안내문의 핵심 안내·행동·문의, 보고서의 범위·근거·결과·한계·후속 조치는 검토 관점이며 필수 고정 목차가 아니다. 실제 요청에 필요한 항목만 골라 자유로운 블록 순서로 설계한다. 다른 종류도 같은 원리로 설계할 수 있다.
4. `design.json`의 `plan.blocks`에 heading/paragraph/bullets/table/page_break를 배치한다. 비교·일정·담당 등 동일 속성의 반복 자료에는 표, 설명은 문단, 병렬 안내는 항목을 선택한다. 짧은 안내문은 제목 아래 몇 문단으로 끝내도 된다. 본문 전체를 표로 감싸지 않는다. 표 열 너비는 내용 길이와 중요도로 정하고 `reason`에 표를 쓴 목적을 남긴다. 긴 서술은 셀에 몰아넣지 않는다.
5. 제목의 계층은 순서대로 최대 3단계이며 같은 수준에서 일관성을 유지한다. 대제목 15pt·중제목 13pt·소제목 12pt를 기본으로 하되 복잡도에 맞춰 단계 수를 줄인다. 명확한 부록·독립 배포 부분만 명시적 쪽 나눔을 쓰고 이유를 남긴다. 제목은 다음 문단과 함께 붙이는 속성을 적용한다. 줄 수나 쪽 수를 ZIP 구조만으로 확정하지 않는다.
6. 기본 서식은 A4 세로·사방 20mm·맑은 고딕 본문 11pt·줄 간격 160%·제목 20pt이다. 사용자 `brief.format`이 작성 에이전트의 `design.format`보다 우선한다. 사용자 지정 폰트를 가용 폰트와 대조하고 없으면 대체 여부를 확인한다. 지정이 안 된 속성만 기본값을 사용한다. 이 버전의 실행기에서 지원하지 않는 속성은 오류로 반환하며 조용히 생략하지 않는다. 쪽 수 제한은 native 렌더 없이 준수했다고 말하지 않는다.
7. 모든 요구에 고유 id를 주고 `coverage`에 대응 블록 id를 기록한다. 필수 사실의 정확한 문구는 `facts[id].text`로 보존한다. `claims`는 실제 사실로 서술한 주장 전부와 근거 id를 연결하며 현재 실행기는 정확한 원문 부분 문자열만 허용한다. 제안·미정과 사실을 명확히 구분한다. 숫자 검사는 제공 사실에 없는 숫자를 차단하지만 같은 숫자를 다른 의미로 쓰는 오류나 비수치 환각까지 판단하지 못하므로 작성 에이전트가 모든 주장·날짜·금액·이름을 별도 대조한다.

## 실행

설치된 hwpx Python 환경을 사용한다. 설치·DLL 등록·보안 설정 변경은 이 경로에 포함되지 않는다.

```powershell
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$pythonExe = (Get-Content -LiteralPath (Join-Path $codexRoot 'skills/hwpx/environment.json') -Raw -Encoding UTF8 | ConvertFrom-Json).pythonPath
if (!$pythonExe) { throw '이 PC의 Python 환경이 아직 준비되지 않았습니다.' }
& $pythonExe scripts/create_new_document.py intake --brief brief.json
& $pythonExe scripts/create_new_document.py validate --brief brief.json --design design.json
& $pythonExe scripts/create_new_document.py create --brief brief.json --design design.json --output draft.hwpx
& $pythonExe scripts/create_new_document.py audit --brief brief.json --design design.json --output draft.hwpx
```

`facts`는 `{ "fact-id": { "text": "사용자가 제공한 정확한 문구", "required": true } }`이다. `requirements`는 `{ "id": "goal", "description": "요구 내용", "must_include": ["필수 문구"] }` 배열이다. `unknowns`는 `{ "key": "일시", "question": "행사 일시는 언제인가요?", "critical": true }` 배열이다. 합성 예시는 `examples/new-document/`에 있다.

사용자가 가상 샘플을 요청한 경우에만 작성 에이전트가 합성 원자료를 설계할 수 있다. 해당 facts에는 `origin: agent_authored_synthetic_fixture`, `not_user_provided: true`를 남기고 문서 상단에 모든 수치·기간·사례가 가상이며 사용자 제공 사실이 아니라고 표시한다. 실제 결과·예산 작성 요청을 가상 샘플 요청으로 바꾸면 안 된다. 충분한 본문과 표, 산식 검증을 가진 보강 예시는 `examples/new-document-realistic/`에 있다. 해당 예시의 길이 목표는 실제 native 쪽수 확인 결과가 아니다.

`design`은 `schema: hwpx.new_document.v1`, `plan: {schemaVersion: hwpx.document_plan.v1, title, subtitle?, blocks}`, `coverage: {요구id: [블록id]}`, `claims: [{text, evidence: [fact-id]}]`, `format`, `review`로 구성한다. 각 블록에 `id`, 선택적으로 `evidence`를 둔다. 목록의 `ordered: true`는 표시 번호를 생성한다. 이 번호는 사실이 아니라 문서 구조이다. 블록의 직접 텍스트 안에 넣은 숫자는 사실 검사를 받는다.

## 완료 판정

내용 누락·불필요한 내용 추가·지정 서식 불이행·파일 손상은 필수 탈락 조건이다. 목적별 필요한 항목, 위계, 적절한 복잡도와 비조작을 `review`에 대조 결과로 남긴다. 종합 점수로 탈락을 상쇄하지 않는다. `must_include`는 누락 방지 보조이며 의미상의 요구 충족 여부는 에이전트가 검토한다.

생성 후 package/document 검증, core 재열기, 모든 텍스트의 순서·중복 개수, 표 셀과 병합, 스타일 참조·제목 크기·제목 다음 문단 보호·여백을 검사한다. 기존 출력은 덮어쓰지 않는다. 통과 상태 `PASS_STRUCTURE`는 native 한글 재열기나 시각적 완성을 뜻하지 않는다. 서식의 모든 속성을 독립 XML 검사하는 것은 아니므로 native 렌더 및 서식 확인이 남는다.

가능한 환경에서는 동료 스킬 `hwpx-windows-finalize`의 COM Open/SaveAs/재열기/PDF와 전체 쪽 검토를 이어간다. 정책 차단을 만나면 그 단계에서 멈추고 우회·설정 변경 없이 미검증으로 보고한다. 이 통합판의 검증 래퍼는 내부 ExecutionPolicy Bypass를 제거했다. native PDF 라벨 검사가 pypdf 부재로 막히면 설치하지 않고 검사별 미검증으로 남긴다. 학생 실문서를 테스트하지 않는다.

## 구현 근거

- [한컴 HWPX 구조](https://tech.hancom.com/hwpxformat/): ZIP/XML과 shape table 참조. 생성은 설치 core public API로, 검사만 XML readback으로 한다.
- [한컴 다음 문단과 함께](https://help.hancom.com/hoffice/multi/ko_kr/hwp/format/paragraph/paragraph%28next%29.htm): 제목이 쪽 끝에 홀로 남는 것을 줄이는 속성 선택의 근거.
- [문단 모양 확장](https://help.hancom.com/hoffice/multi/ko_kr/hwp/format/paragraph/paragraph_expanded.htm): 문단 보호와 강제 쪽 나눔의 의미.
- [공식 개발자 포럼](https://forum.developer.hancom.com/t/hwpx-owpml-model/1974): 모델 파싱만으로 한글의 실제 페이지 배치를 재현할 수 없다는 한계.
- [공식 Automation 가이드](https://developer.hancom.com/hwpautomation): COM 매뉴얼과 보안 모듈의 존재. 본 작업에서는 다운로드·등록·설정 변경을 하지 않는다.
