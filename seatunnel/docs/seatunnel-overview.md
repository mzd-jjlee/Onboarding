# Apache SeaTunnel이란 무엇이고, 왜, 어떻게 쓰는가

`openmetadata/docs/openmetadata-overview.md`와 같은 성격의 문서다. "직접 손으로 환경을 구성하는 법"은
[archive/seatunnel-tutorial.md](archive/seatunnel-tutorial.md)에 따로 정리했고, 이 문서는 그보다 한 단계 위에서
**SeaTunnel 자체가 어떤 도구이고, 왜 쓰고, 개념적으로 어떻게 동작하는가**를 다룬다.

## 어떤 도구인가

Apache SeaTunnel은 공식 문서에서 스스로를 이렇게 정의한다:

> "a very easy-to-use, ultra-high-performance, distributed data integration platform that supports
> real-time synchronization of massive data"
> — [About](https://seatunnel.apache.org/docs/2.3.12/about/)

한 줄로 요약하면: 여러 이기종 시스템(DB, 파일, 메시지 큐, SaaS API, 웨어하우스 등) 사이에서
**데이터를 옮기고 가볍게 변환하는 데이터 통합(ETL/ELT) 도구**다. OpenMetadata가 "흩어진 데이터를
검색 가능하게 카탈로그화"하는 도구라면, SeaTunnel은 "흩어진 데이터를 실제로 한쪽에서 다른 쪽으로
움직이는" 도구라는 점에서 서로 보완적인 포지션에 있다.

### 히스토리

- 2017년 **Waterdrop**이라는 이름으로 시작.
- 2021년 10월 **SeaTunnel**로 개명.
- 2021년 12월 Apache Incubator 진입.
- 2023년 6월 Apache **최상위 프로젝트(Top-Level Project)**로 승격.

(출처: [SeaTunnel Proposal](https://cwiki.apache.org/confluence/display/INCUBATOR/SeaTunnelProposal),
[ASF Blog](https://news.apache.org/foundation/entry/asf-project-spotlight-apache-seatunnel))

## 왜 필요한가

"DB A에서 DB B로 데이터를 옮긴다"는 요구는 어느 조직에서나 반복된다. 이걸 그때그때 스크립트(Python + 커넥터 라이브러리)로
짜면 매번: 커넥션 관리, 배치/재시도, 스키마 변환, 대용량일 때의 성능(병렬 처리), 장애 시 재시작 지점 같은 문제를
새로 풀어야 한다. SeaTunnel은 이 반복 작업을 **"source/sink 커넥터 + 설정 파일"**로 표준화한다 — 즉 이 저장소의
`etl.py`가 "CSV를 읽어 정제해서 SQLite에 넣는" 로직을 Python 코드로 직접 짠 것과 달리, SeaTunnel은 같은 일을
**코드 없이 선언적 config 파일**로 표현한다.

## 아키텍처

### 1) 실행 엔진(Engine)

SeaTunnel 잡은 세 가지 엔진 중 하나로 실행할 수 있다:

| 엔진 | 특징 |
|---|---|
| **Zeta (SeaTunnel Engine)** | SeaTunnel 자체 개발 엔진. 별도 Spark/Flink 클러스터 없이 가볍게 돌릴 수 있어 **기본/권장** 엔진 |
| **Flink** | 기존 Flink 클러스터가 있는 조직이 그 인프라를 재사용하고 싶을 때 |
| **Spark** | 기존 Spark 클러스터가 있는 조직이 그 인프라를 재사용하고 싶을 때 |

핵심은 **같은 config 파일을 엔진만 바꿔서 그대로 실행**할 수 있다는 것 — 잡 정의(source/transform/sink)와
실행 엔진이 분리되어 있다.

### 2) 파이프라인 구조: Source → Transform → Sink

설정 파일은 **HOCON**(`.conf`, JSON의 상위 호환 포맷) 문법으로 4개 블록을 갖는다.

```hocon
env {
  parallelism = 1
  job.mode = "BATCH"        # 또는 "STREAMING"
}

source {
  # 어디서 읽을지 (JDBC, LocalFile, Kafka, FakeSource(테스트용) 등)
}

transform {
  # (선택) 필드 매핑, SQL 변환 같은 가벼운 가공
}

sink {
  # 어디에 쓸지 (JDBC, Console, S3, Elasticsearch 등)
}
```

블록 사이는 `plugin_output`(이 단계 결과에 붙일 이름)과 `plugin_input`(어느 결과를 입력으로 쓸지)으로 연결한다.
여러 source/transform/sink를 하나의 config에 자유롭게 엮을 수 있다.

### 3) 커넥터 생태계

공식 홈페이지 기준 대략 100~200개 커넥터를 제공한다: JDBC 계열(Postgres/MySQL/Oracle/SQL Server/...),
파일(Local/S3/HDFS/FTP/...), 메시지 큐(Kafka/Pulsar/RabbitMQ/...), 웨어하우스(Iceberg/Hudi/Doris/ClickHouse/...),
검색엔진(Elasticsearch), SaaS API(Notion/GitHub/Jira/...) 등. 커넥터마다 독립된 jar로 분리되어 있어
필요한 것만 골라 쓸 수 있다.

### 4) Batch / Streaming / CDC

`env.job.mode`로 배치와 스트리밍을 전환하는 것 외에, **CDC(Change Data Capture)** 커넥터군(`connector-cdc-mysql`,
`connector-cdc-postgres` 등)을 통해 소스 DB의 WAL/binlog를 실시간으로 읽어 변경분만 계속 흘려보내는 것도 지원한다.
같은 배치/스트리밍/CDC 개념을 하나의 커넥터 프레임워크 안에서 다룬다는 게 SeaTunnel이 스스로 내세우는 차별점이다.

### 5) 정합성(Fault Tolerance)

Chandy-Lamport 알고리즘 기반의 분산 스냅샷(체크포인트)을 사용해서, 잡이 중간에 실패해도 마지막 성공한
체크포인트 지점부터 재시작할 수 있다.

## 핵심 기능 요약

| 기능 | 내용 |
|---|---|
| **Source/Sink 커넥터** | ~100~200개, DB/파일/큐/웨어하우스/SaaS API 등 |
| **Transform** | SQL 기반 필드 가공(단, 문서 기준 멀티 테이블 JOIN·집계는 미지원 — 조인은 source 쪽 DB에 SQL로 위임하는 패턴이 일반적) |
| **멀티 엔진** | 같은 config를 Zeta/Flink/Spark 중 선택해 실행 |
| **Batch/Streaming/CDC 통합** | 하나의 커넥터 프레임워크로 세 가지 모두 지원 |
| **체크포인트 기반 정합성** | 장애 시 마지막 체크포인트부터 자동 복구 |

## 활용 사례

공식 홈페이지와 [Users 페이지](https://seatunnel.apache.org/user)가 강조하는 시나리오:

1. **여러 소스 DB → 하나의 데이터 웨어하우스로 통합하는 배치 마이그레이션**
2. **CDC 기반 실시간 동기화** (예: MySQL → ClickHouse로 변경분 실시간 반영)
3. **스트리밍 파이프라인 안에서의 경량 변환** (SQL Transform, 필드 매핑)

JPMorgan, ByteDance, Tencent Cloud, Shopee, OPPO, Vipshop, PING AN, Hyundai Motor, S7 Airlines 등
100개 이상 기업/조직이 Users 페이지에 사용 사례로 등재되어 있다.

## 폐쇄망(에어갭) 환경에 설치하려면

실습은 인터넷이 되는 환경에서 Docker로 편하게 했지만, 실제 도입 대상이 **폐쇄망**이라면 이야기가 달라진다.
설치 방식 두 가지(tarball vs Docker)가 폐쇄망에서 요구하는 게 다르므로 미리 알아두는 게 좋다.

### tarball + `install-plugin.sh` 방식의 숨은 함정

[Deployment 문서](https://seatunnel.apache.org/docs/2.3.13/getting-started/locally/deployment/)가 안내하는
`bin/install-plugin.sh`는 겉보기엔 "커넥터 jar를 인터넷에서 받는 스크립트" 정도로 보이지만, 실제 스크립트
원문([2.3.13 태그 기준](https://raw.githubusercontent.com/apache/seatunnel/2.3.13/bin/install-plugin.sh))을
까보면 내부적으로 **Maven의 `dependency:get`**을 그대로 호출한다:
```bash
${SEATUNNEL_HOME}/mvnw dependency:get -Dtransitive=false -DgroupId=org.apache.seatunnel \
  -DartifactId=${line} -Dversion=${version} -Ddest=${SEATUNNEL_HOME}/connectors
```
좋은 소식은 이게 **Maven 표준 메커니즘**이라는 것 — `~/.m2/settings.xml`에 사내 Nexus/Artifactory 같은
미러 저장소를 `<mirror>`로 등록해두면 SeaTunnel 쪽 코드 수정 없이 그 사내망 경로로 다운로드를 돌릴 수 있다.

**그런데 함정이 하나 더 있다.** `mvnw`는 "Maven Wrapper"라서, 로컬에 Maven이 아예 없으면 **Maven 실행파일
자체를 먼저 인터넷에서 받으려고 시도**한다 (`.mvn/wrapper/maven-wrapper.properties`에 박힌
`https://repo.maven.apache.org/...` URL). 즉 폐쇄망에서는:
1. 커넥터 jar (Maven mirror로 우회 가능)
2. **Maven 배포판 자체** (별도로 미리 반입해서 로컬에 캐시해두거나, wrapper 설정을 손봐야 함)

이렇게 **이중으로 인터넷 의존성**이 걸려있는데, 이건 SeaTunnel 공식 문서 어디에도 명시적으로 경고돼 있지 않다
(직접 스크립트를 읽어봐야 알 수 있는 부분). 참고로 [공식 다운로드 페이지](https://seatunnel.apache.org/download)를
확인해보면 "커넥터가 이미 다 포함된 완전판" 배포본은 따로 없고, 모든 버전이 커넥터 없는 core tarball
(`apache-seatunnel-{ver}-bin.tar.gz`) 하나뿐이라 이 단계를 피해갈 방법이 없다.

다만 프로젝트도 이 문제를 인지하고 있는 듯 하다 — 2026년 7월 merge된
[PR #11555 "Download connector plugins over HTTPS"](https://github.com/apache/seatunnel/pull/11555)는
"Maven을 부트스트랩하지 않고도 HTTPS로 커넥터를 직접 받을 수 있게 하되, 기존처럼 Maven mirror/proxy/인증
설정에 의존하던 사용자를 위한 경로도 유지한다"는 설명을 달고 있다. 즉 향후 버전에서는 이 이중 함정이 완화될
가능성이 있다 (정확히 어느 릴리스부터 반영되는지는 확인 안 됨 — 실습/도입 시점 버전에서 다시 확인 필요).

### Docker 이미지 반입 — 더 간단한 대안

`apache/seatunnel` 이미지는 커넥터가 이미 다 설치된 상태로 빌드돼 있으므로, **이미지를 통째로 반입**하면
위 함정을 전부 피해갈 수 있다:
```bash
# 인터넷 되는 환경에서
docker pull apache/seatunnel:2.3.13
docker save apache/seatunnel:2.3.13 -o seatunnel.tar

# 폐쇄망으로 USB/사내 파일서버 등으로 반입 후
docker load -i seatunnel.tar
# 또는 사내 프라이빗 레지스트리(Harbor 등)로 tag + push해서 배포
```
이미지 크기는 `linux/amd64`/`linux/arm64` 멀티arch 기준 아키텍처당 약 **3.18GB**
([Docker Hub 태그 정보](https://hub.docker.com/r/apache/seatunnel/tags) 확인) — 반입 방식(USB 등) 선택 시
이 용량만 감안하면 특별한 제약은 없다.

### 정리

| 방식 | 폐쇄망 대응 | 준비할 것 |
|---|---|---|
| tarball + `install-plugin.sh` | 가능하지만 손이 많이 감 | Maven mirror 설정 + Maven 배포판 자체도 별도 반입 |
| Docker 이미지 | 간단 | `docker save/load`로 이미지 통째로 반입 (약 3GB) |

"air-gapped"라는 단어로 이 상황을 직접 언급하는 공식 가이드는 찾지 못했다 — 위 내용은 공식 스크립트/문서를
직접 확인해서 도출한 결론이지, SeaTunnel이 공식적으로 권장하는 폐쇄망 설치 절차는 아니라는 점은 감안할 것.

## 이 저장소 맥락에서: etl.py / OpenMetadata와의 관계

이 저장소에는 이미 두 가지가 있다:

- `etl.py` — CSV를 Python 코드로 직접 파싱/정제해서 SQLite에 적재하는 수작업 ETL
- `openmetadata/` — Postgres에 있는 테이블들을 **카탈로그화(검색 가능하게)**하는 도구

SeaTunnel은 이 둘 사이 어딘가에 위치한다: `etl.py`가 코드로 하던 "데이터 옮기기·적재"를 **선언적 config**로
대체할 수 있는 도구이면서, 동시에 OpenMetadata가 카탈로그화할 **원본 테이블을 실제로 채워 넣는** 역할도 할 수 있다.
"코드 없이 config 파일로 DB 간 데이터를 동기화한다"는 감각을 잡는 게 이 도구를 이해하는 핵심이다.

## 참고한 공식 문서

- [About SeaTunnel](https://seatunnel.apache.org/docs/2.3.12/about/)
- [Architecture Overview](https://seatunnel.apache.org/docs/architecture/overview/)
- [SeaTunnel 홈페이지](https://seatunnel.apache.org/)
- [Users](https://seatunnel.apache.org/user)
- [GitHub - apache/seatunnel](https://github.com/apache/seatunnel)
- [SeaTunnel Proposal (Apache Incubator)](https://cwiki.apache.org/confluence/display/INCUBATOR/SeaTunnelProposal)
- [Deployment (2.3.13)](https://seatunnel.apache.org/docs/2.3.13/getting-started/locally/deployment/)
- [bin/install-plugin.sh 원문 (2.3.13 태그)](https://raw.githubusercontent.com/apache/seatunnel/2.3.13/bin/install-plugin.sh)
- [Apache SeaTunnel Download](https://seatunnel.apache.org/download)
- [PR #11555 — Download connector plugins over HTTPS](https://github.com/apache/seatunnel/pull/11555)
- [Docker Hub - apache/seatunnel tags](https://hub.docker.com/r/apache/seatunnel/tags)
