# 실제 한글 측정값으로 선택 표 높이를 준비하는 제한 경로

제목 간격·소계 행 묶기 편집 후 PDF는 같지만 직접 `hp:sz.height`가 저장에서 달라지는
경우에만 선택한다. 일반 저장에 자동 적용하지 않는다. 현재 한글 13.0.0.3903,
python-hwpx 6.3.0, 한 section 안의 전체 표 1~2개 중 명시한 표 ID 1~2개가 범위다.
대상은 루트 문단의 보호되지 않은 floating CELL/TABLE, 기존 절대 너비·높이이며
마지막 행 첫 셀까지 고유 문구로 검증하는 경로가 최대 20회 이동이어야 한다.
중첩·다수 표·다른 빌드는 미검증으로 중단한다.

두 sibling 스킬의 `environment.json`이 같은 현재 PC 설정이어야 한다. 도구는 선택한
Python·한글·검토된 DLL·정책 파일과 해시를 읽는다. 이전 PC의 모듈 이름을 가정하거나
등록값을 쓰지 않는다. `--context`는 호출자가 승인받은 실행 맥락의 기록이며 권한을
부여하는 인자가 아니다. 호출 실패 시 자동 권한 상승·다른 맥락 재시도는 하지 않는다.

```powershell
python -X utf8 -B scripts/native_height_cli.py inspect edited.hwpx --table-id 1446756043 --output new-inspect.json
python -X utf8 -B scripts/native_height_cli.py run edited.hwpx --table-id 1446756043 --work new-height-run --context host-approved
```

`inspect`는 읽기 전용이다. `run`은 새 작업 폴더에 원본·도구·PC 의존성을 고정하고
저장 전에 정확한 표와 모든 경유 셀을 실제 한글에서 확인한다. TablePropertyDialog의
동적/typed API를 검증된 셀과 표 선택 위치에서 읽는다. 네 수치 읽기가 모두 같고
Height=LayoutHeight, 너비·바깥 위아래 여백이 원본과 같아야 한다. GetDefault 성공은
관찰된 bool true 또는 정확한 정수 1만 허용한다. COM 생성과 모듈 등록은 별도 기록한다.

측정된 높이가 다를 때만 public section.element/mark_dirty/save_to_path로 그 표의
직접 높이를 쓴다. 비대상 패키지 snapshot은 정확히 같아야 한다. 같으면 원본의
바이트 사본을 쓰며 캐시를 지우지 않는다. PDF에서 추정한 높이·고정 상수·저장 후
추적 보정·비교기의 높이 예외를 사용하지 않는다.

원본 사전 PDF → 준비본 사전 PDF → 저장/재열기 PDF → 반복 저장/재열기 PDF의 정확한
픽셀, 원본 문구 누락, 활성 구조와 사용되지 않는 정의까지 포함한 전체 정의를 따로
검사한다. `file-audit.json`에는 원본 바이트/멤버/XML/ZIP 차이도 남긴다. 활성+전체 정의
PASS를 파일 바이트 동일로 표현하지 않는다. 다른 변화는 BLOCKED_NO_RETRY이며
진단 사본과 영수증을 보존한다. 기존 작업 폴더를 재사용하지 않는다.

exit 0 / READY_FOR_VISUAL_REVIEW는 실제 페이지 검토 전 상태다. 모든 필요한 페이지를
검토하고, 요청 내용·위치·수치·비대상 보존을 확인한다. 같은 기능으로 저장본을 다시
편집한 시험은 별도 실행해야 한다. 현재 사례를 임의 표나 전체 편집 기능의 완료로
확대하지 않는다. 이 경로는 DLL 설치·등록이나 파일 접근 승인 자동화를 수행하지 않는다.
