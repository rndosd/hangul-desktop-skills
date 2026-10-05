# 길어진 기존 표의 쪽 흐름과 제목행

새 내용을 넣어 표가 길어진 경우에만 선택해 사용한다. 내용 형식이나 전역 여백의 의무 규칙이 아니다. 원본 실제 출력에서 잘림·제목행 누락·앞 설명의 고립을 먼저 확인한다.

[한컴 공식 표 설명](https://help.hancom.com/hoffice130_assistant/ko-KR/Hwp/table/tableattribute/table%28table%29.htm)에 따르면 글자처럼 취급한 표는 여러 쪽 나눔을 지원하지 않으며, 제목행 반복은 첫 줄의 제목 셀 지정도 필요하다. 속성값만 보고 성공으로 판정하지 않는다.

`scripts/expanded_table_flow_cli.py inspect SOURCE --table N --header-rows 1 [--caption "바로 앞 설명 전체"]`로 원본 해시·표 전체·셀·앞 설명 binding을 구한다. 요청 schema는 `hwpx.expanded-table-flow.v1`, 정확한 키는 schema/sourceSha256/binding/convertInline/pageBreak/outsideSpacingHwpunit/editableReason이다. `apply SOURCE NEW_OUTPUT --request REQUEST --dry-run` 후 사본에 적용한다. 출력 덮어쓰기·오래된 binding·불리언 숫자·예상 밖 키는 거부한다. 사유는8자 이상이며 셀·바이너리·구역·공유 정의를 독립 비교한다.

두 경로의 범위를 구분한다.

- **명시적 inline 변환**: 본문에 직접 속한 하나의 잠금 없는 일반 표, noAdjust=0, 단순 병합 없는 셀 격자, 첫1행 제목, PARA/COLUMN 기준·offset0·flowWithText1·겹침 금지·TOP_AND_BOTTOM 배치만 지원한다. 바로 앞 plain 설명이 있어야 한다. convertInline=true, pageBreak="TABLE"; outsideSpacingHwpunit은 top/bottom 각각200~1800(2~18pt) 중 필요한 값을 선택한다. 시험값600/800(6/8pt)은 기본 의무값이 아니다. 글자처럼 취급을 해제하고 본문 기준점 유지, 제목 셀·반복, 설명 keepWithNext만 명시적으로 바꾼다. 문서 내용 편집 범위에서 이 배치 변경 의도를 먼저 확정한다.
- **기존 floating 병합 제목행**: convertInline=false, pageBreak=null, outsideSpacingHwpunit={}이고 caption은 생략한다. 첫1~3행의 실제 소유 셀에만 제목 flag를 설정한다. 표는 최대20열/100행이며 제목/본문을 가로지르는 병합과 보호 셀은 거부한다. noAdjust=1인 기존 표도 이 제목 flag만 바꾸는 경로에 한해 허용한다. 크기·span·나눔 방식·배치는 바꾸지 않는다. 일반 표 편집의 고정 크기 가드를 완화하지 않는다.

HWP064 시험에서 국토 업무계획 기반 이전 가상 사본의 표43을11행으로 늘려 실제 잘림을 재현했다. 동일 내용으로3쪽에 나눠 전체 문구와 제목행을 확인했다. 실제 저장본에 같은 행 추가를 다시 적용해12행도 확인했다. 별도 전남 평가보고서 사본의18열/3단 병합 머리행은 논리8·9쪽에 반복했다. 기존 통계·span·셀 크기·noAdjust를 유지했다. 다른 표나 모든 문서에 대한 인증은 아니다.

적용 후 실제 한글에서 열기→저장→저장본 재열기→PDF→반복 저장/재열기를 검증하고 모든 출력 쪽·원래/신규 문구·표 크기·목차를 확인한다. 첫 국토 저장에서 선택 표의 전체 높이와 새 문단 끝 빈 run 구성이 재구성돼 strict FAIL이 남았다. 실제 문구·셀 크기·나머지 적용 서식과 지면은 보존됐다. 빈 끝 run에 삽입할 때의 기본 caret 서식은 미검증이다. 내부 실패를 시각적 성공으로 덮지 않는다. 실제 저장본에 행을 다시 추가한 편집과 전남 제목행은 strict PASS였다.

모아찍기에는 문서 내에서도 가로면 좌우2쪽과 세로면 상하2쪽이 섞일 수 있다. 원본의 인쇄면 크기·footer 위치·번호·실제 지면으로 논리쪽 clip을 확정하며 페이지 수나 방향만으로 보편적으로 추정하지 않는다.

마지막1~3줄 넘침의 선택적 여백 조절은 기존 `native_vertical_fit.py`의 원본 분석·제한 후보·native 검증을 사용한다. 본 HWP064는 stepMilliMm=500/maxAttempts=1/minimumHwpunit=2835의 요청으로 위아래 각각0.5mm 한 후보만 시험했다. 2쪽의 마지막1줄이1쪽에 들어갔고 글자·좌우 여백·표·문구는 보존됐다. 연속 최솟값을 찾았다는 뜻이 아니며 긴 표 잘림을 전역 축소로 숨기지 않는다. 실패하면 보존하고 더 줄이려면 해당 요청 범위를 다시 정한다.
