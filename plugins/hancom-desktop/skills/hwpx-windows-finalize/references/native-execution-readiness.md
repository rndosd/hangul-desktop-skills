# 네이티브 실행 준비와 실패 단계

설치 성공과 실제 COM 실행 준비를 구분한다. 설치 확인만으로 native-ready를 표시하지 않는다. 문서를 열기 전 실제 worker가 COM 생성, 검토한 RegisterModule 반환을 따로 기록해야 한다.

`scripts/classify_hancom_failure.py input.json --output new-classification.json`은 controller command 또는 worker receipt를 읽어 실패 단계를 구분하는 진단기다. 설정 변경·재시도·보안 모듈 등록을 수행하지 않는다.

- `CONTROLLER_PROCESS_LAUNCH`: Start-Process dictionary/Path 충돌이면 worker 자체가 시작하지 않았을 수 있다. Python 호출자가 환경을 암묵적으로 상속하는 경로와 명시적으로 직렬화하는 경로를 확인한다. 자식 환경만 `env=dict(os.environ)` 또는 Windows 이름을 정규화한 새 dict로 전달하는 후보를 실제 검증한다. 사용자/시스템 환경변수나 실행 정책을 고치지 않는다. HWP008의 원래 오류는 독립 실험에서 다시 재현되지 않아 근본 예방 효과는 미검증이다.
- `COM_ACTIVATION`: COM 객체를 못 만들었으면 보안 모듈은 미호출이다. 0x80080005와 같은 시점의 DCOM 로그를 기록한다. 같은 스크립트·DLL·후보를 승인된 일반 로그인 사용자 맥락에서 한 번 비교한다. 일반 맥락 성공은 설치/DLL 장애보다 실행 맥락 차이를 뒷받침하나, HRESULT만으로 특정 DCOM 권한을 원인이라고 단정하지 않는다.
- `SECURITY_MODULE_REGISTRATION`: COM 성공 뒤 실제 RegisterModule=false일 때만 모듈 문제를 조사한다. 모듈 이름/검토한 DLL/32·64비트/실제 사용자 등록 경로를 읽기 비교하고 문서 Open은 중단한다.
- `PRE_COM_CONFLICT`: 기존 Hwp/자동화 잠금은 COM/등록 실패가 아니다. 사용자 프로세스를 종료하지 않는다.
- Open/Save/reopen/PDF/cleanup은 각각 해당 영수증으로 구분한다. PASS_FULL과 strict 보존/시각 완료는 별도다.

배포 설계에서는 네이티브 작업을 안정적인 동일 Windows 로그인 세션의 STA worker에서 수행하도록 실행 경로를 제공해야 한다. Codex 샌드박스 밖 실행은 호스트가 승인한 executor 또는 명시적으로 설치·선택한 로컬 backend를 사용한다. 스킬 자체가 권한을 높이거나 샌드박스를 해제할 수 있다고 가정하지 않는다. 승인 없이 예약 작업/서비스를 설치하거나 실행 정책·레지스트리·DCOM ACL을 변경하지 않는다.

HWP009 후보에는 `scripts/run_native_job.py`와 읽기 전용 `check_native_context.ps1` 실행 경로를 추가했다. Python 3.12·sibling 환경 일치·실제 한글 경로/버전/PE 형식·검토된 DLL/정책 해시·일반 로그인 세션·STA·기존 프로세스 충돌을 확인한다. 자식 환경 키를 Windows 규칙으로 정규화하고 값이 다른 Path/PATH 입력은 거부한다. 기존 controller/worker와 프로세스 보호를 유지하며 단계별 command/context/receipt/classification을 새 run에 기록한다.

```powershell
& $hangulPython -X utf8 -B scripts/run_native_job.py source.hwpx --mode OpenOnly --run new-preflight --context ordinary-shell --preflight-only
& $hangulPython -X utf8 -B scripts/run_native_job.py source.hwpx --mode SaveAs --output new-saved.hwpx --pdf new-output.pdf --run new-native-job --context ordinary-shell
```

`$hangulPython`은 해당 PC의 선택된 environment.json의 pythonPath다. 두 sibling의 environment.json은 해당 PC 설치 안내로 구성하고 이전 PC 파일을 복사하지 않는다. 검토되지 않은 DLL·정책을 자동 설치/등록하지 않는다. 설정이 없거나 파일/해시/설치가 달라지면 중단하고 최소 조치를 제안한다. read-only preflight 통과는 COM/등록 성공이 아니다. 실제 worker 영수증에서 각각 확인한다.

context 인자는 호출자가 선택한 맥락 표시이며 샌드박스 자동 감지/해제 기능이 아니다. `host-approved`는 호스트가 승인한 같은 사용자 실행 맥락에만 사용한다. 자동 권한 상승·fallback·재시도·서비스/예약 작업 설치는 하지 않는다. 실제 backend 설치·transport·자동 경로 선택과 타 PC 설치 E2E는 아직 미구현/미검증이다. 이 PC 일반 맥락 7건 성공을 타 PC 준비 완료로 확대하지 않는다. 각 PC에서 실제 호출 경로로 합성 문서의 열기/저장/재열기/PDF까지 확인한다.
