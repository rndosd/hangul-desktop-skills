# 실행 경로와 전문 기능

일반 작성·편집은 `Invoke-HangulTask.ps1`을 진입점으로 쓴다. 기존 기능은 아래처럼 연결하며 같은 편집을 MCP/로컬 사이에서 다시 선택하지 않는다. 도구별 지원 범위와 보존 검사는 그대로 적용한다.

## 실행 경로 선택

| 요청 | 공통 실행 |
|---|---|
| 원본 연결·재사용 양식 선택 | `source` 또는 기존 `tool select_document_block.py`. 같은 원본의 분석과 선택 사본 재사용 |
| 본문·표의 여러 문구 | `inspect → text-plan → text`. 필요한 역할별 서식은 같은 `text --layout` 호출에 포함 |
| 빈 셀 채움·지정 run·본문/표의 복합 구조 편집 | bounded 조회의 현재 revision과 canonical path → `batch --request`. 서식 연결도 `batch --layout`으로 같은 실행에 포함 |
| 역할별 글꼴·정렬·빈 문단·행 높이만 수정 | `layout` |
| 행 추가/삭제·국소 표 속성 | `table` 또는 `tool`로 기존 제한 편집 도구 호출 |
| 준비된 블록 조합·최종 출력 | `compose` 한 번. 이미 생성한 저장본·PDF·영수증 재사용 |
| 조합 없는 문서의 실제 출력 | 형제 finalize의 기존 OpenOnly/SaveAs 경로 |
| 전문 양식·메일머지·시험·직인·변경추적 등 | 아래 전문 기능 색인에서 필요한 기존 API만 선택 |

본문 한 곳의 단순 수정은 `replace`를 유지한다. 원본 활용 작업의 내용 구성·서식 역할은 [원본 기반 작성](source-template-reuse.md), 명령 계약은 [공통 도구](simple-entry.md)에 둔다. 기능마다 별도 시작·검토 절차를 만들지 않는다.

공통 CLI와 MCP는 `vendor/hwpx` 및 `vendor/hwpx_automation`의 같은 유지 코드를 쓴다. MCP는 `scripts/hwpx_mcp.py`가 먼저 공용 코드를 선택하고 통신 어댑터를 시작한다. 통신 의존성 때문에 Python 환경은 다를 수 있지만 편집 구현은 같다. `doctor.runtime`과 어댑터 `--runtime-info`의 core/automation 경로·코드 해시로 설치를 확인한다. 일반 문서마다 두 경로를 검사하지 않는다. 이미 실행 중인 구형 MCP는 재연결 전까지 새 설정이 적용됐다고 보지 않는다.

MCP의 bounded 구조 조회는 같은 원본 revision으로 공통 batch에 이어 쓸 수 있다. 전문 API도 이 공용 엔진에서 실행하지만 기능별 검증 범위까지 동일하다고 주장하지 않는다. 지원 밖 연산이면 필요한 공식 한글 기능이나 다른 지원 연산을 검토한다. 해시 불일치·보존 실패·환경/소유권 오류는 다른 경로로 우회하지 않는다.

## 케이스 → 경로 라우팅 표

전체 기능은 [전문 기능·API 색인](tool-catalog.md)에 보존한다. 일반 작성 때 이 전체 목록을 읽거나 그 안의 옛 MCP 호출 예를 별도 기본 경로로 선택할 필요는 없다.

## 참조 인덱스

[전체 참조 인덱스](tool-catalog.md#참조-인덱스)에서 필요한 전문 기능만 연다.
