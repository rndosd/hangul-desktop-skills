# 후보 라이브러리와 HWPX 파일 보존

이 후보는 설치된 python-hwpx 6.3.0의 사본을 vendor/hwpx에 포함한다. 바뀐 파일은 opc/xml_utils.py 하나이며 2016 네임스페이스를 읽을 때 태그·속성 이름과 namespace binding만 2011로 정규화한다. hp:required-namespace 같은 속성값·본문·주석은 바꾸지 않는다. 설치된 Python 패키지·환경변수·등록/보안 설정은 수정하지 않는다. vendor/licenses와 UPSTREAM-METADATA를 함께 보존한다.

실제 Python 파일을 새로 작성할 때 hwpx를 import하기 전에 이 후보 scripts 경로를 sys.path에 넣고 `from candidate_runtime import activate; activate()`를 실행한다. 실제 hwpx.__file__과 vendor/hwpx/opc/xml_utils.py SHA를 기록한다. 이미 다른 hwpx를 import한 프로세스에서는 실패하므로 새 프로세스에서 올바른 후보를 선택한다. 임의의 monkey patch나 raw XML 편집으로 돌아가지 않는다.

기존 CLI는 다음처럼 후보 launcher로 실행한다. Python 경로와 스킬 경로는 해당 PC/후보의 environment.json에서 확정한다.

```powershell
& $hangulPython -X utf8 -B scripts/candidate_runtime.py scripts/safe_rich_table.py inspect source.hwpx --table 1 --output inspection.json
```

HWP011에서는 기본 스켈레톤의 개요 서식16~18에 있는 조건 URI가 일반 문자열 치환으로 2016→2011로 바뀌어, 한글 저장 뒤 OUTLINE7/8/9가 NONE으로 변했다. 실제 사용하지 않은 정의라 PDF는 같았지만 HWPX에는 차이가 있었다. 빈 문서를 미리 저장하는 접근도 같은 입력 처리 문제를 해결하지 못했다. 이 실험의 빈 초기화 helper는 배포 후보에서 제외했으며 기본 스켈레톤으로 작성하되 위 라이브러리 사본을 선택한다.

저장 검증은 동료 finalize의 native-writing.md에 있는 전체 활성 트리·모든 header refList 정의·모든 쪽 출력 비교를 각각 수행한다. 버전/글꼴/미사용 서식 변화는 자동 승인하지 않는다. HWPX ZIP의 각 항목 hash 차이를 보고하고 파일 자체가 바이트 단위로 같다고 말하지 않는다. Preview·파일 메타데이터 차이는 별도로 남는다. 저장된 파일을 다시 실제 API로 편집한 사본이 한글 저장·재열기 뒤 요청한 글과 서식을 유지하는지도 필요한 사례에서 확인한다. 이 시험은 모든 UI 편집 기능의 검증을 대신하지 않는다.

새 표의 내용이 쪽 높이를 넘을 때에는 [새 표의 여러 쪽 출력](created-report-table.md)을 읽는다. 픽셀 동등성을 확인해도 양쪽 출력이 모두 잘린 경우가 있으므로 입력의 마지막 행·모든 필요한 문단을 실제 출력과 대조한다.
