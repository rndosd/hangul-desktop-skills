# 한글 엔진으로 최종 기록 완성

표 행 추가·병합 뒤 선택 표의 전체 높이를 한글이 계산해 기록하도록 요청한 경우에만 `scripts/native_write.py`를 사용한다. 기존 OpenOnly 기본 경로를 대체하지 않는다. 셀 높이·너비·안 여백·본문/개체 위치 변경이나 버전/글꼴 변환을 자동 허용하지 않는다.

```powershell
& $hangulPython -X utf8 -B scripts/native_write.py prepare authored.hwpx --work new-work --table-id 1735889239 --context ordinary-shell
& $hangulPython -X utf8 -B scripts/native_write.py execute new-work
```

prepare는 원본·명시한 표 ID·실제 도구 hash를 고정한다. 실행은 검토된 기존 모듈을 사용하는 PC별 설정과 승인된 일반 로그인 맥락에서 수행한다. context는 샌드박스를 탐지/해제하는 옵션이 아니다. 현재 사용자 원본을 덮어쓰거나 설정을 바꾸지 않는다.

정확한 작성 파일 OpenOnly/PDF → 별도 native SaveAs/재열기/PDF → 활성 내용·서식 검증 → 반복 SaveAs/재열기/PDF → 세 출력의 전쪽 픽셀 비교를 수행한다. 요청한 표의 직접 `hp:sz.height`만 한글이 계산한 값으로 비교 기대값에 반영한다. 이 조정은 읽기 전용 메모리 비교에만 적용하며 XML 작성에 사용하지 않는다. 모든 나머지 활성 구조·문단별 글·셀 크기·서식·글꼴 목록·스키마·바이너리 연결은 보존해야 한다. 다른 변화가 남으면 `BLOCKED_OTHER_CHANGE`이고 결과를 배포하지 않는다.

계산된 높이를 다른 문서에 숫자로 복사하거나 행 높이 합만으로 한글과 동일하다고 주장하지 않는다. 구형 스키마/대체 글꼴 변환은 자동 승인하지 않는다. 최신 한글에서 확인된 입력 사본을 기준으로 시작할 수 있지만 원본→그 기준의 변환 동등성은 별도 미검증으로 기록한다.

`READY_FOR_ALL_PAGE_REVIEW`는 시각 검토 대기다. trial.pdf의 모든 요구 쪽을 검토한 뒤 새 review.json을 작성한다. review는 `result=ref(result.json)`, `pdf=result.pdf`, `reviewer`, `reviewedAt`, `outcome=PASS`, `pages=[{page:1,outcome:PASS,observation:구체적인 검토 기록}, ...]`을 포함한다. ref는 path/sha256/bytes이며 기존 파일의 현재 값을 사용한다. 기록은 검토자의 진술이지 자동 인증이 아니다. 시각/보존 실패를 PASS로 적지 않는다.

```powershell
& $hangulPython -X utf8 -B scripts/native_write.py publish new-work --review new-review.json --output new-delivery.hwpx --pdf-output new-delivery.pdf
```

발행은 원본/도구/출력/영수증/반복 저장과 검토의 hash를 다시 검사하고 신규 파일만 만든다. `PASS_NATIVE_WRITE_BOUNDED`는 이 요청의 최종 기록·검토 완료이며 기존 strict gate 통과가 아니다. 다른 한글 버전·타 PC 설치·모든 기능 편집을 보장하지 않는다. 기존 strict 실패는 별도로 유지한다.

HWP011 후보는 `compare_package_definitions.py`로 사용하지 않은 정의까지 포함한 header/refList를 읽기 전용으로 비교한다. 태그·속성 순서와 XML prefix 차이를 제외한 실제 정의 트리는 정확히 같아야 한다. URI값·조건 분기·미사용 문단/글자/번호/선 서식이 바뀌면 BLOCKED_OTHER_CHANGE다. 반복 저장에서도 같은 조건을 적용한다. 정의 확인 도구의 hash도 prepare 계약에 묶는다.

`write-proof.json.packageAudit`는 ZIP 항목별 이전/이후 hash 차이를 기록한다. 파일 hash가 달라도 출력 모습이 같은 경우가 있으므로 파일 바이트 동등성·활성 내용·미사용 정의·모든 쪽 PDF를 구분한다. Preview와 content.hpf/version.xml 메타데이터는 전체 바이트 보존 미검증으로 남기며, 내부 의미가 모두 같다는 보증으로 해석하지 않는다. HWPX 직접 재편집·저장/재열기 시험도 별도의 근거로 기록한다. 새 작성·API 재편집은 sibling hwpx의 references/candidate-runtime.md를 따라 수정한 후보 라이브러리를 선택한다.
