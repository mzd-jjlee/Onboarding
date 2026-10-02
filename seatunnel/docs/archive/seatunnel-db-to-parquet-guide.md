# SeaTunnel 실습: DB → 로컬 Parquet 파일 (Batch + CDC)

팀장님 피드백으로 확정된 실제 실습 범위를 다루는 문서. 이전에 만든 [seatunnel-batch-cdc-guide.md](seatunnel-batch-cdc-guide.md)는
"DB → DB"(Postgres → Postgres) 예제였는데, 실제 과제는 **목적지가 로컬 파일(Parquet)**이라는 점이 다르다.

> **요구사항 원문 정리**
> - 소스: MySQL 또는 Postgres
> - 타겟: 로컬 특정 위치의 **Parquet 파일**
> - Batch: DB에 있는 데이터를 그 시점 그대로 Parquet로 떨어뜨림
> - CDC: DB의 변경분(트랜잭션)을 Parquet로 떨어뜨림
> - 기한: 9/30 or 10/2, 난이도 있어 밀릴 수 있음을 팀장님도 인지

## ⚠️ 실제로 돌려서 확인한 결과 (중요)

Docker로 직접 실행해서 확인했다. 결론부터: **에러 없이 잘 된다. 그런데 "뭘 주는지"가 아니라 "뭐가 빠졌는지"가 진짜 함정이다.**

| 구성 | 검증 상태 |
|---|---|
| Postgres batch → Postgres (JDBC sink) | ✅ 직접 실행 확인 ([이전 가이드](seatunnel-batch-cdc-guide.md) 2장) |
| Postgres CDC → Console | ✅ 직접 실행 확인 (같은 문서 3장) |
| Postgres batch → **로컬 Parquet** | ✅ 직접 실행 확인 (아래 1장) — 문제 없음 |
| Postgres **CDC** → **로컬 Parquet** | ✅ **에러 없이 실행됨** — 그런데 결과물에 중요한 정보 손실이 있음 (아래 2장 필독) |
| `format = COMPATIBLE_DEBEZIUM_JSON` (op 정보 보존 시도) | ❌ 2.3.13에서 `NullPointerException`으로 실패 (아래 2-3) |
| MySQL CDC 사전 설정 | 공식 문서 기준 정리만 함, 미실행 |

### 진짜 문제: Parquet 파일에 "무슨 일이 있었는지"가 안 남는다

CDC 잡을 STREAMING으로 띄워두고 소스 테이블에 `INSERT(id=3)`, `UPDATE(id=1: East→South)`, `DELETE(id=2)`를
동시에 발생시킨 뒤 생성된 Parquet 파일을 직접 열어보면:

```
   id   name region
0   3  Carol  North      ← INSERT
1   1  Alice   East      ← UPDATE의 "이전" 값
2   1  Alice  South      ← UPDATE의 "이후" 값
3   2    Bob   West       ← DELETE된 행의 마지막 값
```

"바뀐 값 자체를 그대로 append"하는 건 정확히 이렇게 동작한다 — 그 부분은 걱정할 필요 없었다.
**문제는 이 4개 행 중 어느 게 INSERT였고, 어느 게 UPDATE의 전/후였고, 어느 게 DELETE였는지 파일 안에
아무 표시가 없다는 것.** `id`, `name`, `region` 세 컬럼뿐이고 `op`/`kind`/`__op` 같은 구분 컬럼이 없다.
극단적으로 말하면 `(2, Bob, West)`가 "Bob이 삭제됐다"는 기록인지 "Bob이 새로 insert됐다"는 기록인지
**이 파일만 봐서는 구분이 안 된다.**

흥미로운 건 이 정보가 SeaTunnel 내부에서 아예 없는 게 아니라는 것 — CDC → **Console** sink로 받았을 때는
분명히 `SeaTunnelRow#kind=INSERT`/`UPDATE_BEFORE`/`UPDATE_AFTER`/`DELETE`가 로그에 찍혔다
([이전 가이드](seatunnel-batch-cdc-guide.md) 3-5). 즉 **`kind` 메타데이터는 내부적으로 존재하는데, `LocalFile`
(Parquet) sink가 이걸 컬럼으로 안 남기고 값만 뽑아서 쓰는 것**이 원인이다. JDBC sink는 이 `kind`를 보고 실제
INSERT/UPDATE/DELETE SQL을 알아서 실행해주니 문제가 없었는데(`primary_keys` 지정 시), 파일 sink는 그런 처리
없이 "값만 그대로 한 줄 적자"로 동작하는 걸로 보인다.

