# Iceberg는 어디에 있고, Hive와 DuckDB는 각각 무슨 역할인가

> **조사 원본 · 정정 안내 (2026-10-02):** 아래 내용에는 DuckDB의 저장 기능, HadoopCatalog,
> 불변 파일, gzip, 파일 수명 및 Hive REST 버전 등에 대한 과도한 단정이 있다.
> [그림 중심 안내서 9절](local-lakehouse-visual-guide.md#9-기존-조사에서-확인한-내용과-정정할-내용)의 검증 결과를 우선한다.
> 원래 조사와 정정 내용을 비교할 수 있도록 본문은 보존했다.

로컬에 소규모 데이터 레이크를 만들기 전에, 세 컴포넌트의 **포지션**을 먼저 정리한 문서다.
"무엇을 설치해서 어떻게 띄우는가"는 [local-lakehouse-build-options.md](local-lakehouse-build-options.md)에서 다룬다.

## 0. 한 줄 요약과 흔한 오해 정정

| 컴포넌트 | 실제 정체 | 한 줄 역할 |
|---|---|---|
| **Apache Iceberg** | 파일 레이아웃 **규약(스펙) + 라이브러리** | 디스크의 parquet 더미를 "테이블"로 보이게 하는 메타데이터 계층 |
| **Hive Metastore** | 상주하는 **서비스**(Thrift RPC + 백엔드 RDB) | "테이블 이름 → 현재 metadata 파일 위치" 포인터를 원자적으로 관리하는 카탈로그 |
| **DuckDB** | 프로세스에 임베드되는 **쿼리 엔진** (라이브러리) | Iceberg 메타데이터를 해석해 필요한 parquet만 읽어 SQL로 응답 |

처음 가정했던 것 중 두 가지를 짚어둘 필요가 있다.

1. **"DuckDB는 Iceberg 조회할 때 쓰는 저장소"** → DuckDB는 저장소가 아니라 **쿼리 엔진**이다.
   데이터는 끝까지 로컬 디스크의 parquet 파일에 있고, DuckDB는 그걸 읽어서 계산만 한다
   (자체 `.duckdb` 파일에 복사해 담을 수도 있지만, 그건 레이크하우스 조회가 아니라 그냥 적재다).
   "항상 서비스로 떠있지 않고 Python 애플리케이션이 쓸 때만 붙는다"는 이해는 **정확하다** —
   DuckDB는 SQLite와 같은 in-process 모델이라 서버 프로세스가 없다. 다만 그래서 역할이 "저장"이 아니라 "조회"인 것이다.
2. **"Iceberg가 어디에 있나"** → 어디에도 떠 있지 않다. 프로세스가 없다. Iceberg는
   **warehouse 디렉터리 안의 파일들**과 **각 엔진이 링크해서 쓰는 라이브러리**로만 존재한다.

## 1. Iceberg: 떠 있는 게 아니라 "디스크에 놓여 있는 규약"

Iceberg를 설치해서 실행하는 게 아니다. `pip install pyiceberg`, DuckDB의 `iceberg` extension,
SeaTunnel의 iceberg 커넥터 jar — 전부 **같은 스펙을 구현한 서로 다른 언어의 라이브러리**다.
그 라이브러리들이 읽고 쓰는 실체는 warehouse 디렉터리다.

```
warehouse/                                  ← 그냥 디렉터리 (file:///, s3://, hdfs:// 아무거나)
└── retail.db/                               ← namespace(= database)
    └── orders/                              ← table
        ├── data/
        │   ├── 00000-0-xxxx.parquet          ← 실제 데이터. 평범한 parquet 파일.
        │   └── 00001-0-yyyy.parquet
        └── metadata/
            ├── v1.metadata.json              ← ① 테이블 메타데이터: 스키마, 파티션 스펙,
            ├── v2.metadata.json                  스냅샷 목록, current-snapshot-id
            ├── snap-7412...-1-abc.avro        ← ② manifest list: 이 스냅샷에 속한 manifest 목록
            ├── abc-m0.avro                    ← ③ manifest: 데이터 파일 경로 + 행 수 + 컬럼별
            │                                      min/max 통계 (프루닝의 핵심)
            └── version-hint.text              ← hadoop catalog일 때만: 현재 버전 번호("2")
```

읽기 경로는 항상 이 순서다:

```
카탈로그 ──("orders" 테이블의 현재 metadata는?)──▶ v2.metadata.json
                                                      │ current-snapshot-id
                                                      ▼
                                                 snap-...avro (manifest list)
                                                      ▼
                                                 abc-m0.avro (manifest)
                                                      │ min/max로 WHERE 조건에 안 걸리는 파일 제거
                                                      ▼
                                                 실제로 읽을 parquet 파일 목록
```

여기서 중요한 포인트: **`metadata/` 안의 파일은 전부 불변(immutable)이다.** 데이터를 추가하면
새 parquet + 새 manifest + 새 `v3.metadata.json`을 만든다. 그래서 "어느 metadata.json이 지금 유효한가"를
가리키는 **단 하나의 포인터를 누가 원자적으로 바꿔주느냐**가 유일한 미해결 문제로 남는다.
그 문제를 푸는 게 카탈로그고, Hive가 바로 그 자리에 들어간다.

| 비교 | 그냥 parquet 디렉터리 | Iceberg 테이블 |
|---|---|---|
| 스키마 | 각 파일에 따로, 바뀌면 깨짐 | 테이블 단위로 관리, 컬럼 추가/삭제/rename 안전 |
| 읽을 파일 선택 | 디렉터리 전체 스캔(또는 hive 파티션 경로 규칙) | manifest의 통계로 파일 단위 프루닝 |
| 쓰는 중 읽기 | 반쯤 쓰인 파일이 보임 | 스냅샷 커밋 전까지 안 보임 (ACID) |
| 과거 조회 | 불가 | 스냅샷 ID/시각으로 time travel |
| 파일 추가 | 디렉터리에 복사 | 메타데이터 커밋 필요 (단, `add_files`로 복사 없이 등록 가능) |

## 2. Hive: SQL 엔진이 아니라 "메타스토어"만 쓴다

Hive라고 하면 보통 HiveQL/MapReduce를 떠올리는데, 이 실습에서 쓰는 건 Hive의 일부분인
**Hive Metastore(HMS)** 하나뿐이다. HiveServer2(SQL 엔진), YARN, HDFS 전부 필요 없다.

HMS의 실체:

```
  [SeaTunnel]   [DuckDB/PyIceberg]   [Spark]
       │              │                 │
       └──────────────┴─────────────────┘
                      │  Thrift RPC (:9083)  또는  REST (:9001, Hive 4+)
                      ▼
            ┌──────────────────────┐
            │  Hive Metastore      │
            │  (Java 프로세스)      │
            └──────────┬───────────┘
                       │ JDBC
                       ▼
            ┌──────────────────────┐
            │ 백엔드 RDB            │  ← Derby(임베디드, 로컬 실습용) /
            │ (TBLS, DBS, ...)     │     Postgres·MySQL(실전)
            └──────────────────────┘
```

Iceberg가 HMS에 저장하는 것은 사실상 **테이블당 문자열 하나**다:
`metadata_location = file:///warehouse/retail.db/orders/metadata/v2.metadata.json`.

커밋할 때 HiveCatalog는 "현재 값이 v2면 v3로 바꿔라"는 **compare-and-swap**을 HMS에게 요청한다.
RDB 트랜잭션 + 테이블 락으로 보장되므로, 두 writer가 동시에 커밋하면 한쪽만 성공하고
다른 쪽은 재시도한다. 이게 Iceberg의 ACID가 실제로 성립하는 지점이고, Hive가 존재하는 **유일한** 이유다.

### Hive 없이도 되는데 왜 쓰나

Hive 없이 쓰는 방식이 `hadoop` catalog다. 디렉터리 구조를 카탈로그로 간주하고,
`version-hint.text` 파일로 현재 버전을 가리킨다. 로컬 단독 실습이면 충분히 동작한다. 하지만:

- **원자성**: 커밋이 "파일 rename/overwrite"에 의존한다. 로컬 FS는 rename이 원자적이라 괜찮지만,
  S3 같은 객체 스토리지는 보장이 없어 동시 writer가 있으면 스냅샷이 유실될 수 있다.
  그래서 Iceberg 공식 문서도 hadoop catalog를 production 비권장으로 분류한다.
- **디스커버리**: 여러 엔진이 `retail.orders`라는 **이름**으로 같은 테이블을 찾으려면 공용 카탈로그가 필요하다.
  hadoop catalog는 "warehouse 경로를 모두가 공유해야" 성립한다.
- **다른 테이블 포맷과의 공존**: HMS는 Hive 외부 테이블, Delta, Iceberg를 한 네임스페이스에서 관리할 수 있다.

즉 Hive의 역할은 "메타데이터 저장"이라기보다 **"어느 metadata.json이 현재인지에 대한 단일 진실 공급원 + 원자적 교체"**다.
실제 스키마/통계는 여전히 디스크의 Iceberg 메타데이터 파일에 있다.

### Hive 4의 Iceberg REST Catalog (DuckDB 연결의 핵심)

Hive 4.x의 HMS는 Thrift와 **별도로 Iceberg REST Catalog API를 노출**할 수 있다.
`metastore.catalog.servlet.port`를 설정하면(공식 도커 이미지는 9001) 클라이언트가
`http://localhost:9001/iceberg/v1/`로 표준 REST 카탈로그 프로토콜을 쓸 수 있다.
인증은 OAuth2 / JWT(기본) / Simple(`x-actor-username` 헤더, 테스트용) / None(테스트용) 중 선택한다.

이게 중요한 이유는 다음 절에 나온다 — **DuckDB는 Thrift HMS를 못 읽지만 REST 카탈로그는 읽는다.**

## 3. DuckDB: Iceberg를 읽는 네 가지 경로

DuckDB는 서버가 없는 임베디드 OLAP 엔진이다. `import duckdb` 하는 순간 그 Python 프로세스 안에
엔진이 생기고, 프로세스가 끝나면 사라진다. 로컬 레이크하우스에서는 "조회/분석 담당"이다.

Iceberg에 접근하는 경로가 네 가지인데, **할 수 있는 일이 서로 다르다.** 이걸 구분하는 게 구성 설계의 핵심이다.

### (1) 카탈로그 없이 경로로 직접 — `iceberg_scan()`

```sql
INSTALL iceberg; LOAD iceberg;
SET unsafe_enable_version_guessing = true;   -- version-hint.text가 없을 때 필요
SELECT count(*) FROM iceberg_scan('/warehouse/retail.db/orders', allow_moved_paths = true);
-- metadata.json을 직접 지정도 가능
SELECT * FROM iceberg_scan('/warehouse/retail.db/orders/metadata/v2.metadata.json');
```

- **읽기 전용.** 쓰기 불가.
- version hint나 명시적 버전이 없으면 읽지 못한다. `unsafe_enable_version_guessing`을 켜면
  "파일명이 사전순으로 가장 큰 것"을 최신으로 간주하는데, 공식 문서가 **ACID를 깰 수 있다고 경고**한다.
- gzip 압축 메타데이터만 지원.
- 로컬 실습 첫 단계로는 가장 빠르다. Hive가 전혀 필요 없다.

### (2) REST 카탈로그 ATTACH — 쓰기까지 가능한 유일한 정식 경로

```sql
ATTACH 'my_warehouse' AS lake (TYPE iceberg, ENDPOINT 'http://localhost:9001/iceberg');
SELECT * FROM lake.retail.orders;
INSERT INTO lake.retail.orders VALUES (...);   -- 카탈로그 ATTACH 시에만 가능
```

- DuckDB 공식 문서가 지원을 명시한 카탈로그: **Iceberg REST(일반), AWS Glue, S3 Tables,
  Cloudflare R2 Data Catalog, Apache Polaris, Lakekeeper, SeaweedFS, Google BigLake.**
- `CREATE SCHEMA`/`CREATE TABLE`/`INSERT`/`UPDATE`/`DELETE`/`MERGE INTO`가 열린다.
  **"쓰기에는 카탈로그 ATTACH가 필수"**라는 게 문서의 표현이다.
- **목록에 Thrift Hive Metastore는 없다.** 그래서 Hive를 쓰려면 Hive 4의 REST 서블릿(9001)을
  경유해야 한다. 일부 카탈로그는 REST 스펙을 부분만 구현해서 호환 옵션이 필요할 수 있다고 문서가 언급하므로,
  Hive REST ↔ DuckDB 조합은 **실제로 붙여 봐야 확인되는 부분**이다.

### (3) `hive_metastore` 커뮤니티 익스텐션 — Thrift 직결, Iceberg는 읽기만

```sql
INSTALL hive_metastore FROM community; LOAD hive_metastore;
ATTACH 'thrift://localhost:9083' AS hms (TYPE hive_metastore);
```

- HMS의 database/table을 DuckDB 카탈로그로 그대로 노출한다.
- 포맷별 지원: Parquet/CSV는 읽기·쓰기, **Iceberg와 Delta는 읽기 전용**, Avro 읽기, ORC 부분 지원.
- HMS 테이블에 대한 `UPDATE`/`DELETE`/`COPY TO`는 미지원. `INSERT`는 비파티션 CSV/Parquet만.
- Spark가 만든 Iceberg 테이블은 `unsafe_enable_version_guessing = true`가 필요할 수 있다.
- **커뮤니티 익스텐션**(DuckDB 코어 아님)이라는 점은 감안해야 한다.

### (4) PyIceberg 브릿지 — 가장 확실한 경로

```python
from pyiceberg.catalog import load_catalog
import duckdb

catalog = load_catalog("hive", **{"type": "hive", "uri": "thrift://localhost:9083"})
tbl = catalog.load_table("retail.orders")

con = tbl.scan(row_filter="status = 'DONE'").to_duckdb(table_name="orders")  # Arrow 경유
con.sql("select factory_id, sum(quantity) from orders group by 1").show()
```

- PyIceberg는 **REST / Glue / Hive / SQL(Postgres·SQLite) 카탈로그를 공식 지원**한다.
  Hive 카탈로그를 "제대로" 쓸 수 있는 Python 경로는 사실상 이것이다.
- 쓰기도 PyIceberg가 담당한다(append/overwrite, 스키마 진화, `add_files`).
- DuckDB는 Arrow로 넘겨받아 계산만 한다. "Python 애플리케이션일 때만 DB가 붙는" 사용 형태와 가장 잘 맞는다.
- 트레이드오프: DuckDB가 Iceberg 메타데이터를 직접 보지 않으므로, DuckDB 쪽의 프루닝/푸시다운 최적화를
  온전히 못 쓴다(필터는 PyIceberg scan 쪽에 줘야 효과가 있다).

### 정리: 경로별 가능/불가능

| 경로 | Hive 필요 | 읽기 | 쓰기 | 비고 |
|---|---|---|---|---|
| `iceberg_scan('path')` | ✗ | ○ | ✗ | 가장 간단. version guessing 주의 |
| `ATTACH (TYPE iceberg, ENDPOINT)` | REST 엔드포인트 필요 | ○ | ○ | Thrift HMS 직접 불가 → Hive 4 REST 경유 |
| `ATTACH (TYPE hive_metastore)` | ○ (Thrift) | ○ | ✗(Iceberg) | 커뮤니티 익스텐션 |
| PyIceberg → `to_duckdb()` | ○ (선택) | ○ | ○(PyIceberg가) | Hive 카탈로그에 가장 안전 |

## 4. 전체 그림에서 SeaTunnel의 자리

지금까지 해온 SeaTunnel ELT는 **"데이터를 레이크에 밀어넣는 쪽(write path)"**이고,
이번에 추가되는 Iceberg/Hive/DuckDB는 **"테이블로 관리하고 조회하는 쪽(table + read path)"**이다.

```
 [Postgres/MySQL]                                            [Python app]
        │                                                          │
        │ SeaTunnel (Zeta)                                         │ DuckDB (in-process)
        ▼                                                          ▲
 ┌──────────────────────┐                                          │
 │ A) LocalFile sink     │──▶ /output/*.parquet ──┐                │
 │    (지금 하고 있는 것) │                         │ PyIceberg      │
 └──────────────────────┘                         │ add_files()    │
                                                   ▼                │
 ┌──────────────────────┐              ┌───────────────────────────┴──┐
 │ B) Iceberg sink       │─────────────▶│  warehouse/ (parquet + metadata) │
 │    (메타까지 직접 커밋) │              └──────────────┬───────────────┘
 └───────────┬──────────┘                              │
             │                               "현재 metadata는?" │
             └──────────────▶ ┌──────────────────────┐ ◀────────┘
                              │ Hive Metastore :9083 │
                              │  (+ REST :9001)      │
                              └──────────────────────┘
```

SeaTunnel 2.3.13 Iceberg sink는 카탈로그 타입으로 **hadoop / hive / rest / glue**를 지원한다
(로컬이면 `type = "hadoop", warehouse = "file:///..."`가 가장 간단). Flink 엔진에서 hive 카탈로그를 쓸 때는
`hive-exec-*.jar`, `libfb303-*.jar`를 `$FLINK_HOME/lib`에 넣어야 한다고 문서가 명시한다.
Zeta 엔진에서는 커넥터 플러그인 jar 배치 방식이 달라서 **실제로 확인이 필요한 부분**이다.

## 5. 참고: DuckLake라는 대조군

이 스택이 왜 복잡한지 이해하는 데는 비교 대상이 하나 있으면 좋다. DuckDB Labs의 **DuckLake**는
"메타데이터 파일 + 별도 카탈로그 서비스"를 전부 걷어내고 **모든 카탈로그/테이블 메타데이터를 그냥 SQL DB
(Postgres, SQLite, DuckDB)에 넣는** 방식이다. manifest list도, HMS도, REST 서비스도 없다.
2026년 4월 v1.0으로 production-ready가 선언됐다.

- Iceberg + Hive가 푸는 문제(원자적 커밋, 동시성)를 **RDB 트랜잭션으로 공짜로 얻는다.**
- 작은 쓰기는 parquet 파일을 만들지 않고 카탈로그 DB에 인라인한다(소파일 문제 완화).
- 다만 생태계 호환성은 Iceberg가 압도적이다. Spark/Trino/Flink/Snowflake/BigQuery가 다 읽는 쪽은 Iceberg다.

**이번 실습 목적이 "데이터 레이크의 구성 요소를 이해하는 것"이라면 Iceberg + Hive가 맞다.**
각 레이어가 왜 존재하는지 직접 보게 되기 때문이다. DuckLake는 "그래서 왜 이렇게 복잡한가"에 대한
답을 비교로 보여주는 용도로 쓰면 좋다.

## 출처

- [DuckDB — Iceberg Extension Overview](https://duckdb.org/docs/current/core_extensions/iceberg/overview)
- [DuckDB — Iceberg Catalogs](https://duckdb.org/docs/current/core_extensions/iceberg/catalogs)
- [DuckDB — Iceberg REST Catalogs](https://duckdb.org/docs/lts/core_extensions/iceberg/iceberg_rest_catalogs)
- [DuckDB Community Extension — hive_metastore](https://duckdb.org/community_extensions/extensions/hive_metastore) / [소스](https://github.com/ilum-cloud/duckdb-hive-metastore)
- [Apache Hive — Iceberg REST Catalog API backed by Hive Metastore](https://hive.apache.org/docs/latest/admin/iceberg-rest-catalog/)
- [Apache SeaTunnel 2.3.13 — Iceberg Sink](https://seatunnel.apache.org/docs/2.3.13/connectors/sink/Iceberg/)
- [PyIceberg API 문서](https://py.iceberg.apache.org/api/)
- [A Tour of Iceberg Catalogs with PyIceberg](https://kevinjqliu.substack.com/p/a-tour-of-iceberg-catalogs-with-pyiceberg) / [Iceberg REST Catalog with Hive Metastore](https://kevinjqliu.substack.com/p/iceberg-rest-catalog-with-hive-metastore)
- [hive-metastore-standalone (Docker)](https://github.com/criccomini/hive-metastore-standalone)
- [Registering Parquet Files Into Iceberg Tables Without Rewrites Using PyIceberg](https://binayakd.tech/posts/2024-12-25-register-parquet-files-to-iceberg-without-rewrites/)
- [DuckLake v1.0 소개](https://duckdblab.org/en/post/ducklake-v1-intro/) / [DuckLake Architecture Deep Dive](https://motherduck.com/blog/ducklake-architecture-deep-dive/)
