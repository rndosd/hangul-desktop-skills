# 보고서 쪽 흐름·표 간격·페이지 여백

이 지침은 내용/목차를 고정하지 않는다. 필요한 형식을 선택하며 명시한 사용자 서식과 고정 제출 양식이 우선한다.

## 새 보고서의 간격

- 표 바깥 간격은 `format.table_outer_spacing_pt:{before:6,after:8}`처럼 pt로 지정한다. 생성기 기본은 앞뒤 6pt이며 사용자가 요청한 보고서 예시는 앞 6pt·뒤 8pt다. 셀 안쪽 여백 및 셀 문단 뒤 간격과 별개다. 0~36pt 범위에서 명시 조절한다. 표의 왼쪽 들여쓰기와 열 너비는 이 값으로 바꾸지 않는다.
- `1.·2.·3.` 같은 큰 항목은 `heading_layout[0].spacing_before_pt:14`, `spacing_after_pt:6`을 시작안으로 쓴다. 본문 줄 간격을 늘리는 대신 큰 항목 앞 문단 간격을 더 준다. 하위 항목/본문은 기존 간격을 유지한다. 예시나 형식 계약에서 다른 값이 명시되면 그 값을 사용한다.
- 제목의 `keep_with_next`로 첫 본문과 함께 이동할 수 있다. 다음 본문의 `keep_lines`는 문단 전체를 붙여야 할 때만 선택한다. 모든 긴 문단을 붙이면 큰 빈 공간이 생길 수 있다. 검토한 새 문단에는 public `doc.styles.apply_paragraph_format(paragraph_index=...,keep_with_next=True)` 또는 `keep_lines=True`를 사용한다. 기존 임의 문서 편집의 보존 검증까지 자동 보장하는 전용 CLI가 생긴 것은 아니다.

## 긴 표

`table_layout`의 기존 필수 키는 `cell_margins_mm,vertical_align,line_wrap,page_break,repeat_header`다. 선택 키 `treat_as_char`가 추가됐다. 없는 경우 과거 호환을 위해 True다. 여러 쪽으로 이어질 긴 표는 **명시적으로 False**를 사용한다. 글자처럼 취급한 큰 표는 쪽 나눔 설정이 있어도 잘릴 수 있다.

- `page_break:'CELL'`: 셀 안의 텍스트도 쪽을 넘어 이어진다.
- `page_break:'TABLE'`: 완전한 셀/행 사이에서 표를 나눈다. 쪽보다 큰 한 행까지 정상 처리된다는 뜻은 아니다.
- `repeat_header:true`와 첫 행 `header=1`을 함께 저장해야 제목행이 반복된다. 생성기는 첫 행을 제목 셀로 표시한다. 반복이 필요 없으면 False를 명시한다.
- `NONE`은 이 제한 생성기의 정상 출력 경로에 추가하지 않았다. 정수 enum을 추정해 쓰지 않는다.
- 한글이 표를 담는 새 run에 추가하는 빈 t를 public run.text setter로 생성 단계에서 준비한다. 기존 컨트롤 run의 전체 내용을 지우는 경로가 아니다.

이 생성기의 표 외부 속성 설정은 **새로 만드는 표에만** 한정한다. 기존 미병합 plain 표의 제한 속성 편집은 [기존 표 쪽 흐름](existing-table-flow.md)의 별도 진단·보존·native 검증 경로를 사용한다. 기존 양식의 임의 raw XML 폴백은 없다. 기존 일반 표의 행/크기는 table-layout-edit.md의 별도 경로를 유지한다.

## 위·아래·왼쪽·오른쪽 페이지 여백

`format.margins_mm:{top:15,bottom:15,left:17,right:17}`처럼 네 방향을 독립적으로 지정할 수 있다. 생략한 방향은 현재 기본값 20mm를 이어받는다. 새 문서에서 public `doc.page.setup`으로 설정하고 저장한 secPr/pagePr/margin 값을 대조한다. 쪽 폭에 따라 새 표 너비도 다시 계산한다.

한 쪽 맞춤 요청이 있으면 요청한 여백 범위 내에서 후보를 만들고 native PDF로 확인한다. 임의 글자 축소·내용 삭제로 맞추지 않는다. 명시적인 고정 제출 양식의 여백을 자동 변경하지 않는다. 프린터마다 실제 인쇄 가능 영역은 다르므로 한글/PDF 검증과 특정 프린터 인쇄 검증을 구분한다.

## 검증 범위와 한계

2026-10-03, 한글 2024 13.0.0.3903 / python-hwpx 6.3.0에서 같은 내용의 통제 사례로 확인했다. CELL/TABLE/제목행 반복/글자처럼 취급은 각각 한 속성만 다른 파일로 비교했다. 제목 유지도 같은 내용에서 비교했다.

- 긴 표 3개 정상 사례: 각 4쪽, 모든 R01~R18 시작/끝과 뒤 본문/부록 보존. CELL은 R07/R16 내부 분리, TABLE은 전 행 유지, 제목행 반복은 표가 있는 매 쪽에서 확인.
- 제목 유지: 2쪽 사례에서 고아 제목을 재현하고 유지 설정으로 제목+본문을 2쪽에 함께 배치.
- 간격/여백: 표 앞 6pt 뒤 8pt, 큰 항목 앞 14pt 뒤 6pt를 유지한 동일 보고서가 사방 20mm에서 2쪽, 위아래 15mm/좌우 17mm에서 1쪽. 글자 크기/내용은 동일.
- 잘리는 큰 inline 표와 고아 제목 비교 문서는 completion gate에서 blocked로 남겼다.
- strict completion gate의 텍스트/개수/섹션/자산/컨트롤 불변 조건은 변경하지 않았다. 전 페이지 실제 출력 검토와 해시 바인딩을 수행했다.

생성기 `audit_output`은 생성 패키지의 원시 서식 검사다. 한글 SaveAs 후에는 HwpUnitChar case를 유지하면서 fallback margin 값을 두 배 단위로 바꾸므로 그 검사가 BODY/CELL/HEADING spacing mismatch를 보고할 수 있다. native 출력 검증은 이를 무시하지 않고 지원 case를 해석한 독립 서식 비교와 전체 시각 검토로 확인한다. 이번 사례의 실제 case 값·글꼴/크기·정렬·간격·유지 플래그는 보존됐다. 임의 HWPX에서 모든 switch 구조를 정상으로 간주하지 않는다.

공식 참고: https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/table/tableattribute/table%28table%29.htm

## 조금 넘친 내용의 자동 후보

사용자가 여백으로 맞추기를 요청하면 [선택적 여백 맞춤](auto-margin-fit.md)의 새 보고서 전용 자동 후보 검색을 사용한다. 실제 한글 출력에서 마지막 쪽에 조금만 남은 경우에만 시험하며 하한·시험 간격·시각 검토를 지킨다. 기존 양식의 범용 자동 맞춤 기능으로 확대하지 않는다.

쪽 번호·표지 번호 제외·머리말/꼬리말이 필요하면 [선택적 쪽 요소](report-page-elements.md)를 따른다. 단일 구역 신규 생성 전용이며 기존 문서의 임의 컨트롤 편집/자동 여백 맞춤과 같지 않다.
