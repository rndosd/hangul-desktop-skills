# 판정 기준

검증 결과는 도구 성공 여부와 문서의 확인 범위를 분리한다.

## 실무 차트 전달 기준

사용자가 문서 생성·실제 사용을 우선하고 내부 OLE 바이트 동일성이나 구버전 호환성까지 요구하지 않는 경우에만 적용한다. 정확한 전달 파일의 패키지, 원자료의 값·계열·항목·제목, 관련 서식·앵커·배치·비대상 내용과 필요한 실제 한글 열기·저장/재열기·출력을 확인한다. 조판 검토는 실제 전달 파일에서 출력한 모든 요구 쪽을 대상으로 한다.

이 확인이 완료되고 남은 차이가 차트 OLE 바이너리뿐이면 실무 전달은 `PASS_WITH_OLE_WARNING`으로 별도 기록한다. native receipt와 strict gate의 원래 상태는 그대로 보존하고, `oleSemanticPreservation=UNVERIFIED`를 명시한다. 내부 차이만으로 파일 생성·전달·다음 작업을 멈추거나 같은 저장/분석을 반복하지 않는다. 이 판단은 기존 gate exit3을 exit0으로 고치는 기능이나 전체/구형 OLE 호환성 합격이 아니다.

열기·필요한 저장/재열기·출력 실패, 패키지 손상, 잘못된 값·누락, 차트/그림 유실, 예상 밖 서식·배치 변화, OLE 이외의 미확인 변경은 이 경고 경로로 넘기지 않는다. native 확인이 막히면 완성한 후보는 보존하고 검증 대기라고 보고한다. COM/보안 모듈/프로세스 보호 조건도 유지한다. 사용자가 OLE 동일성이나 구버전 편집 호환성을 명시적으로 요구하면 해당 엄격 검사를 완료해야 한다.

## 기존 COM 영수증

- PASS_FULL: 스크립트가 요구한 COM 열기/재열기(선택 모드의 저장 포함)를 완료했다.
- PASS_NO_COM: COM을 사용할 수 없어 해당 검사가 수행되지 않았다.
- BLOCKED_COM: COM 시작·열기·저장·재열기가 실패하거나 사용자 조작이 필요했다.
- FAIL_VALIDATION: 패키지·내용·구조 등 검사가 실패했다.

이 상태를 수정하거나 GUI 성공으로 대체하지 않는다. PASS_FULL은 그 자체로 시각 검수 통과가 아니다.

## 별도 검증 기록

실제로 수행한 항목만 기록한다.
- 전달 파일의 경로와 hash 또는 수정 시각
- 검사 방법: COM / native GUI / native PDF
- 패키지·내용 보존, 실제 열림, 실제 페이지 수와 관련 레이아웃 검수
- 저장·재열기는 performed / not-required / blocked 중 실제 상태
- 증거 파일 경로와 남은 제한

실제 한글 GUI에서 요구된 검사를 끝냈다면 COM 실패와 별도로 그 결과를 인정한다.
COM 불가만으로 모든 산출물을 실패로 취급하지 않되, 관찰하지 않은 항목은 미검증으로 남긴다.
상위 도구의 명시적 visual evidence/approval 계약은 이 기록으로 임의 우회하지 않는다.

## 기존 PDF의 읽기 검사

`scripts/audit_existing_pdf.py`는 E04에서 확인한 원본 라벨 대조를 실행한다.
`--expected-label`을 반복하거나 `--source-hwpx candidate.hwpx --source-label-regex 'R\d{2}'`로
실제 원본 표식 목록을 지정한다. 임의 PDF 숫자 패턴만으로 누락을 추정하지 않는다.
`checked_no_source_label_mismatch`는 해당 라벨 검사일 뿐 전체 출력 성공이 아니다.
`missing_pdf`, `missing_dependency`, `extraction_failed`는 `not_checked`로 남긴다.
짧은 쪽은 경고만이며 `render_not_performed`는 성공으로 승격하지 않는다.
라벨 중복·누락은 내용을 확인하고, PDF 추출 공백은 native 내용·비대상 좌표·실제 이미지
근거가 함께 있을 때만 제한적으로 해석한다. 공백 제거를 레이아웃 동등성 규칙으로 쓰지 않는다.

## 전달 판단

### 복합 문서 출력 완료 연결

```powershell
python scripts/hancom_completion_gate.py prepare --bundle "new-bundle" --source "candidate.hwpx" --final "new-final.hwpx" --pdf "new-final.pdf" --run "new-run"
# 위와 같은 입력/출력/run으로 지원되는 실제 COM 명령을 실행한다.
powershell.exe -NoProfile -File scripts/verify_hwpx_with_hancom.ps1 -CandidatePath "candidate.hwpx" -Mode SaveAs -OutputPath "new-final.hwpx" -PdfPath "new-final.pdf" -RunDirectory "new-run"
python scripts/hancom_completion_gate.py collect --bundle "new-bundle"
# differences와 모든 페이지 이미지를 실제 확인하고 review-template을 별도 review.json에 기록한다.
python scripts/hancom_completion_gate.py check --bundle "new-bundle" --review "review.json" --output "new-completion.json"
```

