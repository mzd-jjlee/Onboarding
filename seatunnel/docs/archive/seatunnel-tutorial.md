# SeaTunnel 로컬 설치/실습 튜토리얼

[seatunnel-overview.md](../seatunnel-overview.md)에서 다룬 개념을 실제로 손으로 만져보기 위한 단계별 가이드.
**환경 구성(디렉터리 구조, docker-compose, 잡 스크립트 등)은 각자 필요에 맞게 직접 짜는 걸 전제로 하고,**
여기서는 "SeaTunnel을 어떻게 실행하고 config를 어떻게 쓰는지"에 필요한 명령어와 개념만 다룬다.
모든 명령어는 이 문서를 쓰면서 실제로 로컬 Docker(이 저장소 환경 기준 Rancher Desktop)에서 직접 실행해 확인했다.

## 0) 사전 준비

Docker만 있으면 된다. 별도 설치(tarball, JDK 세팅 등) 없이 공식 이미지 하나로 충분하다.

```bash
docker pull apache/seatunnel:2.3.13   # 2026-09 기준 최신 stable
```

## 1) 이미지 안에 뭐가 들어있는지 먼저 확인하기

공식 이미지는 SeaTunnel의 실제 배포판(tarball)을 그대로 담고 있고, `SEATUNNEL_HOME`은 `/opt/seatunnel`이다.

```bash
docker run --rm apache/seatunnel:2.3.13 sh -c 'ls /opt/seatunnel'
# bin  config  connectors  lib  licenses  LICENSE  NOTICE  plugins  README.md  starter
```

여기서 두 디렉터리가 중요하다:

- **`connectors/`** — 커넥터 jar가 **전부 미리 설치되어 있다.** 공식 튜토리얼에 나오는 "필요한 커넥터를 `config/plugin_config`에
  적고 `install-plugin.sh`로 설치"하는 절차는 **소스 tarball**을 직접 받아 쓸 때 이야기고, Docker 이미지는 이미 다 들어있어서
  이 단계가 필요 없다. (`connector-jdbc`, `connector-file-local`, `connector-console`, `connector-fake`, `connector-cdc-*` 등
  거의 모든 커넥터가 기본 포함)
- **`lib/`** — 라이선스 문제로 SeaTunnel이 배포할 수 없는 JDBC 드라이버(`postgresql-42.4.3.jar`, `mysql-connector-java-8.0.27.jar`,
  `mssql-jdbc-*.jar`, `ojdbc8-*.jar` 등)도 **이미 넣어져 있다.** 즉 Postgres/MySQL 같은 주요 DB는 드라이버를 따로 받을 필요가 없다.
  (문서상으로는 "직접 받아서 `lib/`에 넣으라"고 안내하지만, 최소한 2.3.13 공식 이미지는 이미 포함돼 있다 — 버전이 바뀌면
  다시 확인해볼 것)

즉 이 이미지 하나만 있으면 별도 설치/네트워크 다운로드 없이 바로 잡을 실행할 수 있다.

## 2) 가장 간단한 잡: FakeSource → Console

SeaTunnel은 테스트용으로 데이터를 직접 만들어내는 `FakeSource`와, 결과를 터미널에 그냥 찍는 `Console` sink를 제공한다.
DB든 파일이든 아무 인프라 없이 "config 파일 하나 = 잡 하나"라는 감각을 잡기에 가장 좋다.

이미지에 기본 템플릿이 이미 들어있다:

```bash
docker run --rm apache/seatunnel:2.3.13 cat /opt/seatunnel/config/v2.batch.config.template
```

```hocon
env {
  parallelism = 2
  job.mode = "BATCH"
  checkpoint.interval = 10000
}

source {
  FakeSource {
    parallelism = 2
    plugin_output = "fake"
    row.num = 16
    schema = {
      fields {
        name = "string"
        age = "int"
      }
    }
  }
}

sink {
  Console {
  }
}
```

이 템플릿 그대로 로컬(Zeta, `-m local`) 모드로 실행:

```bash
docker run --rm apache/seatunnel:2.3.13 \
  ./bin/seatunnel.sh --config ./config/v2.batch.config.template -m local
```

로그 맨 아래에 이런 통계가 찍히면 성공이다:

```
***********************************************
           Job Statistic Information
***********************************************
Total Read Count          :                  32
Total Write Count         :                  32
Total Failed Count        :                   0
***********************************************
```

`-m local`은 Zeta 엔진을 클러스터 없이 "이 프로세스 안에서" 돌리는 모드 — 실습/개발용으로 이걸 쓰면 된다.
운영에서는 `seatunnel-cluster.sh`로 별도 마스터/워커를 띄우는 클러스터 모드를 쓴다.

