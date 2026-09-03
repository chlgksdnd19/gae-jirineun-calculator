# 리셀 계산기 프로

리셀 계산기 프로의 Android 업데이트 APK와 백화점 행사 정보 피드를 배포하는
공개 저장소입니다.

## 백화점 정보 자동 갱신

`scripts/update_shopping_info.py`가 현대백화점·롯데백화점·신세계백화점의
공식 공개 행사 페이지를 읽어 `docs/shopping-info.json`을 만듭니다.

GitHub Actions의 `Update shopping information` 작업은 매일 한국 시간 오전
6시 17분에 실행됩니다. 외부 유료 서버나 유료 API는 사용하지 않습니다.

- 앱용 피드: `docs/shopping-info.json`
- 수집 실패 시: 해당 백화점의 마지막 정상 데이터를 유지
- 카드 선택 시: 원문 `sourceUrl`에 담긴 공식 행사 상세 홈페이지로 이동

공식 사이트의 페이지 구조가 바뀌면 파서 수정이 필요할 수 있습니다. 행사 적용
조건과 기간은 각 카드의 공식 상세 홈페이지에서 최종 확인해야 합니다.