prepare/collect의 정상 미완료 상태는 pending(exit2), 검토·실행 실패/해시 불일치는 blocked(exit3),
필수 증거가 묶인 완료만 complete(exit0)다. COM 전에 prepare하고 수행 경로의 실제 receipt/job을
사용한다. 버전/경로/파일이 다른 증거를 수기로 맞추거나 PASS 플래그만 덧붙이지 않는다.
검토는 내용/비대상 구조/서식·그림의 실제 차이와 전체 페이지 관찰을 포함한다.
이 gate의 범위는 COM 후보→저장본/PDF다. 원본→편집 후보의 의도한 변경 검증은 별도 유지한다.
수동 검토 기록이 사람이 보았다는 사실 자체를 소프트웨어로 증명하지는 않는다.

collect가 blocked라도 생성된 차이/페이지 자료는 원인 검토에 사용할 수 있다.
자료가 있다는 이유로 complete를 표시하지 않는다. 특히 한글 저장의 BinData 이름·참조 재배치가
발견되면 바이트 목록 일치만으로 사용 위치 보존을 단정하지 않는다. 확인된 출력 비교와
미해결 구조 보존 판정을 분리하고, 검사 기준을 약화해 실패를 통과로 바꾸지 않는다.

그림 참조 위치 불일치는 `scripts/diagnose_binary_references.py candidate.hwpx final.hwpx
--output new-diagnosis.json`으로 먼저 좁힌다. 이 읽기 전용 도구는 pic/borderFill 소유 개체의
전체 하위 구조에서 binary 참조만 실제 파일 hash로 치환해 비교한다. 같은 개체의 XML 경로
이동, 개체 속성 변화, 그림 내용 변화, 매칭 불가를 구분한다. 개체 순번 매칭은 실제 배치나
스타일 사용 위치의 보존 증명이 아니므로 진단 결과로 완료 gate를 우회하지 않는다.

배경 정의 번호가 이동하면 `scripts/trace_border_fill_usage.py candidate.hwpx final.hwpx
--output new-usage.json`으로 section의 직접 참조 및 charPr/paraPr를 경유한 borderFill 적용을
비교한다. 정의의 id만 제외하고 그림 hash·나머지 서식을 비교하여 번호 변경과 다른 셀 연결을
구별한다. `imageConsumers.bindingsEqual`은 이 범위의 그림 연결만 의미한다. 다른 스타일 상속,
빈 run 합치기, 실제 배치 및 전체 완료를 보장하지 않으며 미해결 차이는 그대로 남긴다.

완료 gate는 section별 ctrl 요소의 순서·속성·하위 구조도 비교한다. 쪽 번호 등 제어 요소가
사라지면 `native_control_elements_changed`로 차단하며, 빈 run 정리로 간주하지 않는다.
이 비교는 의미적 동등성의 완전한 증명이 아니라 보수적인 변경 감지다. 의도한 제어 요소
변경도 별도 확인이 필요하다. 검사 코드가 바뀐 뒤 기존 증거의 비교 digest가 다르면 기존
영수증을 수정하지 말고 새 검증 자료를 생성한다.

- 인쇄/제출용은 전달 파일의 패키지·내용 보존과 실제 한글 레이아웃 확인이 필요하다.
- 재저장·재열기가 작업상 요구되면 그것도 끝나야 한다.
- 필요한 검증이 막히면 후보와 미완료 항목을 명시한다. 최종 검증 완료라고 부르지 않는다.
- PDF와 HWPX는 별도 산출물이다. HWPX 수정 후 이전 PDF를 증거로 재사용하지 않는다.
  PDF만 수정했으면 PDF에 대해서만 확인한 결과를 말한다.

## 재저장 비교

내용·표·구역·내장 그림 등 의미적 보존을 확인한다. 패키지 hash는 저장으로 달라질 수 있다.
문단 수 등 구조 지표가 달라지면 원인을 조사하되 지표 차이만으로 손상을 단정하지 않는다.
요청된 쪽 나눔 수정은 승인된 변화다. 관련 없는 누락·중복·예상 밖 조판 변화는 실패로 본다.

최초 저장 정규화와 활성 내용 손실을 추가로 좁힐 때 [활성 의미 비교](active-semantics-check.md)를 사용한다. 이 보조 검사 PASS가 strict gate 실패·native·시각 검토를 대체하지 않는다. 저장된 사본의 반복 저장 통과와 최초 변환의 미검증을 분리한다.
