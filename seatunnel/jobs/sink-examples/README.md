# 시스템별 config 예시

현재 실행용 설정은 jobs/README.md의 네 가지 데모를 참고한다.
이 `examples/` 폴더는 성격이 다르다 — **공식 문서를 기반으로 작성한 템플릿**이고, 실제로 그 스토리지
(S3/MinIO/HDFS/Kafka)를 이 환경에 띄워서 실행 검증까지 한 건 아니다. 실제로 쓰려면:

1. `<...>` 표시된 부분을 실제 값(주소, 버킷명, 키 등)으로 채우고
2. `docker run` 시 해당 스토리지가 붙어있는 네트워크에 SeaTunnel 컨테이너를 같이 연결(`--network`)해야 한다
3. 처음 실행할 땐 반드시 [seatunnel-tutorial.md](../../docs/archive/seatunnel-tutorial.md)의 opengauss 우회를 그대로 적용하고, 결과를 직접 확인해볼 것

| 파일 | 소스/싱크 | 참고 문서 |
|---|---|---|
| `s3_sink.conf` | AWS S3 | [S3File Sink](https://seatunnel.apache.org/docs/2.3.12/connector-v2/sink/S3File) |
| `minio_sink.conf` | MinIO (S3 호환) | 위 문서 + endpoint만 커스터마이징 |
| `hdfs_sink.conf` | HDFS | [HdfsFile Sink](https://seatunnel.apache.org/docs/2.3.12/connector-v2/sink/HdfsFile) |
| `kafka_sink.conf` | Kafka | [Kafka Sink](https://seatunnel.apache.org/docs/2.3.12/connector-v2/sink/Kafka) |

공통적으로 `source`는 우리가 이미 검증한 `jobs/01_postgres_to_parquet.conf`의 `Jdbc` source를 그대로 재사용한다고
가정하고, **`sink` 블록만** 예시로 보여준다 (source는 이미 실전 검증된 걸 쓰는 게 안전하니까).
