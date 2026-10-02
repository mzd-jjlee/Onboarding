# iceberg — 로컬 소규모 데이터 레이크 실습

SeaTunnel로 로컬에 parquet을 쌓고, 그것을 **Iceberg 테이블**로 관리하면서
**DuckDB**로 조회하는 구성을 로컬에서 실험하는 프로젝트. 카탈로그는 **Hive Metastore**를 쓴다.

현재 상태: **자료 조사 완료, 구현 전.**

## 문서

**먼저 읽기:** [그림 중심 안내서 (브라우저용 HTML)](docs/local-lakehouse-visual-guide.html) · [Markdown 원문](docs/local-lakehouse-visual-guide.md)

역할, Docker 배치, 쓰기·조회 흐름, 스냅샷, OpenMetadata와의 차이를 **그림 8개**로 설명한다.
2026-10-02 공식 문서 대조 결과와 기존 조사 정정 사항은 안내서 9절에 있다. 아래 두 문서는 조사 원본이며, 정정 사항을 함께 읽어야 한다.

| 문서 | 내용 |
|---|---|
| [docs/iceberg-hive-duckdb-roles.md](docs/iceberg-hive-duckdb-roles.md) | Iceberg가 실제로 어디에 있는지(디스크 구조/메타데이터 3계층), Hive Metastore가 왜 필요한지, DuckDB가 Iceberg를 읽는 4가지 경로와 각각의 한계 |
| [docs/local-lakehouse-build-options.md](docs/local-lakehouse-build-options.md) | 구성 선택지 4가지 비교, 데이터 적재 두 방식(SeaTunnel parquet + PyIceberg `add_files` vs SeaTunnel Iceberg sink), HMS 로컬 기동 방법, 구현 전 검증 필요 항목 |

## 세 줄 결론

- **Iceberg**는 오픈 테이블 포맷과 이를 처리하는 구현이다. 별도 Iceberg SQL 서버를 띄우는 구조가 아니다.
- **Hive Metastore**는 테이블 이름과 현재 메타데이터 위치 등을 관리하는 카탈로그 서비스다.
  Iceberg JSON·manifest 파일과 Parquet 데이터는 파일 저장소에 있다. 이 설계에 HiveServer2는 필요 없다.
- **DuckDB**는 자체 저장 기능도 있는 임베디드 DB 엔진이다. 여기서는 외부 테이블을 SQL로 조회한다.
  PyIceberg → Arrow 경로와, 카탈로그에서 얻은 정확한 metadata 경로를 DuckDB가 직접 읽는 경로를 먼저 비교한다.

## 다음 단계 (제안)

1. 기존 Parquet을 DuckDB로 조회해 기준 결과 확인
2. HMS + 백엔드 DB + 공유 `/lake`를 구성하고 PyIceberg로 작은 테이블 생성·파일 등록
3. PyIceberg 경유 조회와 DuckDB 직접 읽기 비교, 커밋 전후·이전 스냅샷 확인
4. SeaTunnel Iceberg sink로 전환한 뒤 CDC 수정·삭제 검증

안내서의 HTML과 SVG 재생성: `python3 docs/build_visual_guide.py` (외부 패키지 불필요).
