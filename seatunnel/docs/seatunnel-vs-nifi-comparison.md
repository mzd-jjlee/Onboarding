# SeaTunnel vs Apache NiFi — 냉정하게 비교하기

팀에 SeaTunnel을 소개하는 김에, 기존에 많이 쓰이는 **Apache NiFi와 뭐가 다른지**를 객관적으로 정리한 문서다.
"SeaTunnel이 더 좋다"는 결론을 미리 정해두고 근거를 끼워맞추는 게 아니라, 두 도구가 애초에 **다른 문제를
풀도록 설계됐다**는 걸 보이고, 그 위에서 우리 팀 상황(아래 참고)에는 어느 쪽이 맞는지 판단하는 게 목적이다.

> **우리 팀 상황 참고**: 현재 실습 중인 과제는 [seatunnel-db-to-parquet-guide.md](archive/seatunnel-db-to-parquet-guide.md)에
> 정리된 대로 **MySQL/Postgres → 로컬(추후 S3/MinIO 등 데이터레이크) Parquet 파일로 Batch + CDC 적재**다.
> 목적지가 고정되어 있고, 조건별로 다른 곳으로 라우팅할 필요는 없는 전형적인 "대용량 배치 이관" 시나리오다.

## 1. 데이터 처리 아키텍처

| | Apache NiFi | Apache SeaTunnel |
|---|---|---|
| 처리 단위 | **FlowFile** (payload 포인터 + 속성 메타데이터) | Row/Record (배치·스트림 레코드) |
| 흐름 형태 | 임의의 그래프 — Processor를 자유롭게 연결해 분기·병합·팬아웃 가능 | 대체로 선형 파이프라인 — `source → transform → sink` |
| 실행 엔진 | NiFi 자체 (단일 엔진) | **커넥터와 엔진이 분리** — 같은 커넥터가 Zeta(자체 경량 엔진)/Flink/Spark 위에서 모두 실행 가능 |
| 상태 저장 | FlowFile Repository(메타데이터, WAL) / Content Repository(payload, immutable copy-on-write) / Provenance Repository(전체 이력)의 **3중 저장소** | Chandy-Lamport 기반 분산 스냅샷(체크포인트) — 실패 시 마지막 체크포인트부터 재시작 |
| 설계 철학 | 데이터 한 건 한 건의 **이동 경로와 이력을 추적**하는 데 최적화 (라우팅·감사) | **대량 데이터를 정해진 목적지로 빠르고 일관되게 동기화**하는 데 최적화 (ETL/CDC) |

NiFi는 FlowFile 단위로 속성·계보(lineage)를 계속 들고 다니기 때문에 "이 레코드가 어디서 와서 어떤 경로로
갔는가"를 사후에 재구성할 수 있다. SeaTunnel은 그런 추적 체계 대신, **배치/스트리밍/CDC를 하나의 커넥터
프레임워크**로 묶어서 이기종 시스템 간 동기화 자체의 처리량과 일관성에 집중한다.

## 2. 개발 및 운영 생산성 (GitOps / GUI)

| | Apache NiFi | Apache SeaTunnel |
|---|---|---|
| 설계 방식 | 드래그앤드롭 **GUI** — 비개발자도 플로우 구성 가능 | **HOCON/JSON/SQL 텍스트 설정 파일**(`source`/`transform`/`sink` 블록) |
| 버전 관리 | 플로우는 내부적으로 XML/JSON 직렬화. 과거엔 별도 **NiFi Registry** 필요했으나, **NiFi 2.x부터 GitHub/GitLab/Bitbucket/Azure DevOps용 Git Flow Registry Client 네이티브 지원** | 설정 파일 자체가 곧 Git 리포지토리의 텍스트 파일 — 별도 export 과정 없이 바로 PR/코드리뷰 대상 |
| CI/CD | NiFi 2.x 기준 GitHub Actions로 PR에 플로우 버전 diff 코멘트를 남기는 사례 존재(NiPyAPI Actions 등) — **가능하지만 구성이 더 필요** | 텍스트 설정 파일이라 **lint/검증/배포 자동화가 자연스럽게 CI 파이프라인에 들어감** ("config as code") |
| 학습 곡선 | 낮음 — GUI로 바로 조립 가능 | 상대적으로 높음 — HOCON 문법과 커넥터 옵션을 알아야 함 |

정리하면 NiFi는 "GUI 우선 설계 + 최근 들어 Git 연동이 추가된" 형태이고, SeaTunnel은 "설정 파일(텍스트) 자체가
곧 코드인" 형태다. 팀이 비개발자와 함께 시각적으로 플로우를 조정해야 한다면 NiFi가, PR 기반 리뷰·자동배포
파이프라인을 우선한다면 SeaTunnel이 자연스럽게 맞는다.

## 3. 실무 권장 사용 사례

| 시나리오 | 권장 도구 | 이유 |
|---|---|---|
| DB → DW/데이터레이크(S3, MinIO, Parquet/Iceberg 등)로 대량 배치·증분 동기화 | **SeaTunnel** | 100개 이상 커넥터, 배치·스트리밍·CDC 통합 모델, 동기화 특화 성능, config-as-code |
| 복잡한 조건부 라우팅·다단계 변환이 필요하거나 규제·감사 요건(전수 계보 추적)이 있는 플로우 | **NiFi** | Provenance Repository, FlowFile 단위 성공/실패/재시도 경로 분기, 팬아웃(하나의 소스를 여러 목적지로 동시 전송) |
| IoT/엣지 수집, 프로토콜이 다양하고 비개발자가 직접 플로우를 조정해야 하는 환경 | **NiFi** | 드래그앤드롭 GUI, MiNiFi 엣지 에이전트 |
| 스케줄러(Airflow/DolphinScheduler)와 조합해 대규모 배치 ETL을 코드(PR) 기반으로 관리 | **SeaTunnel** | 텍스트 설정 파일이 스케줄러의 코드베이스에 자연스럽게 편입됨 |

