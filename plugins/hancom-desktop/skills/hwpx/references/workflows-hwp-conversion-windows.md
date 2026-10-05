# Windows HWP to HWPX conversion

구형 바이너리 `.hwp`는 HWPX MCP 도구에 바로 넣지 않는다. Windows에 한컴의
`HwpxConverter.exe`가 설치되어 있으면 GUI 자동화보다 명령줄 전처리를 우선한다.

## 절차

1. 원본 `.hwp`를 작업공간 안의 별도 임시 폴더에 복사한다. 원본 폴더에서 직접 변환하지 않는다.
2. 아래 후보 중 실제 존재하는 변환기를 찾는다.
   - `C:\Program Files (x86)\Hnc\HwpxConverter\HwpxConverter.exe`
3. 변환기를 복사본의 절대 경로 하나와 함께 실행한다.

   ```powershell
   & 'C:\Program Files (x86)\Hnc\HwpxConverter\HwpxConverter.exe' 'C:\path\to\copied-file.hwp'
   ```

   변환기는 같은 폴더에 같은 기본 이름의 `.hwpx`를 생성한다. 경로에는 항상 따옴표를 쓴다.
4. 실행 종료만 성공 증거로 삼지 않는다. 제한 시간을 두고 예상 `.hwpx`의 생성 여부와 파일 크기를 확인한다.
5. 생성 파일을 `document_to_markdown` 또는 적절한 HWPX 읽기 도구로 다시 열어 `ok=true`, 문단·표 수,
   경고를 확인한다. 편집 산출물이면 일반 HWPX 검증 절차와 `hwpx-windows-finalize`도 이어서 수행한다.

## 실패 처리

- 출력이 생기지 않으면 동일 명령을 반복하지 말고 변환기 설치 경로, 입력 확장자, 암호 문서 여부,
  동일 이름 출력 파일 충돌을 확인한다.
- 변환기가 없거나 명령줄 변환이 실패할 때만 한컴 GUI/Computer Use 또는 다른 승인된 변환 경로를 사용한다.
- 기존 `.hwpx`가 있는 폴더에서는 덮어쓰기 위험을 피하기 위해 매번 비어 있는 임시 폴더를 사용한다.
