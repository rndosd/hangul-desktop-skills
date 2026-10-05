# 보안 모듈 선택과 최소 변경

처음 설치한다면 [사용자 설명서](getting-started.md)를 먼저 읽으세요. 이 문서는 DLL 출처·허용 범위·등록값·복구 방법을 자세히 설명합니다. COM은 설치된 한글을 호출하는 연결이고, 보안 모듈은 그 연결에서 사용하는 파일 접근 검사 구성 요소입니다. DLL 등록값이 존재하는 것, COM 객체가 만들어지는 것, 실행 중 `RegisterModule`이 true를 반환하는 것은 서로 다른 상태입니다.

`CodexHancomFilePathChecker`는 이전 PC에서 사용하던 별칭이며 필수 DLL 이름이 아닙니다. 모든 native worker는 현재 PC 설정의 이름으로 `RegisterModule('FilePathCheckDLL', moduleName)`을 호출합니다. COM 객체 생성 성공과 이 호출의 반환값은 별도로 기록합니다. 반환값이 false이면 문서를 열지 않습니다.

## 기본 설치

`Install.ps1`은 DLL을 등록하지 않습니다. 검토·선택되지 않은 모듈이면 native 작업은 차단하고 순수 HWPX 작업 준비 상태와 구분합니다. 정상 기존 선택을 재검증하는 것은 새 레지스트리 등록이 아닙니다. 승인창 조작이나 보안 검사 제거로 우회하지 않습니다.

## 공식 예제 선택

[한컴 공식 devcenter-archive](https://github.com/hancom-io/devcenter-archive/tree/main/hwp-automation)의 `보안모듈(Automation).zip`만 사용합니다.

| 항목 | 고정 값 |
|---|---|
| DLL | `FilePathCheckerModuleExample.dll` |
| DLL PE | x86 `0x014C` |
| 레지스트리 | 현재 사용자 HKCU, Registry32, `Software\HNC\HwpAutomation\Modules` |
| REG_SZ 이름 | `FilePathCheckerModuleExample` |
| REG_SZ 값 | 현재 PC의 검증한 DLL 절대 경로 |
| 호출 인자 | `'FilePathCheckDLL', 'FilePathCheckerModuleExample'` |
| ZIP SHA256 | `5d87292efafd7311cba6d35e4b416ac8bfa78608a64dde1656c8cb827b051bd8` |
| DLL SHA256 | `9ac5b97c47ac8aed1e8bca27a3eef39411361d8f68c262509f0c40a8f9d21bb6` |

동봉 소스의 `IsAccessiblePath`는 바로 TRUE를 반환합니다. 허용 범위는 전역 파일 경로이며 Windows 권한을 넘어서는 권한은 부여하지 않습니다. 사용자별 명시적 선택이 필요합니다. x64 한글용 동일 검증 바이너리는 준비하지 않았습니다. 대체 DLL을 자동으로 찾거나 설치하지 않습니다.

`Setup-OfficialModule.ps1 -AcceptGlobalFileAccess`는 한글 실행 중이면 중단합니다. 원본 다운로드 후 ZIP/DLL 해시 및 아키텍처를 확인하고 위 값 하나를 등록합니다. 기존 값/종류를 영수증으로 백업하고 뒤이어 스킬 설치가 실패하면 기존 값으로 복구합니다. worker는 실행할 때 등록 경로, DLL·정책 기록 해시, 비활성 상태, 한글/DLL 아키텍처를 다시 확인합니다.

등록 되돌리기: 출력된 `registration-*.json` 경로로 아래 명령을 먼저 읽기 전용으로 확인합니다. 한글은 저장 후 정상 종료해야 합니다.

```powershell
.\plugins\hancom-desktop\Restore-ModuleRegistration.ps1 -ReceiptPath '실제 영수증 경로'
```

실제로 복구하기로 선택하면 같은 명령에 `-Apply`를 추가합니다. 현재 등록값이 설치 당시 값과 다르면 복구하지 않습니다. DLL/런타임 파일의 자동 삭제나 다른 등록값 변경은 하지 않습니다.

## 기관의 검토된 기존 모듈

패키지의 `Install-HangulSkills.ps1`에 `-SecurityModuleName`, `-SecurityDllSha256`, `-SecurityPolicyPath`, `-ConfirmReviewedSecurityModule`을 함께 전달합니다. 이미 REG_SZ로 등록된 모듈만 선택합니다. 이 경로는 레지스트리를 쓰지 않습니다. 접근 허용 범위가 확인되지 않은 DLL은 선택하지 마세요.

## 실행 맥락의 차이

패키지/샌드박스에서 COM 또는 등록이 실패하면 일반 Windows 사용자 맥락과 한 번 비교합니다. 실제 성공 맥락에서는 등록을 다시 쓰지 않습니다. 같은 오류를 반복하거나 실행 정책·ACL을 변경하지 않습니다. 설정 준비, COM 생성, RegisterModule, 문서 열기/편집/저장/재열기/PDF, 정상 종료는 서로 다른 단계입니다.