**직접 만든 config를 실행하려면** 로컬 파일을 컨테이너에 마운트하면 된다:

```bash
docker run --rm -v /path/to/my_job.conf:/jobs/my_job.conf:ro \
  apache/seatunnel:2.3.13 \
  ./bin/seatunnel.sh --config /jobs/my_job.conf -m local
```

## 3) 실제 데이터 읽어보기: LocalFile(CSV) → Console

이 저장소의 `data/customers_raw.csv`, `data/sales_raw.csv`를 SeaTunnel의 `LocalFile` source로 읽어보자.
**주의할 점 하나**: `LocalFile`의 `path`는 "파일 하나"가 아니라 **그 파일들이 들어있는 디렉터리**를 가리켜야 한다
(디렉터리 안의 파일들을 스캔해서 읽는 방식). 그래서 CSV 하나만 읽고 싶어도 그 파일이 속한 폴더를 마운트해야 한다.

```hocon
env {
  parallelism = 1
  job.mode = "BATCH"
}

source {
  LocalFile {
    path = "/data/customers"     # customers_raw.csv가 들어있는 디렉터리
    file_format_type = "csv"
    csv_use_header_line = true   # 첫 줄을 헤더로 인식하고 건너뜀
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
  Console {
    plugin_input = "raw_customers"
  }
}
```

실행 (CSV가 있는 디렉터리를 `/data`로 마운트):

```bash
docker run --rm \
  -v "$(pwd)/data/customers:/data/customers:ro" \
  -v "$(pwd)/my_csv_job.conf:/jobs/my_csv_job.conf:ro" \
  apache/seatunnel:2.3.13 \
  ./bin/seatunnel.sh --config /jobs/my_csv_job.conf -m local
```

이 저장소의 `customers_raw.csv`를 그대로 읽으면 콘솔에 이렇게 찍힌다 (직접 실행해서 확인함):

```
SeaTunnelRow#tableId=raw_customers SeaTunnelRow#kind=INSERT : Alice, East, 2025-01-01
SeaTunnelRow#tableId=raw_customers SeaTunnelRow#kind=INSERT : Bob, West, 2025-02-15
SeaTunnelRow#tableId=raw_customers SeaTunnelRow#kind=INSERT : Alice, North, 2025-01-01
SeaTunnelRow#tableId=raw_customers SeaTunnelRow#kind=INSERT : Dave, South, 2025-03-01
SeaTunnelRow#tableId=raw_customers SeaTunnelRow#kind=INSERT : Eve, , 2025-04-01
```

`etl.py`의 `transform_customers()`가 파이썬으로 걸러내던 "region 빈 값"(`Eve` 행)도 여기서는 **걸러지지 않고
그대로 들어온다** — SeaTunnel의 CSV 소스는 스키마 타입만 강제할 뿐 비즈니스 규칙(중복 제거, 빈 값 필터링)은
알아서 해주지 않는다. "일단 원본 그대로 옮기고, 정제는 다음 단계(SQL transform이나 sink 쪽 DB의 쿼리)에서 한다"는
ELT적인 사고방식이 SeaTunnel의 기본 철학에 가깝다.

## 4) 실제 DB로: JDBC source/sink

여기서부터는 Postgres 같은 실제 DB가 필요하다. 공식 문서 기준 최소 설정은 이렇다.

**Source (Postgres에서 읽기):**
```hocon
source {
  Jdbc {
    url = "jdbc:postgresql://<host>:5432/<db>"
    driver = "org.postgresql.Driver"
    user = "<user>"
    password = "<password>"
    query = "select * from your_table"
    plugin_output = "src"
  }
}
```

**Sink (Postgres에 쓰기, 테이블 자동 생성 포함):**
```hocon
sink {
  jdbc {
    plugin_input = "src"
    url = "jdbc:postgresql://<host>:5432/<db>"
    driver = "org.postgresql.Driver"
    user = "<user>"
    password = "<password>"
    generate_sink_sql = true       # 대상 테이블이 없으면 자동 생성
    database = "<db>"
    table = "public.<table>"
    # primary_keys = ["id"]        # upsert(있으면 UPDATE, 없으면 INSERT)가 필요하면 지정
  }
}
```

컨테이너에서 호스트에 떠 있는 Postgres(예: `openmetadata/`의 `retaildb`, `localhost:5432`)에 붙이려면
Mac Docker Desktop/Rancher Desktop 기준 `host.docker.internal`을, 같은 docker network에 있는 컨테이너라면
컨테이너 이름을 host로 쓴다 — `openmetadata/docker-compose.sourcedb.yml`에서 쓰는 것과 같은 패턴이다.

### 트러블슈팅: `Protocol error. Session setup failed.` — 원인 특정함

