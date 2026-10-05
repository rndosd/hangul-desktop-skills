# 공식 보고서 기능의 선택 작성·그림 교체

보고서 내용이나 목차를 정하지 않는다. 캡션·주석·링크·요약 상자는 내용에 필요할 때만 선택한다.
아래는 한글 2024 13.0.0.3903에서 확인한 범위다. 공식 기능의 존재와 이 스킬의 구현을 구분한다.

## 새 보고서의 개체

`scripts/report_objects.py`는 검증된 새 문서 composer 위에 선택 개체를 추가한다.
`environment.json`의 Python을 쓰며 python-hwpx와 PyMuPDF가 필요하다. PyMuPDF가 없으면
기존 설치기의 `-InstallPdfRuntime`을 사용한다. COM/DLL의 준비 상태는 finalize의 PC별 환경을 따른다.

```powershell
python -X utf8 scripts/report_objects.py --brief brief.json --design design.json --objects objects.json --output new.hwpx
```

objects 입력은 `{"schema":"hwpx.report-objects.v1","items":[...]}`이다.
각 항목의 block은 design.plan.blocks에 있는 유일한 일반 본문 paragraph의 id다.
목록·표 셀·중첩 story를 앵커로 쓰지 않는다. 같은 문구가 다른 블록에도 있으면 거부한다.

| kind | 추가 값 | 실제 범위 |
|---|---|---|
| picture | path, sha256, width_mm, caption, 선택 gap_mm | 검증된 PNG/JPEG, 원비율, 글자처럼 취급, native 아래 캡션 |
| box | text, width_mm, height_mm | 새 사각형 요약 상자, native 줄바꿈 |
| footnote / endnote | text | 본문 문단 끝의 native 각주/미주 앵커 |
| bookmark | name | 유일한 이름의 본문 책갈피 저장 |
| hyperlink | url, text | http/https 웹 링크; native 저장/PDF URI 확인 |

그림·상자·링크는 해당 앵커 문단을 대체한다. 각주·미주·책갈피와 대체 개체의 동일 앵커 혼용은 거부한다.
그림은 10~170mm, 상자는 20~170mm이며 실제 본문 폭을 넘을 수 없다. 상세 크기 제한은 코드의 validate를 따른다.
PNG/JPEG의 확장자·실제 형식·해시를 대조한다. 예시 JSON과 가상 그림은 `assets/official-features`에 있다.
객체용 placeholders는 작성 에이전트의 설계 입력일 뿐 사용자의 짧은 요청에 요구하지 않는다.

주의할 동작:

- 캡션은 native 개체에 붙지만 문구 안의 그림 번호를 자동 재계산하지 않는다.
- 각주/미주는 새 본문 끝에만 작성한다. 기존 주석의 위치/번호 정책 변경은 이 도구의 범위 밖이다.
- 문서 끝 미주가 별도 쪽을 만들 수 있다. 한 쪽에 맞추기 위해 주석을 임의 삭제하지 않는다.
- 책갈피 control 저장 보존을 확인했다. GUI 이동을 검증한 것으로 해석하지 않는다.
- URL을 name에만 저장하던 라이브러리 동작은 내부 링크로 출력됐다. 새 필드의 Command를 공식 `URL;1;0;0`으로 명시한다.
- URL은 자격 증명, raw 세미콜론, 공백과 실행 파일 링크를 거부한다. 링크 실행 보안 설정은 바꾸지 않는다.

기본 문서 감사와 비대상 본문·개체 텍스트·개수·URL Command 검사를 통과한 결과는 PASS_STRUCTURE다.
실제 한글 출력까지 완료했다고 말하려면 해당 후보의 필요한 native 저장·재열기·전 쪽 검토를 수행한다.

## 기존 그림의 제한 교체

`scripts/safe_picture_replace.py`는 명시한 단일 비공유 그림의 이미지 데이터만 교체한다.

```powershell
python -X utf8 scripts/safe_picture_replace.py inspect source.hwpx replacement.png --picture 1 --plan new-plan.json
python -X utf8 scripts/safe_picture_replace.py apply new-plan.json --output new.hwpx --dry-run
python -X utf8 scripts/safe_picture_replace.py apply new-plan.json --output new.hwpx
```

picture는 manifest의 section spine 순서로 열거한 1부터 시작하는 그림 순번이다.
순번만 신뢰하지 않고 source/image 해시, 객체 id·XML 해시, 기존 payload 해시와 단일 참조를 바인딩한다.
공유·외부 연결·해결되지 않은 그림, PNG/JPEG 이외 형식, 다른 형식/픽셀 크기는 거부한다.
같은 형식과 정확히 같은 픽셀 크기만 허용하므로 프레임, crop, 회전, 캡션, 위치를 그대로 보존한다.
비율 변경·자동 잘라맞춤은 별도 미지원 연산이다. 기존 편집 진단의 BLOCK을 우회하는 폴백이 아니다.

