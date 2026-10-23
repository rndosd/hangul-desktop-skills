# 원본 서식과 다른 PC 이전

2026-10-23 현재 사용 중인 `hwpx`와 `hwpx-windows-finalize`의 작성·편집·검수 규칙 및 도구를 공개 묶음에 반영했습니다. 개인적인 생각이나 생활 기록은 포함하지 않습니다.

## 동봉한 서식

`plugins/hancom-desktop/skills/hwpx/assets/document-templates/catalog.json`에는 계획서·보고서·안내/신청서·회의문서 원본의 출처, 용도, 파일 해시와 확인 범위를 보존했습니다. 실제 파일은 같은 폴더의 `source-library/`에 있습니다.

- `source-A`부터 `source-F`: 기관 원본 6개.
- `extra-01`부터 `extra-07`: 예산·정산·안내/신청·회의 등에 쓰는 관련 원본 7개.
- `style-01`부터 `style-03`: 계획서·검토보고서·결과보고서용으로 가공한 서식 견본 합본 3개.
- 각 문서에 대응하는 PDF 미리보기 16개.

합본 3개만으로 모든 용도를 처리하는 구조는 아닙니다. 현재 기본 선택은 계획서 `source-A`, 보고서 `source-D`, 안내/신청서 `extra-04`, 회의문서 `extra-07`이며, 원본 또는 견본을 복사한 뒤 새 내용에 맞춰 변형합니다. 동봉 파일은 완성된 새 업무 문서가 아닙니다.

사용자의 공개 배포 요청에 따라 현재 보관본을 포함했습니다. 외부 원본은 자체 출처와 이용조건을 따르며, 이 저장소의 코드 라이선스를 원본 서식에 일괄 적용하지 않습니다. 목록에 기록된 이용조건 미확인·별도 조건·예시 수치의 제한도 그대로 유지합니다.

직접 준비한 원본은 다음처럼 새 사본으로 복사합니다. Python과 스킬 경로는 현재 PC의 설치 결과를 사용합니다.

```powershell
& $pythonExe -X utf8 "$taskSkillDir/scripts/select_document_template.py" --source '사용자서식.hwpx' --output '업무폴더/새 사본.hwpx'
```

`--list`와 `--all`은 출처 목록 조회입니다. `--kind`나 `--id`는 동봉한 보관 원본을 해시 확인 후 복사합니다. 목록에 기록된 과거 원본 열기·출력 검수는 새 문서나 새 PC 검수의 성공을 뜻하지 않습니다.

## 다른 PC에서 현재 버전 설치

다음처럼 공개 저장소의 최신 Git 소스를 받습니다. 릴리스 ZIP은 이전 버전일 수 있으므로 최신 Git 소스와 구분하세요.

```powershell
git clone --depth 1 https://github.com/rndosd/hangul-desktop-skills.git
cd hangul-desktop-skills
.\Install.ps1 -CheckOnly
.\Install.ps1
```

이전 PC의 `environment.json`, Python 실행 파일, 한글 프로그램, DLL 및 보안 모듈 승인 기록은 복사하지 않습니다. 설치기는 새 PC의 환경을 준비하며 보안 모듈 선택과 실제 한글 출력 검수는 해당 PC에서 별도로 확인합니다. 기본 설치가 다른 PC의 보안 모듈 등록이나 승인을 대신하지 않습니다.
