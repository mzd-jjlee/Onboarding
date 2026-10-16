# Trino로 기존 Iceberg 테이블 조회하기

기존 SeaTunnel이 작성한 `retail.orders`를 Trino에서 조회하는 구성이다. Superset은 후속 단계다.

## 연결 구조

```text
DBeaver / Trino CLI
        │ localhost:8081 (호스트)
        ▼
Trino :8080 ── Thrift ──▶ HMS :9083 ──▶ catalog-db
        │                 현재 metadata_location 반환
        └─ 읽기 전용 /lake → JSON → manifest list → manifest → Parquet
```

`compose.analytics.yaml`은 기존 Compose에 Trino만 추가하는 파일이다. 두 파일을 함께 사용해야 같은 서비스·네트워크 설정을 적용한다. Superset 서비스는 아직 없다.

## 시작과 조회

Mac 터미널에서 저장소 루트로 이동한 뒤 실행한다.

```sh
cd /Users/mz01-jaejunlee/projects/Onboarding/iceberg
bash scripts/up-trino.sh
bash scripts/trino.sh --execute 'SELECT * FROM iceberg.retail.orders ORDER BY order_id'
```

`up-trino.sh`는 기존 catalog-db와 HMS, Trino를 기동하고 준비 상태를 기다린다. 원본 DB나 SeaTunnel 적재 job은 실행하지 않는다. 기존 DB 볼륨과 lake 파일이 있는 환경을 전제로 한다.

전체 검증:

```sh
python3 scripts/verify_trino.py
```

이 검증은 현재 실습 데이터인 주문 5건과 각 행의 값, 합계 170000, 상태별 합계, 스냅샷 2개, 첫 스냅샷 3건/69000, 데이터 파일 2개를 확인한다. 나중에 데이터를 추가했다면 기존 기대값을 사용하는 검증이 실패하는 것이 정상이다. SQL과 CSV 결과는 `evidence/trino/`에 기록한다.

## DBeaver 연결

새 연결에서 **Trino**를 선택한다. 기존 PostgreSQL 연결과는 별개다.

| 항목 | 값 |
|---|---|
| Host | `localhost` |
| Port | `8081` |
| Catalog | `iceberg` |
| Schema | `retail` |
| Username | `analyst` |
| Password | 비워 둠 (로컬 무인증 구성) |
| JDBC URL | `jdbc:trino://localhost:8081/iceberg/retail` |

드라이버 다운로드 안내가 나오면 Trino JDBC 드라이버를 설치한다. 조회 SQL:

```sql
SELECT * FROM iceberg.retail.orders ORDER BY order_id;
SELECT status, count(*) AS order_count, sum(amount) AS total_amount
FROM iceberg.retail.orders GROUP BY status ORDER BY status;
SELECT snapshot_id, parent_id, operation
FROM iceberg.retail."orders$snapshots";
```

`http://localhost:8081`은 Trino 실행 상태·쿼리 모니터링 화면이다. Superset 같은 SQL 작성·차트 화면이 아니다. 사용자 이름을 요구하면 `analyst`를 입력한다. Superset을 추가하면 컨테이너끼리는 `trino:8080`으로 연결한다.

## 설정 파일의 역할

| 파일 | 역할 |
|---|---|
| [compose.analytics.yaml](../compose.analytics.yaml) | 이미지 483, 포트, 2GB 메모리 제한, 읽기 전용 마운트 |
| [iceberg.properties](../config/trino/catalog/iceberg.properties) | Iceberg 커넥터, HMS 연결, 파일시스템, 읽기 전용 정책 |
| [config.properties](../config/trino/config.properties) | 단일 coordinator/worker와 쿼리 메모리 설정 |
| [jvm.config](../config/trino/jvm.config) | Java 힙 1GB |
| [node.properties](../config/trino/node.properties) | 노드 이름·실행 데이터 위치 |

catalog 이름 `iceberg`는 `iceberg.properties` 파일명에서 나온다. HMS namespace `retail` 및 테이블 `orders`와 결합해 `iceberg.retail.orders`가 된다.

### 기존 file: 경로를 읽는 설정

