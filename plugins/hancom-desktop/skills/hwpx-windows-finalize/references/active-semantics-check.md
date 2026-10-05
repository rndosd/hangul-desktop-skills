# 활성 내용·서식 비교

표 구조 편집 뒤 선택 표 전체 높이의 native 계산·최종 기록이 요청되면 [한글 최종 기록](native-writing.md)을 별도로 선택한다. 일반 활성 의미 비교의 높이 실패를 자동으로 무시하지 않는다.

```powershell
python -X utf8 -B scripts/compare_active_semantics.py before.hwpx after.hwpx --output new-comparison.json
```

읽기 전용 보조 검사이며 기존 strict 완료 gate를 대체하지 않는다. 문단·표·셀·개체의 소유 위치를 유지하며 사용 중인 charPr/paraPr/style/font/borderFill 등의 참조를 실제 정의로 풀어 비교한다. 바이너리 목록뿐 아니라 소유 개체 연결을 비교한다. 같은 서식의 인접 순수 텍스트 run만 합치고 문단·다른 서식·제어 경계를 넘지 않는다. 인라인 제어 전후 text와 tail도 보존한다. 빈 run의 서식·제어는 지우지 않는다.

- 종료 0 `PASS_ACTIVE_SEMANTICS`: 검사 범위의 활성 내용·서식·개체 연결 일치. 전체 패키지·배치·native 성공 인증이 아니다.
- 종료 3 `FAIL_PRESERVATION`: 내용/자산 손실 또는 같은 스키마·글꼴 환경에서 활성 구조 변화.
- 종료 2 `UNVERIFIED_NORMALIZATION` / `UNVERIFIED_INVALID_INPUT`: 버전·대체 글꼴·알 수 없는 정의/참조 등의 미해결 차이. 자동으로 동등 처리하지 않는다.

`linesegarray` 배치 캐시는 의미 비교에서 제외하므로 실제 한글과 모든 요구 쪽 출력 검토가 필요하다. 사용하지 않는 정의·메타데이터·다른 한글 버전·향후 편집 동작까지 보장하지 않는다. 최초 SaveAs와 저장된 사본의 반복 SaveAs를 각각 비교한다. 반복 저장 통과가 최초 변환의 미해결 차이를 소급 통과시키지 않는다.

HWP009 최초 저장: 긴 문서의 1.4→1.5/대체 글꼴 변화는 미검증, 합성 문서 표 전체 높이 23000→29082는 보존 실패로 남았다. 출력은 각각 모든 쪽에서 동일했고 이후 반복 저장은 활성 비교를 통과했다. 인라인 제어 뒤 글자 손실 오판은 실패 쌍을 보존하고 수정 후 손실로 검출했다.
