# 지정 위치 텍스트 편집 — 0.1.0 기능, 현재 로컬 CLI 0.3.1

기존 HWPX 문서의 지정 내용만 바꾼다. 설치된 로컬 CLI 기능이며
python-hwpx **6.3.0** public `HwpxOxmlRun.replace_text`를 사용한다.
0.2.0부터 양식 채우기와 원본/출력 보존 엔진을 공유한다.
ZIP/XML을 읽어서 대상과 보존 조건을 검사하지만 직접 XML을 써서 고치지 않는다.
기존 `safe_replace.py`와 COM/실한글 검증 경로도 유지한다.

## 지원 범위

- 한 문단 안의 여러 run에 나뉜 문구. 각 run은 자식 없는 plain t 하나여야 한다.
- 0.3.0은 각 section의 첫 직접 본문 문단에 있는 선행 무텍스트 secPr/colPr 메타데이터 run만
  그대로 보존하고 건너뛴다. secPr 또는 colPr만 든 ctrl 외의 자식, p/t/tbl/pic/필드가 포함되면 거부한다.
  텍스트와 컨트롤이 같은 run에 섞인 문단으로 지원을 넓힌 것은 아니다.
- 일반 표 셀, 병합 셀의 실제 소유 셀 안의 지정 문단. 표 번호·행·열·문단은 1부터 시작한다.
- 같은 문구가 여러 문단/셀/같은 run에 반복될 때, 명시적으로 선택한 위치만 수정.
- 원본 좌표 기준 최대 100개 비중첩 요청을 한 번에 처리. 일부 요청 실패 시 전체 출력 거부.
- 표·병합·테두리·여백·결재란·그림·비대상 텍스트/서식을 유지하는 보존 검사.

중첩 표를 포함한 대상 셀 및 안쪽 셀, 필드/탭/줄바꿈/그림/혼합 markup가 섞인 대상
문단, 머리말·꼬리말 등 별도 story, 문단을 가로지른 검색과 구조 변경은 거부한다.
본문의 지원된 문구를 수정하면서 다른 곳의 중첩 표·결재란·그림은 보존할 수 있다.
셀 전체의 set_text/clear_text는 편집에 사용하지 않는다. 빈 셀 채움과 새 줄 삽입은
이 첫 묶음에 포함하지 않는다. 레거시 HWP 직접 편집도 포함하지 않는다.

병합 좌표는 읽어서 실제 소유 셀에 연결한다. row/column 범위가 겹치거나 빈 소유 좌표가
있는 표는 거부한다. 잘못된 표를 자동으로 다시 구성하거나 병합을 풀지 않는다.

## 작업 순서

작업 폴더의 Python에서 작업본 scripts를 지정한다. 아래 scripts 경로는 이 스킬 기준이며
JSON/HWPX 출력은 항상 새로운 파일 이름을 쓴다. CLI는 실제 쓰기를 하는 MCP에 주입되지 않는다.

```powershell
python -X utf8 scripts/diagnose_edit.py source.hwpx --operation selected_text --find "기존문구"
python -X utf8 scripts/safe_edit.py inspect source.hwpx --find "기존문구" --output new-targets.json
# 특정 셀로 후보를 좁힐 경우:
python -X utf8 scripts/safe_edit.py inspect source.hwpx --find "기존문구" --table 2 --row 1 --column 2 --output new-cell-targets.json
python -X utf8 scripts/safe_edit.py plan --inspection new-cell-targets.json --target "검토한 target_id" --replace "수정문구" --output new-plan.json
python -X utf8 scripts/safe_edit.py apply source.hwpx new-candidate.hwpx --plan new-plan.json --dry-run
python -X utf8 scripts/safe_edit.py apply source.hwpx new-candidate.hwpx --plan new-plan.json
```

inspect 결과의 `scope`, 문맥, 문자 범위와 `supported`를 확인한다. 같은 문구 중 첫 항목을
자동 선택하지 않는다. plan의 `--target`을 반복하면 같은 치환을 명시한 여러 위치에 적용한다.
다른 치환을 한 batch에 넣을 경우 같은 원본의 inspection에서 선택한 target_id/find/replace를
plan.edits에 넣는다. apply는 계획 내용과 별개로 원본 hash와 모든 대상을 다시 검사한다.
계획은 원본 내용에 연결되며 원본이 바뀌면 새 inspect/plan이 필요하다.

