---
name: hwpx-windows-finalize
description: "Verify edited or created HWPX files in installed Hancom Hangul on Windows, including opening, print layout, and save/reopen checks when needed."
---

# Windows 한글 실제 검증

구조 검사와 실제 한글 출력은 따로 판정한다. 원본·후보를 덮어쓰지 않고 결과별 신규 경로와 영수증을 연결한다.

현재 문서의 전달 조건에 필요한 검사만 선택한다. 같은 파일·환경의 유효한 증거는 재사용하고 변경·새 실패·미확인 조건이 있을 때 관련 검사를 다시 수행한다. 검증이 끝나면 종료한다. 일반 작업을 개발용 전체 회귀시험·상시 개선으로 확대하지 않는다.

## 기본 순서

1. environment.json과 [PC 환경](references/desktop-environment.md)을 확인한다. 후보는 형제 hwpx/vendor와 지원 스크립트 전체를 함께 사용한다.
2. 일반 Windows 실행 맥락에서 `scripts/run_native_job.py`의 [실행 준비/호출](references/native-execution-readiness.md)을 따른다. COM 생성 성공과 `RegisterModule('FilePathCheckDLL', 선택한 모듈 이름)` 성공을 구분한다. RegisterModule=false이면 문서를 열지 않는다.
3. OpenOnly는 열기/PDF가 필요한 때, SaveAs는 저장·재열기 확인이 필요한 때만 선택한다. 저장본을 다시 열어 PDF를 출력한다. 정상 COM을 우선하고 UI는 실제 COM 차단이 있을 때만 선택한다.
4. 복합 작성·편집 완료는 [완료 판정](references/acceptance-policy.md)의 `hancom_completion_gate.py prepare → COM → collect → 실제 검토 → check`로 연결한다. 일반 열기만 필요한 요청에 불필요한 저장을 추가하지 않는다.
5. [파일 보존 검사](references/native-file-roundtrip-audit.md)를 수행한다. PDF가 같아도 활성 서식/전체 정의/개체/내용 차이를 별도로 기록한다. 저장본의 같은 기능 재편집이 필요한 과제는 실제 저장본을 입력으로 시험한다.
6. PDF 전체 쪽에서 누락·겹침·잘림·고립 제목·표와 글/그림/캡션 간격을 확인한다. 한글 쪽수와 모아찍기 인쇄면 수를 구분한다. [내어쓰기](../hwpx/references/hanging-indent-verification.md)처럼 필요한 기능 검수만 추가한다.

## 실패와 보안

- Codex 패키지 맥락의 RegisterModule=false/HKCU 값만으로 설치 등록 누락을 단정하지 않는다. [장애 처리](references/hancom-com-failures.md)에 따라 일반 Windows 사용자 맥락과 한 번 비교한다. 성공한 맥락에서는 등록값을 다시 쓰지 않는다.
- 레지스트리·권한·실행 정책·DLL·승인 범위를 자동 변경하거나 승인창을 우회하지 않는다. 필요한 변경은 이유와 최소 조치를 먼저 알린다.
- timeout/결과 불명확이면 같은 쓰기를 즉시 반복하지 않는다. 영수증·출력·락·기록된 소유 프로세스를 먼저 확인한다. [소유 종료 확인](references/owned-exit-check.md)을 유지하며 사용자 한글 문서/프로세스를 임의로 종료하지 않는다.
- PASS_COM/PASS_NATIVE/exit 0을 요청 내용·파일 보존·전체 시각 검수의 PASS로 바꾸지 않는다. FAIL/UNVERIFIED/ENVIRONMENT_BLOCKED를 구분한다.

## 기능별 필요 참조

| 상황 | 참조 |
|---|---|
| 표 높이 저장 정규화 | [실제 측정 높이](references/native-measured-table-height.md) |
| 표/줄바꿈/쪽 넘김 | [레이아웃](references/layout-validation.md), [부분 지면 검사](references/report-layout-subset.md) |
| COM 제한 편집·병합 셀 위치 읽기 | [기존 상세 경로](references/detailed-workflows.md), [native 작성](references/native-writing.md) |
| 그림/캡션/개체 | [개체 배치](references/object-placement-validation.md) |
| 저장 후 미사용 서식 정의 | [명시적 보관](references/unused-definition-retention.md) |
| 차트/OLE 차이 | [판정 기준](references/acceptance-policy.md) |

기존 명령과 제한 지원 범위는 [상세 안내](references/detailed-workflows.md)에 보존한다. 전문 도구의 범위를 간편 경로 때문에 확대하지 않는다.
