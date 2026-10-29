# 한글 자동화 장애 처리

## 원인 분리

COM 미등록, 시작 실패, 보안/모달 대화상자, 시간 초과는 자동화 장애일 수 있다.
손상 경고나 내용·패키지 오류 등 근거 없이 문서를 복구하거나 재작성하지 않는다.
한글 설치·설정 변경이나 보안 경고 우회는 사용자 승인 없이 하지 않는다.

## 제한된 재시도

Codex 셸에서 모듈 등록값이 보이거나 보이지 않는 것만으로 실제 등록 상태를 판정하지 않는다.
이 PC에서는 MSIX 레지스트리 가상화 때문에 셸의 HKCU와 실제 Hwp.exe가 읽는 일반 사용자
영역이 달랐다. 권위 있는 사전검사는 실제 HwpObject에서 문서를 열기 전에 수행한
환경 설정에서 검토한 모듈 이름으로 호출한 `RegisterModule('FilePathCheckDLL', moduleName)`의 반환값이다. 미구성 상태에서는 호출하지 않는다.
각 COM worker는 이를 한 번 호출하고 false면 문서를 열지 않은 채 중단한다.

Codex 패키지 컨텍스트의 RegisterModule=false와 일반 Windows 사용자 컨텍스트의 true가
동시에 재현되면 설정 누락이 아니라 실행 컨텍스트 차이다. false 결과만 보고 재등록하지 말고,
실제 문서 COM 작업을 true가 확인된 일반 사용자 컨텍스트에서 실행한다. 제한 권한 임시 작업을
사용했다면 정확한 작업 하나만 만들고 완료 후 제거하며, 기존 사용자 Hwp 프로세스는 종료하지 않는다.

RegisterModule이 false라면 실제 Hwp.exe의 RegQueryValue를 확인한다. 승인된 전용 모듈을
일반 Windows 사용자 환경에서 등록한 뒤 RegisterModule=true로 확인할 수 있다.
등록·재등록은 사용자 영역 설정 변경이므로 명시적 승인 없이 자동 복구하지 않는다.
전역 가상화나 보안 설정을 끄지 않는다.
이전 PC의 보안 DLL/설치 설명은 원본 ZIP에 포함되지 않았다. 현재 선택·진단은 [PC별 환경](desktop-environment.md)을 따른다. 이름만 보고 공식 예제나 다른 DLL로 대체하지 않는다.

Quit 직후 새 HwpObject 생성은 RPC_E_DISCONNECTED를 일으킬 수 있다.
문서 재열기는 같은 객체에서 Clear(1) 후 Open으로 수행하고 마지막에 Quit한다.

같은 원인은 최초 시도와 원인에 근거한 재시도 1회까지만 한다.
정상 진행 중인 작업은 도구의 상태·시간 제한 계약으로 기다린다.
자동화가 막히면 사용 가능한 computer-use 스킬의 native GUI 검증으로 전환하거나,
사용자에게 필요한 최소 확인을 요청한다. GUI 입력 충돌도 반복되면 조작을 멈춘다.

문서 손상이 확인된 경우에만 원본을 보존한 복구 후보를 한 번 만든다.
그 후보도 실패하면 오류와 필요한 다음 조치를 보고한다.

## 저장·프로세스 안전

저장 실패 시 후보를 유지한다. 부분 출력은 검증 전 최종본으로 제시하지 않는다.
새 창을 연 뒤에는 파일명과 창 식별자를 다시 확인한다.
사용자 한글 프로세스를 종료하지 않는다. 일반 `verify_hwpx_with_hancom.ps1` controller는 timeout 때 취소 표식을 만들고 최대 5초간 worker의 정상 종료를 기다린다. worker는 다음 단계에서 취소를 확인하고 finally의 Clear(1)과 Quit을 수행한다. 동기 COM 호출이 대화상자를 기다리는 동안에는 취소 표식을 읽을 수 없다. 이 경우 프로세스를 강제 종료하지 않으며 영수증의 worker PID, owner, 마지막 stage, 취소 표식과 부분 출력을 보존한다. 다른 전문 controller에 같은 동작이 적용됐다고 가정하지 않는다.

PDF를 요청하지 않아도 진행 기록은 영수증 옆 `.progress.jsonl`에 남는다. PDF를 요청하면 기존 PDF 옆 기록 위치를 유지한다. 각 행은 누적 시간과 직전 단계 이후 시간, 당시 완료 상태를 담는다. timeout 영수증의 `inFlightOutcome=UNKNOWN_DO_NOT_RETRY`는 진행 중 호출의 결과를 확인해야 한다는 뜻이다. 마지막 완전한 행이 없는 항목은 null로 남긴다. 원본 hash나 산출물 관찰이 실패해도 `observationErrors`를 포함한 차단 영수증을 남긴다. 같은 쓰기를 반복하지 않는다.

