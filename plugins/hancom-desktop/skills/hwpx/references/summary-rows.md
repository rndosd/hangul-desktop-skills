# 소계·합계행과 숫자 표시

내용/목차나 특정 디자인을 의무화하지 않는다. 필요한 셀만 선택한다. 단위·금액·비율의 의미를 먼저 확인하며 숫자 정렬과 표시 형식 변경은 값 계산과 구분한다.

## 선택 기능

- 항목명은 왼쪽, 제목은 가운데, 숫자는 오른쪽 정렬 등이 후보이다. 문서의 기존 규칙과 요청을 따른다.
- 소계는 굵기·연한 채우기·위쪽 구분선, 총합계는 더 강한 구분선/채우기 등을 필요할 때 선택한다. 색·선 두께를 모든 보고서의 기본값으로 강제하지 않는다.
- 단위가 이미 머리글에 있다면 유지한다. 원/천원/백만원, 수/비율을 임의 환산하지 않는다.
- 값이 변하지 않는 범위에서 천 단위 구분과 소수 자리 표시를 맞출 수 있다. 표시를 맞추려고 반올림하거나 숫자·합계의 의미를 추정하지 않는다.
- 쪽 경계에서는 마지막 상세행·소계·총합계의 실제 위치를 본다. `keepWithNext` 설정이나 COM 성공만으로 표 행 묶음이 유지됐다고 말하지 않는다.

## 기존 셀의 제한 편집

`scripts/safe_summary_style.py`: core 6.3.0 전용. 본문 직접 표 2~100행·1~12열, 기존 소유 셀의 1~20 plain 문단/문단당 1~20 run과 native lineBreak를 검사한다. 기존 가로 병합 제목은 정확한 소유 셀을 지정하며 병합 구조를 변경하지 않는다. 중첩 표·그림·필드·컨트롤·세로 쓰기·보호 대상·고정 표는 거부한다.

`inspect → 명시 요청 → apply --dry-run → apply`를 사용한다. 표/행/열은 1부터 시작한다. 원본/기존 출력을 덮어쓰지 않는다.

```powershell
python -X utf8 scripts/safe_summary_style.py inspect source.hwpx --table 1 --output new-inspection.json
python -X utf8 scripts/safe_summary_style.py apply source.hwpx new-candidate.hwpx --request reviewed-request.json --dry-run
python -X utf8 scripts/safe_summary_style.py apply source.hwpx new-candidate.hwpx --request reviewed-request.json
```

```json
{
  "schema":"hwpx.summary-cell-format.v1",
  "source_sha256":"inspect의 실제 원본 SHA256",
  "table":1,
  "edits":[
    {"row":7,"column":1,"expected_texts":["소계 1"],"bold":true,"alignment":"LEFT"},
    {"row":2,"column":3,"expected_texts":["1200"],"alignment":"RIGHT","number_format":{"decimal_places":1,"grouping":true}}
  ]
}
```

최대 100셀을 명시한다. `expected_texts`는 각 셀의 모든 기존 문단을 순서대로 정확히 확인한다. 굵기·정렬은 선택 셀의 모든 기존 문단/run에 적용하며, 부분 글자 선택 기능은 아니다. 동일 셀 중복·알 수 없는 키·오래된 원본 해시·숫자를 boolean으로 지정한 주소/옵션은 거부한다.

숫자 표시는 **plain run 하나/문단 하나의 숫자 전체**에만 허용한다. decimal_places는 정수 0~4, grouping은 boolean이다. 소수점은 `.`이며 쉼표는 정상적인 천 단위 그룹만 허용한다. 음수·0·기존 소수는 정확한 Decimal 값으로 비교한다. `1200 → 1,200.0`, `1.20 → 1.2`는 값 보존; `92.25 → 92.3`은 반올림이므로 거부한다. 단위·퍼센트 문자가 포함된 문자열, 수식/필드, 날짜, 지수, 모호한 구분자, 단위 환산/비율 변환은 이 경로에서 처리하지 않는다. 자동 합계식이나 수식 갱신도 추가하지 않았다.