### "복잡한 라우팅"이 구체적으로 뭘 뜻하는가

NiFi의 라우팅은 **Processor의 출력을 조건에 따라 여러 갈래로 분기**시키는 것을 말한다. 예:

```
GetFile → RouteOnAttribute
              ├─ (filename ends with .csv)  → CSV 파싱 → S3 적재
              ├─ (filename ends with .json) → JSON 파싱 → S3 적재
              └─ (unmatched)                → 격리 폴더 + 알림

PutS3Object ── success → 다음 처리 계속
           └── failure → 재시도 → 그래도 실패 시 DLQ + 알림

ConsumeKafka → [동시에] ├→ PutS3Object (원본 그대로 레이크 적재)
                         ├→ ConvertRecord → PutDatabaseRecord (실시간 대시보드용 DB)
                         └→ RouteOnContent (PII 포함?) → 마스킹 → 별도 감사 저장소
```

즉 하나의 소스에서 나온 데이터가 **내용/속성/처리 결과에 따라 완전히 다른 경로·다른 목적지**로 갈라질 수
있다는 뜻이다. SeaTunnel의 파이프라인은 대체로 목적지가 설정 시점에 고정되므로, 이런 동적 분기가 필요하면
잡을 여러 개로 나눠야 한다.

## 4. 우리 팀 상황에 대한 시사점

지금 진행 중인 실습([seatunnel-db-to-parquet-guide.md](archive/seatunnel-db-to-parquet-guide.md))은 목적지가
Parquet 파일 하나로 고정되어 있고 조건부 분기가 필요 없는 **전형적인 대량 배치 이관** 시나리오라서, 위 기준으로는
SeaTunnel이 맞는 선택이다.

다만 실습 중 발견한 실제 한계 하나는 짚어둘 필요가 있다. 같은 문서 2장에 정리했듯, **SeaTunnel의 Postgres
CDC → LocalFile(Parquet) sink 조합은 INSERT/UPDATE/DELETE 중 무엇이었는지 구분하는 `op` 컬럼을 남기지 않는다**
(`format = COMPATIBLE_DEBEZIUM_JSON` 옵션도 2.3.13에서는 `NullPointerException`으로 실패). 이건 정확히 위 1절에서
설명한 아키텍처 차이의 실제 사례다 — SeaTunnel은 "값을 목적지로 빠르게 동기화"하는 데 집중한 나머지, NiFi의
Provenance Repository 같은 "무슨 일이 있었는지"를 보존하는 장치가 file sink 단에는 약하다.

참고로 NiFi 쪽도 완전히 자유롭지는 않다 — **MySQL CDC는 `CaptureChangeMySQL`이라는 정식 프로세서로 안정적으로
지원**하지만, **PostgreSQL 논리 복제(logical replication) 기반 CDC 프로세서(`CaptureChangePostgreSQL`)는
2017년 JIRA([NIFI-4239](https://issues.apache.org/jira/browse/NIFI-4239))에 PR이 올라간 뒤로도 정식 병합
여부를 문서상 확인하지 못했다** — 즉 Postgres CDC가 필요하면 NiFi도 기본 제공 프로세서만으로는 부족해서
Debezium+Kafka 조합 같은 외부 도구를 얹는 경우가 많다는 뜻이다. 결론적으로 **"CDC의 변경 유형(op)을 끝까지
안전하게 보존하고 싶다"는 요구는 SeaTunnel/NiFi 어느 쪽도 기본 설정만으로는 완벽히 풀어주지 않는다** — 이 부분은
JDBC sink(양쪽 다 지원 양호)로 우회하거나, 별도 CDC 전용 파이프라인(Debezium 등)을 검토해야 할 수 있다.

## 참고한 자료

- [Apache SeaTunnel 공식 문서 — Architecture Overview](https://seatunnel.apache.org/docs/2.3.13/architecture/overview/)
- [SeaTunnel Engine (Zeta)](https://seatunnel.apache.org/docs/engines/zeta/about/)
- [Apache NiFi In Depth](https://nifi.apache.org/docs/nifi-docs/html/nifi-in-depth.html)
- [Apache NiFi FlowFile Architecture](https://www.dfmanager.com/blog/apache-nifi-flowfile-architecture)
- [Registry - Apache NiFi](https://nifi.apache.org/projects/registry/)
- [Continuous Integration for NiFi Flows in GitHub - Datavolo](https://datavolo.io/2024/11/nifi-flows-branching-and-pull-requests-in-github/)
- [DolphinScheduler and SeaTunnel VS. AirFlow and NiFi](https://hackernoon.com/dolphinscheduler-and-seatunnel-vs-airflow-and-nifi)
- [CaptureChangeMySQL — Apache NiFi](https://nifi.apache.org/components/org.apache.nifi.cdc.mysql.processors.CaptureChangeMySQL/)
- [NIFI-4239 — Implement a CaptureChangePostgreSQL processor (병합 여부 미확인)](https://issues.apache.org/jira/browse/NIFI-4239)
- [Working with S3 Compatible Data Stores via Apache NiFi (MinIO 연동)](https://community.cloudera.com/t5/Community-Articles/Working-with-S3-Compatible-Data-Stores-via-Apache-NiFi/ta-p/244584)
- 이 저장소 내부: [seatunnel-db-to-parquet-guide.md](archive/seatunnel-db-to-parquet-guide.md) — CDC → Parquet sink의 `op` 정보 손실 실측 결과
