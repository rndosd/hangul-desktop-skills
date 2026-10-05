# 레이아웃 검사와 지원 경계

관련 증상만 검사한다. 아래 도구는 문서를 고치지 않으며, 실제 한글 출력의 관찰과
자동 편집 지원은 별개다. `scripts/` 경로는 이 스킬 폴더 기준이다.
PDF 검사는 PyMuPDF(`fitz`)가 필요하다. 사용 가능한 HWPX 전용 Python을 확인하고
의존성이 없으면 미검사로 보고한다. 런타임 경로는 현재 PC의 environment.json에 있는 pythonPath를 사용한다.

## 먼저 증거를 연결한다

정확한 후보의 OpenOnly PDF 출력 영수증에서 입력 전후 SHA-256, PDF artifact SHA-256,
성공 상태와 정상 Quit를 실제 파일에 대조한다. PDF 파일명·출처 메모만으로 연결을 증명하지 않는다.
이전 PDF를 새 후보의 증거로 사용하거나 기존 영수증을 수정하지 않는다.
COM `PASS_FULL`은 실제 시각 검토의 대체물이 아니다.

## 지정어 줄바꿈

```powershell
python -X utf8 scripts/audit_hwpx_linebreaks.py preflight candidate.hwpx --term "대상어" --output new-preflight.json
python -X utf8 scripts/audit_hwpx_linebreaks.py inspect-pdf native.pdf --source-hwpx candidate.hwpx --provenance-note "OpenOnly 영수증과 실제 해시 대조 완료" --term "대상어" --expected-total "대상어=3" --output new-lines.json --crop-dir new-crops
```

지정어는 원본에서 확정한다. 기본 예제 단어가 요청의 대상이라고 추정하지 않는다.
반복 양식의 쪽마다 동일 횟수라면 `--expected-per-page`를 쓴다.
HWPX preflight의 폭·밀도는 위험 후보이지 실제 줄 수나 넘침 판정이 아니다.
PDF의 `NO_SPLIT_OBSERVED`도 지정어 범위의 관찰뿐이다. 누락·기대 횟수 불일치·입력 변경은
`UNVERIFIED`이며 0건 검출을 정상이라고 해석하지 않는다.

지정어의 원래 한 칸 공백에서 나뉜 `AT_SOURCE_WHITESPACE`는 정상 어절 경계일 수 있다.
분리 검출과 한국어 어색함을 동일시하지 않는다. 단어 내부 분리와 나누어 보고한다.
다단, 서로 다른 블록·글꼴·방향, 큰 간격, 개체와 섞인 읽기 순서는 좌표만으로 확정하지 않는다.
기본 2줄 검사는 한글이 한 문단을 별도 PDF 블록으로 출력하는 경우도 찾는 기하 휴리스틱이다.
따라서 finding은 실제 줄바꿈 확정 전의 검토 후보이며, 특히 블록이 다르면 이미지로 연결을 확인한다.
3~4줄은 `--max-split-lines 3` 또는 `4`를 명시한다. 이 경로는 같은 블록의 연속 줄·수평 방향·
매칭 글꼴/크기·인접 기하를 요구한다. 문자열이 재구성돼도 조건이 다르면 원인을 진단하고
발생 수에 더하지 않는다. 실제 3줄 시험에서 블록 `[0,0,1]`은 `DIFFERENT_BLOCKS`로 미검증 유지다.
발견 위치의 이미지와 문맥을 확인한다. 전체 검토가 요구된 반복 인쇄물은 의심 쪽만 보고 끝내지 않는다.
종료코드: 0=정상 관찰, 1=분리 발견 또는 미검증, 2=실행/계약 오류. 1의 원인은 JSON으로 구분한다.

### 출처 대조 교차 블록 보완 검사

기본 검사에서 `DIFFERENT_BLOCKS`로 미검증이지만 실제 한글에서 한 문단이 여러 PDF 블록으로
분리된 사례에는 다음 별도 읽기 전용 프로토타입을 선택적으로 사용한다. 기본 판정 가드는 유지한다.

```powershell
python -X utf8 scripts/source_anchored/source_anchored_multiblock_prototype.py --source-hwpx candidate.hwpx --pdf native.pdf --receipt actual-openonly-receipt.json --term "원본의 고유 지정어" --max-lines 4 --output new-source-anchored.json
```