```properties
fs.local.enabled=true
local.location=/
```

Trino 483 소스는 `file`과 `local` 스킴을 같은 local filesystem에 연결한다. `local.location`의 실제 구현 타입은 `java.nio.file.Path`이며 URI 문자열이 아니다. 기존 `file:/lake/...`에서 읽은 상대 path `lake/...`에 루트 `/`를 붙여 실제 `/lake/...`로 해석한다.

따라서 이 환경에서 `local.location=/lake`로 설정하면 `/lake/lake/...`를 찾게 된다. 이전 설계 문서의 `local.location=local:///lake` 예시는 이번 실제 설정으로 대체한다. 호스트 전체를 마운트하는 것은 아니며, 공유 데이터 마운트는 `./lake:/lake:ro`뿐이다. Iceberg catalog도 `READ_ONLY`로 설정한다.

근거: [Trino 483 FileSystemModule](https://github.com/trinodb/trino/blob/483/lib/trino-filesystem-manager/src/main/java/io/trino/filesystem/manager/FileSystemModule.java), [LocalFileSystem](https://github.com/trinodb/trino/blob/483/lib/trino-filesystem/src/main/java/io/trino/filesystem/local/LocalFileSystem.java), [LocalFileSystemConfig](https://github.com/trinodb/trino/blob/483/lib/trino-filesystem/src/main/java/io/trino/filesystem/local/LocalFileSystemConfig.java).

## 중지와 설정 반영

```sh
# Trino만 중지. HMS·DB와 데이터는 유지한다.
docker compose -f compose.yaml -f compose.analytics.yaml stop trino

# properties 설정을 바꾼 뒤 다시 로드하려면 재시작한다.
docker compose -f compose.yaml -f compose.analytics.yaml restart trino
```

Compose 설정 자체를 바꾼 경우 `bash scripts/up-trino.sh`로 다시 적용한다. `down -v`는 데이터 볼륨을 삭제하므로 사용하지 않는다.

## 작업 규칙과 프로젝트 문서

`AGENTS.md`는 Codex 등 에이전트의 진입 지침이며 이 프로젝트에서는 `CLAUDE.md`의 공통 규칙을 참조한다. `CLAUDE.md`에는 아키텍처 경계와 현재 상태를, README에는 문서 진입점과 실행 요약을, 이 문서에는 재현 가능한 설정과 연결 방법을 둔다. 대화에서 정한 내용을 파일에 남겨 다른 도구가 이어서 작업할 수 있게 한다.

## 실제 검증 결과 — 2026-10-06

| 확인 항목 | 결과 |
|---|---|
| Trino 서버 버전 | 483 (`linux/arm64`) |
| HMS에서 테이블 탐색 | `retail.orders` 확인 |
| 현재 데이터 | 5건, 각 행 값 확인, 합계 170000 |
| 상태별 집계 | DONE 3건/113000, NEW 2건/57000 |
| 스냅샷 | 2개 |
| 첫 스냅샷 조회 | 3건, 합계 69000 |
| 현재 데이터 파일 | 2개, 합계 5행 |
| 호스트 HTTP 접속 | localhost:8081의 `/v1/info` 응답 확인 |
| 원본 lake 파일 보존 | 검사 대상 9개 파일 SHA-256 변경 없음 |
| 기동 명령 | Compose `up --wait` 정상 종료 |

[검증 요약](../evidence/trino/verification.json), [현재 행 CSV](../evidence/trino/orders.csv), [파일 목록](../evidence/trino/files.csv), [실행 환경](../evidence/trino/runtime.json), [파일 보존 검사](../evidence/trino/lake-integrity.json).

SeaTunnel job을 재실행하거나 HMS 등록 정보/JSON/Avro 경로를 수정하지 않았다. DBeaver GUI 연결은 사용자가 위 접속 정보로 수행하면 된다. 검증한 클라이언트는 컨테이너의 Trino CLI이며, 호스트 HTTP 연결도 별도로 확인했다. Superset, CDC 수정·삭제, 다중 노드, 성능 검증은 이번 범위가 아니다.
