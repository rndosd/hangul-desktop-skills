# 선택적 쪽 번호·머리말·꼬리말

보고서에 필요할 때만 쓴다. 표지, 머리말, 꼬리말을 모든 문서에 강제하거나 내용을 고정하지 않는다.
`scripts/create_report_pages.py`는 검토한 brief/design을 기본 생성기로 새로 작성한 뒤 선택한 쪽 요소를 넣는다.
기존 양식이나 원본 문서를 열어 컨트롤을 바꾸는 도구가 아니다.

## 지원 범위와 선택

단일 구역의 새 보고서, 아래 가운데 native PAGE 숫자, 한 줄 머리말(왼쪽)/꼬리말(오른쪽).
쪽 번호와 꼬리말 문구는 별개다. 번호를 본문에 직접 입력하지 않는다.
표지가 있으면 첫 쪽의 머리말·꼬리말·번호를 숨기고, 지정한 본문 시작에서 1로 재시작한다.
본문 시작은 design의 page_break 다음에 놓인 유일한 문단 제목이어야 한다.
표지가 없으면 첫 쪽부터 1로 시작한다. 본문이 늘면 native 컨트롤이 다음 번호를 계산한다.
홀짝 다른 머리말, 여러 구역, 전체 쪽 수 분모, 기존 문서의 임의 쪽 요소 편집은 이 경로에 포함하지 않는다.

```json
{"schema":"hwpx.report-page-elements.v1","header_text":"검토 자료","footer_text":"업무 검토용","cover":true,"body_start_text":"추진 개요"}
```

header_text/footer_text는 각각 생략할 수 있다. 예시 문구를 실제 업무 내용으로 추정하지 않는다.
문구는 줄바꿈 없이 최대 80자이며 길면 겹침/줄바꿈이 생길 수 있으므로 실제 출력에서 확인한다.
글꼴 9pt, 머리말·꼬리말 여백 10mm는 이 도구의 시작값이다. 본문 글자 크기·사방 여백은 원래 디자인을 유지한다.
다른 위치/크기를 요청하면 이 경로의 실제 지원 범위를 확인하고 별도 후보에서 검증한다.

```powershell
python -X utf8 scripts/create_report_pages.py --brief brief.json --design design.json --options pages.json --output new-candidate.hwpx
```

prepare/validate/create 기존 기본 경로를 대체하지 않는다. 이 선택 경로도 같은 author compose/validation을 호출한다.
전용 `.receipt.json`은 구조 후보를 기록하며 native 완료는 pending이다.
기본 생성기용 auto_margin_fit receipt와 같지 않다. 현재 이 후보에 자동 여백 맞춤을 연쇄 적용하지 않는다.

## 중요한 코드 경계

python-hwpx 6.3.0은 머리말/꼬리말을 secPr와 body ctrl에 중복 기록한다.
이 도구는 **방금 만든 새 문서**에서 public 생성 결과를 native body ctrl 표현으로 맞춘다.
기존 파일을 raw XML로 수정하는 fallback이 아니다. 새 번호는 pageNum, 본문 재시작은 newNum이다.
새 빈 셀의 empty t와 재시작 run도 실제 Hancom 저장 형태에 맞춰 준비한다.
한글이 저장할 때 보이지 않는 control run을 합치는 것과 표시되는 텍스트/셀의 서식 변경은 구분한다.

후보 → 한글 SaveAs/재열기/PDF → 엄격한 completion gate → 전체 쪽 실제 검토를 수행한다.
컨트롤 불일치나 누락을 정상화 명목으로 무시하지 않는다. gate는 변경하지 않았다.
선택적인 읽기 검사:

```powershell
python -X utf8 scripts/audit_report_page_elements.py candidate.hwpx saved.hwpx saved.pdf --options pages.json --output new-audit.json
```

이 검사는 PyMuPDF가 필요하다(설치 패키지의 선택 `-InstallPdfRuntime`).
원본의 텍스트, 번호 순서, 표지 숨김, 머리말/꼬리말-본문 및 꼬리말-번호 간격과 실제 사용 서식을 확인한다.
Hancom 13의 활성 HwpUnitChar 분기, inactive strikeout 기본값과 control-bearing 빈 run 합치기를 구분하는
읽기 검사이며 일반 문서의 완전한 의미 동등성 증명이 아니다. native job/PDF 연결과 전체 시각 검토를 대체하지 않는다.

2026-10-03 한글 2024 13.0.0.3903 / core 6.3.0: 표지 포함 3쪽 본문 1·2,
추가 쪽을 넣은 4쪽 본문 1·2·3, 첫 쪽부터 번호를 매긴 3쪽 1·2·3을 확인했다.
모두 SaveAs·재열기·native PDF 및 전체 쪽 검토, 엄격한 gate complete다.