단일 source 문단/text node의 유일 지정어, 전체 문단의 정확한 공백 포함 재구성, 고유 이웃 문단,
구조 경계 부재, 같은 쪽의 연속 줄·수평 방향·glyph 스타일·기하·유일 시퀀스 및 실제 OpenOnly
영수증의 경로/hash/정상 종료/입력 불변이 모두 필요하다. 누락된 영수증 필드를 만들어 넣지 않는다.
출력은 배타 생성하며 종료코드0=제한된 출처 대조 관찰, 1=미검증, 2=계약/파일/파싱 오류다.
`OBSERVED_SOURCE_ANCHORED_MULTIBLOCK_RENDERER_FRAGMENT`는 이 조건의 좌표 관찰이지
문서 전체 검수·자연어 어색함 판정·exporter 내부 원인의 증명이 아니다. 영수증도 서명된 인증서는 아니다.
이미지 글자·해석 불충분·모호한 문단/배치에는 미검증을 유지한다. 실제 시각 검토는 여전히 필요하다.

회귀는 같은 하위 폴더의 `test_source_anchored_multiblock_prototype.py`에 실제 입력을
`--native-hwpx`, `--native-pdf`, `--native-receipt`, `--term`으로 전달한다.
`test_file_e2e.py --engine ENGINE_PATH --work-dir NEW_DIR --output NEW_JSON`은 비개인
합성 파일 회귀이며 native 증거로 인정하지 않는다. 합성 PDF 생성/검수에는 PDF 스킬을 적용한다.

## 쪽배치·빈 쪽·표식

```powershell
python -X utf8 scripts/audit_hwpx_pagination.py hwpx candidate.hwpx --output new-structure.json
python -X utf8 scripts/audit_hwpx_pagination.py pdf native.pdf --expected-label-count "시작표식=1" --expected-label-count "끝표식=1" --expected-order "시작표식" --expected-order "끝표식" --output new-pages.json
```

HWPX는 spine 순서와 section 직속 문단을 읽는다. 중첩 셀의 마지막 문단을 문서 끝으로
간주하지 않는다. 해석 불충분은 미검증이다. 실제 쪽 수·빈 쪽은 PDF에서 별도로 확인한다.
표식은 실제 원본의 고정 기준이며 검사를 통과시키려고 제거하거나 변경하지 않는다.
표식 순서는 PDF 추출 순서이며 다단의 시각적 읽기 순서 증명이 아니다.
`blankCandidates`는 텍스트·그림·드로잉 부재 후보다. 실제 페이지 이미지에서 백지인지,
의도된 빈 쪽인지 확인한다. 이미지/도형만 있는 쪽도 자동 정상으로 처리하지 않는다.
종료코드: 0=정적 preflight 완료 또는 지정 조건 OBSERVED, 1=UNVERIFIED 계열,
2=입력·계약·출력충돌·실행 오류. 출력 JSON은 새 경로만 허용한다.

끝 빈 문단 하나를 제거한 특정 사례의 성공은 일괄 삭제 권한이 아니다. 쪽 나눔·표·제어 요소·
개체 위치 원인을 구분하고, 지원되는 후보 편집 뒤 비대상 보존과 실제 전후 조판을 대조한다.

## 표 넘침·여러 쪽 지원

표 넘침은 작성 API 지원, 설치된 한글 automation 지원, 실제 native 조판을 분리해 판정한다.
`python-hwpx 6.3.0` public API에는 `repeatHeader`·`pageBreak`·`treatAsChar`·셀 제목 속성의 전용 setter가 없다.
또한 한글 `13.0.0.653`의 한 관측에서는 `TableCreate` GetDefault의 `TableProperties.PageBreak`가 없어
해당 discovery 경로가 `UNSUPPORTED`였다. 이는 다른 한글 버전이나 다른 공식 API의 보편적 미지원을 뜻하지 않는다.

2026-09-09 추가 검수에서는 같은 빌드의 `TablePropertyDialog` GetDefault와 symbolic
`TableBreak`의 Table/Cell/None 구분까지 확인했다. 그러나 관측한 HSet 경로에 `ItemExist`가
노출되지 않아 `RepeatHeader`·`PageBreak`·`TreatAsChar`·`HCell.Header`의 존재와 readback을
입증하지 못했다. 제목행·행분할·하단 이동의 세 시험 축은 생성 전에
`UNSUPPORTED_FOR_BUILD_PATH`로 중단됐다. 이 결과는 속성 자체가 없다는 증명이 아니다.
다음 시험에는 다른 빌드 또는 재현 가능한 공식 UI 경로 등 원인을 바꾸는 근거가 필요하다.

실험용 artifact verifier와 완료 가드의 34개 모의/스텁 회귀 통과는 가드 동작의 증거다.
해당 native 시험에서 생성된 HWPX·PDF·출력 영수증·페이지 이미지는 모두 0개이므로,
`PASS_UNSUPPORTED_NO_ARTIFACTS`를 실제 표 편집·조판 통과로 보고하지 않는다.
이 실험용 runner와 verifier는 전역 스킬의 운영 도구로 설치하지 않았다.