테스트 중 `org.postgresql.util.PSQLException: Protocol error. Session setup failed.` 에러를 여러 번 만났고,
**원인을 확정했다.** apache/seatunnel 공식 이슈 [#10242](https://github.com/apache/seatunnel/issues/10242)에
정확히 같은 증상이 보고되어 있다:

`/opt/seatunnel/lib/`에는 `postgresql-42.4.3.jar`뿐 아니라 **`opengauss-jdbc-5.1.0.jar`도 같이 들어있는데**,
OpenGauss(화웨이의 PostgreSQL 포크 DB) JDBC 드라이버가 **같은 `org.postgresql.Driver` 클래스명**을 그대로 재사용한다.
SeaTunnel이 JDBC 커넥터용 클래스로더를 만들 때 이 충돌 때문에 진짜 PostgreSQL 드라이버가 아니라 OpenGauss용
드라이버가 로드될 수 있고, OpenGauss는 PostgreSQL과 인증 핸드셰이크 방식이 달라서 서버가 보낸 정상적인
`AuthenticationMD5Password` 메시지를 파싱하지 못해 이 에러를 던진다. (순수 Java로 `postgresql-42.4.3.jar` 하나만
클래스패스에 넣고 연결하면 성공했던 것도 이 때문 — 그때는 충돌 대상이 없었다.)

**해결책 (컨테이너 시작 시 충돌 jar를 비활성화):**
```bash
docker run --rm --entrypoint sh apache/seatunnel:2.3.13 -c '
  mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak &&
  ./bin/seatunnel.sh --config /jobs/my_job.conf -m local
'
```
OpenGauss를 실제로 쓸 계획이 없다면 이 jar는 없어도 무방하다. 실제로 이 방법으로 JDBC sink(`generate_sink_sql = true`로
테이블 자동 생성 포함)와 Postgres-CDC source 둘 다 정상 동작하는 걸 확인했다 (아래 5), 6)번 참고).

이 이슈는 이 문서를 쓰는 시점 기준 **아직 Open**이라 2.3.13을 포함한 배포 이미지에 그대로 남아있다. 향후 버전에서
고쳐졌는지는 실습 시점에 이미지 버전에 맞춰 다시 확인해볼 것.

## 5) SQL Transform으로 가벼운 가공

source와 sink 사이에서 필드를 고치거나 계산하고 싶을 때 `Sql` transform을 쓴다. 단, **문서 기준으로 멀티 테이블
JOIN이나 GROUP BY 집계는 지원하지 않는다** — 순수 SELECT/필터/함수 수준의 가공만 가능하다. 그래서 "customers와
sales를 조인해서 고객별 합계를 낸다" 같은 작업(이 저장소 `openmetadata/dags/customer_sales_summary_join.py`가
Airflow+psycopg2로 하는 일)은 SeaTunnel Transform이 아니라 **source 쪽 JDBC `query`에 JOIN·GROUP BY가 포함된
SQL을 직접 써서** 가져오는 패턴이 된다 (DB 엔진이 조인을 수행하고, SeaTunnel은 그 결과를 그대로 다른 곳으로 옮기는 역할).

```hocon
transform {
  Sql {
    plugin_input = "fake"
    plugin_output = "fake1"
    query = "select id, concat(name, '_') as name, age + 1 as age from dual where id > 0"
  }
}
```

## 다음으로 해볼 만한 것

- `openmetadata/`의 `retaildb`(customers, sales 테이블)에 JDBC source로 붙어서 읽어보기
- JOIN이 포함된 `query`로 `customer_sales_summary_join.py`가 하던 집계를 SeaTunnel 잡 하나로 재현해보기
- `env.job.mode = "STREAMING"` + CDC 커넥터(`connector-cdc-postgres`)로 실시간 변경분 동기화 실습
- 여러 source/sink를 하나의 config에 엮어서 두 테이블을 동시에 옮기는 잡 짜보기

## 참고한 공식 문서

- [Set Up With Docker](https://seatunnel.apache.org/docs/getting-started/docker/)
- [Deployment (locally)](https://seatunnel.apache.org/docs/2.3.12/start-v2/locally/deployment/)
- [Quick Start (SeaTunnel Engine)](https://seatunnel.apache.org/docs/2.3.12/start-v2/locally/quick-start-seatunnel-engine/)
- [JDBC Source](https://seatunnel.apache.org/docs/2.3.12/connector-v2/source/Jdbc/)
- [PostgreSQL Sink](https://seatunnel.apache.org/docs/2.3.12/connector-v2/sink/PostgreSql/)
- [SQL Transform](https://seatunnel.apache.org/docs/2.3.12/transform-v2/sql)
