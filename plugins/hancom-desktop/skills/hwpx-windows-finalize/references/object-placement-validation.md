# 개체 배치 정적 계약 검사

`scripts/object_placement/audit_object_placement.py`는 HWPX를 수정하지 않고 manifest에 고정된 합성 사례의 개체 계약을 읽는다. 위치 기준과 offset, 크기, 바깥 여백, wrap, z-order, BinData 연결·hash, 고유 표식 개수를 대조한다.

```powershell
python -X utf8 scripts/object_placement/audit_object_placement.py --manifest contract/manifest.json --expected-manifest-sha256 HASH --output new-inspection.json
```

출력 경로의 부모는 이미 존재해야 하고 출력 파일은 새 경로여야 한다. 종료코드 0은 normal의 정적 false positive가 없고 manifest에 선언한 모든 defect가 정적 후보로 식별됐다는 뜻이다. `STATIC_CONTRACT_MATCH_NATIVE_UNVERIFIED`와 `STATIC_DEFECT_CANDIDATE_NATIVE_UNVERIFIED`는 실제 한글 조판 판정이 아니다.

PDF 좌표나 동일한 렌더 경계는 내부 HWP anchor identity를 증명하지 않는다. 이 검사기는 자동 수정이나 임의 기존 개체의 안전한 편집 가능성도 판정하지 않는다. D1 수정은 합성 fixture를 공용 저작 API로 재생성한 제한 레시피이며 일반 수정기로 설치하지 않는다.

동결 D2 사례는 수직 offset만 바꾸면서 기대 문구는 오른쪽 가장자리의 부분 clipping을 기술한다. 실제 한컴에서는 전체 개체가 보이지 않아 동결 기대가 재현되지 않았다. 검사기의 `PAGE_BOUNDARY_OVERFLOW`는 정적 경계 초과 후보일 뿐 부분 clipping 재현 판정이 아니다.

## 실제 한글 추가 검수의 범위 (2026-09-09)

Hancom 13.0.0.653의 새 비개인 합성 사례에서 안쪽 배치는 정상 표시됐고, 오른쪽 경계 초과는
부분 잘림이나 자동 재배치가 아니라 개체 전체가 보이지 않는 현상으로 관찰됐다.
이는 해당 후보의 관찰이며 임의 문서의 경계 초과 결과를 예측하는 규칙은 아니다.

공식 symbolic `CtrlCode.Properties/HorzOffset`의 한 축 수정은 대상 유일성·즉시 readback·
SaveAs·새 프로세스 재열기와 실제 PDF에서 약 20mm 이동까지 확인했다. 그러나 SaveAs 후
strict 보존 검사에서 `texts`와 `binaryReferences`가 불일치했고 BinData 이름도 변경됐다.
논리 텍스트가 같고 그림이 이동했다는 사실만으로 내부 보존까지 통과했다고 해석하지 않는다.
최종 판정은 `NOT_END_TO_END_PASS_STRICT_PRESERVATION_BLOCKED`다.

현재 설치된 도구는 정적 읽기 검사기다. 위 실험용 개체 편집기는 일반 수정 도구로 통합하지 않았다.
새 편집 지원에는 저장 전후 차이의 의미를 검증하는 보존 검사와 실제 문서 회귀가 필요하다.
이미지 이름 변경만 무시하거나 기존 gate 기준을 낮춰 성공으로 바꾸지 않는다.

회귀 실행:

```powershell
python -X utf8 scripts/object_placement/test_audit_object_placement.py --frozen-bundle FROZEN_BUNDLE
```

회귀는 normal 3건, 정적 defect 3건, manifest/source hash, fixture/BinData 누락, 중복 target, 기존 출력 거부를 확인한다. 새 문서에 쓰려면 문서별 고유 표식과 기대 계약을 먼저 고정해야 한다.
