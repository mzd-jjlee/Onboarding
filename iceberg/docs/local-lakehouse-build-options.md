# 로컬 레이크하우스 구축 선택지: Trino·Superset 전환

개정일: 2026-10-06. [전체 구축 안내서](local-lakehouse-superset.md)를 먼저 읽는다.
A안은 Trino 483으로 구현·조회 검증 완료했다. [실행 안내](trino-local-query.md)를 우선한다. B안의 S3 설정은 통합 실행 검증 전 설계 예시다.

## 1. 고정할 것과 선택할 것

SeaTunnel Iceberg sink, Iceberg 테이블, Hive Metastore는 유지한다. 웹 조회는 Superset, SQL 엔진은 Trino로 정한다. Hive REST Catalog, PyIceberg `add_files()`, DuckLake는 이번 구축의 필수 단계가 아니다.

| 선택지 | 저장소 | 장점 | 추가 검증/준비 | 선택 기준 |
|---|---|---|---|---|
| A. 기존 공유 디렉터리 | 호스트 `./lake` | 기존 파일·스냅샷 재사용, 서비스 추가 최소화 | Trino의 기존 `file:` URI 지원, 모든 노드의 `/lake` 마운트 | 먼저 작은 조회 시험 |
| B. 로컬 S3 호환 저장소 | 로컬 객체 저장소 볼륨 | writer/reader가 공통 `s3://` URI 사용 | 저장소 서비스, bucket, S3FileIO 의존성, 새 적재 | A가 맞지 않거나 향후 다중 노드 구성을 고려할 때 |

B도 로컬 구축이다. MinIO 등 호환 저장소의 버전/이미지 배포 방식은 구현 시 확정하고 고정한다. S3 저장소가 HMS를 대체하지는 않는다. **HMS는 카탈로그, S3는 파일 저장소**다.

## 2. A안: 기존 writer 설정 유지

[현재 SeaTunnel job](../jobs/01_orders_to_iceberg.conf)은 이미 다음 구성을 사용한다.

```hocon
sink {
  Iceberg {
    catalog_name = "local_hive"
    iceberg.catalog.config = {
      type = "hive"
      uri = "thrift://hms:9083"
      warehouse = "file:///lake/warehouse"
    }
    namespace = "retail"
    table = "orders"
    iceberg.table.write-props = {
      write.format.default = "parquet"
    }
    schema_save_mode = "CREATE_SCHEMA_WHEN_NOT_EXIST"
    data_save_mode = "APPEND_DATA"
  }
}
```

기존 namespace 준비 스크립트는 `retail`의 location을 `file:///lake/warehouse/retail.db`로 지정한다. SeaTunnel이 테이블을 생성하고 데이터를 쓴다. 기존 두 배치 실행을 완료했다면 재적재 없이 조회 계층만 추가한다.

