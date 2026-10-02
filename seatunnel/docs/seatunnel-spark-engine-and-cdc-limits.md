# SeaTunnel Spark 엔진의 제약과 CDC 비호환성

2026-09-16. Apache SeaTunnel 2.3.13 공식 문서를 직접 조회해 확인한 내용이다. Gemini와의 대화에서 얻은 내용을 출발점으로 삼되, 이 문서에 적은 사실 관계는 모두 아래 "근거" 절의 공식 문서 원문으로 재검증했다.

## 결론 요약

1. **Spark 엔진을 쓰려면 Spark를 미리 설치해야 한다.** SeaTunnel이 Spark를 내장하지 않는다. `seatunnel-env.sh`에 `SPARK_HOME`을 지정해 기존 Spark 배포본을 가리켜야 한다.
2. **Spark 엔진은 CDC를 지원하지 않는다.** 이 프로젝트가 실제로 쓰는 `Postgres-CDC` 커넥터의 공식 문서도 지원 엔진으로 "SeaTunnel Zeta, Flink"만 명시하고 Spark는 언급하지 않는다.
3. 이 프로젝트의 CDC 실습(`jobs/09`, `jobs/15`)은 애초에 Spark로는 재현할 수 없는 실습이었다. Spark를 검토했다가 배제한 게 아니라, Postgres-CDC 커넥터 자체가 Spark 엔진에서 지원되지 않기 때문에 선택의 여지가 없었다.

## 1. Zeta / Flink / Spark — 사전 설치 요구사항 비교

공식 엔진 개요 문서(근거 1)의 "Dependency" 비교:

| 엔진 | 성격 | 별도 설치 필요 |
|---|---|---|
| SeaTunnel Engine (Zeta) | Native engine built specifically for data integration | 없음 (`None`) |
| Apache Flink | Distributed stream processing engine | 기존 Flink 인프라 필요 |
| Apache Spark | Distributed batch/stream processing engine | `YARN/Mesos` — 즉 별도로 구축된 Spark(+ 클러스터 매니저) 필요 |

이 프로젝트의 `docs/archive/seatunnel-introduction-and-cluster-batch.md`에 정리해 둔 "이번 실습에서는 Zeta 엔진 사용" 근거와 일치한다. Zeta는 이미지 안에 내장되어 있어 추가 설치 없이 Docker 컨테이너 하나로 실습이 가능했지만, Spark를 선택했다면 이 프로젝트와 별개로 Spark 클러스터부터 구축해야 했다는 뜻이다.

## 2. Spark 엔진을 쓰려면 실제로 뭘 해야 하는가

공식 Spark Quick Start 문서(근거 2, SeaTunnel 2.3.13 기준) 원문:

> Download Spark first(**required version >= 2.4.0**)

> Change the setting in `${SEATUNNEL_HOME}/config/seatunnel-env.sh` and set `SPARK_HOME` to the Spark deployment dir.

즉 다음 순서가 필요하다.

1. Spark 2.4.0 이상을 별도로 다운로드·설치한다 (SeaTunnel이 자동으로 가져오지 않는다).
2. `${SEATUNNEL_HOME}/config/seatunnel-env.sh`를 열어 `SPARK_HOME`을 그 설치 경로로 지정한다.
3. Spark 버전에 맞는 실행 스크립트로 잡을 제출한다.

```bash
# Spark 2.4.x
./bin/start-seatunnel-spark-2-connector-v2.sh \
  --master local[4] \
  --deploy-mode client \
  --config ./config/v2.streaming.conf.template

# Spark 3.x.x
./bin/start-seatunnel-spark-3-connector-v2.sh \
  --master local[4] \
  --deploy-mode client \
  --config ./config/v2.streaming.conf.template
```

`-m local`/`-m cluster`로 실행하는 Zeta와 달리, Spark 엔진은 스크립트 이름 자체가 `start-seatunnel-spark-2-connector-v2.sh` / `-spark-3-`로 나뉘어 있다. SeaTunnel이 설정 파일을 Spark가 이해하는 실행 계획으로 변환해 **이미 떠 있는 Spark(YARN/Mesos 등)에 제출**하는 구조이지, SeaTunnel 프로세스 자체가 Spark 역할을 대신하는 게 아니다.

**이 프로젝트에 적용하면:** 기존에 Spark 인프라가 없는 상태에서 Spark 엔진으로 전환하려면, Docker 컨테이너 하나를 더 띄우는 수준이 아니라 Spark 배포본 설치 + `SPARK_HOME` 연결이라는 별도 인프라 작업이 선행되어야 한다. 이번 실습처럼 Docker만으로 완결되는 구성은 Zeta이기 때문에 가능했다.

## 3. Spark 엔진은 CDC를 지원하지 않는다 — 공식 문서 근거

### 3.1 엔진 개요 문서의 CDC 지원 표

공식 엔진 개요 문서(근거 1)의 "CDC" 관련 행:

- SeaTunnel Engine (Zeta): **지원 (✅)**
- Flink: **지원 (✅)**
- Spark: **미지원 (❌ Not supported)**

### 3.2 이 프로젝트가 실제로 쓰는 커넥터 문서로 재확인

