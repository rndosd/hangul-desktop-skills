# 기존 양식 서식 다면 점검과 제한 후보 — 작업본 0.3.0

`audit_form_format.audit_format(source)`는 XML 설정만 읽는다. 페이지 여백, 글꼴 정의, 모든 문단의
가로/세로 정렬·행간·문단 앞뒤 간격·들여쓰기·내어쓰기·줄/쪽 나눔·번호 참조, run별 글자 크기·
자간·장평, 표/소유 셀 크기·안쪽 여백·세로 정렬·병합을 기록한다. 본문 텍스트를 별도 내보내지 않는다.
쪽 수, 실제 줄바꿈, 잘림과 가독성을 XML 캐시에서 확정하지 않는다.

`safe_format.py`는 명시한 기존 문단의 비어 있지 않은 plain run에 **자간과 장평만** 제한 적용한다.
python-hwpx 6.3.0 public `styles.ensure_run`, `run.char_pr_id_ref`, `run.replace_text`를 사용한다.
글자 크기, 글꼴, 색, 활성 밑줄/취소선과 다른 서식은 보존 검사 대상이다. 정렬·행간·여백·셀 크기·
안쪽 여백·병합·번호 설정은 읽기/보존 확인만 하며 이 CLI에서 바꾸지 않는다.

계획 schema는 `hwpx.bounded-character-format.v1`이며 `source_sha256`와 1..20개 `targets`를 가진다.
각 target에는 `part`, `paragraph_path`, 전체 `expected_text`, 정수 `letter_spacing`, 정수 `ratio`,
검토 사유 `reason`이 필요하다. 원본 값과의 차이는 각각 5 이내, 자간은 -10..10, 장평은 95..105이다.
언어별 원래 값이 서로 다르면 현재 계약으로 처리하지 않는다. 잘못된 위치·중복·오래된 hash·지원되지
않는 혼합 문단을 거부한다. 축소 수치가 허용 범위라는 이유로 적용 필요성이 입증되지는 않는다.

```powershell
python -X utf8 -B safe_format.py content-only.hwpx new-format-candidate.hwpx --plan reviewed-format-plan.json --dry-run
python -X utf8 -B safe_format.py content-only.hwpx new-format-candidate.hwpx --plan reviewed-format-plan.json
```

검토한 새 스타일과 대상 run 참조만 달라지는지 전체 패키지를 대조한다. 기존 스타일 정의는 그대로
검사한다. 새 스타일 clone에 한해 API의 자식 순서와 비활성 NONE 밑줄/취소선 생략을 의미상 비교하고,
그 외의 속성·색·글꼴·크기와 활성 효과는 모두 검사한다. 제외는 Preview와 선택 문단의 lineSegArray다.
재열기/open-safety와 원본 hash 검사 후 새 파일만 원자적 hard link로 게시한다. 실패 시 출력하지 않는다.

## 6.3.0 전용 URI 값 보존

6.3.0의 `normalize_hwpml_namespaces`는 XML 전체 bytes에 namespace URI 치환을 적용하므로,
실제 파일에서 `required-namespace` 속성의 **URI 값**도 바뀌었다. 설치 라이브러리와 원본은 수정하지
않았다. [해당 버전의 구현](https://raw.githubusercontent.com/airmang/python-hwpx/v6.3.0/src/hwpx/opc/xml_utils.py)에
근거한 `namespace_literal_guard.py`가 이 제한 경로에만 적용된다.

어댑터는 모든 XML/HPF를 안전하게 읽어 실제 element/attribute 확장 이름에 2016 namespace가 없는
문서만 허용하고, 순차 작업의 함수 호출 동안 불필요한 URI 치환만 일시적으로 생략한다. 함수 종료 시
복원한다. 기존 XML 크기/깊이/entity/network 가드는 유지한다. 2016 실제 태그 지원을 주장하지 않는다.
이 방식은 내부 함수에 의존하는 버전 전용 어댑터이므로 다른 버전·동시 실행·다른 namespace 문서를
배포 지원으로 넓히기 전에 재검증 또는 upstream 수정이 필요하다.

## 실제 한글 확인

이 경로는 자동 맞춤, 전역 서식 통일, 일괄 글자 크기 축소를 하지 않는다. 실제 문서에서 필요한
최소 변경을 선택하고 원본/내용만 수정본/서식 후보를 같은 한글 환경에서 비교해야 한다. 가독성,
넘침·잘림·쪽 나눔·번호·재저장 후 재열기가 미확인이라면 `format_candidate_native_pending`으로 남긴다.
보안 모듈·권한 차단 시 설정 변경이나 다른 실행 경로로 우회하지 않는다.

자간·장평·행간·여백은 서로 다른 설정이며 실제 줄바꿈과 읽기 편함에 미치는 영향은 native 결과로
검토한다. 정의 참고: [자간](https://help.hancom.com/hoffice/multi/ko_kr/hwp/format/font/fonts%28spacing%29.htm),
[장평](https://help.hancom.com/hoffice/multi/ko_kr/hwp/format/font/fonts%28scale%29.htm),
[줄 간격](https://help.hancom.com/hoffice/multi/ko_kr/hwp/format/paragraph/paragraph%28line_spacing%29.htm),
[문단 간격](https://help.hancom.com/hoffice/multi/ko_kr/hwp/format/paragraph/paragraph%28spacing%29.htm),
[표 설정](https://help.hancom.com/hoffice/multi/ko_kr/hwp/table/table%28table%29.htm).


어절 유지 뒤 소폭 자간 후보의 실제 효과 비교는 [어절과 긴 표](word-flow.md)를 따른다. 기존 safe_format의 한계는 그대로이며, 고정 78mm 열의 0→-1 효과와 75mm의 -3/-4 무효 사례를 구분했다. 문단 전체 글자 밀도와 전 페이지를 확인한다.
