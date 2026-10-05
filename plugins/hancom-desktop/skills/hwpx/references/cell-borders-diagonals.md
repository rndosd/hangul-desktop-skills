# 기존 셀의 혼합 테두리·대각선·배경색

`scripts/safe_cell_decoration.py`는 기존 셀 내용과 배치를 보존하고 지정한 선·채우기만 변경한다.
문서에 필요한 경우에 선택하며 보고서 목차나 내용 형식을 규정하지 않는다.

## 지원 범위

python-hwpx 6.3.0 전용. 평면 표 2~100행·1~12열, 기존 셀 1~20문단·문단당 1~20 run의 plain 텍스트와 native lineBreak tail을 보존한다.
표·행·열 번호는 1부터 시작하며 병합 셀은 정확한 소유 셀(앵커) 주소만 지정한다.
중첩 표·그림·필드·컨트롤·세로 쓰기, 보호 셀과 복잡한 대각선·중심선·3D·그림자는 이 경로에서 거부한다.

- `borders`: left/right/top/bottom 중 필요한 면만 지정한다. 선 속성은 type, width_mm, color 중 필요한 값만 명시하며 다른 값은 유지한다.
- `type`: NONE / SOLID / DOT / DASH. `width_mm`: 0.1 / 0.12 / 0.15 / 0.2 / 0.25 / 0.3 / 0.4 / 0.5. 색은 #RRGGBB.
- `diagonal.direction`: NONE(제거), NW_SE(＼), NE_SW(／), CROSS(둘 다). 선 속성은 일반 선과 같다. 제거할 때 기존 대각선의 선 스타일은 남기고 표시 방향만 끈다.
  한글 저장본에서 비활성 diagonal 요소가 생략된 경우도 다시 활성화할 수 있다. 활성 대각선의 스타일이 누락된 비정상 입력은 거부한다.
- `fill_color`: #RRGGBB 또는 null(채우기 제거). 기존 단색 채우기만 교체한다. 그림·그라데이션 채우기는 거부한다.

공유 경계선은 양쪽 셀에 같은 선을 적용한다. 영수증에서 명시 대상과 인접 셀의 반영 범위를 확인한다.
병합 이웃의 한 변 중 일부만 건드리면 거부한다. 같은 스타일로 그 변 전체를 명시하거나 요청 범위를 줄인다.
서로 다른 공유선 요청은 거부한다. 최대 명시 50셀, 인접 반영 포함 100셀.

**선 이름과 실제 모양:** 시험한 한글 2024에서는 OWPML `DASH`가 촘촘한 점 패턴, `DOT`가 긴 끊어진 선으로 출력됐다.
토큰의 영어 뜻만으로 ‘점선/파선’을 정하지 말고 이 PC의 실제 출력 예시로 요청한 모양을 확인한다.
시험 결과의 길이는 각각 약 1.20pt와 6.23pt였으며 다른 버전의 외관까지 보장하지 않는다.

대각선 추가는 기존 글자를 자동으로 옮기지 않는다. 문구와 선이 겹치는지 실제 한글 PDF에서 확인한다.
이번 합성 예시는 새 문서를 만들 때 문단 정렬·문단 간격으로 모서리 문구를 준비한 것이다.
임의 기존 셀의 글자를 자동 모서리 배치하는 기능으로 확대하지 않는다.

## 실행

Python 경로는 현재 PC의 environment.json에서 읽는다. 새 출력 경로만 사용한다.

```powershell
python -X utf8 scripts/safe_cell_decoration.py inspect source.hwpx --table 1 --output new-inspection.json
python -X utf8 scripts/safe_cell_decoration.py apply source.hwpx candidate.hwpx --request reviewed-request.json --dry-run
python -X utf8 scripts/safe_cell_decoration.py apply source.hwpx candidate.hwpx --request reviewed-request.json
```

```json
{
  "schema": "hwpx.safe-cell-decoration.v1",
  "source_sha256": "inspect에서 읽은 실제 SHA256",
  "table": 1,
  "edits": [
    {"row":3,"column":1,"borders":{"right":{"type":"NONE"}},"fill_color":"#EEF2F6"},
    {"row":2,"column":1,"diagonal":{"direction":"NW_SE","type":"SOLID","width_mm":0.3,"color":"#64748B"}}
  ]
}
```

중복 셀·알 수 없는 키·오래된 원본 해시는 거부한다. 원본과 기존 출력 파일을 덮어쓰지 않는다.
PASS_STRUCTURE / PASS_STRUCTURE_DRY_RUN은 구조 보존 결과이며 native 상태는 pending이다.
전달할 후보에 finalize prepare → SaveAs → collect → 실제 전체 쪽 검토 → check를 적용한다.

## 보존 구현과 확인 범위

core 6.3.0에 방향별 선·대각선 전용 public setter가 없어, 별도 검증한 **제한 스타일 복제 어댑터**를 사용한다.
public document/table/cell 바인딩과 set_cell_border_fill을 사용하고, 원래 borderFill 전체를 복제해 지정 속성만 바꾼 정의를 추가한다.
기존 공유 정의는 전부 유지한다. 선택 셀 및 공유 경계 이웃의 참조만 바꾸며 전체 예상 header/section과 비대상 패키지 바이트를 비교한다.
채우기는 core namespace의 fillBrush/winBrush를 사용한다. 셀 내용 쓰기나 임의 XML 폴백은 없다.

**기존 서로 다른 테두리를 가진 셀에 같은 색을 넣을 때 core의 set_cell_shading을 사용하지 않는다.**
채우기 색만으로 스타일을 합치는 기존 API의 동작으로 두 번째 셀 테두리가 바뀌는 문제가 재현됐다.
이 새 경로는 원래 테두리와 채우기를 함께 복제·검사하여 그 문제를 막는다. core 라이브러리를 패치한 것은 아니다.

2026-10-03, 한글 2024 13.0.0.3903 / core 6.3.0에서 편집 9종과 기준 1종을 실제 저장·재열기·PDF 출력,
전체 12쪽 시각 검토·strict gate complete로 확인했다. 각 셀의 실제 저장본 스타일, 글꼴·문단·크기·여백·텍스트를 독립 대조했다.
대각선 방향과 5개 혼합 대각선의 글자 겹침 없음, 같은 색에서 서로 다른 선 보존, 제거/복원 픽셀 일치,
3쪽 문서의 표지·마지막 쪽 픽셀 보존을 확인했다. 임의 복잡한 양식에 대한 포괄 보장은 아니다.
31개 가드/보존 시험은 Python -O에서도 통과했다. fixture는 assets/cell-decoration/source.hwpx이며 이전 cell-spacing fixture도 사용하는 회귀 시험이다.

[한컴 대각선 안내](https://help.hancom.com/hoffice130/ko-KR/Hwp/table/cellborder/cellborder%28diagonal%29.htm),
[테두리 안내](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/table/cellborder/cellborder%28border%29.htm),
[공식 OWPML 선 타입 정의](https://github.com/hancom-io/hwpx-owpml-model/blob/main/OWPML/Class/enumdef.h).
COM·보안 DLL·레지스트리 설정은 이 편집 도구에서 변경하지 않는다.