이 프로젝트의 CDC 실습(`jobs/09_postgres_cdc_to_jdbc_sink.conf`, `jobs/15_postgres_10m_cdc_insert_update.conf`)은 `Postgres-CDC` 소스 커넥터를 쓴다. 공식 커넥터 문서(근거 3)의 "Support Those Engines" 절에는 다음만 나열되어 있다.

> SeaTunnel Zeta, Flink

Spark는 이 목록에 없다. 즉 일반론이 아니라, **이번 실습에서 실제로 쓴 그 커넥터가 Spark 엔진에서 지원되지 않는다는 것이 공식 문서로 확인된다.**

### 3.3 왜 구조적으로 안 맞는가 (아키텍처적 설명 — 공식 문서의 직접 인용은 아님)

이 부분은 SeaTunnel 공식 문서가 명시한 근거가 아니라, Spark와 CDC 아키텍처의 일반적 특성에서 나오는 설명이다. 사실 확인이 아니라 해석이므로 발표에서는 "공식 문서에 이렇게 쓰여 있다"가 아니라 "구조적으로 이런 이유가 있을 것으로 보인다" 수준으로 표현한다.

- CDC는 DB의 변경 로그(WAL, binlog 등)를 논리 복제로 계속 구독하면서, 커밋되는 즉시 다음 단계로 넘겨야 하는 **연속 스트리밍** 워크로드다. 이 프로젝트의 CDC 실습에서도 `checkpoint.interval = 3000`(약 3초)마다 상태를 커밋하며 이벤트가 없을 때도 잡이 `RUNNING` 상태로 계속 대기했다 (`docs/cdc_seatunnel.md` 참고).
- Apache Spark의 핵심 처리 모델(Spark Structured Streaming 포함)은 일정 주기로 데이터를 모아 처리하는 **마이크로배치** 방식이다. 배치 단위로 끊어 처리하는 모델은 초 단위 미만의 지속적 변경 로그 구독·순서 보장이 필요한 CDC 커넥터 구현과는 결이 다르다.
- Zeta와 Flink는 순수 스트리밍 실행 모델을 기본으로 두고 있어 CDC 커넥터(Debezium 기반 등)와의 통합이 엔진 차원에서 구현되어 있다. 반면 Spark용 CDC 커넥터 구현 자체가 SeaTunnel 2.3.13 시점에는 존재하지 않는다 (§3.1, §3.2의 표가 이를 보여준다).

이 설명은 "왜 그런 설계 선택이 났는지"에 대한 합리적 추정이며, SeaTunnel 프로젝트가 이 이유를 공식적으로 문서화했다는 근거는 찾지 못했다. 발표에서 다룰 때는 "Spark 엔진은 CDC를 지원하지 않는다"(사실, 문서로 확인됨)와 "그 이유는 아마 마이크로배치 구조 때문일 것이다"(추정)를 구분해서 말한다.

## 4. 이 프로젝트 실습에 대한 함의

- 지금까지 배치 실습(`jobs/01`, `jobs/12`)과 CDC 실습(`jobs/09`, `jobs/15`) 모두 Zeta 엔진으로 진행했고, 이는 "기존 Spark 인프라가 없다"는 이유뿐 아니라 **CDC 실습 자체가 Spark로는 애초에 불가능했다**는 더 강한 이유가 있었다.
- 향후 발표나 문서에서 "Spark는 무겁고 번거로워서 Zeta를 썼다"고만 설명하면 절반만 맞는 말이 된다. CDC 파트는 "Spark를 배제하고 Zeta를 골랐다"가 아니라 "Spark는 선택지에 아예 없었고 Zeta 또는 Flink만 가능했다"고 표현하는 것이 정확하다.
- 배치 전용 파이프라인(예: `jobs/01`, `jobs/12`)이라면 이론적으로는 Spark 엔진도 선택지에 들어갈 수 있다 — 다만 그 경우에도 기존 Spark 인프라가 없다면 Zeta 대비 얻는 이득 없이 설치 부담만 늘어난다는 점은 기존 문서의 결론과 같다.

## 근거

1. [Engine Overview (2.3.13)](https://seatunnel.apache.org/docs/2.3.13/engines/overview/) — 엔진별 Dependency, CDC 지원 여부 비교표
2. [Quick Start With Spark (2.3.13)](https://seatunnel.apache.org/docs/2.3.13/getting-started/locally/quick-start-spark/) — Spark 다운로드 요구 버전(>=2.4.0), `SPARK_HOME` 설정 방법, 실행 스크립트 예시
3. [PostgreSQL CDC 커넥터 (2.3.13)](https://seatunnel.apache.org/docs/2.3.13/connectors/source/PostgreSQL-CDC/) — "Support Those Engines" 절에 SeaTunnel Zeta, Flink만 명시 (Spark 없음)

## 확인하지 않은 것

- Spark 3.x/4.x 최신 버전이나 SeaTunnel 최신(2.3.13 이후) 버전에서 CDC 지원 상태가 바뀌었는지는 확인하지 않았다. 이 문서는 이 프로젝트가 실제로 쓰는 2.3.13 기준이다.
- Spark Structured Streaming 자체의 지연시간 한계에 대한 정량적 벤치마크는 조회하지 않았다. §3.3의 아키텍처 설명은 정성적 추정이다.
- 이 프로젝트에서 Spark 엔진을 실제로 설치·실행해본 적은 없다. 위 설정 절차는 공식 문서 인용이며 이 환경에서 재현 검증한 것은 아니다.
