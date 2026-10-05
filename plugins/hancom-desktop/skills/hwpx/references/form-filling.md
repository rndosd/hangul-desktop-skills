# 기존 양식 채우기 — 로컬 CLI 0.3.1

`form_fill.py`는 기존 표의 라벨로 목표 셀을 찾고 **이미 있는 문단**을 채운다.
python-hwpx 6.3.0의 public run API만 쓰며 XML은 조회·보존 비교에만 사용한다.
설치된 로컬 CLI에서 사용한다. MCP 구현은 변경하지 않았다. 대표 3쪽 사례의 실제 한글 검증은 [자주 쓰는 편집](common-editing.md)에 기록하며 각 후보의 필요한 검증은 유지한다.

## 요청 계약

```json
{
  "schema": "hwpx.form-fill-request.v1",
  "fields": [
    {
      "id": "purpose",
      "label": "추진목적",
      "direction": "right",
      "table": 2,
      "expected_occurrences": 1,
      "paragraphs": [1, 3],
      "values": [["첫 번째 내용", "두 번째 내용"]]
    },
    {
      "id": "activities",
      "label": "활동",
      "direction": "right",
      "table": 3,
      "expected_occurrences": 2,
      "paragraphs": [1],
      "values": [["첫 활동"], ["둘째 활동"]]
    }
  ]
}
```

라벨은 셀의 직접 문단을 연결한 텍스트와 **정확히 일치**해야 한다. 여러 run에 나뉜 라벨은
연결해 찾지만 부분 검색·공백 정규화·의미 추측은 하지 않는다. 여러 문단에 걸친 라벨은 현재 지원하지 않는다.
table/section/row/column/paragraph/occurrence는 모두 1부터 시작한다. table은 spine 순서로 센 전체 표 번호이며
중첩 참고표도 번호에 포함된다. `table`과 `section`은 후보 범위를 명시적으로 좁히는 선택 조건이다.

`right`는 라벨 병합 범위의 오른쪽 경계, `below`는 아래 경계 바로 바깥의 소유 셀을 찾는다.
경계의 모든 좌표가 같은 실제 셀에 속해야 한다. 병합을 풀지 않으며 여러 셀로 이어지면 거부한다.
0.3.0에서는 `right`에 `target_row_offset`, `below`에 `target_column_offset`를 명시할 수 있다.
offset은 라벨 병합 범위 안의 0부터 시작하는 정수이며 해당 rowSpan/colSpan 미만이어야 한다.
예를 들어 3행 병합 라벨 오른쪽의 첫 행만 고르면 `target_row_offset: 0`이다.
생략 시 기존 경계 전체 검사와 거부가 유지된다. 첫 셀을 자동 선택하지 않으며 다른 방향의 offset,
음수·bool·범위 밖 값은 거부한다. 실제 선택 좌표와 소유 셀을 반드시 계획에서 검토한다.
반복 라벨은 section/표/행/열 순서로 정렬한다. 라벨 개수, expected_occurrences, values 바깥 배열 길이가
정확히 같아야 한다. 각 occurrence 안의 값 개수도 선택 문단 개수와 정확히 같아야 한다.
각 값을 영수증에 별도로 기록한다. 원본 순서에 맞는 요청인지 계획에서 확인한다.

`paragraphs`는 대상 셀의 기존 문단 번호 목록이다. 예의 `[1,3]`은 2번 문단을 보존한다.
문단이 부족하면 자동 추가하지 않고 중단한다. 각 값은 한 줄의 XML 유효 문자열이어야 한다.
여러 문단은 여러 값으로 명시하며 newline/탭을 문자열로 넣지 않는다. 최대 100개 문단 슬롯을 선택한다.

기본적으로 정확히 빈 텍스트만 채운다. 공백/안내문/기존 값이 있으면 `allow_replace: true`가 필요하며,
계획에서 이전 값과 교체할 값을 확인한다. 같은 요청의 라벨 셀을 다른 필드의 목표로 덮거나 같은 문단을
두 번 선택하는 것은 거부한다. 일부 필드만 성공해도 나머지 필드가 실패하면 전체 출력이 거부된다.

## 명령

새 JSON/HWPX 파일 이름을 쓴다. 아래는 해당 scripts 폴더 기준이다.