`audit_hwpx_pagination.py`는 HWPX의 section/spine 구조와 PDF의 쪽 수·표식 횟수·순서를 검사하는 데 재사용한다.
표 행 분할, 반복 제목행, 경계선, 하단 잘림은 PDF 전체 페이지 이미지와 정확한 저장본의 symbolic readback을 함께
확인해야 한다. 둘 중 하나라도 없으면 실제 조판은 `UNVERIFIED`이며 자동 수정 완료로 보고하지 않는다.

비교 사례는 `pageBreak` 등 시험 축 하나만 다른 새 source-controlled 쌍이어야 한다. 실제 source control이 같은
여러 파일을 정상/결함쌍으로 간주하지 않는다. 숫자 enum 하드코딩, raw XML 쓰기 폴백, 중첩 셀 전체 쓰기는 금지한다.
실험용 native runner의 성공·실패는 해당 build와 정확한 계약의 증거일 뿐 일반 지원이나 전역 설치 근거가 아니다.

## 개체 배치 정적 계약

고정 manifest가 있는 합성 사례는 `scripts/object_placement/audit_object_placement.py`로 위치 기준과
offset, 크기, 바깥 여백, wrap, z-order, BinData 연결·hash, 고유 표식 수를 읽기 전용으로 대조한다.
자세한 실행과 판정 경계는 [개체 배치 정적 계약 검사](object-placement-validation.md)를 따른다.
정적 `PAGE_BOUNDARY_OVERFLOW`는 실제 clipping의 모양을 확정하지 않으며, PDF 좌표나 동일 경계 상자는
내부 anchor identity를 증명하지 않는다. D1 합성 재생성 성공을 일반 개체 수정 지원으로 확대하지 않는다.

## 병합표

기존 `plan_grid_cell.py`/`InspectGrid`의 제한 읽기 계약을 유지한다. 오른쪽 한 번이 항상
같은 셀에 도착한다고 가정하지 않는다. 병합 영역에서 다른 도착점이 관찰됐지만
숨은 행 선호 같은 내부 원인은 직접 관찰한 사실이 아니라 가설이다.
텍스트 일치만으로 셀을 식별하지 않고 table ID·부모·문단·좌표·허용된 이동 경로와 복원을 함께 확인한다.
예상 밖 분기·동일 문구 다른 셀·부모 불일치·복원 실패는 검증 실패다.
이미 수집된 v3 계획·적응 이동 영수증·독립 anchor 영수증이 있는 정확한 두 분기는 다음으로 검산한다.

```powershell
python -X utf8 scripts/validate_adaptive_grid_selection.py --contract observed-contract.json --plan verified-plan.json --receipt adaptive-receipt.json --anchor-receipt anchor-receipt.json --output new-branch-validation.json
```

계약은 `anchor → Right → owner` 또는 `anchor → Right → intermediate → Lower → owner`만
다룬다. 실제 관측으로 셀 ID·좌표를 고정해야 하며 통과를 위해 영수증이나 예상 좌표를 만들어 넣지 않는다.
`PASS_READ_ONLY_BRANCH`와 `writePreGateReady`는 실제 수정 허가가 아니고 `writeAuthorized=false`다.
`--require-write-pregate`는 raw 부모 증거/빈 artifacts 등 추가 증거의 존재를 확인할 뿐이며,
변경 전 정렬값·실행기 연동·새 프로세스 재검증을 증명하지 않는다. 기존 영수증의 불충분한 항목은
추가해서 꾸미지 말고 미검증으로 남긴다. 합성 자체 회귀는 `scripts/test_validate_adaptive_grid_selection.py`다.
`SetAlignmentGrid` 및 임의 병합셀 쓰기는 미지원으로 유지한다. 새 쓰기 지원은 격리된 합성 사본의
대상/비대상 보존·저장/재열기·실제 출력 회귀가 먼저 필요하다. 기존 제한 첫 문단 정렬 지원을 확대 해석하지 않는다.

## 알려진 결함의 처리

증상을 발견하면 입력/도구 해시와 실패 기준을 고정한다. 원인을 좁혀 수정 후보를 만들고
양성·정상·거부 사례를 함께 재검사한다. 과거 실패 기록은 남기고 새 버전의 결과를 별도로 기록한다.
검출기 보완이 문서 수정 완료는 아니다. 해결하지 못한 증상은 영향 범위·차단 이유·다음에 필요한
구체적 시험을 적고 완료 판정에서 제외한다. 기준 완화·묵시적 폴백으로 통과시키지 않는다.

검사기 수정 시 패키지 위치에서 `python -X utf8 scripts/test_audit_hwpx_pagination.py`와
`python -X utf8 scripts/test_audit_hwpx_linebreaks.py --work-dir NEW_EMPTY_DIR`를 실행한다.
이 회귀 통과는 새 실제 문서의 한글 검수를 대신하지 않는다. 개발 사본만 고치고 설치본은
이전 버전인 상태가 되지 않도록 전달한 코드·테스트와 설치 파일의 SHA-256을 대조한다.
