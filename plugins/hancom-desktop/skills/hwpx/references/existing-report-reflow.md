# 기존 강제 쪽 나눔과 고정 목차 숫자

HWP062 후보의 별도 제한 경로다. 일반 body-structure의 거부를 우회하거나 모든 control 문단을 허용하지 않는다. 빈 공간을 줄이라는 요청에서 원래 내용·표·그림·여백을 보존하고 특정 불필요한 강제 나눔을 풀 때만 사용한다. 다른 의도한 구분·표지·빈 쪽은 먼저 식별해 보호한다.

`report_reflow_cli.py inspect-flow SOURCE --index ROOT_INDEX`와 `inspect-toc SOURCE`는 읽기 전용 binding을 반환한다. `apply SOURCE NEW_OUTPUT --request REQUEST.json --dry-run`으로 전체 package 보존을 검사한 뒤 같은 입력·요청의 실제 apply를 수행한다. 원본/출력을 덮어쓰지 않는다. 해당 candidate_runtime의 core6.3.0을 사용한다.

요청의 최상위 키는 schema=`hwpx.report-reflow.v1`, sourceSha256, editableReason, flow, toc다. flow 항목은 `{binding:실제검사결과, changes:{pageBreak:false, keep_with_next:true}}`처럼 정확한 bool을 지정한다. pageBreak는 문단 instance 속성, page_break_before와 keep_with_next는 참조 paraPr.breakSetting 속성이므로 둘 다 읽는다. 최대6개 기존 root 대상만 허용한다. plain 본문 또는 중첩 없는 inline1행1열 제목 표만 지원한다. field/story/picture/ctrl/outline/다단 등은 거부한다. 파생 스타일만 만들고 기존 공유 정의를 수정하지 않는다.

toc 항목은 `{binding:실제검사결과, number:실제출력번호}`다. 기존 로마숫자 장 번호·단일 탭·탭 뒤 공백+숫자 tail 형식만 지원한다. public Run.replace_text로 숫자 tail을 바꾸고 기존 탭 width/leader/type·run 서식을 보존한다. native 자동 목차·복수 탭·field·중첩 표·임의 도형 구조 편집을 지원하지 않는다. 목차 문단은 도형 drawText 안에 있을 수 있으므로 표라고 가정하지 않는다.

쪽 흐름 수정→실제 한글 OpenOnly PDF에서 각 장의 실제 표시 번호 확인→고정 목차 숫자 갱신→실제 SaveAs/Clear/Open/PDF→저장본 반복 저장·재열기 순서로 검증한다. 실제 제목은 같은 문구의 요약 도식과 구분해 원래 번호·원본 위치/서식에 바인딩한다. PDF 숫자가 제목/점선과 같은 line에 합쳐질 수 있으므로 오른쪽 숫자 단어의 좌표와 기준선으로 확인한다. keepWithNext만으로 배치를 가정하지 않고 제목과 후속 본문이 같은 한글 쪽인지, 희소 쪽이 해소됐는지 전쪽을 직접 본다. 이후 내용이 변하면 고정 목차도 다시 대조해야 한다.

HWP062 국토 기반 가상 저장본23→22쪽/46표/6그림, 다른 표지 보고서3→2쪽에서 제한 범위를 확인했다. 각 저장본 재열기 PDF는 저장 전 PDF와 동일하며 내용·실제 적용 서식은 독립 확인했다. 첫 국토 저장의 미사용 문단 정의 삭제는 엄격 FAIL/기존 gate blocked로 남겼다. 바이트/전체 정의 동일·타 PC·전체 기능 지원으로 확대하지 않는다. 다른 PC는 현재 runtime/한글/검증된 공식 DLL 준비와 실제 native 출력 검증이 필요하다. 보안 정책/승인창 처리 변경은 이 기능에 포함하지 않는다.

편집 엔진과 공개 page_break wrapper는 native 배치 전에 고정됐다. 이 CLI/안내는 배치 완료 뒤 붙인 얇은 전달 경로이며, 기존 native 검증을 CLI 자체의 E2E 인증으로 확대하지 않는다. 실행 결과와 정확한 후보 해시는 HWP062의 execution-contract/candidate-files/summary에서 확인한다. 설치된 사용자 스킬은 교체하지 않았다.
