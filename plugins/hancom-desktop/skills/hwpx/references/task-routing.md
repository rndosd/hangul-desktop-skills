# 기능별 경로 및 참조

현재 SKILL.md의 경로 선택·실패 정책을 우선한다. 아래는 필요한 도구와 참조를 찾는 색인이다.

## 케이스 → 경로 라우팅 표

| 사용자 요청 패턴 | 1차 경로 (MCP 도구) | 상세 참조 |
|---|---|---|
| 낯선 기존 문서의 구조 탐색 + 본문·표 셀·기존 단순 머리글 story·블록 이종 편집·이동·복사 | `get_document_node` → `query_document_nodes` → `apply_document_commands` (dry-run → commit) | [workflows-agent-document](workflows-agent-document.md) |
| 지원 문서·결재/양식 블록을 다른 HWPX로 안전하게 이식 | `get_document_node`/`query_document_nodes` → `dump_document_blueprint` → `replay_document_blueprint` (dry-run → commit) | [workflows-agent-blueprint](workflows-agent-blueprint.md) |
| 일반 복합 HWPX 읽기·편집·생성 (아래 전문 양식·시험 경로 제외) | `start_workflow` → `continue_workflow` → 필요 시 `approve_workflow_decision` | [workflows-autonomous](workflows-autonomous.md) |
| 최종 산출물을 실제 한컴으로 렌더·검증 | `render_health` → `render_submit` → `render_status` | [workflows-real-hancom-render](workflows-real-hancom-render.md) |
| 양식 채움·기존 좌표 편집용 구조·표·필드·앵커 지도 | `get_document_map` | [workflows-editing](workflows-editing.md) |
| 텍스트·개요·표 내용 읽기 | `get_document_text` · `get_document_outline` · `get_table_text` | [api](api.md) |
| Markdown/HTML/JSON 변환·추출 | `hwpx_to_markdown` · `hwpx_to_html` · `hwpx_extract_json` · `document_to_markdown` · `document_extract_json` | [api](api.md) |
| 런서식(굵게·색·크기·글꼴) + 각주/미주 본문까지 충실 읽기 | `hwpx_extract_json` (`format_detail`·`doc.notes[]`) · `hwpx_to_markdown` (각주 부록) | [workflows-reading](workflows-reading.md) |
| 일반 텍스트 위치 찾기 | `find_text` | [workflows-editing](workflows-editing.md) |
| 이미 canonical path가 확정된 본문·표 좌표와 기존 단순 머리글 story 편집 (2건 이상) | `apply_document_commands` (dry-run → commit) | [workflows-agent-document](workflows-agent-document.md) |
| 바이트-스플라이스 다단 편집(표 구조+본문+셀 채움 혼합, 실패 시 부분 적용이 허용 안 되는 작업) | `run_edit_plan` (계획 1파일, `dry_run=true` → 실행 — all-or-nothing 원자, 개별 도구 연타 금지) | [workflows-editing](workflows-editing.md) |
| 단건 치환·문단·표 셀 편집 | `search_and_replace` · `batch_replace` · `insert_paragraph` · `set_table_cell_text` | [workflows-editing](workflows-editing.md) |
| 직전 편집 되돌리기 | `undo_last_edit` | [workflows-editing](workflows-editing.md) |
| 줄간격·정렬·들여쓰기·문단 간격 변경 | `set_paragraph_format` | [workflows-editing](workflows-editing.md) |
| 용지 크기·방향·여백·단 설정 | `set_page_setup` | [workflows-editing](workflows-editing.md) |
| 머리글/바닥글 추가·수정 | `set_header_footer` | [workflows-editing](workflows-editing.md) |
| 쪽번호 추가·수정 | `set_page_number` | [workflows-editing](workflows-editing.md) |
| 기존 문단을 불릿/번호 목록으로 | `set_list_format` | [workflows-editing](workflows-editing.md) |
| 그림 삽입 / 그림만 교체 | `insert_picture` · `replace_picture` | [workflows-editing](workflows-editing.md) |
| 굵게·색·글꼴 등 글자 서식, 사용자 스타일 | `format_text` · `create_custom_style` · `list_styles` | [workflows-editing](workflows-editing.md) |
| 표 병합·분할·머리행·테두리(선 종류/색/굵기)·셀 음영 | `merge_table_cells` · `split_table_cell` · `format_table` | [workflows-editing](workflows-editing.md) |
| 검토 메모 추가·삭제 | `add_memo` · `add_memo_by_anchor` · `remove_memo` | [workflows-editing](workflows-editing.md) |
| 충실도 민감·대형 문서의 문단 텍스트 패치 | `byte_preserving_patch` | [workflows-editing](workflows-editing.md) |
| 생성/편집 후 레이아웃 확인 | `render_preview` self-check 루프 | [workflows-editing](workflows-editing.md) |
| 한컴 없이 수식 포함 문서 스크롤 통독 검수 | `render_preview(viewer=true, screenshot="off")` | [workflows-preview](workflows-preview.md) |
| 자연어 요청으로 새 문서 생성 | `validate_document_plan` → `create_document_from_plan` | [workflows-creation](workflows-creation.md) |
| Markdown/비-HWPX 원본에서 HWPX 초안 생성 | `document_to_markdown` → `markdown_to_document_plan` → `create_document_from_plan` | [workflows-creation](workflows-creation.md) |
| 공문·보고서·가정통신문 (유형별 한컴 양식 프로파일 + 공문 구조 hard-gate·결문 메타·맞춤법 정직보고) | `create_document_from_plan` (`metadata.document_type` + `gyeolmun`) | [workflows-authoring](workflows-authoring.md) |
| 살아있는 목차(한컴이 재계산)·쪽 번호 상호참조 | `add_toc` · `add_cross_reference` · `verify_toc` | [workflows-toc](workflows-toc.md) |
| 변경추적 redline 저작 (삽입/삭제/치환 + 코멘트, 사람이 한컴서 수락/거부) | `add_tracked_edit` (+ `add_memo_by_anchor`) | [workflows-redline](workflows-redline.md) |
| 개인정보(PII) 탐지·마스킹 (읽기·추출 기본 마스킹, 쓰기 입력 사전 정제) | `scan_personal_info` · 읽기/추출 `mask` param | [workflows-pii](workflows-pii.md) |
| 정부보고서·공문형 보고서 (□/○/※ 불릿) | `parse_government_report_text` → document plan 구성·검증 → `create_document_from_plan` | [workflows-creation](workflows-creation.md) |
| 운영 계획서 제출 후보 | document-plan + `quality_profile="operating_plan"` | [workflows-creation](workflows-creation.md) |
| 운영 계획서 하우스 스타일·섹션칩 변주 | skill이 genre/profile/variable slot 판단 → 기존 document-plan MCP 경로 | [workflows-house-style](workflows-house-style.md) |
| 제안서·기획안 | proposal document plan → `create_document_from_plan` → `inspect_document_quality` | [workflows-creation](workflows-creation.md) |
| 기안문 서식 저작 (별지 제1호 일반기안문 / 제2호 간이기안문) | `compose_official_draft` · `compose_simple_draft` → `validate_document_plan` → `create_document_from_plan` (결재란 칸은 결재자 수만큼만·결문 라벨 미인쇄·선택항목은 `[ ]`+√) | [workflows-authoring](workflows-authoring.md) |
| 체크박스 양식개체가 실제로 쓰이는 서식(공문서 아님) | `add_check_box` 계열 core API (공문서는 `[ ]` 텍스트 관례) | [workflows-authoring](workflows-authoring.md) |
| 공문서 작성규정 lint·결재란 | `inspect_official_document_style` | [workflows-creation](workflows-creation.md), [규정](official-document-rules.md) |
| 직인/관인 날인 (발신명의 끝글자에 도장) · 날인 규정 pass/fail 검사 | `place_seal` · `check_seal_compliance` | [workflows-forms](workflows-forms.md) |
| 출제 md를 학교 시험지 양식에 재조판 (문항 keep-together, 그림은 placeholder) | `compose_exam` · `verify_question_splits` | [workflows-exam](workflows-exam.md) |
| LaTeX 수식을 네이티브 `<hp:equation>`으로 삽입 (커버리지 밖 typed 거부) | `add_equation` | [workflows-authoring](workflows-authoring.md) |
| 데이터 시리즈를 네이티브 차트로 삽입 (막대·꺾은선·원, 밖은 typed 거부) | `add_chart` | [workflows-authoring](workflows-authoring.md) |
| 운영계획서를 백지에서 장르-충실하게 저작(섹션칩·개조식·박스 조직도) | `get_genre_grammar` · `compose_section_chip` · `add_boxed_org_chart` | [workflows-authoring](workflows-authoring.md) |
| **평가계획(교수학습운영 및 평가계획) 전문 채움** (J1~J6 두뇌 판단·붙여넣기용 MD 저작) | `apply_evalplan_fill(filename=..., review_md=..., output=..., phase="clean", render_check="required", score_gold_path=...)` → 필요 시 advanced `score_form_fill` | [workflows-evalplan](workflows-evalplan.md) |
| 낯선 양식·누름틀·라벨 셀·경로 셀·표 밖 본문이 섞인 채움 | `analyze_form_fill(plan=...)` → plan 승인 → `apply_form_fill(plan=...)` (`plan.dryRun` dry-run → commit) → `verify_form_fill(plan=...)` | [workflows-forms](workflows-forms.md) |
| 메일머지 N부 대량생산 (상장·수료증·안내장·명부 CSV/XLSX) · 셀 넘침 격리(fit) | `mail_merge` (`fit_mode`) | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 표 합계·평균·소계 계산 | `table_compute` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 두 문서/문단 비교 (신구 diff) | `doc_diff` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 신구대조표 문서 생성 | `doc_diff` → comparison document plan → `create_document_from_plan` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 사진대지 생성 | `build_image_grid` → `create_document_from_plan` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 회의 명패 생성 | `build_meeting_nameplates` → `create_document_from_plan` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 조직도 생성 | `build_organization_chart` → `create_document_from_plan` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 참조 문서 서식 이식·템플릿 등록 | `extract_style_profile` · `apply_style_profile_to_plan` · `register_template` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 붙임·표/그림 번호 정합성 검사 | `inspect_reference_consistency` | [workflows-bulk-compare](workflows-bulk-compare.md) |
| 깨졌거나 한컴에서 안 열리는 파일 | `repair_hwpx` (복구 복사본 생성) | [api](api.md) |
| 원본 보존용 사본 만들기 | `copy_document` | [api](api.md) |
| Windows에서 구형 `.hwp`를 `.hwpx`로 변환한 뒤 처리 | 설치된 `HwpxConverter.exe`를 명령줄로 실행 → 생성 파일 재열기 검증 | [workflows-hwp-conversion-windows](workflows-hwp-conversion-windows.md) |
| MCP 없음: 텍스트 추출·표 포함 전역 치환 | `scripts/text_extract.py` · `scripts/zip_replace_all.py` | [api](api.md) |


