---
name: hancom-setup
description: Windows 한글 스킬의 PC별 의존성 설치·진단과 사용자가 선택한 보안 모듈 구성을 안내한다.
---

# 한글 데스크톱 설치

이 SKILL.md의 실제 경로에서 두 단계 위를 플러그인 루트로 정한다. `Install-HangulSkills.ps1`이 있으면 그 패키지를 사용한다. 전역 설치본에서 실행 중이면 현재 CODEX_HOME/skills의 environment.json에 기록된 bundleRoot를 사용한다. 다른 PC의 경로를 추정하지 않는다.

1. 먼저 패키지의 `Install-HangulSkills.ps1 -CheckOnly`를 읽기 전용으로 실행한다. Python 3.12/고정 의존성/한글 설치/보안 선택 상태를 분리한다. 설정 준비는 COM 성공 증거가 아니다.
2. 설치 요청이면 해당 패키지 설치기를 실행한다. Python이 없으면 `Bootstrap-Python.ps1 -CodexRoot 현재경로`로 관리 런타임을 준비하고 PythonPath를 전달한다. 기존 스킬은 설치기가 백업한다. 전역 PATH·실행 정책·권한을 변경하지 않는다.
3. 기본으로 DLL을 선택/등록하지 않는다. 다른 사용자의 환경·승인 기록을 복사하지 않는다. 이미 검토된 같은 PC의 선택은 설치기의 재검증을 따른다.
4. 사용자가 한컴 공식 예제의 **모든 파일 경로 허용** 범위를 이해하고 해당 PC 등록을 선택한 경우만 `Setup-OfficialModule.ps1 -AcceptGlobalFileAccess`를 사용한다. 전용 폴더 제한이 아니며 Windows 권한은 적용된다. 한글은 사용자가 저장하고 정상 종료해야 한다. 이 패키지는 x86 공식 DLL만 검증하며 x64/출처 불명 DLL은 대체하지 않는다.
5. 설치 후 같은 PC의 설정으로 `hwpx-windows-finalize/scripts/check_hancom_com.ps1`에서 COM 생성과 RegisterModule 반환값을 따로 확인한다. 실제 문서 작업은 원본 사본으로 열기/편집/필요한 저장·재열기/PDF/검수까지 별도 수행한다. 실행 맥락 오류이면 일반 사용자 맥락과 한 번 비교하고 설정 변경이나 승인창 자동 클릭으로 우회하지 않는다.

웹 플러그인 설치만으로 로컬 Windows COM이 실행되지는 않는다. 정상 검증이 끝나면 종료하고 사용자의 문서 작업으로 돌아간다.
