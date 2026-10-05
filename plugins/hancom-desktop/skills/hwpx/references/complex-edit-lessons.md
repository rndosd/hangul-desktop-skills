# 복합 편집의 확인 범위

기입된 양식은 빈 양식 변형 도구의 지원을 넓혀 처리하지 않는다. 본문 추가/삭제, 일반 표 행 추가/삭제, 셀 병합/해제를 각각 지원하는 hash-bound 도구로 연결한다. 병합 전에 유지할 모든 셀 내용을 정확한 소유 셀로 옮기고 나머지 셀이 비었는지 확인한다. 임의 중첩 구조로 일반화하지 않는다.

다단 보고서는 기존 단 정의·떠 있는 그림의 앵커·캡션을 보존한 본문 편집을 우선한다. 제목이 한 단 끝에 고립된 것이 실제 출력에서 확인됐을 때 해당 제목에만 paragraph_flow의 keep_with_next를 적용하고 다시 검토한다. 전체 문단에 일괄 적용하지 않는다. HWP003/004의 서로 다른 합성 문서에서 확인했지만 자연어 도구 선택의 독립 모델 E2E 검증을 뜻하지 않는다.

Windows 제한 토큰에서 TemporaryDirectory의 소유자 전용 임시 디렉터리 때문에 편집 전 파일 쓰기가 거부될 수 있다. safe_edit/safe_cell_layout/safe_table_layout은 workspace_candidate_directory.py를 함께 배포하며, 승인된 출력 부모 안의 UUID 디렉터리를 상속 권한으로 생성한다. ACL 변경 없이 본인이 만든 candidate 파일과 빈 폴더만 정리한다. 뜻밖의 파일은 삭제하지 않는다. 이 오류를 COM/DLL 등록 실패로 해석하지 않는다.

그림 payload 교체의 기존 same-format/same-pixel-dimensions 계약은 유지한다. 다른 비율의 그림을 좁혀 넣으면 한글이 caption lastWidth도 좁혀 긴 캡션을 재배치할 수 있다. 실제 비율·전체 캡션 폭·줄바꿈과 주변 본문을 따로 검토한다. HWP005 contain 프로토타입은 한 사례 실패로 배포에서 제외했으며, 이 참조가 그 기능의 지원을 추가하지 않는다.

native 차트는 생성 성공만으로 원자료 반영을 보장하지 않는다. 표 개체만 선택한 InsertChart는 기본 예제값을 만들 수 있다. 전체 셀 선택을 정확히 확인하고 생성 결과의 Chart/chart*.xml에서 계열명·항목·모든 수치를 원자료와 대조한다. COM 차트 생성/저장과 실제 UI 데이터 재편집을 구분한다. 이번 제한 실험은 데이터 일치 두 사례를 확인했지만 재저장 fallback OLE strict 보존 실패 및 UI 재편집 미검증으로 일반 차트 도구를 배포하지 않는다.

공식 참고: [생성 인자](https://forum.developer.hancom.com/t/topic/1529), [2024년 차트 편집 API 답변](https://forum.developer.hancom.com/t/topic/1649), [전체 셀 선택](https://forum.developer.hancom.com/t/topic/1086/11). ChartDataDialogDisable은 차트 데이터창 옵션이며 파일 접근 승인 설정을 바꾸지 않는다.

## 보고서 차트 전후 간격

차트를 독립 본문 블록으로 배치할 때는 표·차트 경계가 붙지 않게 바깥 위/아래 여백을 확보하고 뒤 본문이 차트 아래에서 이어지는지 확인한다. 이번 보고서의 시작안은 위4mm/아래4mm이며 사용자의 양식/공간 조건에 맞춰 조절한다. 좌우 본문 어울림이 필요한 별도 배치까지 금지하는 규칙이 아니다.

한글2024의 정확한 native chart runtime ID를 확인한 합성 두 사례에서 ShapeObjDialog의 TextWrap=1(TOP_AND_BOTTOM), OutsideMarginTop/Bottom=1134 HWPUNIT를 적용했다. 데이터 Chart XML bytes·전체 표·비대상 본문/활성 서식·차트 크기는 그대로였다. 실제 표-차트 약6.0mm, 차트-본문 약9.5mm를 측정하고 각1쪽을 실제 검토했다. 저장/재열기/PDF를 확인했지만 기존 fallback OLE strict 보존 실패와 UI 데이터 재편집 미검증은 여전히 별개다. 이 사례만으로 임의 차트 자동 편집 도구를 배포 지원에 추가하지 않는다.