### 그럼 op 정보를 살릴 방법은?

공식 문서에 PostgreSQL CDC 소스의 `format` 옵션이 `DEFAULT`/`COMPATIBLE_DEBEZIUM_JSON` 두 가지가 있길래
후자를 시도해봤다 — Debezium처럼 `{op, before, after, ts_ms}` 구조로 감싸서 op 정보를 필드로 노출해줄 걸
기대했는데, **2.3.13에서 `Postgres-CDC` + `format = COMPATIBLE_DEBEZIUM_JSON` 조합은 `NullPointerException`으로
아예 잡이 안 뜬다.** 공식 문서에도 이 옵션에 대한 설명이 사실상 한 줄("valid enumerations are DEFAULT,
COMPATIBLE_DEBEZIUM_JSON")뿐이라 현재 버전에서는 신뢰하기 어려운 기능으로 보인다.

**결론적으로 이번 실습 범위(LocalFile/Parquet + 기본 옵션)에서는 "변경 종류(op)"를 살릴 방법을 못 찾았다.**
팀장님께 공유할 때 이 지점을 정직하게 짚는 게 좋을 것 같다 — "값은 잘 떨어지는데, 이게 insert인지 update인지
delete인지는 이 파일만으로는 알 수 없다"는 게 실제 확인된 한계다. 만약 이 구분이 실제로 필요한 요구사항이라면
(예: "삭제된 데이터는 별도로 추적해야 한다"), 다음 대안을 팀장님과 논의해볼 만하다 (전부 미검증 — 방향 제안 수준):
- **JDBC sink로 받기**: `primary_keys` 지정하면 SeaTunnel이 kind를 보고 실제 UPDATE/DELETE SQL을 실행해줌
  (이미 검증됨) — 다만 이건 "DB"지 "파일"이 아니라 요구사항과 안 맞을 수 있음
- **Iceberg/Hudi/Paimon 같은 sink**: 이미지에 `connector-iceberg`, `connector-hudi`, `connector-paimon`이
  이미 포함되어 있는 걸 확인함 — 이 테이블 포맷들은 애초에 upsert/delete를 지원하도록 설계되어 있어서, "파일
  기반이면서 변경 이력도 살리고 싶다"는 요구에는 Parquet 원시 파일보다 이쪽이 정답에 가까울 수 있음 (단, 이번엔
  시간 관계상 테스트 못 함)
- Transform 단계에서 `kind`를 컬럼으로 끌어낼 수 있는지는 확인 안 함 (SQL Transform이 row kind 메타데이터에
  접근 가능한지 불명)

---

## 1. Batch: DB → 로컬 Parquet (직접 실행해서 확인함)

### 1-1. config (이 그대로 실행해서 검증함)

Postgres 기준 (`LocalFile` sink는 소스가 MySQL이든 Postgres든 동일하게 동작 — sink 쪽은 source 타입과 무관):

```hocon
SeaTunnel Config

env {
    # 실행 환경 설정
}

source {
    # 어디서 읽을 것인가?
    # MySQL, PostgreSQL, Kafka ...
}

transform {     ← 생략 가능
    # 어떻게 변환할 것인가?
    # 컬럼 변경, 필터링 등
}

sink {
    # 어디에 저장할 것인가?
    # Parquet, MySQL, Kafka ...
}

① JDBC로 DB에 접속 → ② 데이터 Extract → ③ 별도 Transform 없이 → ④ 로컬 Parquet으로 Load

source -> sink
1. JDBC로 DB에 접속 -> 2. 데이터 Extract -> 3. Transform -> 4. 로컬 Parquet으로 Load
```

```hocon
env {
  parallelism = 1
  job.mode = "BATCH"
}

source {
  Jdbc {
    url = "jdbc:postgresql://st_pq_pg:5432/srcdb"
    driver = "org.postgresql.Driver"
    user = "demo"
    password = "demo"
    query = "select id, name, region from inventory.customers order by id"
    plugin_output = "customers"
  }
}

sink {
  LocalFile {
    plugin_input = "customers"
    path = "/data/out_batch"
    file_format_type = "parquet"
  }
}
```

