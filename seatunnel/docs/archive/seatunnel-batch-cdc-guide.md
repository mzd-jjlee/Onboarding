# SeaTunnel Batch / CDC 실습 가이드

이 문서는 [seatunnel-overview.md](../seatunnel-overview.md)(이론)와 [seatunnel-tutorial.md](seatunnel-tutorial.md)(입문)를
읽었다는 전제로, **Batch 잡 하나와 CDC(실시간 변경 캡처) 잡 하나를 직접 손으로 완주하는 것**을 목표로 하는 상세 가이드다.
여기 나온 모든 명령어와 출력 결과는 로컬 Docker(Rancher Desktop) 환경에서 실제로 실행해서 확인한 것이고,
중간에 만난 실제 에러와 그 원인/해결책까지 그대로 남겨뒀다.

## 0. 공식 Quick Start 문서

먼저 원본을 링크해둔다. 이 가이드가 다루지 못하는 옵션이나 버전이 바뀐 부분은 여기서 확인.

| 문서 | 용도 |
|---|---|
| [SeaTunnel 홈페이지](https://seatunnel.apache.org/) | 프로젝트 전체 소개, 최신 버전 확인 |
| [Set Up With Docker](https://seatunnel.apache.org/docs/getting-started/docker/) | 공식 Docker 실행 가이드 (이 문서의 기반) |
| [Deployment (locally)](https://seatunnel.apache.org/docs/2.3.12/start-v2/locally/deployment/) | 소스 tarball 기반 로컬 설치 (Docker 안 쓸 경우) |
| [Quick Start (SeaTunnel Engine)](https://seatunnel.apache.org/docs/2.3.12/start-v2/locally/quick-start-seatunnel-engine/) | Zeta 엔진 최초 실행 튜토리얼 |
| [JDBC Source](https://seatunnel.apache.org/docs/2.3.12/connector-v2/source/Jdbc/) / [PostgreSQL Sink](https://seatunnel.apache.org/docs/2.3.12/connector-v2/sink/PostgreSql/) | Batch 잡에 쓰는 JDBC 커넥터 전체 옵션 |
| [PostgreSQL CDC Source](https://seatunnel.apache.org/docs/2.3.12/connector-v2/source/PostgreSQL-CDC/) | CDC 잡에 쓰는 커넥터 전체 옵션 |
| [Config File 개념](https://seatunnel.apache.org/docs/2.3.12/concept/config/) | HOCON 문법 자체가 궁금할 때 |

## 1. 사전 준비

Docker만 있으면 된다. 이미지 안에 커넥터(JDBC 포함)와 주요 DB 드라이버가 이미 다 들어있다는 건
[seatunnel-tutorial.md 1장](seatunnel-tutorial.md)에서 이미 확인했다.

```bash
docker pull apache/seatunnel:2.3.13
```

### ⚠️ 실습 전에 반드시 알아야 할 이슈: OpenGauss 드라이버 충돌

Postgres에 JDBC로 연결하는 잡(Batch sink든 CDC source든 전부 해당)을 돌리면 다음 에러를 만날 수 있다:

```
org.postgresql.util.PSQLException: Protocol error.  Session setup failed.
```

**원인** ([apache/seatunnel#10242](https://github.com/apache/seatunnel/issues/10242)에 동일 사례 보고됨,
이 가이드를 쓰면서 직접 재현·검증함): 이미지의 `/opt/seatunnel/lib/`에 진짜 Postgres 드라이버
(`postgresql-42.4.3.jar`)와 화웨이의 PostgreSQL 포크 DB용 드라이버(`opengauss-jdbc-5.1.0.jar`)가 같이 들어있는데,
두 드라이버가 **동일한 클래스명 `org.postgresql.Driver`**를 쓴다. SeaTunnel이 커넥터 클래스로더를 구성할 때
이 충돌로 엉뚱한(OpenGauss용) 드라이버가 로드될 수 있고, OpenGauss는 인증 핸드셰이크가 달라서 정상적인
Postgres 서버 응답을 못 읽고 이 에러를 던진다. 이 글을 쓰는 시점 기준 아직 미해결(Open) 이슈다.

**해결책**: 컨테이너 시작 시 이 jar를 이름 바꿔서 무력화한다. 아래 모든 예제 명령어에 이미 반영해뒀다.
```bash
mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak
```
OpenGauss를 실제로 쓸 계획이 없다면 완전히 없애버려도 무방하다. 이후 버전에서 고쳐졌을 수도 있으니,
최신 이미지로 실습한다면 이 우회가 여전히 필요한지 먼저 확인해볼 것 (`ls /opt/seatunnel/lib | grep opengauss`).

---

## 2. Batch 실습: CSV → Postgres

**목표**: 이 저장소의 `data/customers_raw.csv`를 SeaTunnel Batch 잡으로 Postgres 테이블에 적재하고,
테이블이 자동 생성되는 것까지 확인한다.

### 2-1. 소스/타겟 역할을 할 Postgres 하나 띄우기

실습용으로 새 컨테이너 하나만 있으면 된다 (기존 `openmetadata/`의 `retaildb`와는 별개로 완전히 독립적인 실습 환경).

```bash
docker network create st_practice_net

docker run -d --name st_practice_pg --network st_practice_net \
  -e POSTGRES_USER=demo -e POSTGRES_PASSWORD=demo -e POSTGRES_DB=warehousedb \
  postgres:16

# 준비될 때까지 대기
until docker exec st_practice_pg pg_isready -U demo -d warehousedb; do sleep 1; done
```

### 2-2. config 작성

`batch_customers.conf`:
```hocon
env {
  parallelism = 1
  job.mode = "BATCH"
}

source {
  LocalFile {
    path = "/data/customers"       # CSV가 들어있는 디렉터리 (파일 하나가 아니라 폴더!)
    file_format_type = "csv"
    csv_use_header_line = true
    schema = {
      fields {
        customer = string
        region = string
        signup_date = string
      }
    }
    plugin_output = "raw_customers"
  }
}

sink {
  Jdbc {
    plugin_input = "raw_customers"
    url = "jdbc:postgresql://st_practice_pg:5432/warehousedb"
    driver = "org.postgresql.Driver"
    user = "demo"
    password = "demo"
    generate_sink_sql = true       # 대상 테이블이 없으면 자동 생성
    database = "warehousedb"
    table = "public.raw_customers"
  }
}
```

`customers_raw.csv`가 들어있는 디렉터리 하나를 준비 (`LocalFile`의 `path`는 파일이 아니라 폴더를 가리켜야 함):
```bash
mkdir -p ./practice_data/customers
cp /Users/mz01-jaejunlee/projects/cluade-test/data/customers_raw.csv ./practice_data/customers/
```

### 2-3. 실행

```bash
docker run --rm --network st_practice_net \
  -v "$(pwd)/practice_data:/data:ro" \
  -v "$(pwd)/batch_customers.conf:/jobs/batch_customers.conf:ro" \
  --entrypoint sh \
  apache/seatunnel:2.3.13 \
  -c '
    mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak &&
    ./bin/seatunnel.sh --config /jobs/batch_customers.conf -m local
  '
```

**실제로 실행하면 이렇게 끝난다** (직접 확인한 로그):
```
***********************************************
           Job Statistic Information
***********************************************
Total Read Count          :                   5
Total Write Count         :                   5
Total Failed Count        :                   0
***********************************************
```

### 2-4. 검증

```bash
docker exec st_practice_pg psql -U demo -d warehousedb -c "select * from raw_customers;"
```

실제 결과 (테이블을 미리 만들지 않았는데도 `generate_sink_sql = true`가 자동 생성했다):
```
 customer | region | signup_date
----------+--------+-------------
 Alice    | East   | 2025-01-01
 Bob      | West   | 2025-02-15
 Alice    | North  | 2025-01-01
 Dave     | South  | 2025-03-01
 Eve      |        | 2025-04-01
(5 rows)
```

`Eve` 행의 `region`이 빈 값으로 그대로 들어온 걸 주목 — `etl.py`가 파이썬으로 걸러내던 규칙(`transform_customers()`의
"region 빈 값 skip")을 SeaTunnel은 적용하지 않는다. **원본을 있는 그대로 옮기고, 정제는 별도 SQL/파이프라인 단계에서
한다**는 ELT적 동작이 실제로 이렇게 나타난다. (원한다면 sink의 `query` 옵션에 `WHERE`가 포함된 SQL을 직접 써서
적재 시점에 필터링하는 것도 가능은 하다.)

---

## 3. CDC 실습: 실시간 변경 캡처

**목표**: Postgres 테이블에 INSERT/UPDATE/DELETE가 발생하는 걸 SeaTunnel이 **폴링이 아니라 WAL(Write-Ahead Log)을
실시간으로 읽어서** 그대로 잡아내는 걸 눈으로 확인한다. Batch가 "그 순간의 스냅샷을 한 번 옮기는" 거라면, CDC는
"계속 떠서 변경분을 스트리밍"하는 것 — 둘의 체감 차이가 이 실습의 핵심이다.

### 3-1. CDC를 쓰려면 왜 소스 DB 설정이 따로 필요한가

일반 JDBC batch 잡은 그냥 `SELECT`로 읽으면 끝이라 소스 DB에 특별한 설정이 필요 없었다. CDC는 다르다 —
Postgres가 복제(replication)를 위해 내부적으로 쌓아두는 **WAL(트랜잭션 로그)**을 읽어야 하는데, 기본값으로는
이 로그에 "논리적으로 어떤 행이 바뀌었는지" 복원할 수 있는 정보가 담기지 않는다(`replica` 레벨). 그래서:

- `wal_level = logical` — WAL에 논리적 디코딩이 가능한 수준의 정보를 남기도록 설정
- `REPLICA IDENTITY FULL` — UPDATE/DELETE 시 "바뀌기 전 값"까지 WAL에 남기도록 테이블별로 설정 (아니면 DELETE된
  행의 이전 값 등을 알 수 없음)

이 두 가지가 CDC 실습에서 Batch와 다르게 추가로 필요한 사전 준비다.

### 3-2. 소스 Postgres 준비 (logical replication 활성화)

```bash
docker network create st_cdc_net

docker run -d --name st_cdc_pg --network st_cdc_net \
  -e POSTGRES_USER=demo -e POSTGRES_PASSWORD=demo -e POSTGRES_DB=cdcdb \
  postgres:16 -c wal_level=logical -c max_replication_slots=10 -c max_wal_senders=10

until docker exec st_cdc_pg pg_isready -U demo -d cdcdb; do sleep 1; done

# wal_level이 실제로 logical인지 확인
docker exec st_cdc_pg psql -U demo -d cdcdb -c "SHOW wal_level;"
# → logical
```

테이블 생성 + REPLICA IDENTITY 설정 + 초기 데이터:
```bash
docker exec st_cdc_pg psql -U demo -d cdcdb -c "
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE TABLE inventory.customers (
  id INT PRIMARY KEY,
  name TEXT,
  region TEXT
);
ALTER TABLE inventory.customers REPLICA IDENTITY FULL;
INSERT INTO inventory.customers VALUES (1,'Alice','East'), (2,'Bob','West');
"
```

### 3-3. CDC config 작성

`cdc_customers.conf`:
```hocon
env {
  parallelism = 1
  job.mode = "STREAMING"     # Batch와의 가장 큰 차이 — 잡이 끝나지 않고 계속 떠 있는다
  checkpoint.interval = 3000
}

source {
  Postgres-CDC {
    plugin_output = "customers_cdc"
    username = "demo"
    password = "demo"
    database-names = ["cdcdb"]
    schema-names = ["inventory"]
    table-names = ["cdcdb.inventory.customers"]
    url = "jdbc:postgresql://st_cdc_pg:5432/cdcdb?loggerLevel=OFF"
    decoding.plugin.name = "pgoutput"    # Postgres 10+ 기본 내장 플러그인, 별도 설치 불필요
  }
}

sink {
  Console {
    plugin_input = "customers_cdc"
  }
}
```

`pgoutput`을 쓴 이유: `decoderbufs`, `wal2json` 등 다른 디코딩 플러그인은 Postgres에 확장(extension)을 별도
설치해야 하는 경우가 많은데, `pgoutput`은 Postgres 10부터 **기본 내장**이라 별도 설치 없이 바로 실습 가능하다.

### 3-4. 실행 (백그라운드로 계속 띄워둠)

Batch와 달리 이 잡은 끝나지 않는다. 별도 터미널에서 실행해두거나, 아래처럼 로그 파일로 리다이렉트하고 백그라운드로 돌린다.

```bash
docker run --rm --name st_cdc_job --network st_cdc_net \
  -v "$(pwd)/cdc_customers.conf:/jobs/cdc_customers.conf:ro" \
  --entrypoint sh \
  apache/seatunnel:2.3.13 \
  -c '
    mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak &&
    ./bin/seatunnel.sh --config /jobs/cdc_customers.conf -m local
  ' > cdc_run.log 2>&1 &
```

몇 초 뒤 로그를 보면, 먼저 **기존 데이터를 스냅샷으로 한 번 읽고**(Batch처럼), 그다음 **WAL 스트리밍 모드로 전환**된다
(직접 확인한 실제 로그):
```
Snapshot step 2 - Snapshotting data
Finished exporting 2 records for split 'cdcdb.inventory.customers:0'
...
auto enter pure increment phase.
Start incremental read task for incremental split...
```
→ 이게 CDC의 표준 동작 방식이다: **initial snapshot(현재 전체 데이터) + 이후 WAL 기반 증분(incremental) 스트리밍**을
하나의 잡이 이어서 처리한다. `startup.mode = "initial"`(기본값)이 바로 이 동작을 말하는 것.

이 시점에 콘솔 sink에는 초기 스냅샷 2건이 이미 찍혀 있다:
```
SeaTunnelRow#tableId=cdcdb.inventory.customers SeaTunnelRow#kind=INSERT : 1, Alice, East
SeaTunnelRow#tableId=cdcdb.inventory.customers SeaTunnelRow#kind=INSERT : 2, Bob, West
```

### 3-5. 잡이 떠 있는 상태에서 실시간으로 데이터 바꿔보기

**다른 터미널**(잡을 멈추지 않고!)에서 소스 테이블에 INSERT/UPDATE/DELETE를 실행한다:
```bash
docker exec st_cdc_pg psql -U demo -d cdcdb -c "INSERT INTO inventory.customers VALUES (3,'Carol','North');"
docker exec st_cdc_pg psql -U demo -d cdcdb -c "UPDATE inventory.customers SET region='South' WHERE id=1;"
docker exec st_cdc_pg psql -U demo -d cdcdb -c "DELETE FROM inventory.customers WHERE id=2;"
```

몇 초 안에 (`checkpoint.interval = 3000`이므로 최대 3초 이내) `cdc_run.log`에 이 변경들이 **실시간으로** 찍힌다.
직접 확인한 실제 출력:
```
SeaTunnelRow#tableId=cdcdb.inventory.customers SeaTunnelRow#kind=INSERT : 3, Carol, North
SeaTunnelRow#tableId=cdcdb.inventory.customers SeaTunnelRow#kind=UPDATE_BEFORE : 1, Alice, East
SeaTunnelRow#tableId=cdcdb.inventory.customers SeaTunnelRow#kind=UPDATE_AFTER  : 1, Alice, South
SeaTunnelRow#tableId=cdcdb.inventory.customers SeaTunnelRow#kind=DELETE        : 2, Bob, West
```

여기서 확인할 수 있는 CDC의 특징:
- **UPDATE는 `UPDATE_BEFORE` + `UPDATE_AFTER` 두 줄로 표현된다** — 변경 전/후 값을 모두 캡처. 이게 정확히
  `REPLICA IDENTITY FULL`이 있어야 가능한 부분이다 (없으면 `UPDATE_BEFORE`에 바뀐 컬럼 외에는 null이 찍히거나
  PK만 남는 등 정보가 부족해진다).
- **DELETE도 삭제되기 직전의 전체 행 값**을 그대로 들고 온다.
- Batch로 옮겼다면 "그 순간의 최종 상태"만 알 수 있는데, CDC는 **"무슨 일이 있었는지"(이벤트 히스토리)**까지 안다 —
  이게 배치와 CDC의 근본적인 차이다.

### 3-6. 잡 종료

```bash
docker rm -f st_cdc_job
```
(STREAMING 잡은 사람이 멈추기 전까지 계속 돈다 — Batch처럼 저절로 끝나지 않는다는 것도 실습 포인트.)

### 3-7. 여기서 한 단계 더: CDC 결과를 다른 DB로 흘려보내기

이번 실습은 `sink { Console {} }`로 눈으로 확인하는 데 집중했지만, sink를 JDBC로 바꾸면 CDC로 캡처한 변경분을
그대로 다른 Postgres/MySQL/ClickHouse 등에 실시간 반영할 수 있다 (`Protocol error` 우회는 sink 쪽에도 동일 적용):
```hocon
sink {
  jdbc {
    plugin_input = "customers_cdc"
    url = "jdbc:postgresql://<타겟host>:5432/<db>"
    driver = "org.postgresql.Driver"
    username = "..."
    password = "..."
    generate_sink_sql = true
    database = "<db>"
    table = "public.customers_replica"
    primary_keys = ["id"]      # UPDATE/DELETE를 올바르게 반영하려면 PK 지정이 사실상 필수
  }
}
```
이게 바로 SeaTunnel 활용사례에서 나왔던 "MySQL CDC → ClickHouse 실시간 동기화" 같은 패턴의 축소판이다.

---

## 4. Batch vs CDC, 실습으로 체감한 차이 정리

| | Batch (2장) | CDC (3장) |
|---|---|---|
| `job.mode` | `BATCH` | `STREAMING` |
| 잡 생명주기 | 한 번 실행하고 끝남 | 계속 떠서 스트리밍 (수동 종료 전까지) |
| 소스 DB 사전 준비 | 없음 (그냥 SELECT) | `wal_level=logical`, `REPLICA IDENTITY FULL` 필요 |
| 캡처하는 정보 | 실행 시점의 스냅샷 | 스냅샷 + 이후 모든 변경 이벤트(INSERT/UPDATE_BEFORE/UPDATE_AFTER/DELETE) |
| 최신 상태 반영 | 다시 실행해야 함 | 자동으로 계속 반영 |
| 적합한 상황 | 1회성 마이그레이션, 정기 배치 리프레시 | 실시간 동기화, 변경 이력이 중요한 경우 |

## 5. 리소스 정리

```bash
docker rm -f st_practice_pg st_cdc_pg st_cdc_job
docker network rm st_practice_net st_cdc_net
```

## 6. 다음으로 해볼 만한 것

- Batch 잡의 sink를 `openmetadata/`의 `retaildb`로 바꿔서, 이 저장소 실제 데이터로 실습 반복
- CDC sink를 Console 대신 JDBC로 바꿔서 "실시간 복제본 DB" 만들어보기
- `exactly_once = true` 옵션을 켜고 체크포인트 동작 관찰
- Zeta의 모니터링 Web UI(`seatunnel.yaml`에서 `enable-http: true`) 켜서 STREAMING 잡이 `:8080` 대시보드에
  Running Job으로 잡히는지 확인

## 참고한 공식 문서 (전체)

- [Set Up With Docker](https://seatunnel.apache.org/docs/getting-started/docker/)
- [JDBC Source](https://seatunnel.apache.org/docs/2.3.12/connector-v2/source/Jdbc/)
- [PostgreSQL Sink](https://seatunnel.apache.org/docs/2.3.12/connector-v2/sink/PostgreSql/)
- [PostgreSQL CDC Source](https://seatunnel.apache.org/docs/2.3.12/connector-v2/source/PostgreSQL-CDC/)
- [apache/seatunnel Issue #10242 — OpenGauss JDBC driver conflict](https://github.com/apache/seatunnel/issues/10242)
