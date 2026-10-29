# Quit 뒤 소유 프로세스 종료 확인

verify_hwpx_with_hancom.ps1은 worker의 owned/quit/owner가 모두 확인됐을 때만 Hancom.OwnedExit.ps1을 호출한다. PID와 process instance는 다르므로 handle을 확보한 뒤 같은 instance의 HasExited를 확인한다. 이미 종료됐거나 metadata 읽기 도중 종료가 확인되면 identityMatched=null이며 종료 관찰 경로를 별도로 기록한다. 살아 있는 name/path/startTicks 불일치는 차단한다. 이미 확인된 불일치는 뒤의 종료로 지우지 않는다. 실제 일치하는 살아 있는 instance만 최대10초 기다리며 시간이 지나도 종료하지 않는다.

정상 Quit 직후 handle을 얻지 못해도 PID 조회에는 잠깐 남을 수 있다. 이 경로에서만 기존 LimitMs(최대10초) 안에 최대50ms 간격으로 해당 PID의 부재를 다시 조회한다. 최초 객체와 모든 fresh 객체에서 읽을 수 있는 startTicks/name/path 불일치는 즉시 차단한다. handle 없는 metadata는 불일치를 거부하는 근거로만 쓰며 소유권 일치로 인정하지 않는다. PID 부재가 확인된 경우만 `PID_ABSENT_BEFORE_HANDLE`, `exited=true`, `identityMatched=null`, `waited=false`로 기록하며 `absenceChecks`에 재조회 수를 남긴다. PID가 끝까지 존재하거나 조회 오류면 차단하고 `exited=null`을 유지한다. 불명확한 프로세스의 WaitForExit/종료 신호는 호출하지 않는다.

worker의 Quit 성공, 전체 Hwp 잔여0, sourceUnchanged, lock, RegisterModule-before-Open 및 신규 출력 조건은 계속 적용한다. helper에는 종료 신호/강제종료/보안 설정 쓰기가 없다. 기존 worker timeout 처리는 이 변경의 범위가 아니다. Invoke-HancomCell/RowSplit/NativeHeight 등 다른 controller를 수정한 것으로 해석하지 않는다.

필수 지원 파일 누락은 run_native_job.dependencies에서 COM 전에 거부한다. environment.json의 기존 검토된 모듈을 계속 쓰며 DLL 재등록이나 접근 승인 정책 변경은 하지 않는다. Test-HancomOwnedExit.ps1은 실제 원래 controller block을 in-memory 프로세스 fixture로 실행해 기존 오류와 정상 대조를 함께 검증한다. fixture는 특정 과거 실행 순서를 증명하지 않으며 실제 한글 시험과 구분한다.

`Test-HancomOwnedExitRace.ps1`은 설치 전 helper를 `BaselineHelper`로 받아 handle 취득 실패 뒤 PID가 한 번 더 관찰되는 순서를 재현한다. 수정본의 지연 부재, PID 재사용/불일치, 접근 오류, 관찰 제한시간, 기존 handle 기반 경로를 in-memory fixture로 확인한다. OS 프로세스나 COM을 시작하지 않으며 실제 native 재검증을 대신하지 않는다.

근거: HWP069의 intent-contract/ownership-fixtures/summary/visual-review. .NET Process.HasExited와 handle의 종료 정보 유지: https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.hasexited