### 1-2. 알아둘 옵션 (공식 문서 기준)

| 옵션 | 의미 |
|---|---|
| `path` | 결과가 쌓일 디렉터리. `${table_name}` 같은 변수 치환도 가능 |
| `tmp_path` | 결과 파일을 **임시로 먼저 쓰고 `mv`로 최종 위치에 옮기는** 중간 경로 (기본 `/tmp/seatunnel`) — 쓰다 만 파일이 최종 경로에 안 보이게 하는 안전장치 |
| `file_name_expression` | 생성 파일명 규칙. 기본은 `${transactionId}` — 실행마다 다른 파일이 새로 생김(덮어쓰지 않고 계속 쌓임에 주의) |
| `is_enable_transaction` | 기본 `true`. 파일명 앞에 트랜잭션 ID를 붙여서 부분 쓰기/중복을 방지 |
| `compress_codec` | `snappy`/`lz4`/`gzip`/`brotli`/`zstd`/`none` — Parquet 압축 |
| `sink_columns` | 특정 컬럼만/특정 순서로 쓰고 싶을 때 지정 (생략하면 원본 스키마 그대로) |

### 1-3. 실행 (Docker, opengauss 우회 포함 — 실제 실행 로그로 확인됨)

호스트에 결과가 쌓일 디렉터리를 미리 만들고 **읽기전용이 아니라 쓰기 가능하게** 마운트해야 한다 (이전 CSV
실습은 소스라 `:ro`였지만, 이번엔 sink라 마운트를 쓰기 모드로 열어야 함):

```bash
mkdir -p ./practice_data/out_batch

docker run --rm --network st_practice_net \
  -v "$(pwd)/practice_data/out_batch:/data/out_batch" \
  -v "$(pwd)/batch_to_parquet.conf:/jobs/batch_to_parquet.conf:ro" \
  --entrypoint sh \
  apache/seatunnel:2.3.13 \
  -c '
    mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak &&
    ./bin/seatunnel.sh --config /jobs/batch_to_parquet.conf -m local
  '
```

**실제로 실행하면 이렇게 끝난다** (직접 확인한 로그):
```
Total Read Count          :                   2
Total Write Count         :                   2
Total Failed Count        :                   0
```

### 1-4. 검증 방법

컨테이너 밖, 호스트에서 바로 파일이 생겼는지 확인:
```bash
find ./practice_data/out_batch -name "*.parquet"
```
Parquet는 텍스트가 아니라서 `cat`으로는 못 본다. 로컬에 `pandas`/`pyarrow`가 없으면, 굳이 설치하지 말고
파이썬 이미지를 하나 그때만 띄워서 읽는 게 간편하다 (실제로 이 방법으로 확인함):
```bash
docker run --rm -v "$(pwd)/practice_data/out_batch:/data:ro" python:3.11-slim sh -c \
  "pip install -q pyarrow pandas && python3 -c \"
import pandas as pd
print(pd.read_parquet('/data'))
\""
```

---

## 2. CDC: DB 변경분 → 로컬 Parquet (직접 실행해서 확인함)

### 2-1. config (이 그대로 돌려서 검증함)

```hocon
env {
  parallelism = 1
  job.mode = "STREAMING"
  checkpoint.interval = 5000
}

source {
  Postgres-CDC {
    plugin_output = "customers_cdc"
    username = "demo"
    password = "demo"
    database-names = ["srcdb"]
    schema-names = ["inventory"]
    table-names = ["srcdb.inventory.customers"]
    url = "jdbc:postgresql://st_pq_pg:5432/srcdb?loggerLevel=OFF"
    decoding.plugin.name = "pgoutput"
  }
}

sink {
  LocalFile {
    plugin_input = "customers_cdc"
    path = "/data/out_cdc"
    file_format_type = "parquet"
  }
}
```

소스 Postgres 사전 준비(`wal_level=logical`, `REPLICA IDENTITY FULL`)는 [이전 가이드 3-2](seatunnel-batch-cdc-guide.md)와 동일하다.

### 2-2. 실행하면 실제로 일어나는 일 (검증 완료)

