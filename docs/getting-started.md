# 설치부터 첫 문서까지

처음 사용하는 Windows 사용자를 위한 설명서입니다. 먼저 ZIP으로 PC 환경과 두 스킬을 준비한 다음 새 대화에서 사용합니다. Codex 플러그인으로 관리하는 방법은 뒤의 선택 항목입니다. 이 문서는 현재 GitHub main의 안내이며, 공개 베타의 확인 범위는 [지원 제한](known-limits.md)에 기록돼 있습니다.

## 1. 준비할 것

| 준비물 | 설명 |
|---|---|
| Windows x64 PC | 실제 한글 검증은 Windows에서 실행합니다. |
| AI의 로컬 실행 환경 | 기본 안내는 Codex 기준입니다. 사용자 PC의 파일과 PowerShell을 실행할 수 있어야 합니다. Claude Code 시험 방법은 아래 별도 항목을 참고하세요. |
| 설치·활성화된 한컴 한글 | 프로그램과 라이선스는 직접 준비합니다. 공식 모듈 자동 설치는 현재 x86 한글용입니다. Windows의 비트수와 한글 프로그램의 비트수는 별개입니다. |
| 인터넷 | 처음 필요한 Python·패키지 다운로드에 사용합니다. 이미 준비된 Python으로 설치하는 방법도 있습니다. |
| 원본 HWPX 또는 작성 자료 | 기존 양식을 쓰려면 HWPX를, 새 문서를 쓰려면 메모나 자료를 준비합니다. |

Python 3.12와 의존성은 설치기가 필요한 경우 전용 환경에 준비합니다. 시스템 Python을 먼저 바꾸거나 관리자 권한으로 시작할 필요는 없습니다. 새 보고서 작성에는 Windows의 맑은 고딕 글꼴이 필요합니다.

웹 대화에 ZIP을 첨부하는 것만으로 이 PC의 한글이 연결되지는 않습니다. 실제 출력까지 사용하려면 로컬 Windows 실행 환경이 필요합니다.

## 2. ZIP 내려받고 PowerShell 열기

