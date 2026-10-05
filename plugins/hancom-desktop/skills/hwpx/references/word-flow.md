# 어절 줄바꿈·선택 자간·긴 표 내용

읽기 편한 지면을 만드는 선택 규칙이다. 내용/목차를 고정하거나 모든 문단을 같은 밀도로 채우지 않는다.
사용자가 단어 보존을 원하면 한글 어절·영문 단어 단위 줄바꿈을 우선 시험한다. 큰 빈 공간이 생긴
문단에는 소폭 자간 축소를 비교할 수 있다. 효과와 가독성이 모두 확인된 후보만 선택한다.

## 대상과 구현

`safe_word_wrap.py`: python-hwpx 6.3.0, hash-bound 기존 plain 본문/평면 셀 문단 1~20개.
정확한 전체 문구와 section/paragraph_path를 지정한다. 여러 plain run과 이미 있는 native 목록
문단의 heading/여백 참조를 보존한다. 중첩 표·필드·그림·ctrl·이야기 영역·native lineBreak 혼합
문단·빈 문단·보호 셀/표·고정 표는 거부한다. 여러 문단을 한 문자열로 재작성하지 않는다.

현재 public API에 문자열 줄 나눔 enum setter가 없어 기존 paraPr를 복제하는 **제한 clone 어댑터**를
별도 검증했다. 기존 공유 정의는 수정하지 않고 두 enum과 선택 문단의 paraPr 참조만 변경한다.
한글 어절은 breakNonLatinWord=BREAK_WORD, 영문 단어는 breakLatinWord=KEEP_WORD이다.
이 한글 enum 이름은 직관과 다르므로 임의로 뒤집지 않는다. 실제 한글 13.0.0.3903 출력으로 확인한 매핑이다.
버전 전용 namespace_literal_guard를 순차 작업에 적용하고 원래 URI 값을 보존한다.
독립 전체 snapshot은 기존 글꼴/자간/장평/문단·목록·표 속성/텍스트/run/컨트롤과 비대상 패키지를 비교한다.
선택 문단의 line cache와 Preview만 기존 safe_edit 계약에 따라 제외한다. 일반 XML 폴백이 아니다.

현재 PC environment.json의 pythonPath를 사용한다. safe_edit의 읽기 inspect 결과에서 전체 문단의
`part`, `paragraph_path`를 확인한다. 셀 row/column은 1부터, 구조 paragraph_path는 inspect의 값을 그대로 쓴다.

```powershell
python -X utf8 scripts/safe_edit.py inspect source.hwpx --find "정확한 전체 문구" --table 1 --row 2 --column 2 --output new-inspection.json
python -X utf8 scripts/safe_word_wrap.py source.hwpx candidate.hwpx --request reviewed-words.json --dry-run
python -X utf8 scripts/safe_word_wrap.py source.hwpx candidate.hwpx --request reviewed-words.json
```

```json
{"schema":"hwpx.word-wrap.v1","source_sha256":"실제 SHA256","targets":[{"part":"Contents/section0.xml","paragraph_path":[3,0,0,4,1,0,0],"expected_text":"정확한 전체 문단","korean":"WORD","latin":"WORD","reason":"단어 내부 분리를 피하기 위한 선택 편집"}]}
```

예시 path를 다른 파일에 그대로 쓰지 않는다. enum 이외의 정렬·최소 공백·글꼴·셀 여백은 바꾸지 않는다.
셀 폭보다 긴 단어·URL·식별자까지 무조건 온전하게 들어간다는 보장은 없다. 실제 잘림/분리 여부를 본다.

## 자간 후보를 선택할 때

[기존 자간 도구](bounded-format-review.md)의 `safe_format.py`를 그대로 사용한다.
선택 **문단**의 letter_spacing을 원래 값에서 조금씩 줄이고 ratio(장평)는 원래 값으로 유지한다.
글자 크기/폰트/열 너비/사방 여백을 함께 바꾸어 자간 효과로 설명하지 않는다.
현재 문단별 plain run 계약이며 특정 화면 줄 하나만 따로 조절한다고 주장하지 않는다.

자간 0 → -1과 같은 작은 후보부터 실제 출력으로 비교한다. 이미 정한 bounded 한계(원래 자간 차이 5,
절대 -10..10)를 늘리거나 실패 후 단계적으로 누적 축소하지 않는다. 허용 범위라는 이유만으로 적용하지 않는다.
단어가 앞줄로 이동했는지, 빈 공간이 줄었는지, 나머지 줄의 밀도가 답답하지 않은지 확인한다.
별도 변수인 한글의 최소 공백/양쪽 정렬도 자간과 혼동하지 않는다. 이번 도구는 그 값을 바꾸지 않는다.

## 긴 내용과 열 너비