1. 잡을 시작하면 **에러 없이 뜬다.** LocalFile sink가 STREAMING 소스를 받는 것 자체는 문제없다 (공식 문서가
   침묵한 게 "미지원"이라서가 아니었다).
2. 시작 직후 초기 스냅샷(테이블에 이미 있던 행들)이 Parquet 파일 하나로 즉시 떨어진다.
3. 잡을 띄워둔 채로 소스에 `INSERT`/`UPDATE`/`DELETE`를 실행하면, **체크포인트 간격(`checkpoint.interval`)마다
   새 Parquet 파일이 하나씩 추가로 생긴다** — 파일명은 `T_<jobId>_<...>_<체크포인트번호>_0.parquet` 형태로 매번 다르다.
4. 그 새 파일을 열어보면 **변경된 행의 값은 정확히 담겨 있다** — 다만 위 "진짜 문제" 절에서 짚은 대로
   INSERT/UPDATE_BEFORE/UPDATE_AFTER/DELETE를 구분하는 컬럼은 없다. "값 이관"은 되지만 "변경 이력 추적"은
   추가 작업 없이는 안 된다는 게 실측 결론.

### 2-3. 참고: op 정보를 살려보려던 시도 (실패)

`format = "COMPATIBLE_DEBEZIUM_JSON"`을 `Postgres-CDC` source에 추가해서 Debezium 스타일(`op`/`before`/`after`)
envelope로 받아보려 했으나, 2.3.13에서는 소스 생성 단계에서 `NullPointerException`이 나면서 잡 자체가 안 뜬다.
공식 문서도 이 옵션에 대한 설명이 한 줄뿐이라 현재 버전에서는 신뢰하기 어려운 기능으로 보인다.

---

## 3. 소스를 MySQL로 할 경우의 사전 준비 (Postgres 대안, 미실행)

MySQL을 선택하면 CDC 사전 준비가 Postgres와 다르다. `my.cnf`(또는 컨테이너면 `--` 커맨드 인자)에 설정 필요:

```ini
server-id         = 223344
log_bin           = mysql-bin
binlog_format     = row
binlog_row_image  = FULL
gtid_mode         = on
enforce_gtid_consistency = on
```

권한이 있는 계정 생성:
```sql
CREATE USER 'st_user'@'%' IDENTIFIED BY 'password';
GRANT SELECT, RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'st_user';
FLUSH PRIVILEGES;
```

config는 `source { Postgres-CDC {...} }` 대신 `source { MySQL-CDC {...} }`, url이 `jdbc:mysql://...`,
driver가 `com.mysql.cj.jdbc.Driver`로 바뀌는 정도고 sink(LocalFile/Parquet) 쪽은 동일하다.
(`mysql-connector-java-8.0.27.jar`는 이미지 `lib/`에 기본 포함되어 있어 별도 드라이버 설치는 불필요 — 다만
`opengauss-jdbc` 충돌 이슈는 Postgres 전용이라 MySQL 연결에는 해당 안 될 가능성이 높음, 이것도 실제 확인 필요.
Parquet sink 쪽의 "op 정보 없음" 문제는 소스가 뭐든 동일하게 적용될 것으로 예상됨 — sink 쪽 한계이기 때문.)

## 4. 다음 액션

- [x] Batch → Parquet 실행 검증
- [x] CDC → Parquet 실행 검증 (op 정보 손실 확인)
- [x] `COMPATIBLE_DEBEZIUM_JSON` 시도 (실패 확인)
- [ ] MySQL 소스로도 같은 흐름 재현 (Postgres와 다른 점 없는지 확인)
- [ ] "op 정보가 실제로 필요한 요구사항인지" 팀장님과 확인 — 필요 없다면 지금 방식으로 충분, 필요하다면 위
      대안(JDBC sink / Iceberg·Hudi·Paimon sink) 중 하나를 다음 스텝으로 검증

## 참고한 공식 문서

- [LocalFile Sink (2.3.12)](https://seatunnel.apache.org/docs/2.3.12/connector-v2/sink/LocalFile)
- [MySQL CDC Source (2.3.12)](https://seatunnel.apache.org/docs/2.3.12/connector-v2/source/MySQL-CDC)
- [PostgreSQL CDC Source (2.3.12)](https://seatunnel.apache.org/docs/2.3.12/connector-v2/source/PostgreSQL-CDC/)
