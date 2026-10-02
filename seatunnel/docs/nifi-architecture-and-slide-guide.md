# NiFi 핵심 아키텍처와 SeaTunnel 비교 — 발표 수정 가이드

작성일: 2026-09-28

## 1. 문서 목적과 적용 범위

SeaTunnel 실습 발표의 NiFi 비교 부분을 수정할 때 참고하는 문서다. NiFi를 직접 실습한 결과가 아니라 공식 문서에 기반한 개념 설명이다. 두 도구의 성능 우열을 검증한 자료가 아니다.

기존 `seatunnel-vs-nifi-comparison.md`에는 과도한 일반화와 이전 CDC 실험에 따른 설명이 남아 있다. **NiFi 아키텍처 및 아래 정정 항목은 이 문서를 우선 적용한다.** PPT 페이지 번호는 편집하면서 달라질 수 있으므로 NiFi 비교 슬라이드의 제목과 내용으로 대상을 찾는다.

## 2. 발표에서 전달할 핵심

> SeaTunnel은 Source–Transform–Sink 설정을 중심으로 배치·CDC 데이터 통합 작업을 구성한다. NiFi는 처리 단계와 대기열을 연결하고, 분기·오류 대응·처리 이력을 포함한 데이터 흐름을 시각적으로 구성하고 운영하는 데 강점이 있다.

NiFi를 단순히 “GUI가 있는 ETL 도구”로만 설명하면 핵심이 빠진다. **처리 단계 사이에서 기다리는 데이터와 처리 상태까지 관리한다는 점**을 강조한다.

두 도구 모두 데이터 수집·변환·적재를 수행할 수 있다. “SeaTunnel은 대용량 배치만, NiFi는 작은 실시간 데이터만”이라는 구분은 틀리다. 이번 SeaTunnel 실습도 배치와 CDC 스트리밍을 모두 포함한다.

## 3. NiFi를 구성하는 핵심 요소

NiFi는 Flow-Based Programming, 즉 처리 부품을 연결해 데이터가 흐르도록 하는 구조를 기반으로 한다.

| 요소 | 쉬운 설명 | 예시 |
|---|---|---|
| FlowFile | 처리하는 데이터 묶음과 속성 정보. 내용은 저장소의 데이터를 참조하며, 반드시 한 행을 의미하지 않는다. | CSV 파일 내용과 파일명·출처 |
| Processor | 수집·검증·변환·전송 등 실제 일을 수행하는 부품 | GetFile, ValidateRecord, PutS3Object |
| Relationship | Processor가 정의한 처리 결과 경로 | valid, invalid, failure, success 등. 종류는 Processor마다 다름 |
| Connection / Queue | Processor 사이를 연결하며 데이터를 대기시키는 공간 | S3 전송을 기다리는 FlowFile |
| Flow Controller | Processor의 실행 일정과 실행 스레드를 관리하는 엔진 | 각 처리 단계의 실행 관리 |
| Process Group | 관련 Processor와 연결을 묶는 단위 | 파일 수집·검증 흐름 묶음 |

**화면의 화살표는 단순 연결선이 아니라 대기열을 가진 연결이다.** 이것이 GUI 모양보다 중요한 아키텍처적 특징이다.

