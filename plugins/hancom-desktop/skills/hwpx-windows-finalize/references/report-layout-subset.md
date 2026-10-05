# 출력 보고서의 제한된 지면 검사

`scripts/audit_report_layout.py PDF --expectations JSON`은 실제 저장본을 재열어 만든 PDF를 읽기만 한다. COM 생성, 보안 설정, 파일 수정/자동 교정은 하지 않는다. 원본 분석으로 기대 항목을 먼저 정한다.

schema `hwpx.report-layout-subset.v1`; 정확한 키는 pdfSha256, expectedPhysicalPages, intentionalBlankPages, headingPairs, tocEntries, sparseRules. headingPairs는 원본의 정확한 headingLine과 nextText, tocEntries는 tocPage/title/bodyTitle/bodyMinPage, sparseRules는 trigger/minimumCharacters/bodyMinPage이다. 각 목록은 최대40개다. 사용 예는 HWP063/package-tests의 실제 기대값 파일이다.

고정 목차는 본문 실제 표시 번호와 목차의 숫자 단어 좌표/제목 기준선을 대조한다. 요약 도식의 중복 제목은 bodyMinPage로 구분한다. 특정 UAM/PIS 희소 쪽 검사도 명시한 임계값에만 적용하며 모든 짧은 페이지를 오류로 취급하지 않는다. 원래 표지 뒤 빈 쪽은 지정해 보존한다.

이 검사는 전체 내용·육안 지면·한글 파일 의미 보존 합격을 대신하지 않는다. 모아찍기에서 물리면을 논리 쪽으로 추론하지 않는다. 두 논리쪽이 같은 인쇄면일 수 있어 제목/본문 같은 면이라는 결과만으로 같은 한글쪽을 보증하지 않는다. PDF 글리프 추출이 불완전하면 해당 binding 검사를 해결해야 하며 문자열 삭제/광범위 Unicode 정규화로 통과시키지 않는다.

HWP063 국토 최신 출력6개에서 목차·제목 연결·특정 희소 쪽 검사를 통과했다. 이전 HWP061 실제 실패 PDF의 고정 목차 불일치와 희소 쪽을 검출하는 검사도 별도로 했다. 전남 모아찍기는 이 도구로 물리7면만 확인하고 논리1~13쪽·표 구조·설명 문단은 별도 독립검사/전쪽 검토했다. 자동 교정/모든 보고서 인증은 아니다.
