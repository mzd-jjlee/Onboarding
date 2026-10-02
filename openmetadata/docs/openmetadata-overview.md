# OpenMetadata란 무엇이고, 왜, 어떻게 쓰는가

`openmetadata/` 아래에서 실제로 띄워본 로컬 데모(공식 스택 + 소스 Postgres)를 이해하기 위한 배경 문서다.
"어떻게 설정했는가"는 [openmetadata-demo-design.md](openmetadata-demo-design.md)에 이미 정리되어 있으므로,
이 문서는 그보다 한 단계 위에서 **OpenMetadata 자체가 어떤 도구이고, 왜 쓰고, 일반적으로 어떻게 쓰는가**를 다룬다.

## 어떤 도구인가 

OpenMetadata는 여러 데이터 시스템에 흩어진 메타데이터를 수집하여 검색·관리할 수 있도록 하는 **오픈소스 메타데이터 플랫폼(데이터 카탈로그)**이다.

공식 사이트는 스스로를 "data discovery, lineage, governance를 위한 통합 플랫폼"이라고 소개한다. 여러 DB, 웨어하우스, BI 도구,
파이프라인 등에 흩어진 "이 데이터가 뭔지"에 대한 정보(스키마, 소유자, 설명, 사용 이력, 품질 상태, 계보)를
한 곳에 모아 검색·문서화·관리할 수 있게 해준다.

## 왜 필요한가

데이터 환경이 복잡해질수록 데이터는 Database, Data Warehouse, Pipeline, Messaging, BI 등 다양한 시스템에 분산됩니다. 이로 인해 필요한 데이터가 어디에 있는지, 어떤 의미인지, 어디서 생성되었는지, 누가 관리하는지를 파악하기 어려워집니다.

OpenMetadata는 다양한 Connector를 통해 각 시스템의 메타데이터를 수집하고 이를 하나의 플랫폼에서 통합 관리합니다. 사용자는 이를 통해 데이터를 검색하고, 스키마와 설명을 확인하고, 데이터의 Lineage와 Owner, 품질 등의 정보를 파악할 수 있습니다.

즉 OpenMetadata의 목적은 단순히 메타데이터를 저장하는 것이 아니라, 조직의 데이터 자산을 쉽게 발견하고 이해하며 신뢰하고 관리할 수 있는 환경을 만드는 것입니다.

메타데이터 카탈로그가 없는 조직에서 실제로 반복되는 문제들:

- **"이 테이블이 뭐 하는 테이블이지?"** — 스키마만 봐서는 의미를 알 수 없고, 아는 사람에게 직접 물어봐야 한다.
- **"이 컬럼 값을 바꾸면 뭐가 깨지지?"** — 어떤 대시보드/파이프라인이 이 테이블을 참조하는지(리니지) 아무도 정확히 모른다.
- **"이 데이터 믿고 써도 되나?"** — 소유자(owner), 최신성, 품질 검증 여부가 문서화되어 있지 않다.
- **문서가 코드/스키마와 따로 논다** — 위키에 수동으로 작성한 문서는 스키마가 바뀌어도 갱신되지 않고 금방 낡는다.

OpenMetadata는 이 문제를 "**메타데이터를 소스에서 자동으로 긁어와서(ingestion)** 최신 상태로 유지"하는 방식으로 푼다.
사람이 수작업으로 문서를 관리하는 대신, 커넥터가 실제 DB/도구에 접속해 스키마·통계·사용 이력을 주기적으로 수집한다.

OpenMetadata는 각 시스템에서 메타데이터를 수집하고 이를 하나의 카탈로그에서 관리함으로써 이러한 파편화된 데이터 정보를 중앙화한다.

## 핵심 기능

| 기능 | 내용 |
|---|---|
| **Discovery(검색/탐색)** | 테이블·컬럼·대시보드·파이프라인 등을 이름/설명/태그로 검색 |
| **Lineage(리니지)** | 어떤 테이블이 어떤 파이프라인을 거쳐 어떤 대시보드까지 이어지는지 계보 추적 |
| **Governance(거버넌스)** | 오너십, 태그, 용어집(Glossary), 접근 정책(RBAC)으로 데이터 관리 체계 수립 |
| **Data Quality / Observability** | 완전성·정확성·적시성 등 기준으로 데이터 품질 테스트, 이상 감지 |
| **Ingestion Framework** | DB/웨어하우스/BI/파이프라인 등 130+ 커넥터로 메타데이터 자동 수집 |
| **Data Contracts** | 데이터 제공자와 소비자 간 스키마/품질 계약을 명시적으로 관리 |

