# 다음 쪽에 조금 넘친 내용의 선택적 여백 맞춤

사용자가 조금 넘친 내용을 여백으로 맞춰 달라고 요청하거나 이 선택 기능을 켰을 때 `scripts/auto_margin_fit.py`를 사용한다. 일반 문서마다 자동으로 여백을 줄이는 필수 규칙이 아니다.

## 지원 범위

create_new_document.py로 작성한 새 보고서의 원본 생성 후보, 해당 .receipt.json, brief/design이 일치할 때만 적용한다. 기존 임의 양식, HWP, 한글에서 수동 수정한 저장본을 이 생성기로 재작성하지 않는다. 기존 양식 내용에 맞춘 자동 변형은 여전히 후속 과제다.

기본 기능은 마지막 쪽에 1~3개 텍스트 줄만 남은 자연 넘침을 한 쪽 줄이는 것이다. 별도 page_break가 계획에 있으면 자동 맞춤을 생략한다. 빈 쪽, 이미지가 있는 마지막 쪽, 내용 대조가 불확실한 출력, 이미 한 쪽인 문서는 대상에서 제외한다. 원래 두 쪽 이상 의도한 내용까지 한 쪽으로 압축하지 않는다.

## 기본 정책과 최소 조절의 의미

- 최소 여백은 사방 15mm, 시험 간격은 0.5mm다. 정책 JSON으로 변경할 수 있다.
- 위·아래를 같은 양만큼 줄이는 후보와 왼쪽·오른쪽을 같은 양만큼 줄이는 후보를 조합한다. 원래 네 여백이 비대칭이어도 원래 차이는 유지한다. `axes:['vertical']`이면 위아래만 조절한다.
- 네 여백 감소량의 합이 작은 후보부터 실제 한글에서 검사한다. 감소량이 같은 후보는 위아래 조절을 우선한다. 첫 성공은 이 **지정한 여백 쌍/간격의 시험 격자**에서 최소 감소량이다. 연속적인 모든 mm 값이나 각 방향 독립 조합의 절대 최솟값을 주장하지 않는다.
- 기본 최대 후보 수는 20개다. 한도에 닿으면 pending으로 멈춘다. 허용 범위 전체를 검사해도 맞지 않으면 no_fit이며 원본을 유지한다. 하한보다 작은 기존 여백을 임의로 키우거나 더 줄이지 않는다.
- 내용·글자 크기·줄 간격·표 앞뒤/큰 번호 간격은 유지한다. 가로 여백을 줄이면 새 표 폭과 열 폭은 같은 비율로 다시 계산된다.

정책 예:
```json
{
  "min_margins_mm": {"top":15,"bottom":15,"left":15,"right":15},
  "step_mm":0.5,
  "axes":["vertical","horizontal"],
  "max_overflow_lines":3,
  "max_tail_fraction":0.25,
  "max_attempts":20
}
```

## 실행과 검토

현재 PC의 environment.json pythonPath를 사용한다. 이 기능의 PDF 의존성은 PyMuPDF다. pypdf는 이 기능에 필요하지 않는다. 환경 JSON의 과거 pdfCheckStatus만으로 기능 준비를 단정하지 않고 실제 import를 확인한다. 현재 통합 환경은 PyMuPDF 1.28.2로 확인했다. 다른 PC는 설치 패키지의 `-InstallPdfRuntime` 선택 인자로 전용 runtime에 설치할 수 있다. 의존성이 없으면 COM 호출 전에 차단된다. 스크립트가 모듈이나 레지스트리를 설치/수정하지 않는다.

```powershell
python -X utf8 scripts/auto_margin_fit.py run --source new-report.hwpx --brief brief.json --design prepared-design.json --output-dir new-fit-run
# 범위를 바꾸려면 --policy margin-policy.json 추가
```

생성 영수증과 hash/원본 서식 검사를 통과한 뒤 baseline을 한글로 저장·재열기·PDF 출력한다. 실제 마지막 쪽을 읽어 조건에 맞으면 후보를 만든다. 각 후보도 실제 한글 출력으로 쪽 수와 본문 조각을 대조한다. PDF는 물리적 위치순으로 읽는다. 부동 표의 내부 스트림 순서 때문에 쪽 사이 본문을 누락으로 오인한 문제를 검증 사례에서 수정했다. 공백 정규화는 제한된 내용 대조에만 사용하며 조판 동등성 판정이 아니다.

`pending_review`는 자동 선택 후보다. 아직 완료가 아니다. selected.bundle의 XML 차이, 실제 PDF 전 페이지 이미지를 보고 review-template을 **별도 review.json**으로 기록한다. strict completion gate의 text/count/section/assets/controls 검사와 실제 검토 조건을 유지한다. 코드가 시각 검토 결과를 자동 pass로 써 주지 않는다.

```powershell
python -X utf8 scripts/auto_margin_fit.py accept --selection new-fit-run/selection.json --review new-fit-run/candidate-001/native-bundle/review.json --output new-fit-run/completion.json
```

accept는 원본/입력/생성기/후보/PDF hash, 최소 후보 순서, 실제 측정, 실제 여백, native evidence 연결과 완료 gate를 다시 확인한다. 선택 정보 변경이나 미수행 검토를 완료로 처리하지 않는다. source와 output directory를 덮어쓰지 않으며 시스템 권한/보안/승인창 정책을 바꾸지 않는다.

## 확인한 결과

2026-10-03, 한글 2024 13.0.0.3903 / python-hwpx 6.3.0 / PyMuPDF 1.28.2에서 기존 2쪽 보고서의 마지막 한 줄을 감지했다. 위아래 20→19.5mm, 좌우 20mm 유지인 첫 후보에서 1쪽이 됐다. 내용/서체/크기/번호/표와 항목 간격 보존, 한글 SaveAs·재열기·PDF 전 페이지 검토와 완료 gate를 통과했다. 이미 1쪽인 대조 문서는 검사 후 조절을 생략했다.

19개 가드/선택/보존 검사와 실제 evidence의 검토 미수행·선택 변경 차단을 확인했다. 이 대표 사례를 임의 양식이나 모든 긴 보고서의 자동 보장으로 확대하지 않는다.

Windows PowerShell을 Python에서 호출할 때 PS7의 모듈 검색 경로를 그대로 넘기면 Get-FileHash 로딩이 실패한 환경 차이를 확인했다. 해당 자식 프로세스에만 Windows PowerShell 기본 모듈 검색을 적용한다. 사용자/시스템 환경 변수와 실행 정책은 변경하지 않는다.
