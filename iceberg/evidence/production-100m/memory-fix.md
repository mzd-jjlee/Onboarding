# Writer 수정 후 관찰

2026-10-08 최종 시도: SeaTunnel 2.3.13, 실제 -Xmx3g, 4GiB 컨테이너 제한.
Docker stats 표본: CPU 418.08%, RSS 약 941.8MiB.
GC.class_histogram 표본: byte[] 37,774,360 bytes, char[] 9,169,056 bytes.
첫 시도의 약 650만 StructLikeWrapper/PathOffset 누적과 달리 수정 후 상위 점유에서 사라짐.
이 histogram은 진단 중 강제 GC를 수반하므로 이후 Full GC 1회는 수동 진단 영향이 포함될 수 있음.
Parquet 파일이 실제로 생성되기 시작했음.
이는 시간별 최대 RSS 또는 성능 벤치마크가 아니라 실행 중 단일 표본이다.
