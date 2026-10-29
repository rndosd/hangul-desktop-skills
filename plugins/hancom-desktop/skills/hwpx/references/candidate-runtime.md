# 공용 편집 코드와 실행 환경

유지 기준 코드는 이 스킬의 `vendor/hwpx`와 `vendor/hwpx_automation`이다. 공통 CLI와 MCP 어댑터 모두 `candidate_runtime.activate()`로 이 코드를 먼저 선택한다. Python별 site-packages의 동명 편집 코드를 섞지 않으며 이미 다른 코드가 로드됐으면 조용히 바꾸지 않고 실패한다. 설치 패키지 버전 문자열이 같아도 실제 수정 코드가 같다는 뜻은 아니다.

일반 작업은 `Invoke-HangulTask.ps1`의 명령과 `tool`을 사용한다. 새 보조 스크립트가 필요한 경우에만 이 scripts를 경로에 넣고 hwpx/hwpx_automation을 import하기 전에 activate한다. 별도 Python 탐색이나 전역 환경변수 변경은 필요 없다.

MCP는 통신 SDK가 있는 기존 Python에서 `scripts/hwpx_mcp.py --transport stdio ...`로 시작한다. CLI는 environment.json의 Python을 유지한다. 두 환경에서 같은 공용 코드의 경로와 해시가 선택돼야 한다. 설치·변경 검증 때 CLI doctor.runtime과 MCP `--runtime-info`를 비교하며 일반 문서마다 반복하지 않는다. 실행 중 서버에 수정 코드가 자동으로 다시 로드된다고 가정하지 않는다.

vendor/licenses 및 원본 메타데이터를 보존한다. 기본 core의 namespace 보존 수정과 문자/문단 서식 수정, automation의 대상 결합/일괄 처리 수정은 같은 유지 코드에서 관리한다. 실제 출력 검증 범위는 현재 SKILL.md와 형제 finalize의 요청별 기준을 따르며 모든 국소 수정에 전체 개발 회귀를 추가하지 않는다.
