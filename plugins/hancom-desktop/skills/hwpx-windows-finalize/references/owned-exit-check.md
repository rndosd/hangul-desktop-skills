# Quit 뒤 소유 프로세스 종료 확인

verify_hwpx_with_hancom.ps1은 worker의 owned/quit/owner가 모두 확인됐을 때만 Hancom.OwnedExit.ps1을 호출한다. PID와 process instance는 다르므로 handle을 확보한 뒤 같은 instance의 HasExited를 확인한다. 이미 종료됐거나 metadata 읽기 도중 종료가 확인되면 identityMatched=null이며 종료 관찰 경로를 별도로 기록한다. 살아 있는 name/path/startTicks 불일치는 차단한다. 이미 확인된 불일치는 뒤의 종료로 지우지 않는다. handle 확보 전 종료된 경우 fresh PID 조회1회로 부재가 확인될 때만 종료로 관찰한다. PID가 있거나 조회/종료 확인 오류면 차단한다. 실제 일치하는 살아 있는 instance만 최대10초 기다리며 시간이 지나도 종료하지 않는다.

worker의 Quit 성공, 전체 Hwp 잔여0, sourceUnchanged, lock, RegisterModule-before-Open 및 신규 출력 조건은 계속 적용한다. helper에는 종료 신호/강제종료/보안 설정 쓰기가 없다. 기존 worker timeout 처리는 이 변경의 범위가 아니다. Invoke-HancomCell/RowSplit/NativeHeight 등 다른 controller를 수정한 것으로 해석하지 않는다.

필수 지원 파일 누락은 run_native_job.dependencies에서 COM 전에 거부한다. environment.json의 기존 검토된 모듈을 계속 쓰며 DLL 재등록이나 접근 승인 정책 변경은 하지 않는다. Test-HancomOwnedExit.ps1은 실제 원래 controller block을 in-memory 프로세스 fixture로 실행해 기존 오류와 정상 대조를 함께 검증한다. fixture는 특정 과거 실행 순서를 증명하지 않으며 실제 한글 시험과 구분한다.

근거: HWP069의 intent-contract/ownership-fixtures/summary/visual-review. .NET Process.HasExited와 handle의 종료 정보 유지: https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.hasexited
