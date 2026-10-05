# 기존 설명 문단의 내어쓰기

라벨·문구·글자 서식을 보존하면서 다음 줄을 **라벨 뒤 실제 설명 시작점**에 맞추는 선택 기능이다. 모든 보고서에 의무 적용하지 않는다. 새 문서 작성/셀/번호/outline/control/story용 경로가 아니다.

`scripts/hanging_explanation_cli.py inspect SOURCE --part Contents/section0.xml --index N --prefix "원래 라벨 "`로 전체 문단 binding을 읽는다. 요청 schema는 `hwpx.hanging-explanation.v1`, sourceSha256, editableReason, targets(binding/hangingHwpunit)이다. apply SOURCE NEW_OUTPUT --request REQUEST --dry-run 후 승인된 기존 사본 편집 범위 내 apply를 실행한다. 원본·기존 출력 덮어쓰기를 거부한다.

기존 여러 구역의 plain root, heading NONE/merged0/왼쪽 여백0, 실제 라벨과 뒤 설명만 지원한다. 대상1~12개, 값200~20000 HWPUNIT, 불리언·중복·오래된 binding·변화 없는 값은 거부한다. 글자 공백을 지우거나 임의로 추가하지 않는다. 공유 paraPr를 고치지 않고 기존 정의에서 intent만 바꾼 새 정의를 public API로 만든다. modern/fallback은 원래 확인한1:2 관계를 유지한다. 모든 기존 정의/문구/글자 run/표/바이너리를 독립 비교한다.

원본 실제 PDF의 첫 줄 시작점과 설명 시작점 차이를 읽고 실제 출력 축척으로 환산한다. 일반 출력과 두 쪽 모아찍기의 축척은 다를 수 있다. 라벨 시작점과 설명 시작점을 구분한다. 모아찍기7면이 반드시14쪽은 아니다. 원본 표시 번호와 빈 인쇄 칸을 확인한다.

HWP063 한 PC의 국토22쪽/46표와 전남3구역/16표/13쪽(7인쇄면) 시험 사본에서 검증했다. 실제 저장·재열기·반복 저장 PDF 전쪽과 HWPX 적용 서식/내용을 확인했다. 저장본에 같은 내어쓰기를 +100HWPUNIT로 다시 편집했다. 첫 보고서 실제 정렬 오차0pt, 두번째 약0.24PDFpt였다. 특정 설명과 스케일을 측정한 결과이며 임의 보고서/다른 PC 인증은 아니다. 신규 CLI는 inspect/dry-run 별도 검사다.

적용 후 hwpx-windows-finalize로 실제 한글 저장본 재열기 PDF와 원본 지면 보존을 확인한다. raw XML/사용 중 서식/모든 정의/PDF 지면은 별도 결과다. 재편집 첫 저장에서 미사용 정의 삭제 strict FAIL은 성공으로 바꾸지 않는다. 근거는 HWP063 report.md/summary.json/functional-verification.json이다.