```powershell
python -X utf8 -B diagnose_edit.py source.hwpx --operation fill_form --request request.json
python -X utf8 -B form_fill.py inspect source.hwpx --request request.json --output new-inspection.json
python -X utf8 -B form_fill.py plan --inspection new-inspection.json --output new-plan.json
python -X utf8 -B form_fill.py apply source.hwpx new-filled.hwpx --plan new-plan.json --dry-run
python -X utf8 -B form_fill.py apply source.hwpx new-filled.hwpx --plan new-plan.json
```

inspect에서 모든 라벨·좌표·병합 소유 셀·선택 문단·기존 내용·채울 값·반복 순서를 검토한다.
plan은 원본 hash와 요청 hash 및 모든 조회 결과에 연결된다. apply는 원본에서 다시 라벨을 찾고
전체 계획을 재계산해 비교한다. 누락한 필드·값 변경·오래된 원본·계획 변조는 거부한다.
dry-run도 편집 후보 저장·재열기·open-safety·전체 보존 검사를 수행하며 출력만 게시하지 않는다.

## 서식·보존·지원 경계

빈 문단은 기존 첫 plain run에 넣고 나머지 빈 run을 유지한다. 기존 값을 교체하면 비어 있지 않은
run의 원래 길이만큼 분배하고 초과 글자는 마지막 비어 있지 않은 run에 넣는다. 기존 run과
글자/문단 서식 참조는 유지한다. 의미에 따라 새 글자의 서식을 추측하지 않는다.
셀 전체 `set_text`/`clear_text`, raw XML 쓰기, 표·행·문단 추가/삭제는 하지 않는다.

공유 `safe_edit.apply_run_updates`가 모든 XML 구조/속성/텍스트/tail과 Preview 외 바이너리, 원본 hash를
검사한다. 제외는 Preview와 선택한 문단의 lineSegArray뿐이다. 잘못된 API 결과·비대상 내용이나
서식의 변화·그림 바이너리 손상은 최종 출력 탈락이다. 새 출력은 동일 폴더에서 원자적 hard link로
게시하고 기존 파일은 덮어쓰지 않는다. 지원하지 않는 파일 시스템에서는 중단한다.

중첩 표를 가진 대상 셀/안쪽 셀, 컨트롤/필드/탭/네이티브 줄바꿈 등 혼합 구조의 선택 문단,
기존 plain run이 없는 문단, native 누름틀/양식 개체, 본문 inline `라벨: 빈 칸`과 별도 story는 지원하지 않는다.
다른 셀의 중첩 참고표·결재란·그림·머리말은 보존 검사 대상이다. 누름틀의 안내문을 보이는 평문과 같은
것으로 취급하지 않는다. 한컴의 [누름틀 도움말](https://help.hancom.com/hoffice/multi/ko_kr/hwp/insert/madanginfo/madanginfo%28press%29.htm)은
필드의 별도 입력/편집 동작을 설명하며, 여기서 그 API를 구현한 것은 아니다.

`PASS_STRUCTURE`와 `all_requested_fields_resolved=true`는 코드/패키지 계약 결과다.
`native_open/native_render=not_checked`, `visual_review=not_performed`,
`completion=filled_candidate_native_pending`을 유지한다. 줄바꿈/넘침/잘림과 저장 후 재열기,
실사용 승인에는 정확한 후보의 전체 한글 native 검증이 필요하다. 점수로 필수 실패를 상쇄하지 않는다.

public API 확인: [python-hwpx v6.3.0 run.py](https://github.com/airmang/python-hwpx/blob/v6.3.0/src/hwpx/oxml/run.py).
`run.text` setter는 다른 텍스트 노드도 다룰 수 있으므로, 이 구현은 plain t가 정확히 하나인 기존 run 또는 한글이 저장한 자식 없는 서식 run만 허용한다. 후자는 form_fill 및 별도 빈 반복 영역 경로에서만 허용하고, 기존 run/charPrIDRef를 유지하며 public setter로 t 하나를 추가한 예상 구조를 전체 비교한다.
빈 텍스트 삽입은 이 제한 안에서 setter로 처리하고, 비어 있지 않은 run은 replace_text를 사용한다.


내용에 맞춘 칸 높이·빈 반복 행 조절이 요청되면 [기존 양식 변형](form-adaptation.md)의 form_adapt.py를 사용한다. 기존 필드 채우기 계약은 그대로 두고 별도 검증한 반복/크기/흐름 경로를 원자적으로 합성한다. form_fill 자체가 행·문단을 생성하는 것은 아니다.
