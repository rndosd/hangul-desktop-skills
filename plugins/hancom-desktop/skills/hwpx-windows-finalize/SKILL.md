---
name: hwpx-windows-finalize
description: "Verify edited or created HWPX files in installed Hancom Hangul on Windows, including opening, print layout, and save/reopen checks when needed."
---

# Windows 한글 실제 검증

원본·후보를 덮어쓰지 않고 새 결과 경로와 영수증을 연결한다. 구조 검사·실제 열기·저장·시각 검수는 따로 판정한다. 전달 조건에 필요한 검사만 선택하고 같은 파일·환경의 유효한 증거는 재사용한다. 변경·새 실패·미확인 조건만 재검증하며 완료 후 종료한다. 일반 문서 검증을 개발용 전체 회귀시험·상시 개선으로 확대하지 않는다.

## 실행 순서

1. environment.json과 [PC 환경](references/desktop-environment.md)을 확인한다. 형제 hwpx/vendor와 지원 스크립트를 함께 사용한다.
2. 일반 Windows 맥락에서 `scripts/run_native_job.py`의 [실행 준비/호출](references/native-execution-readiness.md)을 따른다. COM 생성과 `RegisterModule('FilePathCheckDLL', 선택한 모듈 이름)` 성공을 구분하며 false이면 문서를 열지 않는다.
3. 열기/PDF는 OpenOnly, 필요한 저장·재열기 확인은 SaveAs를 선택한다. 저장했으면 저장본을 다시 열어 PDF를 출력한다. 정상 COM을 우선하고 실제 COM 차단 때만 UI 경로를 쓴다.
4. 저장·재열기가 필요한 복합 작성·편집은 [판정 기준](references/acceptance-policy.md#복합-문서-출력-완료-연결)의 `finalize_document.py run`으로 준비·native 실행·자료 수집을 연결한다. 실제 검토 후 `check`로 판정한다. 준비된 블록 조합은 [공통 compose](../hwpx/references/simple-entry.md#준비된-블록-조합)가 같은 native 작업 안에서 저장·재열기·PDF까지 수행하므로 해당 영수증과 정확한 출력 파일을 검토에 재사용한다. 의도적으로 내용을 추가한 결과를 첫 블록과의 무변경 비교에 넣지 않는다. 일반 열기 요청은 OpenOnly 경로를 유지한다.
5. [파일 보존 검사](references/native-file-roundtrip-audit.md)와 [공통 완료 기준](references/acceptance-policy.md#공통-완료-기준)에 따라 내용·서식·개체 및 PDF 전체 쪽의 가독성·배치를 확인한다. PDF 동등성·열기 성공·잘림 없음만으로 완료하지 않는다. 저장본의 재편집이 필요한 과제는 실제 저장본으로 시험한다.

## 실패·보안·판정

- Codex 패키지의 RegisterModule=false/HKCU 값만으로 등록 누락을 단정하지 않는다. [장애 처리](references/hancom-com-failures.md)에 따라 일반 Windows 사용자 맥락과 한 번 비교하고 성공한 맥락의 등록값은 다시 쓰지 않는다.
- 레지스트리·권한·실행 정책·DLL·승인 범위를 자동 변경하거나 승인창을 우회하지 않는다. 필요한 변경은 이유와 최소 조치를 먼저 알린다.
- timeout·결과 불명확이면 같은 쓰기를 반복하지 않고 영수증·출력·락·기록된 소유 프로세스를 확인한다. [소유 종료 확인](references/owned-exit-check.md)을 지키며 사용자 문서·프로세스는 임의 종료하지 않는다.
- PASS_COM/PASS_NATIVE/exit 0을 요청 내용·파일 보존·전체 시각 검수의 PASS로 바꾸지 않는다. FAIL/UNVERIFIED/ENVIRONMENT_BLOCKED를 구분한다.

## 필요한 기능만 추가

| 상황 | 참조 |
|---|---|
| 표 높이 저장 정규화 | [실제 측정 높이](references/native-measured-table-height.md) |
| 표/줄바꿈/쪽 넘김 | [레이아웃](references/layout-validation.md), [부분 지면 검사](references/report-layout-subset.md) |
| 내어쓰기 | [실제 내어쓰기 검수](../hwpx/references/hanging-indent-verification.md) |
| COM 제한 편집·병합 셀 위치 읽기 | [상세 도구 계약](references/detailed-workflows.md), [native 작성](references/native-writing.md) |
| 그림/캡션/개체 | [개체 배치](references/object-placement-validation.md) |
| 저장 후 미사용 서식 정의 | [명시적 보관](references/unused-definition-retention.md) |
| 차트/OLE 차이 | [판정 기준](references/acceptance-policy.md) |

간편 경로를 이유로 전문 도구의 지원 범위를 확대하지 않는다.
