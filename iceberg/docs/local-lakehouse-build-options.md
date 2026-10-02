# 로컬 소규모 데이터 레이크 구성 옵션

> **조사 원본 · 정정 안내 (2026-10-02):** 아래의 “Derby 동시 접속 1개” 설명은 오류다.
> Hive REST의 버전·이미지 조건, `add_files` 파일 수명, unsafe guessing 설명도 보완이 필요하다.
> [그림 중심 안내서 9절](local-lakehouse-visual-guide.md#9-기존-조사에서-확인한-내용과-정정할-내용)의 검증 결과를 우선한다.
> 원래 조사와 정정 내용을 비교할 수 있도록 본문은 보존했다.

[iceberg-hive-duckdb-roles.md](iceberg-hive-duckdb-roles.md)에서 정리한 역할 분담을 전제로,
**실제로 무엇을 띄우고 어떤 순서로 실습할지**에 대한 선택지를 비교한 문서다.
아직 구현 전이며, 여기 적힌 설정값은 공식 문서 기준 초안이다(검증 필요 항목은 §5에 모아 뒀다).

## 1. 선택지 네 가지

| | 구성 | 띄워야 하는 것 | DuckDB 조회 경로 | 학습 가치 |
|---|---|---|---|---|
| **Opt 1** | Iceberg(hadoop catalog) only | 없음 (디렉터리뿐) | `iceberg_scan('path')` 직결 | Iceberg 메타데이터 구조. Hive 역할은 안 보임 |
| **Opt 2** | HMS(Thrift) + hadoop FS warehouse | HMS 컨테이너 1개 | PyIceberg 브릿지 / `hive_metastore` 익스텐션 | 카탈로그가 왜 필요한지 체감 |
| **Opt 3** | Hive 4 HMS + Iceberg REST 서블릿 | HMS 컨테이너 1개(포트 2개) | `ATTACH (TYPE iceberg, ENDPOINT ...)` — 쓰기도 가능 | 현재 업계 표준 형태 |
| **Opt 4** | DuckLake (대조군) | 없음 (SQLite/Postgres 카탈로그) | 네이티브 | "왜 이렇게 복잡한가"의 비교 기준 |

### 권장 경로: Opt 1 → Opt 2 → (여유 있으면) Opt 3

Opt 1에서 **카탈로그 없이** 테이블이 성립하는 걸 먼저 보고,
거기서 "동시 커밋이 되나? 다른 도구가 테이블 이름으로 찾을 수 있나?"라는 결핍을 직접 만난 뒤
Opt 2에서 Hive를 넣는 순서가 가장 이해가 잘 된다. Opt 3은 DuckDB에서 **쓰기까지** 하고 싶을 때 필요하다.

## 2. 데이터가 들어가는 두 가지 방식

### 방식 A — SeaTunnel은 parquet만 쓰고, PyIceberg가 메타데이터만 등록

지금 하고 있는 `LocalFile` sink를 그대로 두고, Iceberg 테이블에 **파일을 복사 없이 등록**한다.

```python
from pyiceberg.catalog import load_catalog
import pyarrow.parquet as pq

catalog = load_catalog("local", **{
    "type": "sql",                                   # 또는 "hive"
    "uri": "sqlite:////lake/catalog.db",
    "warehouse": "file:///lake/warehouse",
})
catalog.create_namespace_if_not_exists("retail")

schema = pq.read_schema("/output/production_orders/part-0.parquet")
tbl = catalog.create_table("retail.orders", schema=schema)   # Arrow 스키마로 생성
tbl.add_files(["file:///output/production_orders/part-0.parquet"])  # 복사 없음, 메타만 커밋
```

`add_files()`의 제약 (실습 시 바로 걸리는 부분):

- **parquet 스키마가 테이블 스키마와 정확히 일치**해야 한다. 그래서 위처럼 parquet에서 스키마를 읽어
  테이블을 만드는 게 안전하다.
- PyIceberg는 **마이크로초 정밀도까지만** 지원한다. 나노초 타임스탬프가 있으면 미리 변환해야 한다.
- **한 파일이 여러 파티션에 걸쳐 있으면 안 된다.** 파티션 테이블로 만들려면 SeaTunnel 쪽에서
  파티션 경계에 맞게 파일을 나눠 써야 한다.
- 등록된 원본 파일은 **Iceberg가 관리하지 않는 위치**에 있다. 이후 `overwrite()` 같은 연산은
  새 파일을 warehouse 안에 만들고, 원본은 활성 스냅샷에서 떨어져 나간다(orphan). 스냅샷 만료 시
  정리 대상이 될 수 있다. → "외부 테이블"처럼 영구히 쓰는 용도로 착각하면 안 된다.

**장점**: 각 레이어가 분리돼서 눈에 보인다. parquet은 그대로 두고 메타데이터만 얹는 걸 실감할 수 있다.
SeaTunnel 쪽 설정을 전혀 안 바꿔도 된다.

### 방식 B — SeaTunnel Iceberg sink로 직접 커밋

SeaTunnel 2.3.13의 Iceberg sink는 hadoop/hive/rest/glue 카탈로그를 지원한다.

```hocon
sink {
  Iceberg {
    plugin_input = "production_orders_upper"
    catalog_name = "local_lake"
    iceberg.catalog.config = {
      type = "hadoop"
      warehouse = "file:///lake/warehouse"
    }
    namespace = "retail"
    table = "orders"
    iceberg.table.write-props = {
      write.format.default = "parquet"
      write.target-file-size-bytes = 536870912
    }
    iceberg.table.partition-keys = "order_date"
    iceberg.table.primary-keys = "order_id"
    iceberg.table.upsert-mode-enabled = false
    iceberg.table.schema-evolution-enabled = true
    case_sensitive = true
  }
}
```

Hive 카탈로그로 바꿀 때는 `iceberg.catalog.config`만 교체한다:

```hocon
    iceberg.catalog.config = {
      type = "hive"
      uri = "thrift://localhost:9083"
      warehouse = "file:///lake/warehouse"
    }
```

주의: 공식 예시의 hive 카탈로그는 warehouse가 `hdfs://`다. **로컬 `file://` warehouse + Thrift HMS
조합은 문서에 예시가 없어서 직접 확인이 필요하다** — HMS 컨테이너와 SeaTunnel 컨테이너가 같은 경로를
같은 내용으로 봐야 하므로, 두 컨테이너에 **동일한 호스트 디렉터리를 같은 경로로 마운트**하는 게 관건이다.
(`/lake/warehouse`를 양쪽에 똑같이 마운트)

**장점**: 실제 파이프라인의 모습. upsert, 스키마 진화, 파티셔닝을 SeaTunnel 설정만으로 쓸 수 있다.
**단점**: 커넥터 jar/hadoop 의존성 문제로 처음에 막힐 가능성이 높고, 막혔을 때 어느 레이어 문제인지 가려내기 어렵다.

→ 그래서 **A로 개념을 확인한 뒤 B로 넘어가는 순서**를 권한다.

## 3. Hive Metastore를 로컬에 띄우는 방법

### 가장 가벼운 선택: standalone metastore (embedded Derby + 로컬 FS)

```bash
docker run -p 9083:9083 \
  -v /lake/warehouse:/lake/warehouse \
  ghcr.io/criccomini/hive-metastore-standalone:latest
```

이 이미지는 Hive Metastore를 standalone 모드로, 백엔드 DB는 **임베디드 Derby**,
파일시스템은 **로컬 FS**로 설정해 둔 것이다. 다른 컨테이너(HDFS 등) 없이 단독 실행된다.

**가장 중요한 제약: Derby는 동시 접속이 1개뿐이다.** 즉 SeaTunnel이 붙어 있는 동안
PyIceberg가 동시에 붙으면 실패한다. 실습 중 "순차적으로 쓰고 → 조회"하는 흐름이면 괜찮지만,
동시 접속을 보려면 백엔드를 **Postgres로 바꿔야** 한다 (이 저장소에는 이미 Postgres compose가 있어서 재활용 가능).

> 참고: 동시 커밋 충돌(compare-and-swap 재시도)을 눈으로 확인하는 게 이 실습의 하이라이트가 될 수 있는데,
> **그걸 보려면 Derby가 아니라 Postgres 백엔드가 필요하다.**

### Opt 3: Hive 4 + REST 서블릿

Hive 4 공식 이미지(`apache/hive:4.x`)에서 `metastore.catalog.servlet.port`를 켜면
REST 카탈로그가 뜬다. 공식 이미지 기본값은 **9001**이고 클라이언트 URL은 `http://localhost:9001/iceberg/v1/`.
테스트 목적이면 인증을 `none` 또는 `simple`(`x-actor-username` 헤더)로 둘 수 있다
— 둘 다 공식 문서가 **production 부적합**으로 명시한 모드다.

이러면 DuckDB에서:

```sql
ATTACH 'warehouse' AS lake (TYPE iceberg, ENDPOINT 'http://localhost:9001/iceberg');
SELECT * FROM lake.retail.orders;
```

DuckDB 문서는 "일부 카탈로그가 REST 스펙을 부분 구현해서 호환 옵션이 필요할 수 있다"고 언급한다.
Hive의 REST 구현이 DuckDB가 기대하는 범위를 커버하는지는 **직접 붙여 봐야 안다** (§5).

### 대안: HMS를 아예 건너뛰고 Lakekeeper/Polaris

DuckDB 문서가 지원을 명시한 REST 카탈로그 구현체(Lakekeeper, Apache Polaris 등)를 쓰면
"DuckDB ↔ REST 카탈로그"는 거의 확실히 동작한다. 다만 그러면 **Hive를 쓰는 실습이 아니게 된다.**
목적이 "Hive의 역할 이해"라면 Opt 2/3을, "Iceberg 레이크하우스를 빠르게 동작시키기"라면 이쪽을 고르면 된다.

## 4. 디렉터리/구성 초안

```
iceberg/
├── docs/
│   ├── iceberg-hive-duckdb-roles.md          # 역할·개념 (작성 완료)
│   └── local-lakehouse-build-options.md      # 이 문서
├── docker-compose.hms.yml                    # Hive Metastore (+ 백엔드 DB)
├── jobs/
│   ├── 01_postgres_to_parquet.conf           # 방식 A: 기존 LocalFile sink 재사용
│   └── 02_postgres_to_iceberg.conf           # 방식 B: Iceberg sink
├── src/
│   ├── register_parquet.py                   # PyIceberg add_files()
│   └── query_duckdb.py                       # DuckDB 조회 (경로 4가지 비교)
├── notebooks/
│   └── explore_metadata.ipynb                # metadata.json / manifest 직접 열어보기
├── lake/
│   └── warehouse/                            # Iceberg warehouse (gitignore)
└── scripts/{up.sh,down.sh}
```

`lake/warehouse`는 **HMS 컨테이너·SeaTunnel 컨테이너·호스트에서 모두 같은 절대 경로로 보이게**
마운트해야 한다. Iceberg 메타데이터에 데이터 파일의 **절대 경로가 박히기 때문**이다
(경로가 달라지면 `allow_moved_paths` 같은 우회 옵션이 필요해진다).

Airflow로 파이프라인을 묶을 경우, DAG는 `~/projects/.claude/rules/dag-style.md` 규칙에 따라
TaskFlow API로 작성하고 `add_files` 등록/검증 로직은 `src/` 모듈로 분리한다.

## 5. 구현 전에 검증해야 할 미확인 사항

문서 근거로는 성립하지만 **실제로 붙여 봐야 확정되는** 항목들이다. 실습 순서를 정할 때 리스크로 반영한다.

1. **DuckDB `iceberg` ATTACH ↔ Hive 4 REST 카탈로그 호환성.**
   DuckDB가 공식 지원 목록에 Hive를 올려두지 않았고, REST 스펙 부분 구현 시 호환 옵션이 필요하다고만 적혀 있다.
   → Opt 3의 성패가 여기 달려 있다. 안 되면 Opt 2(PyIceberg 브릿지)로 폴백.
2. **SeaTunnel Zeta 엔진에서 Iceberg 커넥터의 jar 의존성.**
   공식 문서의 의존성 안내는 Flink 엔진 기준(`hive-exec`, `libfb303`)이다. Zeta에서 hive 카탈로그를 쓸 때
   필요한 플러그인/jar 배치가 문서에 명확하지 않다. → hadoop 카탈로그부터 시작하는 편이 안전.
3. **SeaTunnel Iceberg sink + 로컬 `file://` warehouse + Thrift HMS** 조합의 동작.
   공식 hive 예시는 HDFS warehouse뿐이다.
4. **`add_files()`로 등록한 파일의 수명.** 이후 Iceberg 쓰기 연산이 들어오면 orphan이 되는 동작을
   실제로 확인해 두면, "외부 parquet 등록"을 어디까지 믿을 수 있는지 판단 기준이 생긴다.
5. **Derby 단일 접속 제약.** 동시 writer 실험을 하려면 백엔드를 Postgres로 교체해야 한다.
6. **`unsafe_enable_version_guessing` 없이 `iceberg_scan`이 되는지.**
   hadoop catalog는 `version-hint.text`를 쓰므로 될 가능성이 높지만, HMS 카탈로그로 만든 테이블은
   version hint 파일이 없어서 guessing이 필요할 수 있다.

## 출처

- [DuckDB — Iceberg Extension](https://duckdb.org/docs/current/core_extensions/iceberg/overview), [Catalogs](https://duckdb.org/docs/current/core_extensions/iceberg/catalogs), [REST Catalogs](https://duckdb.org/docs/lts/core_extensions/iceberg/iceberg_rest_catalogs)
- [DuckDB Community Extension — hive_metastore](https://duckdb.org/community_extensions/extensions/hive_metastore)
- [Apache Hive — Iceberg REST Catalog API](https://hive.apache.org/docs/latest/admin/iceberg-rest-catalog/)
- [Apache SeaTunnel 2.3.13 — Iceberg Sink](https://seatunnel.apache.org/docs/2.3.13/connectors/sink/Iceberg/)
- [hive-metastore-standalone (Docker, embedded Derby + local FS)](https://github.com/criccomini/hive-metastore-standalone)
- [Registering Parquet Files Into Iceberg Tables Without Rewrites Using PyIceberg](https://binayakd.tech/posts/2024-12-25-register-parquet-files-to-iceberg-without-rewrites/)
- [PyIceberg API](https://py.iceberg.apache.org/api/)
- [Iceberg REST Catalog with Hive Metastore](https://kevinjqliu.substack.com/p/iceberg-rest-catalog-with-hive-metastore)