`safe_table_columns.py`는 평면 **미병합** plain 표 2~100행·1~12열의 열 너비만 재배분한다.
셀당 1~20문단·문단당 1~20 run과 기존 native 목록/lineBreak tail을 보존하는 별도 검증 경로다.
기존 safe_table_layout.py의 단일 문단/run 가드는 그대로 유지한다. 병합·중첩·그림·필드·ctrl,
보호/고정 표·셀, inline 표, TABLE 외 쪽 나눔은 거부한다.

```powershell
python -X utf8 scripts/safe_table_columns.py source.hwpx candidate.hwpx --request reviewed-columns.json --dry-run
python -X utf8 scripts/safe_table_columns.py source.hwpx candidate.hwpx --request reviewed-columns.json
```

```json
{"schema":"hwpx.table-columns.v1","source_sha256":"실제 SHA256","table":1,"widths_mm":[32,138]}
```

모든 열 너비를 명시하고 원래 전체 표 너비를 유지한다. 셀의 사용 가능 너비 최소 5mm가 필요하다.
public table.set_column_widths와 독립 전체 section/package 비교를 사용한다. 기존 문구/문단/목록/높이/
셀 여백/테두리/스타일/쪽 여백을 바꾸지 않는다. 값은 170mm 합성 표의 시험 예이며 전역 권장 비율이 아니다.
한글은 내용이 길어지면 실제 행 높이를 늘릴 수 있다. 명목 cellSz/줄 캐시를 실제 높이로 단정하지 않는다.

## 실제 완료 기준과 관찰

finalize prepare → native SaveAs → 재열기/PDF → collect → 모든 쪽 검토 → check를 연결한다.
원본→후보의 의도한 변경 보존과 후보→native 저장본/PDF 보존을 각각 확인한다.
지정어 내부 분리는 finalize audit_hwpx_linebreaks.py로 출처/예상 횟수와 대조하고 실제 이미지도 본다.
NO_SPLIT_OBSERVED는 지정어 범위만 의미한다. 본문 문장과 항목 시작/끝, 목록, 머리글 반복, 표 뒤 여백,
잘림·겹침·쪽 번호를 전 페이지 확인한다. PASS_STRUCTURE/COM 성공만으로 완료하지 않는다.

2026-10-03 / 한글 2024 13.0.0.3903 / core 6.3.0:
- 편집 6종·17쪽의 보존·가독성·strict gate complete. 단어 보존, 소폭 자간, 여러 문단/목록,
  자연스러운 행 높이 확대, 다음 쪽 제목행 반복/행 전체 이동과 표 뒤 문장을 검토했다.
- 고정 78mm 열의 한 문단에서 자간 0→-1로 `사전검토결과보고서를`이라는 어절이 앞줄에 온전히 들어왔다.
  첫 줄 오른쪽 빈 공간이 약 107.8pt 감소했고 글꼴/장평/열 너비/여백은 유지됐다. 뒤의 두 쪽은 픽셀 동일.
- 75mm 열에서는 -3/-4도 같은 어절을 앞줄로 넣지 못했다. 이 후보는 가독성/보존만 통과했고 맞춤 효과는 없으므로 선택하지 않는다.
- 내용 열 75→138mm 재배분은 전체 너비 170mm를 유지하며 3→2쪽. 모든 본문·3문단 목록 셀·쪽 요소를 보존했다.
- 진단 기준은 한글/영문 내부 분리 2건으로 visual_review_failed. 최초 작성 초안은 잘못된 indent 키가 만든
  hh:indent를 native가 제거하여 active style 보존에 실패했다. 둘 다 blocked 상태를 유지했고 gate를 바꾸지 않았다.
  편집은 실제 native 저장 원본의 스타일을 기준으로 수행했다. 새 목록의 margin 키를 추정해서 만들지 않는다.

43개 가드/보존 시험은 Python -O에서도 통과한다. assets/word-flow/source.hwpx는 글자 단위 진단용 native
합성 원본, fit.hwpx는 78mm 자간 비교 원본이다. 실제 업무 자료·자동 판단 규칙·모든 단어에 대한 보장은 아니다.
보안 DLL·레지스트리·권한·실행 정책은 변경하지 않는다.

[한컴 줄 나눔 기준](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/format/paragraph/paragraph_general.htm),
[한컴 자간 정의](https://help.hancom.com/hoffice/multi/ko_kr/hwp/format/font/fonts%28spacing%29.htm).

이미 선택한 모든 문단이 WORD/WORD이면 같은 ID·캐시·정의를 유지한 바이트 사본을 반환한다. 목표 값·해시·경로·보호 조건의 검사는 그대로 수행한다. 실제 변경이 없는 성공을 값 변경이나 native 검증 완료로 세지 않는다. 일부만 미적용이면 그 문단만 바꾸고 이미 적용된 문단의 ID는 유지한다.
