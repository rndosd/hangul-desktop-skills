# 이전 상세 경로와 기능별 계약

공통 진입과 우선순위는 현재 SKILL.md를 따른다. 이 참조는 전문 도구의 지원 범위와 기존 검증 계약을 보존한다. 필요한 절만 읽는다.

# 실제 한글 검증

설치 또는 COM 진단 시 [PC별 환경](desktop-environment.md)을 먼저 읽고
현재 스킬의 `environment.json`을 사용한다. 보안 모듈 미구성은 native 작업 미준비다.

PDF는 같지만 편집한 표의 직접 높이가 저장에서 변할 때는
[실제 측정 표 높이](native-measured-table-height.md)의 제한 후보 경로를 읽는다.
실제 한글의 사전 측정과 HWPX 전체 정의 비교를 요구하며 일반 저장에 자동 적용하지 않는다.

hwpx 편집 후보를 검증한다. 편집 로직을 반복하거나 자동화 실패만으로 문서를 재작성하지 않는다.

## 검증 범위

- 일반 내용 수정: 패키지·내용 보존 검사 후 실제 한글 열림을 확인한다.
- 줄바꿈·쪽 나눔·표·개체 등 조판 수정 또는 인쇄/제출용:
  전달할 후보의 실제 한글 렌더에서 해당 레이아웃을 확인한다.
- 재저장·재열기: 사용자가 요구하거나 호환성/손상 복구, 한글 재계산이 필요한 경우 수행한다.
  단지 학교 문서라는 이유만으로 매번 SaveAs를 강제하지 않는다.

## 경로

1. 원본과 다른 후보, 상위 검증 영수증을 확인한다.
2. 해당 세션에서 미확인일 때 scripts/check_hancom_com.ps1로 COM 생성과
   COM 생성과 환경 설정에서 선택한 모듈의 `RegisterModule('FilePathCheckDLL', moduleName)` 성공을 별도로 확인한다.
   Codex 셸의 HKCU 값 조회는 MSIX 가상화 때문에 실제 Hwp.exe의 판정 근거로 사용하지 않는다.
   Codex 패키지 컨텍스트의 RegisterModule=false만으로 실제 사용자 등록 누락을 단정하지 않는다.
   이 경우 승인된 제한 권한 임시 작업 등 일반 Windows 사용자 컨텍스트에서 한 번 더 판정한다.
3. 정상 COM이면 scripts/verify_hwpx_with_hancom.ps1의 OpenOnly를 기본으로 사용한다.
   필요한 경우에만 SaveAs와 새 OutputPath를 사용한다.
   각 COM worker는 문서를 열기 전에 RegisterModule을 한 번 호출하고 false면 문서를 열지 않는다.
   패키지 컨텍스트는 false이고 일반 사용자 컨텍스트는 true라면 실제 문서 COM 작업도 후자의
   컨텍스트에서 실행한다. 이 상태에서는 레지스트리를 다시 쓰지 않는다.
4. COM이 막히면 실패 원인을 구분한다. 모듈 등록·복구처럼 사용자 영역 설정을 바꾸는 작업은
   명시적 승인 후에만 수행한다. 사용 가능한 computer-use 스킬로 실제 한글 UI에서
   같은 검증을 수행할 수 있다. 학교/개인 문서는 로컬에서만 처리한다.
5. 저장했다면 scripts/compare_hwpx_semantics.py로 후보와 저장본을 비교하고 저장본을 다시 연다.
6. [판정 기준](acceptance-policy.md)에 따라 증거·미검증 항목을 보고한다.
   실패 시에만 [장애 처리](hancom-com-failures.md)를 읽는다.