dry-run도 public API 편집·재열기·open-safety·전체 보존 검사를 실행하고 출력만 생성하지 않는다.
run_diff와 모든 선택을 검토한 후 같은 원본/계획으로 apply한다. 출력은 같은 폴더의 임시
후보에서 원자적 hard link로 게시한다. 새 출력이 이미 있거나 파일 시스템이 이 게시 방식을
지원하지 않으면 중단하고, 파일 덮어쓰기/copy fallback은 하지 않는다.

## 글자 서식과 조판

문구가 여러 run에 걸치면 원래 매칭 부분 길이만큼 새 문구를 각 run에 배분하고,
추가 글자는 마지막 매칭 run에 넣는다. 짧아지거나 삭제되어도 run과 charPrIDRef를 지우지 않는다.
매칭 밖 접두·접미 텍스트와 그 서식을 유지한다. 이 정책은 plan의
`preserve-matched-run-lengths-extra-in-last-run`로 명시하며 다른 정책은 거부한다.
새 글자의 서식을 의미로 추측하지 않는다. run 경계에 의미가 있으면 dry-run 분배를 확인한다.

비교는 모든 XML 노드·속성·텍스트·tail 및 Preview 외 바이너리를 확인한다.
Preview와 **선택한 문단만**의 lineSegArray 캐시는 제외하고 영수증에 기록한다.
다른 문단의 캐시를 전체적으로 무시하지 않는다. 미선택 내용·서식·그림의 변화는 출력 탈락이다.

`PASS_STRUCTURE`는 변경 후보의 구조 검사 완료다. receipt에는 native_open/native_render가
not_checked, visual_review가 not_performed, completion이 edited_candidate_native_pending으로 남는다.
길이 변화량도 기록하지만 줄바꿈·잘림의 실제 판정이 아니다. 내용 누락, 요청하지 않은 변경,
파일 손상은 필수 탈락 조건이며 점수나 시각 검증 미실행으로 가리지 않는다.

인쇄/실사용 완료에는 기존 `hwpx-windows-finalize`의 정확한 후보 열기·필요한 출력/재저장과
전체 native 페이지 검토가 필요하다. 실제 한글 검증을 HTML/구조 pass로 대체하지 않는다.
COM 정책·보안 모듈·권한 때문에 막히면 그대로 미검증을 보고하고 우회/자동 설정 변경하지 않는다.

## 검증과 근거

```powershell
python -X utf8 -B -m unittest -v test_safe_edit test_safe_replace test_diagnose_edit
```

명령은 scripts 폴더에서 실행한다. tests는 모두 합성 파일이며 실제 한글 조판의 증거가 아니다.
최종 수량·전후 산출물·검증 한계는 작업 폴더의 개선 결과 보고서를 따른다.

- API 확인: [python-hwpx v6.3.0 run.py](https://github.com/airmang/python-hwpx/blob/v6.3.0/src/hwpx/oxml/run.py).
- 형식 참고: [한컴 OWPML 모델](https://github.com/hancom-io/hwpx-owpml-model).
- 한글 자체의 셀·서식 기능: [공식 표 탭 도움말](https://help.hancom.com/hoffice/multi/ko_kr/hwp/toolbox/object_table.htm).
- 블록 입력은 기존 내용을 없앨 수 있다는 [공식 블록 도움말](https://help.hancom.com/hoffice/multi/ko_kr/hwp/edit/block.htm).
- COM 표 ID 선택의 한글 2024 제한: [공식 개발자 포럼](https://forum.developer.hancom.com/t/topic/2114).
- [Automation 및 보안 승인 모듈 안내](https://developer.hancom.com/hwpautomation).

한글 프로그램에 기능이 있다는 사실과 이 제한 편집기가 그 기능을 지원한다는 사실은 구별한다.
위 문서를 참고했으며 외부 구현을 복사하거나 설치하지 않았다.

대표 사례의 실제 한글 검증과 다음 지원 우선순위는 [자주 쓰는 편집](common-editing.md)을 따른다. 위 PASS_STRUCTURE 영수증만으로 native 완료를 판정하지 않는 계약은 유지한다.