Trino 로컬 FS 설정과 `file:` URI 호환성 확인 절차는 [전체 안내서 4절](local-lakehouse-superset.md#4-먼저-결정할-것-기존-로컬-파일을-그대로-읽을-수-있는가)을 따른다. Trino 483에서도 현재 5건과 과거 스냅샷 조회에 성공했다.

## 3. B안: 로컬 S3 호환 저장소 구성

예시 이름은 저장소 서비스 `minio`, API `http://minio:9000`, bucket `lakehouse`, namespace `retail_s3`다. 모든 클라이언트가 같은 Docker 네트워크에서 해당 endpoint에 접근해야 한다.

1. 저장소 서버에 영속 볼륨을 연결하고 서비스 준비 상태를 확인한다.
2. 관리 도구로 `lakehouse` bucket을 먼저 생성하고 읽기/쓰기 가능한 실습 계정을 준비한다. bucket 생성은 Iceberg namespace 생성과 다르다.
3. HMS에 **새 namespace `retail_s3`**를 만들고 location을 `s3://lakehouse/warehouse/retail_s3.db`로 지정한다. 기존 `retail`은 수정하지 않는다.
4. SeaTunnel의 S3FileIO 및 AWS SDK 의존성을 준비하고 새 job으로 원본 5건을 한 번 적재한다.
5. Trino에서 `iceberg.retail_s3.orders`를 읽은 뒤 Superset을 연결한다.

namespace는 예를 들어 기존 `prepare_catalog.py`와 같은 HiveCatalog의 `create_namespace_if_not_exists` API로 만들 수 있다. 새 스크립트로 분리하고, 이미 namespace가 있다면 location도 조회해서 맞는지 확인한다. HMS가 생성 작업에서 S3 경로를 실제로 접근하려 한다면 HMS 측 파일시스템 설정/의존성도 준비해야 한다.

### SeaTunnel Iceberg sink 설정 예시

```hocon
# 새 job의 sink 예시. source는 기존 JDBC source를 사용하되,
# 최초 5건 검증 시 batch_id 조건 없이 네 컬럼을 읽는다.
sink {
  Iceberg {
    catalog_name = "local_hive_s3"
    iceberg.catalog.config = {
      type = "hive"
      uri = "thrift://hms:9083"
      warehouse = "s3://lakehouse/warehouse"
      io-impl = "org.apache.iceberg.aws.s3.S3FileIO"
      s3.endpoint = "http://minio:9000"
      s3.path-style-access = "true"
      s3.access-key-id = "<LOCAL_S3_ACCESS_KEY>"
      s3.secret-access-key = "<LOCAL_S3_SECRET_KEY>"
      client.region = "us-east-1"
    }
    namespace = "retail_s3"
    table = "orders"
    iceberg.table.write-props = {
      write.format.default = "parquet"
    }
    schema_save_mode = "CREATE_SCHEMA_WHEN_NOT_EXIST"
    data_save_mode = "APPEND_DATA"
  }
}
```

`<...>`는 실제 설정을 주입하기 전의 자리표시자다. 커밋할 문서/job에 실제 키를 넣지 않는다. 원본 쿼리는 `select order_id, customer_name, amount, status from orders`다. 최초 적재가 성공했다면 반복 실행하지 않는다.

이 설정은 SeaTunnel의 catalog 속성 전달과 Iceberg S3FileIO 구성을 조합한 설계다. **현재 이미지에 필요한 S3 JAR가 모두 있다는 뜻은 아니다.** 기존 실행 기록의 Iceberg 버전은 1.6.1이다. 그 버전과 맞는 Iceberg AWS/S3FileIO 및 AWS SDK 의존성을 선택하고 SeaTunnel Zeta 커넥터의 클래스 로딩 경로에서 검증한다. Flink용 JAR 설치 지침을 Zeta에 그대로 적용하지 않는다. [SeaTunnel sink](https://seatunnel.apache.org/docs/2.3.13/connectors/sink/Iceberg/), [Iceberg 1.6.1 AWS/S3FileIO](https://iceberg.apache.org/docs/1.6.1/aws/)

### Trino의 같은 저장소 연결

다음은 Trino 483 공식 문서 기준 속성명이다. 다른 버전이면 해당 버전 문서를 확인한다.

```properties
# /etc/trino/catalog/iceberg.properties
connector.name=iceberg
iceberg.catalog.type=hive_metastore
hive.metastore.uri=thrift://hms:9083
iceberg.security=READ_ONLY
fs.s3.enabled=true
s3.endpoint=http://minio:9000
s3.region=us-east-1
s3.path-style-access=true
s3.aws-access-key=${ENV:LAKEHOUSE_S3_ACCESS_KEY}
s3.aws-secret-key=${ENV:LAKEHOUSE_S3_SECRET_KEY}
```

Trino 컨테이너에 위 환경변수를 전달한다. SeaTunnel의 `s3.access-key-id`와 Trino의 `s3.aws-access-key`처럼 같은 목적의 설정도 이름이 다르다. Trino는 저장소에서 직접 파일을 읽으므로 자체 자격증명이 필요하다. Superset은 Trino에 연결하므로 레이크 마운트나 S3 키가 필요 없다. [Trino S3 설정](https://trino.io/docs/current/object-storage/file-system-s3.html)

### 데이터 전환 시 지킬 경계

새 warehouse 설정은 기존 파일을 자동 복사하지 않고, 기존 metadata 내부 URI도 바꾸지 않는다. 새 테이블을 만들고 원본에서 재적재하는 방식은 현재 행을 재현하지만 원래 snapshot ID와 과거 이력을 보존하지 않는다. 원본 5건을 한 번에 적재했다면 새 테이블의 데이터 스냅샷 수가 기존 두 배치의 2개와 달라도 정상이다.

## 4. 구현 시 추가할 파일 목록

아래 목록 중 Trino Compose·catalog·서버 설정은 구현 완료했다. Superset도 구현 완료했다 ([실행 안내](superset-local-ui.md)). B안 S3 관련 파일은 후속 제안이다.

| 제안 파일/구성 | 목적 |
|---|---|
| `compose.analytics.yaml` | Trino, Superset, Superset DB를 기존 네트워크에 추가 |
| `config/trino/catalog/iceberg.properties` | HMS와 선택한 저장소 연결 |
| Trino 서버 설정 | 단일 coordinator/worker 구성, 메모리·HTTP 포트 |
| `config/Dockerfile.superset` | 선택한 Superset 버전 + Trino/PostgreSQL 드라이버 |
| `config/superset_config.py` | Superset 전용 메타데이터 DB와 SECRET_KEY |
| Superset 초기화 절차 | DB 마이그레이션, 관리자, 권한 초기화 |
| S3 서버·bucket 초기화 및 SeaTunnel 파생 이미지(B안) | 저장소와 writer 의존성 준비 |
| S3 전용 namespace 준비·적재 job(B안) | 기존 테이블을 보존하며 새 테이블 적재 |

실제 구현 후에는 고정한 이미지/패키지 버전, startup 명령, Trino 결과, Superset 화면 및 재시작 결과를 별도 실행 기록으로 남긴다.