복합 문서 또는 COM 수정 후 실제 출력까지 완료해야 하는 작업은
`scripts/hancom_completion_gate.py`의 `prepare → COM 실행 → collect → 실제 검토 → check`로 연결한다.
prepare는 COM 전에 원본 후보 hash와 신규 final/PDF/run 경로를 고정한다.
collect/check가 요구한 검사나 페이지 검토가 없으면 pending이며 PASS_COM/PASS_FULL로 대체하지 않는다.
일반 OpenOnly만 필요한 작업에는 이 출력용 절차를 추가하지 않는다.
사용자가 차트 문서의 실무 사용을 우선하면 [실무 차트 전달 기준](acceptance-policy.md#실무-차트-전달-기준)에 따라 OLE-only strict 차이와 실제 사용 결과를 분리한다. 필요한 내용·native·레이아웃 검증은 유지하고 내부 바이트 차이만으로 작업을 반복하거나 중단하지 않는다.
정확한 명령과 검토 계약은 [판정 기준](acceptance-policy.md)의 완료 연결 절을 읽는다.

원본·후보는 덮어쓰지 않는다. COM 스크립트의 기존 receipt 상태를 고쳐 쓰지 않는다.
GUI 검증은 별도 기록으로 남기고 COM 성공인 것처럼 표현하지 않는다.
COM OpenOnly/SaveAs 성공만으로 시각 검수까지 끝났다고 주장하지 않는다.

기존 native PDF의 누락 검사는 `scripts/audit_existing_pdf.py`로 원본에서 열거한
고유 라벨과 대조한다. 예: `python scripts/audit_existing_pdf.py final.pdf --expected-label "고유표식"`.
exit 0은 지정 라벨 대조만 완료, 3은 내용 불일치, 2는 미검사다. 짧은 쪽은 경고이며
누락·의존성 부재·추출 실패를 통과로 바꾸지 않는다. 이 도구는 렌더나 시각 검수를 하지 않는다.

합성 개체 배치 사례의 위치 기준·offset·크기·여백·wrap·z-order·BinData 연결·표식 계약은
`scripts/object_placement/audit_object_placement.py`로 선택적으로 점검할 수 있다. 실행 전
[개체 배치 정적 계약 검사](object-placement-validation.md)를 읽는다. 정적 일치나 결함 후보는
실제 한글 레이아웃, 내부 anchor identity 또는 임의 기존 개체의 수정 가능성을 증명하지 않는다.

## 기존 명령

### 줄바꿈·빈 쪽·병합표의 제한 검사

줄바꿈, 빈 쪽, 표식 횟수/순서 또는 병합표 이동의 검증에는
[레이아웃 검사와 지원 경계](layout-validation.md)를 먼저 읽는다.
지정어 좌표 검사 `audit_hwpx_linebreaks.py`와 쪽배치 검사 `audit_hwpx_pagination.py`는
읽기 전용이며 실제 한글 출력 영수증·시각 검토를 대체하지 않는다. 미검증은 성공이 아니다.
임의 병합셀 쓰기와 일괄 빈문단 삭제를 검사기 통합만으로 허용하지 않는다.

### PDF 출력 경로 선택

- 사용자가 UI 방식을 지정하지 않았다면 실제 한글 COM 출력을 우선한다. PDF만 필요한 경우
  `verify_hwpx_with_hancom.ps1 -Mode OpenOnly -CandidatePath ... -PdfPath ...`를 사용하며,
  PDF를 만들기 위해 HWPX까지 불필요하게 재저장하지 않는다. 기존 잠금·소유 프로세스 보호는 유지한다.
- PDF 출력에 필요한 COM 연결·열기·내보내기 자체가 막혔을 때만 사용 가능한 computer-use로
  전환한다. 병합 셀 이동·편집 실패를 PDF 출력 불가로 간주하지 않는다. 전환 이유를 짧게 알리고
  같은 오류를 무작정 반복하지 않는다. 정상 COM 출력물을 UI로 중복 출력하지 않는다.
- 정확한 대상 HWPX의 경로·hash와 출력 PDF를 연결해 기록한다. 이전 PDF나 텍스트 불변만으로
  현재 줄바꿈을 판정하지 않는다. 반복 문서는 코드로 전수 검사하고 의심 부분을 우선 렌더 검토하되,
  전체 페이지 검토 등 해당 작업의 기존 증거 계약을 축소하지 않는다. 텍스트/구조 검사와 시각 검증은 별개다.

### 정확한 표 대상 읽기·제한 문단 정렬

병합 표의 행·열 읽기는 `plan_grid_cell.py source.hwpx --table N --row R --column C
--output new-plan.json`으로 시작한다(모두 1부터). 병합 영역의 실제 소유 셀과 최대 20회
오른쪽/아래 이동 경로를 계산한다. `Invoke-HancomCell.ps1 -Operation InspectGrid`에
GridPlanPath와 계획의 첫 셀 TargetText를 전달한다. 원본 hash·표 ID·이동 중 각 문구·서로 다른
cell list와 복원을 확인하며 저장하지 않는다. v3 계획은 빈 일반 첫 문단도 지원한다. 실제
문단 선택 길이 0과 원본의 빈 문단 여부가 함께 일치해야 하며, 빈 선택에서는 saveblock을
호출하지 않는다. 공백만 있는 문단은 길이 0인 문단과 구별한다. 셀 전체가 빈지는 별도이며
paragraphCount를 함께 기록한다. 출발 첫 셀은 비어 있지 않아야 하고, 경유 셀의 중첩 표·그림·
제어 요소는 아직 지원하지 않는다. 새 계획을 생성하며 v1/v2 계획은 재사용하지 않는다.
실제 가로/세로 병합 표의 일반·빈 대상에서 확인했지만 임의 셀 쓰기를 뜻하지 않는다.
오른쪽 이동이 다음 행으로 이어진다고 가정하지 않는다. `TableRightCellAppend`는 쓰지 않는다.

표가 3~100개인 문서의 부모 첫 셀 안쪽 표를 읽을 때는 `InspectMany`를 사용할 수 있다.
`-ExpectedTableCount`, 1부터 시작하는 `-ParentOrdinal`, `-TargetOrdinal`로 후보 두 개만 좁히며,
순번만으로 성공 판정하지 않는다. 실제 runtime ID·정확한 문구·부모 list·복원 좌표를 확인한다.
부모 셀의 텍스트는 중첩 표를 포함해 줄바꿈이 생길 수 있으므로 실제 읽은 값을 그대로 사용한다.
이 경로는 읽기 전용이며 OutputPath/PdfPath/Alignment를 거부한다. 51표 실제 문서의 한 쌍에서
검증됐지만 임의 셀·모든 중첩 구조를 보장하지 않는다. SetAlignment의 기존 1~2표 범위는 유지한다.

`SetAlignmentMany`는 위와 같은 부모 첫 셀 안쪽 표의 첫 문단에 한해 3(CENTER)→2(RIGHT)를
시험한 제한 경로다. 기존 SetAlignment를 대체하지 않는다. 같은 후보의 InspectMany로 문구와
관계를 확인하고 `ExpectedSourceSha256`, 신규 OutputPath/PdfPath를 필수로 제공한다.
51표 실제 사례에서 저장·재열기·17쪽 출력 및 완료 gate를 통과했다. 단, 대상 문단에 투명/무색
채우기 정의가 명시되는 변화도 관찰됐다. 비대상 보존과 전체 출력 검토를 생략하지 않으며
임의 셀·다른 정렬 전환을 지원한다고 해석하지 않는다. 일반 diagnose_edit의 BLOCK을 우회하는
폴백이 아니라 별도 시험·검증을 요구하는 제한 경로다.

`scripts/Invoke-HancomCell.ps1`의 `Inspect`로 정확한 첫 셀 첫 문단 표식을 먼저 확인한다.
`SetAlignment`는 검증된 단일 표 또는 부모 첫 셀 안쪽 표(전체 표 2개)의 정렬 0/2만 다룬다.
대상은 `-TargetText`, 중첩 부모는 `-ParentText`로 지정한다. `-Expected`는 변경 전 정렬값이며
다른 대상/상태면 쓰기를 거부한다. 임의 셀·텍스트 변경·여백으로 확대하지 않는다.

```powershell
powershell.exe -NoProfile -File scripts/Invoke-HancomCell.ps1 -Operation Inspect -InputPath "candidate.hwpx" -TargetText "정확한 고유 문구" -RunDirectory "new-inspect-run"
powershell.exe -NoProfile -File scripts/Invoke-HancomCell.ps1 -Operation SetAlignment -InputPath "candidate.hwpx" -TargetText "안쪽 첫 문단" -ParentText "부모 첫 문단" -Expected 0 -Alignment 2 -OutputPath "new-final.hwpx" -PdfPath "new-final.pdf" -RunDirectory "new-edit-run"
```

선택 상태와 정확 표식·부모 계층을 검증하고 비대상 보존·재열기/PDF 결과를 대조한다.
이 명령의 `PASS_COM`은 COM 단계만 통과한 것이다. 영수증의
`structuralPreservation=NOT_CHECKED`, `nonTargetPreservation=NOT_CHECKED`,
`visual=NOT_REVIEWED`를 별도 보존/렌더 검사 없이 성공으로 바꾸지 않는다.
`test_hancom_cell_preservation.py`는 E02 고정 합성 사례 전용 회귀검사이며 일반 문서 검사기가 아니다.
근거: 한컴13.0.0.653 E01/E02, 공식 ParagraphShape/ParaShape.AlignType 및
[데스크톱 자동화 문서](https://developer.hancom.com/hwpautomation),
[공식 포럼의 ID 선택](https://forum.developer.hancom.com/t/topic/2114).
셀 블록→Cancel 아이디어는 pyhwpx commit a83b782673ecf49e18964610edea1d12c23b7f09(MIT)을
읽기 참고했으며 전체 라이브러리를 import하지 않는다. 다른 빌드에서도 자동 보장되는 계약은 아니다.

### 일반 열림·저장 검증

```powershell
powershell.exe -NoProfile -File scripts/check_hancom_com.ps1
powershell.exe -NoProfile -File scripts/verify_hwpx_with_hancom.ps1 -CandidatePath "candidate.hwpx" -Mode OpenOnly -ReceiptPath "candidate.com-receipt.json"
powershell.exe -NoProfile -File scripts/verify_hwpx_with_hancom.ps1 -CandidatePath "candidate.hwpx" -Mode SaveAs -OutputPath "final.hwpx" -ReceiptPath "final.com-receipt.json"
python scripts/compare_hwpx_semantics.py candidate.hwpx final.hwpx --json
```

저장 전후 PDF가 같아도 내부 보존은 [별도 파일 검사](native-file-roundtrip-audit.md)와 audit_native_file_roundtrip.py로 확인한다. 원시 바이트/구조/전체 정의/실제 같은 기능 재편집 결과를 합쳐 단일 PDF PASS로 대체하지 않는다.

PDF는 같지만 저장 후 미사용 서식 정의가 사라진 실제 사례는 [명시적 서식 보관](unused-definition-retention.md)의 선택 후보 경로를 적용하고 전체 정의와 실제 재편집을 별도로 검증한다.


실제 출력의 지정 제목/본문·고정 목차·특정 희소 쪽 검사는 [보고서 지면 부분 검사](report-layout-subset.md)를 읽는다. 전체 한글 파일/전쪽 검증을 대신하지 않는다.


모아찍기 한 문서의 인쇄면별 방향과 실제 footer 위치를 확인한다. 가로 좌우/세로 상하 배치가 섞일 수 있으므로 원본 근거 없이 인쇄면을 일률적으로 반으로 나누지 않는다. 길어진 표는 모든 원래/신규 행·반복 제목행·앞 설명/뒤 본문을 실제 저장본 PDF에서 확인한다.


행/셀 구조 편집은 실제 저장본에서 같은 기능으로 재편집하고, 원래 병합·수치·run서식과 양쪽 합친 문단을 확인한다. 정상 종료 대기는 기록된 소유 pid/startTicks/exe에만 제한하여 적용한다. 종료 호출 성공과 프로세스 종료 완료를 구분한다.


다중 run 문구 매핑의 저장 검수는 문단 전체 문자열과 각 run 서식을 함께 대조하고 PDF의 실제 문구 횟수도 확인한다. 같은 문구가 반복된 원인이 저장 전 지도에 있으면 작성 경로를 고친다.


기존 표의 종료 항목 삭제·신규 항목 추가 등 내용에 따른 변경은 형제 hwpx의 references/semantic-table-binding.md를 읽는다. 정확한 전체 셀 키와 새 소스 해시로 작업마다 대상을 다시 찾고 실제 저장본 재편집·긴 내용과 모든 지면을 검수한다.


일반 native controller의 Quit 후 종료 확인은 [소유 프로세스 종료 확인](owned-exit-check.md)을 따른다. 종료 관찰과 live 소유권 일치를 구분하며 불일치/확인 불가를 임의로 허용하지 않는다.
