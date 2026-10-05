# 0.1.0-beta.1 배포 검사 — 2026-10-05

이 공개 묶음 자체를 대상으로 확인했습니다. 과거 개발 기록의 합격 횟수를 새 검사로 세지 않습니다.

| 검사 | 결과 |
|---|---|
| 전체 파일/전송 manifest, private 경로·자격증명 패턴, DLL/EXE/PC 설정 제외 | PASS |
| Python 구문, 스킬 frontmatter/진입점 링크, marketplace 경로, 라이선스 보존 | PASS |
| Windows PowerShell 파일 구문 24개 | PASS |
| 현재 PC 설정 쌍 경로 선택/누락·혼합 거부 6개 | PASS |
| 현재 PC SFNT 글꼴 메타데이터·다른 해시·family/PANOSE/경계 거부 9개 | PASS |
| 공통 작성·표·문구 도구, 사실/입력/덮어쓰기/원자성 가드 16개 | PASS |
| 단순·혼합·중첩 셀 치환 및 비대상 변형 미발행 3개 | PASS |
| 격리 CODEX_HOME 설치·재설치 백업·캐시 doctor·손상 manifest 차단 등 8개 | PASS |
| 새 PC 실제 COM 생성·RegisterModule·문서 출력 | UNVERIFIED |
| 공식 ZIP/uv/Python 신규 네트워크 다운로드와 모듈 등록 | 이번 배포 검사에서 NOT_CALLED |

설치 시험은 한글과 공백이 있는 신규 경로 및 기존 Python 3.12.14에서 수행했습니다. 두 스킬에 동일한 새 PC 설정을 생성하고 보안 선택 없이 nativeStatus는 blocked_security_module인 것을 확인했습니다. `-CheckOnly`와 보안 모듈 동의 없는 호출은 대상 디렉터리도 만들지 않았습니다. 레지스트리·실행 정책·ACL·사용자 설치 스킬은 변경하지 않았습니다. 설치/회귀 PASS가 새 PC의 실제 한글 출력 성공을 증명하지 않습니다.

첫 샌드박스 회귀는 Python TemporaryDirectory의 Windows 접근 거부로 6개가 실행 오류였습니다. 경로 선택 테스트를 작업 공간의 새 디렉터리로 좁히고, 기존 합성 문서 회귀는 승인된 일반 사용자 실행 맥락에서 확인했습니다. 이 최초 오류는 기능 FAIL과 구분합니다.

최초 설치 검사는 샌드박스와 승인된 일반 사용자 맥락 양쪽에서 Python 자식 Windows PowerShell의 Get-FileHash 누락으로 실패했습니다. 직접 Windows PowerShell 호출에는 명령이 존재했습니다. Python 자식이 다른 버전 PowerShell의 모듈 경로를 먼저 상속하는 차이를 관찰했고, 설치 해시를 기존 .NET SHA256 helper로 계산하게 바꾼 후 격리 설치가 통과했습니다. 전역 PSModulePath나 실행 정책 변경은 하지 않았습니다. uv ZIP 해제도 .NET으로 처리하며 실행할 uv.exe를 고정 원본 ZIP 항목의 해시와 대조합니다. 다운로드 경로 자체의 이번 신규 실행 검증은 미완료입니다.

공개 자동 검사로 재현할 수 있는 범위와 native 검증이 필요한 범위는 [지원 제한](known-limits.md)에 나눠 기록했습니다.

최초 [GitHub Actions 실행](https://github.com/rndosd/hangul-desktop-skills/actions/runs/37327071985)은 Windows Server 2025의 다른 Malgun 파일 해시 때문에 새 문서 생성 1개가 실패했습니다. 패키지 검증·6개 경로 검사·나머지 공통 검사 15개는 통과했고 이후 설치 단계는 실행되지 않았습니다. 이 실패 기록을 유지합니다. 현재 PC 글꼴의 family/PANOSE와 SFNT 경계를 검사해 메타데이터를 읽는 방식으로 수정했습니다. 이전 해시와 다른 글꼴은 native 검증 미완료로 표시하며 한글 실제 출력 가드를 제거하지 않습니다. 수정 후 로컬에서는 34개 회귀가 통과했습니다. 별도 Windows 환경의 후속 CI 결과는 GitHub Actions에서 확인할 수 있습니다.

두 번째 [GitHub Actions 실행](https://github.com/rndosd/hangul-desktop-skills/actions/runs/37327936095)에서는 회귀 34개가 모두 통과했으나 Windows PowerShell 5.1 구문 단계에서 UTF-8 BOM 없는 한국어 launcher를 ANSI로 읽어 실패했습니다. 해당 파일에 BOM을 추가하고 공개 검사에서 비ASCII PowerShell의 BOM을 요구합니다. 구문 검사를 생략하지 않으며 후속 CI로 격리 설치도 확인합니다.
