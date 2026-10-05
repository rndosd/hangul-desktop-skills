# 기존 저장본의 위아래 여백 검색 후보

사용자가 작은 자연 넘침을 여백으로 맞추길 요청한 경우에만 선택한다. 생성 영수증 기반 `auto_margin_fit.py`로 기존 저장본을 다시 생성하지 않는다. 이 후보는 저장본 자체의 기존 top/bottom만 같은 양만큼 줄인다.

지원은 한 구역·zero gutter·10표 이하의 보고서에서 실제2쪽/마지막1–3줄/이미지 없는 작은 넘침이다. 본문 p.pageBreak와 p.columnBreak뿐 아니라 사용 중인 paraPr.breakSetting.pageBreakBefore도 읽어 의도한 나눔을 제외한다. 위아래만 조절하므로 가로 여백·표 폭·열 너비·머리말/꼬리말 폭을 자동으로 바꾸지 않는다.

`native_vertical_fit_cli.py inspect source.hwpx --policy policy.json`은 binding과 격자를 읽는다. `run source.hwpx new-run --policy policy.json`은 명시한 사용자/호스트 환경에서 같은 후보 API로 native 실행한다. 개별 정적 편집은 `dry-run source.hwpx new.hwpx --request request.json`으로 확인한다. 현재 독립 CLI의 inspect/dry-run을 실제 실행했고 native run API는 프로젝트 harness에서 실행했다. 독립 CLI run 재실행까지 검증됐다고 주장하지 않는다.

정책 필드는 정확히 schema=`hwpx.native-vertical-fit.v1`, sourceSha256, minimumHwpunit, stepMilliMm, maxAttempts, maxOverflowLines, editableReason이다. 최소 여백은2835HWPUNIT(약10mm)이상, 단계250–1000milli-mm, 최대1–20후보, 꼬리1–3줄이다. 실제 시험은 minimumHwpunit=2835, stepMilliMm=500, maxAttempts=10, maxOverflowLines=3이었다. 기본 권고 여백을 모든 문서에서10mm로 바꾼다는 뜻이 아니다. 해당 작업 정책을 명시하고, 작은 감소부터 실측한다. 최소라는 말은 지정한 위아래 동일 감소 격자 내 첫 적합 후보만 뜻한다.

개별 편집은 기존 ID·전체 정의·내용·셀/병합/여백/테두리·개체·자산을 독립 snapshot으로 확인한다. 변경된 페이지 조판을 위한 paragraph lineSegArray만 명시적으로 재계산한다. native 단계는 활성 구조와 모든 헤더 정의, PDF 전후 픽셀을 별도로 대조한다. 원시 패키지·메타데이터 검사와 실제 모든 쪽 검토를 선택 상태와 분리한다.

선택은 `PENDING_VISUAL_REVIEW`이며 실사용 완료나 배포 합격이 아니다. `NO_FIT`이면 정한 하한과 후보 범위 안에서 맞지 않은 결과를 유지한다. 환경 차단이면 다음 사례/같은 호출을 자동 재시도하지 않는다. DLL·레지스트리·권한이나 접근 승인 정책을 변경하지 않는다. 거부 가드에서 COM 호출 자체를 금지한 대역을 사용한다.

HWP052: 원래 compact 간격 실패의 한 줄을15→12.5mm로1쪽 복구했다. 같은 저장본에 명시 문장을 추가한 실제 검색 재편집은10mm 하한 안에서4후보 모두2쪽으로 NO_FIT이다. 원래 auto-fit native baseline은20→19.5mm, 실제 검색 재편집은19.5→17mm로 맞췄다. 두 입력이 같은 보고서 계획의 다른 상태이므로 서로 다른 모든 양식의 검증으로 확대하지 않는다. 원래 새 문서 생성/영수증/재생성 경로의 전체 검증은 별도 남아 있다.

15개 native 후보의 전체 구조·정의는 정확하며 여백/캐시 밖 원시 차이는 content.hpf ModifiedDate 문자열뿐이었다. 이 차이는 그대로 보고하며 전체 바이트 동일 합격으로 바꾸지 않는다. compact 추가 문장 실패, 첫 거부 가드의 참조 쪽 나눔 누락과 native 충돌도 원래 기록으로 유지했다.51COM/모듈 성공 각각,2COM 전 차단,19native 금지 가드,39서로 다른 실제 출력쪽 검토가 근거다. 범용 설치 스킬 교체와 배포 완료는 아니다.