## 참조 인덱스

- [`references/workflows-autonomous.md`](workflows-autonomous.md) — 서버 강제 5-family workflow, decision/재개/needs_review/사전 렌더 영수증 계약.
- [`references/workflows-agent-document.md`](workflows-agent-document.md) — 낯선 문서 semantic view/query, canonical path, 본문·표 셀·기존 단순 머리글 story의 원자 set과 add/remove/move/copy batch, structured failure와 CLI replay.
- [`references/workflows-agent-blueprint.md`](workflows-agent-blueprint.md) — typed `.hwpxbp` dump/inspect/repack, portable/source-bound dependency mapping, atomic replay, strict fidelity와 real-Hancom 검증.
- [`references/workflows-real-hancom-render.md`](workflows-real-hancom-render.md) — 비동기 실한컴 제출·폴링·artifact provenance·취소·degraded 처리.
- [`references/workflows-editing.md`](workflows-editing.md) — 트랜잭션 편집 루프, 서식 5종, 그림, byte patch, render_preview.
- [`references/workflows-creation.md`](workflows-creation.md) — document-plan, builder, 정부보고서, 운영계획서, 제안서, 공문서 레시피.
- [`references/workflows-redline.md`](workflows-redline.md) — 변경추적 저작(insert/delete/replace + 코멘트), 사람이 한컴서 수락/거부, verify 영수증. `add_tracked_edit`.
- [`references/workflows-pii.md`](workflows-pii.md) — 개인정보(PII) 탐지, 읽기·추출 기본 마스킹, 폼필·메일머지 입력 사전 정제 + 가명/비식별. `scan_personal_info` · 읽기/추출 `mask` param.
- [`references/workflows-reading.md`](workflows-reading.md) — 런서식(굵게·색·크기·글꼴)+각주/미주 본문 충실 읽기. `hwpx_extract_json`(`format_detail`·`doc.notes[]`)·`hwpx_to_markdown` 각주 부록, `document_to_markdown` 로컬 ingest.
- [`references/workflows-toc.md`](workflows-toc.md) — 네이티브 자동 차례·상호참조(재페이지네이션 시 한컴이 재번호). `add_toc`·`add_cross_reference`·`verify_toc`.
- [`references/workflows-preview.md`](workflows-preview.md) — 한컴 없는 스크롤 통독 문서 뷰어(수식 MathML 렌더 fail-closed 3단계), 환경별 전달(Claude Code=Artifact/Codex=local open), 충실도 티어 정직 라벨. `render_preview(viewer=true)`.
- **처음 이 스킬로 HWPX 작업 시작 시**: `describe_capabilities`로 실제 FastMCP 작업군을 확인한다. 정확한 default/advanced/필수 도구 계약은 자동 생성된 [`tool-contract.generated.md`](tool-contract.generated.md)가 정본이다.
- [`references/workflows-forms.md`](workflows-forms.md) — canonical mixed-form plan/apply/verify, 평가계획 facade, legacy replacement 경계.
- [`references/workflows-evalplan.md`](workflows-evalplan.md) — 평가계획 실채움 두뇌 판단(J1~J6): 붙여넣기용 MD 저작, `phase="clean"` 대표 경로, 신규 지시문·정상 본문 구별·측면 매핑·변형 선택·렌더 해석. 스코어≠제출가능·오너 검수 권위.
- [`references/workflows-exam.md`](workflows-exam.md) — 시험지 조판: 출제 md→학교 양식 재조판, 문항 keep-together, 커브-export 정직 게이트(시각 증거).
- [`references/workflows-bulk-compare.md`](workflows-bulk-compare.md) — 메일머지, 표 계산, 신구대조, 생성기 3종, 스타일 프로파일/템플릿.
- [`references/evidence-contract.md`](evidence-contract.md) — openSafety·visual-review v1·hard gates·제출 증거 계약.
- [`references/api.md`](api.md) — python-hwpx 시그니처, MCP 도구 표, repair/recover, 번들 스크립트.
- [`references/workflows-hwp-conversion-windows.md`](workflows-hwp-conversion-windows.md) — Windows 한컴 `HwpxConverter.exe`를 이용한 구형 HWP→HWPX 무인 전처리와 검증.
- [`references/migration-mcp-5.0.md`](migration-mcp-5.0.md) — 5.0 경계: 제거 5종 대체표, DEPRECATED 1군, 2군 권장 경로.
- [`references/official-document-rules.md`](official-document-rules.md) — 공문서 항목 표시·끝 표시·붙임·날짜/금액 규칙.
- [`references/migration-core-5.0.md`](migration-core-5.0.md) — python-hwpx 5.0에서 응용 워크플로가 MCP로 이동한 내역과 직접 import 사용자를 위한 대체표.
- 설치 직후 최소 검증: `python3 examples/01_create_and_save.py` → `python3 scripts/text_extract.py examples/out/01_created.hwpx`.
