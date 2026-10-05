# 출처와 수정 범위

기반: [airmang/hwpx-plugins](https://github.com/airmang/hwpx-plugins) 및 [python-hwpx](https://github.com/airmang/python-hwpx), Apache-2.0. 기존 LICENSE/NOTICE 및 vendor 라이선스를 보존합니다. 이 저장소의 Windows 통합과 편집/검증 보조 도구는 커뮤니티 파생 작업이며 upstream의 공식 릴리스가 아닙니다.

기준 후보는 HWP071-SIMPLE-ENTRY-20261005의 sibling 스킬입니다. 이후 실사용 지침을 반영하고 배포 과정에서 다음을 수정했습니다.

- native launcher가 캐시에서 현재 PC의 sibling 설정 쌍을 읽도록 추가. 로컬 설정이 일부만 있으면 전역 값과 섞지 않고 차단.
- 절대 PC 경로/개인 양식 링크 제거, 실사용 기본값을 짧은 진입점에 반영.
- 설치 대상은 hwpx/hwpx-windows-finalize 두 스킬. 기본 설치와 공식 모듈 전역 허용 선택을 분리.
- 관리 경로의 reparse point 조상 확인, 의존성 버전 및 PDF 준비 상태 정확화.
- Codex Python 자식 Windows PowerShell의 다른 버전 모듈 경로 상속에서 Get-FileHash가 누락되는 경우를 재현. 설치 해시는 기존 .NET SHA256 helper로 계산하고 uv ZIP도 .NET으로 해제하여 전역 모듈/실행 정책 변경을 피함.
- 별도 marketplace/manifest, 공개 검사와 설치/백업 검증 추가.
- 최초 GitHub Windows Server 2025 검사에서 source-PC Malgun 전체 해시 고정으로 새 문서 생성 차단을 재현. 현재 PC SFNT의 family·PANOSE·테이블 경계 검증으로 메타데이터를 읽고, 다른 해시는 native 미검증으로 기록. 글꼴 설치나 가드 전체 해제 없이 이식성 수정.

vendor는 python-hwpx **6.3.0**의 수정 사본입니다. `skills/hwpx/vendor/PATCH.md`에 XML namespace/QName 정규화 변경을 표시했습니다. 이 버전과 python-hwpx-automation **7.0.3**, lxml **6.1.3**, PyMuPDF **1.28.2**를 기준으로 고정합니다. upstream 최신 버전으로 자동 업그레이드하지 않습니다. `source-inventory.json`은 수정 전 코드 해시이며 배포 무결성은 패키지의 `PAYLOAD-SHA256.json`으로 확인합니다. 두 문서는 서로 다른 용도입니다.

한컴 한글과 공식 Automation 예제 DLL은 포함하지 않습니다. DLL은 사용자가 명시적으로 선택할 때 [한컴 공식 저장소](https://github.com/hancom-io/devcenter-archive/tree/main/hwp-automation)에서 다운로드합니다. 저장소의 Apache-2.0 라이선스가 한컴 프로그램/DLL에 적용된다는 뜻은 아닙니다.

Python bootstrap은 [Astral uv 0.12.22](https://github.com/astral-sh/uv/releases/tag/0.12.22)의 x64 Windows 파일을 고정 해시로 받습니다. uv/Python을 저장소에 재배포하지 않습니다. uv는 MIT/Apache-2.0, Python은 PSF License로 제공됩니다. pip 설치 패키지의 라이선스는 각 배포판의 메타데이터를 따릅니다. [PyMuPDF는 AGPL 또는 상용 라이선스](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)이므로 그 라이선스 조건도 확인해야 합니다. 코드 공개 라이선스가 외부 프로그램의 라이선스를 대체하지 않습니다.

`assets/complex-structure/source.hwpx`와 `assets/mixed-runs/source.hwpx`는 이 개발 과정에서 만든 가상 회귀 문서입니다. 실제 업무 정보가 아니며 문서 내용도 검사 입력입니다. 다른 공개 보고서 원본·사진·로고는 배포하지 않습니다.

두 번째 GitHub 검사에서 영어 Windows PowerShell 5.1이 한국어 launcher의 BOM 없는 UTF-8을 ANSI로 읽는 차이를 재현했습니다. Invoke-HangulTask.ps1의 본문은 유지하고 UTF-8 BOM만 추가했으며, 공개 패키지 검사에 비ASCII PowerShell 인코딩 검사를 추가했습니다.