글자 서식은 public `ensure_char_property(base_char_pr_id, predicate, modifier)`로 원래 정의 전체를 복제하고 bold 요소만 바꾼다. 단순 `run.bold` setter는 이 core 버전에서 원래 style를 base로 전달하지 않으므로 사용하지 않는다. 문단은 public `ensure_paragraph_format`으로 정렬/명시한 keepWithNext만 변경한다. 글꼴·크기·자간·장평·기타 서식과 기존 공유 정의를 독립 전체 header/section 비교로 지킨다. 선택 문단의 line cache만 무효화한다. scoped namespace literal 보존 어댑터를 사용한다.

채우기·선은 기존 [셀 선·채우기](cell-borders-diagonals.md)의 별도 도구를 순서대로 적용한다. 같은 배경색으로 기존 서로 다른 테두리를 합치지 않는다. 공유 경계 이웃도 검사한다. 숫자/스타일과 장식 도구의 요청 원본 해시는 각 단계의 실제 파일에서 새로 읽는다.

## 쪽 경계의 검증과 조정

`keep_with_next` boolean은 지정 셀의 모든 기존 문단에 적용한다. **표의 다음 행을 같은 쪽에 유지하는 기능으로 간주하지 않는다.** 시험한 한글 2024에서는 마지막 소계 셀에 이를 적용해도 총합계만 다음 쪽에 남았고 두 쪽의 PDF 픽셀이 원래 경계 사례와 같았다. 이 후보는 visual_review_failed로 남긴다.

몇 줄만 넘친 경우 기존 [셀 안 여백](cell-spacing-wrap.md)이나 [표 앞뒤 간격](existing-table-flow.md)의 과한 부분을 검토한다. 이번 시험에서는 두 번째 묶음 6행의 위/아래 안 여백을 3.25mm에서 2.5mm로 줄여 2쪽이 1쪽이 됐다. 글자 크기·열 너비·쪽 여백·금액·단위·병합·표 앞뒤 간격은 유지했다. 이 숫자는 통제 시험의 조정값이다. 이미 여백이 적거나 내용이 길면 일괄 압축을 계속하지 말고 관련 행을 다음 쪽에서 함께 시작하는 배치를 검토한다. 기존 표의 임의 행 묶기/표 분할 자동화는 아직 구현하지 않았다.

## 확인 범위

2026-10-03 / 한글 2024 13.0.0.3903 / core 6.3.0:

- 기준 원본, 숫자/굵기/정렬, 배경/선, 여러 쪽 계속, 선택 여백 조정: **5사례·6쪽**, 실제 SaveAs → 재열기 → PDF 전체 시각 검토 → strict gate complete.
- 소계 3개와 총합계의 값은 기존 셀/실제 PDF 내용과 대조했다. 금액·진행률의 실제 오른쪽 끝 좌표도 확인했다. 병합 소계 제목, 기존 두 문단 셀, 단위 머리글, 제목행 반복, 쪽 번호, 표 뒤 설명의 여백을 보존했다.
- 총합계가 고립된 경계 및 keepWithNext 후보 **2사례·4쪽**은 시각 실패. 생성 시의 동일 서식 run 합침/꼬리말 참조 재번호화로 strict 텍스트/컨트롤 불변 검사를 실패한 최초 원본 **1사례·1쪽**도 차단했다. native 저장 사본을 별도 재검사해 후속 편집의 기준으로 썼으며 기준을 완화하지 않았다.
- 가드/보존 시험은 `test_summary_style.py`; assets/summary-rows/source.hwpx는 실제 저장된 합성 원본, boundary.hwpx는 고립 합계 재현용이다. 임의 양식의 모든 표/서식을 확인한 뜻은 아니다.

PASS_STRUCTURE는 후보의 요청/보존 검사이며 실제 출력 완료가 아니다. 전달 후보에 finalize prepare → SaveAs → collect → 실제 모든 쪽 검토 → check를 적용한다. 숫자 값·단위·정렬·합계와 관련 행의 실제 위치를 함께 확인한다. COM·보안 DLL·레지스트리·권한·실행 정책을 바꾸지 않는다.

[한컴 표의 여러 쪽·안 여백 안내](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/table/tableattribute/table%28table%29.htm), [문단 정렬 안내](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/format/paragraph/paragraph_general.htm).