출처: [NiFi 공식 개념 및 아키텍처](https://nifi.apache.org/docs/nifi-docs/html/overview.html)

## 4. 검증·분기 예시를 어떻게 설명할 것인가

```text
GetFile → [대기열] → ValidateRecord
                        ├─ valid   → [대기열] → PutS3Object
                        ├─ invalid → [대기열] → PutFile → 알림 처리
                        └─ failure → [대기열] → 읽기·처리 실패 대응
```

이 그림은 개념 예시이며 배포 가능한 완성 설정이 아니다. 인증, 스키마, 파일 경로, 재시도 및 알림 메시지 구성 등이 추가로 필요하다.

- `valid`: 스키마 검증에 맞는 레코드.
- `invalid`: 스키마 검증에 맞지 않는 레코드.
- `failure`: 입력 파싱 실패 등 검증 처리 자체를 수행하지 못한 경우.
- 격리 성공 후 알림을 보내려면 PutFile의 성공 경로 뒤에 알림 처리를 연결한다. 격리와 알림을 별도 분기로 보내면 두 작업의 성공이 하나로 보장되지는 않는다.

**핵심 기능:** Processor의 결과 경로를 대기열로 연결하고 필요한 처리 부품을 조합하는 능력.

**사용자가 설계한 사례:** 검증 실패 데이터를 격리하고 Slack에 알림을 보내는 흐름.

“아무 결과로든 자동 분기한다”보다는 “Processor가 제공하는 결과 경로를 연결하거나 조건 분기 Processor를 추가한다”라고 설명한다.

권장 캡션:

> 처리 결과에 따라 정상 적재·오류 격리·알림 경로를 구성하는 예시

출처: [ValidateRecord](https://nifi.apache.org/components/org.apache.nifi.processors.standard.ValidateRecord/)

## 5. 데이터 흐름을 운영한다는 의미

### 백프레셔: 뒤가 밀리면 앞의 처리를 제한

S3 저장이 느려지면 앞 대기열에 데이터가 쌓인다. 대기열의 FlowFile 건수 또는 용량이 설정 기준에 도달하면 상류 Processor의 실행을 제한한다.

외부 API나 장비에 무조건 “천천히 보내라”는 신호를 보내는 기능은 아니다. 외부 송신자까지 제어할 수 있는지는 프로토콜과 수집 방식에 달려 있다.

### 오류 처리: 실패 경로도 명시적으로 설계

실패 데이터를 별도 보관하거나 재시도하도록 연결할 수 있다. 다만 모든 Processor가 잘못된 한 행만 자동으로 격리하는 것은 아니다. 예를 들어 ConvertRecord는 읽기·변환 실패 시 원본 FlowFile을 failure 경로로 보낼 수 있다. 하나의 FlowFile에 여러 레코드가 있다면 실패 영향도 그 묶음에 미칠 수 있다.

### Provenance: 데이터 묶음의 처리 이력

수신·변환·분기·전송 이력을 조회해 문제 발생 지점을 확인한다. 모든 행·컬럼의 변경을 무기한 추적한다는 뜻은 아니다. 이력 보존 설정과 내용 보존 여부에 따라 조회·내용 확인·재처리 가능 범위가 달라진다. 데이터 정합성 검증을 자동으로 대신하지도 않는다.

출처:
- [NiFi 사용자 가이드 — 대기열, 백프레셔, Provenance](https://nifi.apache.org/nifi-docs/user-guide.html)
- [ConvertRecord — 실패 처리](https://nifi.apache.org/components/org.apache.nifi.processors.standard.ConvertRecord/)

## 6. GUI 뒤의 저장 구조

일반적인 상태 저장 방식의 NiFi 실행 구조에서 역할을 구분하면 다음과 같다. Stateless 실행 방식까지 모두 동일하게 설명하지 않는다.

| 저장소 | 역할 |
|---|---|
| Content Repository | 실제 데이터 내용 보관 |
| FlowFile Repository | 처리 중인 FlowFile의 상태·메타데이터 보관 |
| Provenance Repository | 수신·변환·전송 등 처리 이력 보관 |

이는 데이터 대기, 복구, 이력 조회의 기반이다. “같은 데이터를 세 벌 복제한다”는 뜻은 아니다. 복구는 저장소 보존과 설정이 전제이며, 외부 저장소까지 자동으로 중복 없는 처리를 보장한다는 의미도 아니다.

출처: [NiFi Architecture](https://nifi.apache.org/docs/nifi-docs/html/overview.html#nifi-architecture)

## 7. SeaTunnel과 비교할 때 쓸 표

| 관점 | SeaTunnel | NiFi |
|---|---|---|
| 구성의 중심 | Source–Transform–Sink 기반 데이터 통합 잡 | Processor와 대기열로 연결한 데이터 흐름 |
| 사용자 관점의 질문 | 데이터를 어떻게 읽고 변환해 목적지에 적재할까? | 어느 단계에 데이터가 있고, 실패하거나 밀리면 어떻게 처리할까? |
| 이번 발표의 예시 | PostgreSQL → Parquet 배치·CDC 적재 | 파일 수집 → 검증 → 정상 적재 / 오류 격리 → 알림 |
| 강조할 운영 방식 | 이번 실습에서는 설정 파일로 잡 구성 | GUI에서 단계별 흐름·대기열·처리 이력 확인 |

이 표는 기능 유무나 성능 순위가 아니라 **구성·운영 관점의 차이**를 설명한다. SeaTunnel에도 흐름 제어와 장애 복구가 있고, NiFi도 DB에서 데이터 레이크로 적재할 수 있다.

## 8. 기존 발표·비교 문서에서 수정할 표현

| 피할 표현 | 수정 방향 |
|---|---|
| NiFi는 GUI 기반이라 누구나 쉽게 설정 | 시각적으로 구성할 수 있지만 스키마·인증·실패 처리 등 설계 지식은 필요 |
| SeaTunnel은 선형만 가능, 분기는 잡을 나눠야 함 | Source–Transform–Sink 구성이 중심. 다중 입력·출력 연결도 가능하므로 절대적 제약으로 표현하지 않음 |
| SeaTunnel의 같은 커넥터가 모든 엔진에서 실행 | 엔진별 커넥터 지원 여부 확인 필요. 이번 PostgreSQL CDC는 Spark 지원 대상이 아님 |
| NiFi는 모든 데이터의 완벽한 계보를 보존 | FlowFile 단위 처리 이력이며 보존 설정과 범위에 제약 |
| NiFi는 오류 한 건만 격리, SeaTunnel은 전체 실패 | 오류 분리 단위와 동작은 Processor·커넥터·설정에 따라 달라짐 |
| SeaTunnel은 NiFi보다 빠르고 일관성이 높음 | 동일 조건 비교 실험 없이 성능·정합성 우위 주장 금지 |
| SeaTunnel은 GUI가 없음 | 이번 실습은 설정 파일 방식. 별도 SeaTunnel Web 프로젝트도 존재 |
| SeaTunnel CDC → Parquet은 변경 유형 보존 불가 | 이번 실습에서 RowKindExtractor로 cdc_op 컬럼을 추출해 보존함 |
| DELETE가 없으므로 CDC 커넥터의 한계 | 이번 설정의 SQL 필터가 INSERT·UPDATE_AFTER만 통과시켰기 때문 |

CDC 이벤트 종류를 컬럼으로 보존하는 것과 NiFi Provenance는 서로 다른 개념이다. 또한 Parquet에 변경 이벤트를 저장하는 것과 원본 DB의 최신 상태를 재현하는 것도 구분한다.

참고:
- [SeaTunnel RowKindExtractor 2.3.13](https://seatunnel.apache.org/docs/2.3.13/transforms/rowkind-extractor/)
- [SeaTunnel PostgreSQL CDC 2.3.13](https://seatunnel.apache.org/docs/2.3.13/connectors/source/PostgreSQL-CDC/)
- [SeaTunnel Transform 연결 옵션](https://seatunnel.apache.org/docs/2.3.13/transforms/common-options/)
- [SeaTunnel Web](https://github.com/apache/seatunnel-web)
- [이번 CDC 실습 기록](cdc_seatunnel.md)

## 9. 슬라이드 구성 권장안

### 비교 슬라이드 A: NiFi는 데이터 흐름을 어떻게 관리하는가

- 중앙: GetFile → 대기열 → ValidateRecord → 정상 적재 / 오류 격리·알림 예시.
- 연결선에 대기열이 있음을 표시.
- 하단 핵심 3가지: 처리 결과별 분기 / 대기열·백프레셔 / 처리 이력 조회.
- 저장소 3종은 발표 노트에 넣어 화면 과밀을 피한다.

발표 노트:

> NiFi의 특징은 화면에서 화살표를 그리는 것만이 아닙니다. 각 처리 단계 사이에 데이터가 기다리는 대기열이 있고, 뒤 단계가 느리면 앞의 처리를 제한할 수 있습니다. 실패 데이터는 별도 경로로 보내도록 설계하고, 처리 이력을 통해 어디서 문제가 생겼는지도 확인합니다. 격리 후 Slack 알림은 이런 기능을 조합한 예시입니다.

### 비교 슬라이드 B: 이번 실습에서 SeaTunnel을 사용한 이유

- PostgreSQL에서 Parquet으로 배치·CDC 적재하는 요구를 설정 파일로 구성했다.
- NiFi는 여러 수집 경로와 단계별 분기·오류 대응·이력 확인이 중요한 경우 검토할 수 있다.
- 두 도구는 사용 범위가 겹친다. 선택은 데이터 크기 하나가 아니라 필요한 운영 방식과 지원 커넥터 등을 기준으로 판단한다.

발표 노트:

> 이번에는 DB 데이터를 Parquet으로 적재하는 것이 중심이어서 SeaTunnel의 Source–Transform–Sink 구조로 구현했습니다. NiFi와의 차이는 단순히 데이터가 크냐 작냐가 아닙니다. 다양한 경로를 연결하고, 단계 사이의 대기와 실패 데이터를 세밀하게 운영해야 하는지도 중요한 선택 기준입니다.

## 10. Claude에게 전달할 수정 요청

> 이 문서를 기준으로 발표의 NiFi·SeaTunnel 비교 슬라이드를 수정해줘. NiFi의 핵심을 단순한 GUI나 분기 기능으로만 설명하지 말고 Processor–Queue 구조, 백프레셔, 오류 경로, Provenance를 짧게 설명해줘. GetFile–ValidateRecord–정상 적재/오류 격리·알림은 기능 조합 예시로 표시해줘. SeaTunnel과는 구성·운영 관점을 비교하고, 성능 우위나 기능 부재를 단정하지 말아줘. 기존 비교 문서와 충돌하는 표현은 이 문서의 정정 내용을 우선해줘. CDC 변경 유형 보존 불가 설명은 삭제하고 실제 RowKindExtractor 실습 결과를 반영해줘. 상세 내부 저장 구조와 주의점은 발표 노트에 넣고, 본문은 처음 보는 청중도 이해할 수 있게 간결하게 작성해줘.
