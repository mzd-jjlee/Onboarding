# iceberg 프로젝트 작업 규칙

이 폴더는 Claude와 Codex가 번갈아 작업한다. 공통 프로젝트 규칙은
[CLAUDE.md](CLAUDE.md)를 읽고 따른다. 실행 상태와 검증 결과는 README 및 docs를 기준으로 확인한다.

- 시작할 때 현재 파일과 git 변경을 확인하고, 다른 도구의 변경을 덮어쓰지 않는다.
- 사용자는 레이크하우스 입문자다. 구성 요소의 역할, 설정 이유와 검증 결과를 한국어로 설명한다.
- 기존 lake/ 파일과 catalog-db 볼륨을 보존한다. 원시 APPEND job을 반복 실행하지 않는다.
- Iceberg JSON/Avro 내부 경로를 수동 치환하거나 HMS 내부 DB를 직접 수정하지 않는다.
- 분석 계층은 compose.analytics.yaml을 기존 compose.yaml과 함께 사용한다.
- 실행으로 확인한 결과와 설계 단계인 내용을 구분한다. 새 실행 결과는 evidence/에 남긴다.
- 변경 후 실제 실행 방법과 남은 작업을 README/docs에 반영하고 CLAUDE.md의 현재 상태를 갱신한다.