1. [베타 릴리스](https://github.com/rndosd/hangul-desktop-skills/releases/tag/v0.1.0-beta.1)를 엽니다.
2. **Assets**에서 `hangul-desktop-skills-0.1.0-beta.1.zip`을 내려받습니다. 설치용으로는 이 첨부 파일을 선택하세요.
3. 파일 탐색기에서 ZIP을 **모두 압축 풀기**로 풉니다. ZIP 내부에서 바로 실행하지 않습니다.
4. 압축을 푼 폴더 안에서 **Install.ps1이 보이는 폴더**까지 들어갑니다. 버전에 따라 바깥 폴더가 한 겹 더 있을 수 있습니다.
5. 그 폴더의 탐색기 주소 표시줄에 `powershell`을 입력하고 Enter를 누릅니다. 일반 Windows PowerShell 창이 열립니다.

위치가 맞는지 아래 명령으로 확인합니다.

```powershell
Test-Path -LiteralPath .\Install.ps1
```

`True`면 다음 단계로 진행합니다. `False`면 Install.ps1이 있는 폴더로 이동하세요. 아래 명령의 `PS ...>` 같은 프롬프트 표시는 입력하지 않습니다.

## 3. 변경 없는 진단부터 실행

```powershell
.\Install.ps1 -CheckOnly
```

이 명령은 준비 상태를 읽습니다. 다운로드·설치·DLL 등록·COM 생성은 하지 않습니다. 처음 설치하는 PC에서 아래 상태가 나와도 곧바로 고장이라는 뜻은 아닙니다.

| 출력 항목 | 읽는 방법 |
|---|---|
| `coreStatus: ready` | 필요한 Python과 고정 패키지가 확인됐습니다. 실제 한글 출력 성공은 아직 확인하지 않았습니다. |
| `coreStatus: python_3_12_missing` | 사용할 Python 3.12가 없습니다. 다음 기본 설치에서 준비할 수 있습니다. |
| `coreStatus: dependencies_missing` | Python은 있으나 필요한 패키지가 부족합니다. 다음 설치에서 준비합니다. |
| `hancom: null` | 설치기가 한글 COM 서버 정보를 찾지 못했습니다. 한글 설치·활성화 상태를 확인하세요. |
| `nativeStatus: blocked_security_module` | 검토한 보안 모듈이 선택되지 않아 실제 한글 자동화는 차단됩니다. 기본 설치 직후에는 정상적으로 나올 수 있습니다. |
| `nativeStatus: configured_not_runtime_verified` | 현재 PC의 선택 설정을 확인했습니다. COM·RegisterModule·문서 작업은 별도 시험해야 합니다. |

출력에서 Python 경로·한글 버전·비트수도 확인할 수 있습니다. 다른 PC에서 받은 environment.json을 복사해 준비 상태를 만드는 방식은 사용하지 않습니다.

## 4. 기본 설치

같은 PowerShell 창에서 실행합니다.

```powershell
.\Install.ps1
```

필요한 Python·패키지를 준비하고 `hwpx`, `hwpx-windows-finalize` 두 스킬을 설치합니다. 기본 위치는 현재 사용자 `.codex` 폴더이며, `CODEX_HOME`을 지정했다면 그 위치를 사용합니다. 기존 같은 이름의 스킬은 백업하고, 끝에 **Skills installed. Backup:**과 백업 경로를 출력합니다. JSON의 `coreStatus`도 확인하세요. 설치 파일 복사 성공과 Python 준비 성공은 별개입니다.

기본 설치는 새 DLL을 등록하지 않습니다. 따라서 “Native COM document work remains blocked” 안내는 보안 모듈을 아직 선택하지 않았다는 뜻입니다. HWPX 내용 작성·정적 검사 준비와 실제 한글 자동화 준비를 구분하세요.

설치 후 Codex에서 **새 대화**를 시작합니다. 스킬이 보이지 않으면 앱을 정상 종료·다시 열고 새 대화를 시작한 뒤 아래처럼 요청하세요.

> 설치한 hwpx와 hwpx-windows-finalize 스킬을 사용해 이 PC의 준비 상태를 확인해줘. COM 생성과 보안 모듈 등록 성공은 따로 알려줘. 설정은 바꾸지 마.

## 5. 실제 한글 자동화를 사용할지 선택

COM은 이 PC의 한글 프로그램을 호출하는 Windows 연결입니다. 보안 DLL은 그 연결의 파일 접근 검사에 쓰입니다. DLL이 한글 프로그램이나 편집 엔진을 대신하는 것은 아닙니다.

공식 Automation 예제의 소스는 **모든 요청 파일 경로를 허용**합니다. 전용 작업 폴더만 허용하는 정책이 아닙니다. Windows 사용자 권한은 계속 적용됩니다. [출처·허용 범위·해시·등록값](security-module.md)을 읽고 이 PC에서 그 정책을 사용하기로 선택한 경우에만 다음을 실행합니다.

1. 열려 있는 한글 문서를 직접 저장하고 한글을 정상 종료합니다.
2. ZIP을 풀어둔 Install.ps1 폴더의 PowerShell에서 아래 명령을 실행합니다.

```powershell
.\Install.ps1 -AcceptGlobalFileAccess
```

공식 원본을 다운로드해 고정 SHA256와 x86 여부를 대조하고, 현재 사용자 HKCU에 해당 모듈의 경로를 등록합니다. 기존 등록값은 영수증으로 백업합니다. 다른 PC에서도 같은 절차로 그 PC의 경로·정책 선택을 준비해야 합니다. 다른 사용자의 승인 기록은 복사하지 않습니다.

현재 고정 DLL은 x86입니다. 한글이 x64이거나 파일 해시가 바뀌면 중단합니다. 출처 불명 DLL을 찾아 대신 넣지 마세요. 회사에서 지정한 보안 모듈을 쓰는 경우에는 [검토된 기존 모듈 선택](security-module.md#기관의-검토된-기존-모듈)을 따릅니다.

## 6. 설치 성공과 자동화 성공을 구분하기

한글을 저장·정상 종료한 상태에서, 같은 ZIP 폴더의 PowerShell로 다음 검사를 실행할 수 있습니다. 이 검사는 한글 COM 객체를 생성·종료하지만 문서를 열거나 레지스트리를 바꾸지는 않습니다. 한글이 실행 중이면 충돌을 피하기 위해 중단합니다.

```powershell
.\plugins\hancom-desktop\skills\hwpx-windows-finalize\scripts\check_hancom_com.ps1
```

| 결과 | 의미 |
|---|---|
| `comCreated: false` | 한글 COM 생성에 실패했습니다. 설치·실행 환경 오류를 확인해야 합니다. |
| `comCreated: true`, `registerModuleCalled: false` | COM은 생성됐지만 선택한 모듈의 사전 검사를 통과하지 못했습니다. DLL 등록 성공으로 보고하지 않습니다. |
| `registerModuleCalled: true`, `securityModuleRegistered: false` | 선택 이름으로 RegisterModule을 실제 호출했으나 실패했습니다. 문서를 열지 않습니다. |
| `status: PASS_COM_AND_SECURITY` | COM 생성과 모듈 연결이 모두 성공했습니다. 문서 내용·저장·재열기·PDF·지면 검수는 아직 별도입니다. |

마지막으로 가상 내용의 테스트 문서를 별도 폴더에 만들어 다음을 요청하세요.

> 한글 테스트 문서를 새로 만들어 열기 → 문구 수정 → 새 파일 저장 → 저장본 재열기 → PDF 출력까지 확인해줘. 내용과 표가 유지되는지 보고, 실제 파일과 검증 결과를 줘. 설정은 바꾸지 마.

COM·모듈 성공만으로 이 문서 시험이 성공한 것은 아닙니다. 반대로 파일 접근 승인창이나 실패가 발생하면 발생 단계와 원인을 확인합니다. 자동 클릭, 실행 정책·ACL 변경, 미확인 DLL 교체로 해결하지 않습니다.

## 7. 두 가지 문서 요청 방법

### 기존 양식을 사용할 때

원본 HWPX와 새 내용을 첨부하거나 로컬 파일 경로를 알려줍니다. 예를 들어:

> 이 보고서 양식으로 직원 AI 교육 결과보고서를 써줘. 제목·본문·표·목차를 새 내용에 맞게 바꾸고 기존 글꼴과 배치는 유지해줘. 참가자는 30명, 교육은 2회로 가정하고 가상 사례임을 표시해줘. 원본은 남기고 새 HWPX와 PDF를 줘.

여러 기관의 양식을 분석하도록 설계돼 있으며 특정 양식 3개만 쓰는 도구가 아닙니다. 서술형·개조식·혼합형도 요청할 수 있습니다. 기존 틀에 내용이 맞지 않으면 지원 범위 안의 행 추가·삭제·크기/흐름 조정을 선택할 수 있습니다. 복잡한 중첩·개체 등 지원 경계와 실제 조판 검수가 남는 경우 결과에 표시합니다.

### 빈 문서에서 새로 만들 때

양식 없이 메모나 자료를 주고 목적·분량·필요한 표현을 알려줍니다. 예를 들어:

> 이 회의 메모로 팀 결과보고서를 3쪽 안팎의 한글 문서로 만들어줘. 결정 사항, 담당자·기한을 정리하고 비교가 필요한 내용은 표로 보여줘. 자료에 없는 값은 미정으로 표시해줘. HWPX와 PDF를 줘.

목차·내용·표 수를 고정하지 않습니다. 내용에 맞는 구성과 번호 계층·간격을 선택합니다. 지정 쪽 수는 실제 한글 출력으로 확인하며 무조건 달성한다고 약속하지 않습니다.

최종 전달에서 요청 내용 반영, 비대상 내용·서식 보존, 실제 한글/PDF 검수 여부를 확인하세요. `PASS_STRUCTURE`는 파일 구조 단계의 성공이며 실제 화면 성공과 다릅니다.

## Codex 플러그인으로 관리하려면

위 PC 설치를 마친 뒤, 플러그인 목록으로 관리하려는 사용자의 선택 경로입니다. ZIP의 두 스킬 직접 설치로 사용한다면 이 단계는 필수가 아닙니다.

Codex CLI가 있는 PowerShell에서 실행합니다.

```powershell
codex plugin marketplace add rndosd/hangul-desktop-skills
```

앱을 다시 열고 플러그인 목록에서 추가한 소스를 선택해 `hancom-desktop`을 설치한 뒤 새 대화를 시작합니다. 앱 버전에 따라 화면 이름은 다를 수 있습니다. 명령을 찾지 못하면 CLI 설치를 전제로 하지 않는 위 ZIP 경로를 사용하세요. 소스 추가는 PC의 Python·한글·보안 DLL 준비를 대신하지 않습니다.

[OpenAI 공식 패키징·마켓플레이스 안내](https://developers.openai.com/plugins/build/plugins)를 기준으로 한 절차입니다. 공개 디렉터리 등록·심사를 마친 제품은 아닙니다.

## Claude Code에서 사용하려면

스킬은 `SKILL.md`, scripts, references를 묶는 형식이며 [Claude Code도 Agent Skills와 개인 스킬 폴더를 지원](https://code.claude.com/docs/en/skills)합니다. **현재 이 배포본의 Claude 모델 실제 작성·수정·COM 작업은 미검증입니다.** Codex용 마켓플레이스 명령을 Claude에 그대로 입력하지 않습니다.

시험할 때는 위 Windows PC 설치를 먼저 마치고, [Windows에서 로컬로 실행하는 Claude Code](https://code.claude.com/docs/en/setup)를 사용합니다. ZIP의 `plugins/hancom-desktop/skills/hwpx`와 `hwpx-windows-finalize` 폴더 전체를 개인 `.claude/skills` 아래에 같은 이름의 형제 폴더로 놓습니다. SKILL.md만 복사하면 vendor 코드와 참조가 빠집니다. 기존 같은 이름의 스킬이 있다면 먼저 백업하고 덮어쓰지 마세요.

이 도구들은 현재 PC의 `CODEX_HOME/skills` 설정을 읽습니다. 기본값은 사용자 `.codex/skills`이며 이 설치기가 만든 공유 설정입니다. Claude에서 사용해도 같은 Windows 사용자·CODEX_HOME의 설정을 사용해야 합니다. Codex 앱 계정은 이 Python/PowerShell 도구의 실행 의존성이 아닙니다.

새 Claude Code 세션에서 `/hwpx`로 준비 상태부터 확인하고 작은 합성 문서로 시험합니다. 파일·프로세스 실행 권한과 한글·보안 모듈은 별도로 필요합니다. Claude 웹/API/클라우드/Cowork에 스킬 ZIP을 올리는 방법의 Windows COM 연결은 이 배포에서 지원·검증하지 않습니다.

## 문제가 생겼을 때

| 증상 | 먼저 확인할 것 |
|---|---|
| Install.ps1을 찾지 못함 | 압축을 풀었는지, 현재 폴더에 Install.ps1이 있는지 확인합니다. |
| “스크립트를 실행할 수 없습니다” | 조직의 PowerShell 정책과 파일 신뢰 절차를 확인합니다. 전역 실행 정책을 바꾸거나 Bypass로 우회하지 않습니다. |
| Package hash mismatch | 파일을 수정한 묶음인지 확인하고 원본 릴리스 ZIP을 새 폴더에 풉니다. 손상 검사를 끄지 않습니다. |
| Python·다운로드 실패 | 오류의 다운로드 주소·네트워크/프록시·정책을 확인합니다. 기존 Python 3.12로 설치하는 옵션은 [README](../README.md#다른-pc에-설치)에 있습니다. |
| 설치했는데 스킬이 안 보임 | 새 세션인지, 설치기의 codexRoot와 앱/CLI의 CODEX_HOME이 같은지 확인합니다. |
| 한글 설치 정보 없음·COM 생성 실패 | 실제 한글 실행·활성화 여부와 한글 COM 설치 상태를 확인합니다. 반복해서 DLL을 등록하지 않습니다. |
| RegisterModule 실패·파일 접근 승인창 | 선택 이름·등록 경로·DLL 해시·비트수·정책 기록과 실행 맥락을 비교합니다. [보안 모듈 안내](security-module.md)를 참고하세요. |
| PROCESS_CONFLICT | 열려 있는 한글 문서를 직접 저장하고 정상 종료한 뒤 한 번 다시 확인합니다. 사용자 프로세스를 강제 종료하지 않습니다. |
| XML 검사 PASS인데 화면이 밀림 | 최종 HWPX를 실제 한글에서 출력해 해당 페이지를 확인합니다. 글꼴·내용 길이·표/개체 배치 문제를 정적 성공과 구분합니다. |

문의를 남길 때 Windows/한글 버전·비트수, 실행한 명령, 실패 단계와 오류 메시지를 적어주세요. 개인 문서·PC 승인 기록·전체 환경 설정은 공개 이슈에 올리지 말고 가능한 가상 재현 문서를 사용하세요. 사용 범위와 아직 확인하지 못한 기능은 [지원 제한](known-limits.md), 되돌리기는 [등록 복구 안내](security-module.md)에 있습니다.