출력 HWPX의 모든 비대상 ZIP 구성원과 모든 XML을 byte-exact로 비교한다.
정적 검사가 통과해도 실제 출력·그림 내용·주변 캡션/본문 검토를 생략하지 않는다.
시험에서는 한글 PDF의 JPEG 공유/재압축 때문에 **교체하지 않은 그림의 가장자리·색 픽셀**도 소폭 달라졌다.
그림의 원래 HWPX PNG와 모든 기하는 동일했다. PDF 전체 픽셀 불변까지 보장하지 않는다.

## 번호와 실제 검증

독립 bullets 블록도 native NUMBER/BULLET로 생성한다. 본문에 번호 문자나 글머리 접두어를 붙이지 않는다.
같은 목록 안은 하나의 정의로 이어지고, 번호 목록 블록마다 새 정의를 만든다.
실제 한글에서 3항목→4항목 추가→3항목 삭제, 긴 항목의 이어지는 줄 내어쓰기를 확인했다.
이 편집 시험 worker는 고정 가상 문서용이며 범용 기존 목록 편집 명령으로 배포하지 않는다.
선택 TEXT/saveblock은 전체 문서 번호와 달리 선택한 번호 문단을 1부터 내보낼 수 있다.
빈 번호 문단의 첫 Backspace는 번호만 해제할 수 있다. 정확한 대상/커서 확인 없이 추가 삭제하지 않는다.

실제 시험: 작성 3쪽·목록 1쪽·그림 교체 3쪽과 목록 편집 각 1쪽; 저장·재열기·전체 검토.
57개 회귀검사와 URL/캡션/크기/각주/책갈피/표 여백/그림 연결 7개 변조 거부를 확인했다.
최초 저장의 빈 텍스트·참조명·control 정규화는 writer 수정으로 해결한 것이 아니다.
최초 실패를 보존하고 독립 비교한 정확한 native 저장본에서 새 strict 완료 검사를 수행했다.
완료 gate·보안/DLL 정책은 약화하지 않았다. 다른 PC의 native 준비 상태는 따로 확인한다.

## 공식 기능과 후속 범위

[캡션](https://help.hancom.com/hoffice130/ko-KR/Hwp/insert/caption.htm),
[각주](https://help.hancom.com/hoffice130/ko-KR/Hwp/insert/annotations/footnotes.htm),
[미주](https://help.hancom.com/hoffice130/ko-KR/Hwp/insert/annotations/endnotes.htm),
[책갈피](https://help.hancom.com/hoffice130/ko-KR/Hwp/insert/bookmark/bookmark.htm),
[하이퍼링크](https://help.hancom.com/hoffice130/ko-KR/Hwp/insert/hyperlink/hyperlink.htm),
[한컴 자동화 문서](https://developer.hancom.com/hwpautomation)를 근거로 했다.
ActionTable_2504의 Hyperlink/InsertText/BreakPara, ParameterSetTable_2504의 HyperLink/Command 관련 부분을 대조했다.
공식 매뉴얼·보안 DLL을 이 기능 업데이트에 추가 재배포하지 않는다.

native 데이터 차트, 자동 목차·상호 참조, 임의 기존 주석/캡션/구역 재구성과 일반 목록 구조 편집은
이번 추가 기능으로 지원 완료가 되지 않는다. 실제 요청에 필요할 때 별도 구현·검증한다.


## 추가 검증: 기존 본문/목록 구조

위 고정 scratch COM 항목 실험은 그대로 구분한다. 이후 별도 [safe_body_structure.py 경로](body-structure-edit.md)를 구현해 root-body plain 문단과 기존 native NUMBER/BULLET의 제한 추가·삭제를 제공한다. 복합 3쪽 원본에서 3변경, 12쪽의 실제 한글 완료·전체 출력 검토를 통과했다. 임의 기존 표/control/주석/구역/번호 계층 재설계는 지원하지 않는다.


## 추가 검증: 기존 본문/목록 구조

위 고정 scratch COM 항목 실험은 그대로 구분한다. 이후 별도 [safe_body_structure.py 경로](body-structure-edit.md)를 구현해 root-body plain 문단과 기존 native NUMBER/BULLET의 제한 추가·삭제를 제공한다. 복합 3쪽 원본에서 3변경, 12쪽의 실제 한글 완료·전체 출력 검토를 통과했다. 임의 기존 표/control/주석/구역/번호 계층 재설계는 지원하지 않는다.


사진 아래 긴 캡션과 쪽 경계는 [사진·캡션 배치](picture-caption-layout.md)의 폭·여백·원본 보존 및 실제 출력 확인 절차를 따른다.