## Connectors

OpenMetadata는 다양한 데이터 소스와 Connector를 통해 연동하여 각 시스템의 메타데이터를 수집할 수 있습니다.

```
┌────────────────────── Data Sources ──────────────────────┐
│    [Database/Pipeline/ML Model/Storage/Dashboard/etc..]  |     
|                                                          │
│  PostgreSQL     MySQL       Snowflake      BigQuery      │
│      │            │             │              │         │
│  MongoDB        Kafka         Airflow        dbt         │
│      │            │             │              │         │
│  S3 / Storage   Tableau      Power BI        MLflow      │
│      │            │             │              │         │
└──────┼────────────┼─────────────┼──────────────┼─────────┘
       │            │             │              │
       └────────────┴──────┬──────┴──────────────┘
                           │
                      OpenMetadata
                       Connectors
                           │
                           ▼
                  Metadata Ingestion
                           │
                           ▼
                 ┌──────────────────┐
                 │   OpenMetadata   │
                 │ Metadata Catalog │
                 └────────┬─────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
            Search      Lineage    Governance
```

우리 데모의 `docker-compose.yml`(공식 배포본)에서는 Ingestion Framework가 **Airflow 위에서 스케줄되는 파이프라인**으로
실행된다(`ingestion` 컨테이너, UI는 :8080). 즉 "커넥터를 한 번 실행"하는 게 아니라 "주기적으로 재수집하는 파이프라인을
UI에서 클릭만으로 예약"할 수 있다는 게 실제 프로덕션에서 중요한 지점이다.

## 어떻게 쓰는가 (일반적인 흐름)

PostgreSQL 등의 데이터 서비스를 OpenMetadata에 연결하고 Metadata Ingestion을 실행하여 테이블·컬럼 등의 기술 메타데이터를 자동 수집한다. 이후 사용자가 Description, Owner, Tag, Glossary 등의 정보를 보강하고 Lineage와 Data Quality 등을 활용하여 데이터 자산을 지속적으로 관리한다.

1. **서비스(Service) 등록** — Settings → Services → Databases에서 "이 DB에 접속하는 방법"(호스트, 포트, 인증정보)을 등록.
   커넥터 종류(Postgres, Snowflake, Looker, Airflow 등)에 따라 필요한 정보와 권한이 다르다.
2. **Ingestion Pipeline 생성 및 실행** — 등록한 서비스에 대해 "Metadata Ingestion" 파이프라인을 만들고 실행(또는 cron으로 스케줄).
   커넥터가 실제 소스에 접속해 스키마/테이블/컬럼을 긁어와 API로 전송한다.
3. **카탈로그에서 확인/보강** — UI에서 수집된 테이블을 검색하고, 설명·오너·태그·용어집 링크를 추가해 문서화한다.
4. **리니지/품질로 확장** — 파이프라인(Airflow, dbt 등)까지 연결하면 테이블 간 리니지가 자동으로 그려지고,
   Data Quality 테스트를 붙이면 품질 이상을 감지할 수 있다.

## 참고한 공식 문서

이 문서의 내용은 추측이 아니라 아래 공식 소스를 직접 확인해서 작성했다.

- [OpenMetadata 공식 홈페이지](https://open-metadata.org/) — 제품 포지셔닝("open context layer"), 핵심 가치 제안, 130+ 커넥터
- [Docs 최신 버전 인덱스](https://docs.open-metadata.org/latest) — "Unified platform for data discovery, lineage, and governance" 정의, 기능 목록(Discovery, Lineage, Governance, Data Quality, Data Contracts, Observability)
- [High Level Design](https://docs.open-metadata.org/latest/main-concepts/high-level-design) — 5개 핵심 컴포넌트(API, UI, Entity Store, Search Engine, Ingestion Framework)와 ingestion 데이터 흐름
- [Connectors 목록](https://docs.open-metadata.org/v1.13.x/connectors) — 10개 카테고리(Database, Dashboard, Pipeline, Messaging, ML Model, Storage 등), 130개 이상 커넥터 확인. 위 Connectors 다이어그램의 예시 도구들 출처
- 실행 절차·아키텍처 다이어그램의 세부 사항(버전 `1.13.3-release`, 기본 로그인 정보, Postgres 커넥터 필드 등)은
  기존에 작성된 [openmetadata-demo-design.md](openmetadata-demo-design.md)에서 검증해 둔 내용을 그대로 재사용했다
  (해당 문서의 "참고한 공식 문서" 섹션에 원 출처가 남아 있다).