controller의 직렬화 잠금 외에 worker는 COM 시작 전부터 정상 정리가 끝날 때까지 별도 `Local\CodexHancomAutomationWorker` mutex를 보유한다. timeout 뒤 controller가 반환해도 살아 있는 worker가 새 worker의 COM 시작을 막는다. 취소된 worker가 늦게 시작하면 `com-start` 단계의 취소 검사로 COM 생성 전에 멈춘다.

검색 확인창이 원인이면 computer-use로 이번 소유 창을 확인하고 취소한다. `RepeatFind` 반복 호출은 [매회 옵션 초기화 예시](native-writing.md#com-반복-찾기)를 따른다. 파일 접근·보안 승인창은 이 검색 확인창과 구분한다.

worker가 이미 종료했는데 자신의 Hwp만 남은 경우에는 `scripts/Recover-HancomOwnedInstance.ps1`로 기존 Running Object Table 객체를 정상 종료할 수 있다. 일반 사용자 맥락의 ROT 조회로 실제 모니커를 확인한 뒤 진행 기록, 예상 문서 경로, 모니커, 새 로그 경로를 전달한다. 스크립트는 새 COM 객체를 만들지 않는다. PID·시작시각·실행경로·HWND와 열린 문서 한 개의 경로가 모두 일치할 때만 Clear(1)과 Quit을 호출한다. 문서가 추가됐거나 다른 문서이면 종료하지 않는다.

```powershell
& scripts/Recover-HancomOwnedInstance.ps1 -ProgressPath candidate.pdf.progress.jsonl -ExpectedDocumentPath candidate.hwpx -Moniker '!HwpObject.130.1' -LogPath new-owned-recovery.jsonl
```

모니커는 예시를 그대로 쓰지 않고 해당 실행에서 관찰한 값을 사용한다. 스크립트는 진행 기록의 worker가 아직 살아 있으면 Bind 전에 거부한다. worker 항목이 없는 과거 기록은 controller에서 확인한 `-WorkerProcessId`와 `-WorkerStartTicks`를 전달해야 한다. 정상 복구도 동기 COM 대기가 생길 수 있으므로 실행 도구의 세션 ID와 단계 로그를 유지한다. 로그의 `exit-observed-True`와 PID 부재 또는 일치한 instance의 종료를 확인한 뒤 작업을 이어간다. Bind·문서 경로 확인·Clear·Quit에서 대기하거나 실패하면 반복하지 않고 소유 창의 GUI 상태를 확인한다.


## 차트 재작성 시험에서 확인한 중단의 구분

PROCESS_CONFLICT는 COM 생성 전에 existing Hwp가 발견된 상태다. 파일 열기 실패나 RegisterModule=false로 보고하지 않는다. 파일 작성/정적 검사는 가능한 범위에서 먼저 하고 native 검증은 해당 프로세스가 종료된 뒤 수행한다. COM 객체 여러 개를 만들었다는 이유로 별도 프로세스/문서 소유권이 보장된다고 가정하지 않는다. 한글2024의 공유 프로세스 사례가 공식 보고돼 있으므로 현재 가드는 유지하고 사용자의 프로세스를 자동 종료하지 않는다. owner pid/startTicks/path 검증과 finally Quit/remaining 경고도 유지한다.

완성된 파일을 확인만 할 때는 기본 OpenOnly/PDF 경로를 선택한다. 한글 재저장이 필요한 작업에는 SaveAs와 기존 보존 검사를 사용한다. OLE 파일 해시가 달라지면 최신 ChartML, 구형 Contents, 표시용 OlePres를 구분해 읽기 검사한다. HWP007 두 사례에서 embedded OOXMLChartContents는 같았지만 Contents는 달랐고 한 사례의 OlePres도 달랐다. 따라서 변경 전체를 시각 메타데이터로 분류하거나 OLE를 무조건 제외하지 않는다. 원본 실패와 구형 표현의 미검증 상태를 유지한다.

공식 공유 프로세스 사례: https://forum.developer.hancom.com/t/pid/1577 (2024년 답변이며 현 빌드의 재현 확증과는 구분).

내부 OLE 차이만 남고 사용자가 실무 사용을 우선한 경우는 [실무 차트 전달 기준](acceptance-policy.md#실무-차트-전달-기준)을 적용한다. 확인된 파일의 생성·전달을 이어가며 차이는 별도 경고로 남긴다. 이 경우 원인이 바뀌지 않은 반복 저장, OLE의 재작성/제거, 보안 DLL 재설치를 시도하지 않는다.

설치와 실행 준비를 구분하고 controller 시작/COM 생성/모듈 등록/문서 단계의 실패를 진단할 때는 [네이티브 실행 준비](native-execution-readiness.md)와 읽기 전용 분류기를 사용한다. 일반 사용자 backend 자동 구성은 아직 구현되지 않았다.
