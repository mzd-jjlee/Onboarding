# Java 실행 구조와 JVM 힙: SeaTunnel OOM 이해하기

2026-09-17. SeaTunnel 발표의 OOM 원인 설명에 사용할 배경 자료.

**Java 실행 시 JVM의 초기 힙과 최대 힙을 설정할 수 있다. Linux VM에 메모리가 남아 있어도 JVM의 최대 힙에 도달하면 Java heap OOM이 발생할 수 있다.** 이번 SeaTunnel Local 실험의 512MiB는 Docker의 고정 제한이 아니라 실행 JVM의 최대 힙 설정이었다.

## 1. Java 소스와 JAR는 어떻게 실행되는가?

일반적인 Java 애플리케이션의 빌드와 실행 흐름은 다음과 같다.

```text
Java 소스 파일(.java)
    │ javac로 컴파일: 보통 빌드 시 수행
    ▼
바이트코드(.class)
    │ 클래스와 리소스를 패키징
    ▼
JAR 파일
    │ java 명령으로 JVM 시작 → 필요한 클래스 로드
    ▼
JVM에서 바이트코드 실행
    └─ JIT 컴파일러가 자주 실행되는 코드를 기계어로 변환
```

JAR는 클래스와 리소스를 묶는 파일 형식이다. SeaTunnel을 실행할 때 JAR 안의 Java 소스 전체를 다시 컴파일하는 것이 아니라, 이미 빌드된 바이트코드를 로드해 실행한다. 실행 중 JIT 컴파일은 소스를 `.class`로 만드는 빌드 단계와 다르다. 일부 JDK의 소스 파일 직접 실행 기능은 여기서 설명하는 일반적인 JAR 실행 흐름과 별개다.

보통 `java` 명령으로 시작한 Java 프로세스 하나에 JVM 하나가 구동된다. 그 JVM에 SeaTunnel 엔진과 JDBC·Parquet 관련 여러 JAR의 클래스가 로드된다. JAR마다 별도의 JVM이 생기지는 않는다. JVM은 Java 실행 환경이며, Docker가 사용하는 Linux VM처럼 운영체제를 실행하는 가상 머신과는 역할이 다르다.

## 2. JVM은 힙 메모리를 사용하는가?

JVM은 객체와 배열 등을 저장하는 Java 힙을 사용한다. SeaTunnel에서는 읽어 온 행 객체, 작업 사이의 큐, Parquet Writer의 버퍼와 바이트 배열 등이 힙을 사용한다.

GC(Garbage Collection)는 더 이상 도달할 수 없는 객체의 메모리를 회수한다. Writer나 큐가 계속 참조하는 객체는 작업에 필요한 것으로 남기 때문에 GC가 임의로 제거할 수 없다.

```text
Linux VM의 메모리
└─ Docker 컨테이너
   └─ Java 프로세스 / JVM
      ├─ Java 힙: 행 객체, 큐, Writer 버퍼 등
      └─ 힙 외 메모리: 스레드 스택, Metaspace, 네이티브 버퍼 등
```

힙도 결국 Linux VM의 메모리를 사용한다. 다만 JVM 자체의 힙 상한이 별도로 존재한다. 힙은 Java 프로세스 전체 메모리와 같지 않으며, 모든 버퍼가 반드시 힙에 할당되는 것도 아니다.

## 3. 초기 힙과 최대 힙은 실행할 때 설정한다

일반적인 실행 예시는 다음과 같다. `app.jar`는 설명용 실행 가능 JAR 이름이다.

```bash
java -Xms1g -Xmx3g -jar app.jar
```

| 옵션 | 의미 |
|---|---|
| `-Xms1g` | 초기 힙 크기 1GiB |
| `-Xmx3g` | 최대 힙 크기 3GiB |

힙은 필요에 따라 최대 크기까지 늘어날 수 있다. `-Xmx3g`는 시작 즉시 물리 메모리 3GiB를 모두 사용하는 의미도, JVM 전체 사용량을 3GiB로 제한하는 의미도 아니다. 옵션을 생략했을 때의 기본값은 JDK와 실행 환경에 따라 결정되므로, Java의 최대 힙이 항상 512MiB인 것은 아니다.

JVM 옵션에서 `512m`는 512MiB, `3g`는 3GiB다. 발표에서는 편의상 512MB·3GB라고 말할 수 있지만 정확한 단위는 구분한다. 옵션 정의는 [Oracle의 java 명령 문서](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)를 참고한다.

## 4. JVM 힙 제한과 Docker 메모리 제한은 다르다

| 구분 | 제한 대상 | 부족할 때의 대표적인 현상 |
|---|---|---|
| JVM `-Xmx` | 해당 JVM의 Java 힙 | `OutOfMemoryError: Java heap space` |
| Docker 컨테이너 메모리 제한 | 힙을 포함한 컨테이너의 메모리 사용량 | 커널이 컨테이너 내 프로세스를 OOM kill할 수 있음 |
| Linux VM 메모리 | 여러 컨테이너, OS 등이 공유하는 메모리 | VM 전체 메모리 압박 및 OOM kill 가능 |

예를 들어 컨테이너에 4GiB까지 허용해도 JVM이 `-Xmx512m`로 실행되면 Java 힙은 최대 512MiB다. 컨테이너의 여유 메모리를 힙이 자동으로 초과 사용하지 않는다.

반대로 `-Xmx3g`로 설정했다면 컨테이너에는 힙 외 메모리를 위한 여유도 필요하다. 필요한 여유는 스레드 수, 커넥터, 네이티브 라이브러리 등에 따라 달라진다. Docker 상한만 늘려도 명시된 `-Xmx512m`는 그대로이며, 힙만 늘려도 컨테이너나 Linux VM의 메모리가 자동으로 늘어나지는 않는다.

`Java heap space`와 OS OOM kill은 로그를 구분해서 확인한다. 종료 코드 137만으로 OS OOM kill이라고 단정할 수 없다. 이번 실험에서는 Java OOM 후 수동으로 컨테이너를 종료했으며, 기록상 `OOMKilled=false`였다. Java OOM이 발생했다고 JVM 프로세스 전체가 반드시 즉시 종료되는 것도 아니다.

## 5. DB에서 나눠 읽었는데 왜 Parquet 저장 중 OOM이 발생했는가?

파티셔닝은 읽을 범위를 나누고, JDBC fetch는 데이터를 나눠 가져오도록 한다. 이 설정만으로 Sink가 사용하는 메모리까지 일정하게 제한되지는 않는다.

```text
DB를 나눠 읽기
    → 행 객체와 큐 사용
    → Parquet Writer가 데이터 인코딩·압축 버퍼 사용
    → 이전 Writer와 버퍼가 계속 참조되면 힙에 남음
    → GC로 회수할 수 있는 공간이 부족해짐
    → 새 객체 할당 실패: Java heap space
```

같은 JVM에서 실행하는 병렬 작업은 하나의 힙을 공유한다. `parallelism=8`이라고 512MiB 힙이 8개 생기지 않는다. 동시에 동작하는 Writer와 버퍼가 많아지면 한 JVM이 부담하는 메모리도 커질 수 있다.

프로젝트의 SeaTunnel 2.3.13 / Zeta / JDBC → LocalFile Parquet 실험 기록에서는 다음을 확인했다.

- 병렬도 8, 파티션 수 8, `fetch_size=5000` 조건에서 최대 힙 512MiB 실행은 Java heap OOM이 발생했다.
- 힙 덤프에는 Parquet Writer 46개가 남아 있었다. Writer 쪽 경로로 도달 가능한 고유 바이트 배열의 데이터 길이 합은 약 369.7MiB였다. 객체 헤더를 제외한 값이며 독점 보유 메모리 크기를 계산한 값은 아니다.
- 이번 구성에서는 파일 전환 후에도 이전 Writer가 맵에 남고, 커밋 준비 시 Writer들을 닫는 경로였다. 주기적 체크포인트가 꺼져 있어 여러 Writer의 버퍼가 남아 힙 여유를 소진했다.
- 같은 병렬도·파티션 조건의 최대 힙 3GiB 실행은 2억 행 처리와 커밋에 성공했다. 초기 힙도 256MiB에서 1GiB로 바뀌었으므로 최대 힙만 바꾼 엄밀한 단일 변수 실험은 아니다.

따라서 이번 재현 실험은 “DB 전체 데이터를 한 번에 올려서 실패했다”거나 “클러스터가 반드시 필요했다”는 근거가 아니다. Local에서도 더 큰 힙을 적용한 조건에서 성공했다. 이 결과가 더 큰 모든 작업의 성공을 보장하지는 않으며, Writer 보유 동작은 다른 버전·파일 형식·설정에 그대로 일반화하지 않는다.

실험 조건, 오류 스택, 힙 분석과 증거 경로는 [Local 힙·OOM 검증 문서](local-heap-oom-study.md)에 정리되어 있다. 여기서는 해당 기록을 인용하며 새 실험을 수행한 것은 아니다.

## 6. 현재 프로젝트에서 설정할 위치

| 실행 대상 | JVM 옵션 파일 | 현재 구성의 의미 |
|---|---|---|
| Local 실행 (`seatunnel.sh -m local`) | 컨테이너의 `/opt/seatunnel/config/jvm_client_options` | 현재 래퍼는 이미지 기본 최대 힙 512MiB 사용 |
| Zeta 클러스터 서버 | 컨테이너의 `/opt/seatunnel/config/jvm_options` | 저장소의 `cluster/jvm_options`는 초기 1GiB, 최대 3GiB |

Local의 힙을 변경하려면 해당 실행이 읽는 `jvm_client_options`에 `-Xms`, `-Xmx`를 지정하고 새 JVM으로 실행해야 한다. 서버용 `cluster/jvm_options`만 수정하면 Local 설정은 바뀌지 않는다. 구체적인 파일 마운트 방법은 [기존 문서의 Local 힙 변경 절차](local-heap-oom-study.md#local-힙을-3gib로-바꾸는-방법)를 따른다.

실제 적용값은 실행 중인 JVM에서 확인하는 것이 확실하다. JDK 진단 도구를 사용할 수 있는 컨테이너 안에서 다음과 같이 확인한다.

```bash
jcmd <Java_PID> VM.flags
```

`InitialHeapSize`와 `MaxHeapSize`를 확인한다. `MaxHeapSize=536870912`는 512MiB, `3221225472`는 3GiB다. 클러스터에서는 데이터를 처리하는 서버 JVM의 설정을 확인해야 한다.

## 7. 발표 슬라이드에 바로 넣을 내용

**슬라이드 제목: VM에 메모리가 남아 있는데 왜 OOM이 발생했을까?**

- SeaTunnel은 JVM 위에서 실행되며, 행 객체와 Parquet 버퍼가 Java 힙을 사용한다.
- 이번 Local 실행의 최대 힙은 512MiB였다. Docker나 Linux VM 전체 메모리와는 별도 제한이다.
- DB를 나눠 읽어도 이전 Parquet Writer와 버퍼가 남아 힙이 부족해졌다.
- Local 최대 힙 3GiB 조건에서는 2억 행 처리에 성공했다.

발표 멘트:

> “SeaTunnel은 Java 프로그램이라 JVM 안에서 실행됩니다. 이번에는 컴퓨터 전체 메모리가 아니라 JVM이 객체와 버퍼에 사용할 수 있는 힙의 상한이 512MB였습니다. DB에서는 데이터를 조금씩 읽었지만, Parquet 파일을 쓰는 Writer와 버퍼가 남아 이 공간이 부족해졌습니다. 초기 힙과 최대 힙은 실행 옵션으로 조절할 수 있고, 같은 병렬 작업을 Local에서 최대 힙 3GB로 실행한 조건에서는 2억 행 처리가 완료됐습니다.”

슬라이드 하단 근거: SeaTunnel 2.3.13, Local P8 비교 실험. 작은 힙 `-Xms256m -Xmx512m`, 큰 힙 `-Xms1g -Xmx3g`. 상세 분석은 [Local 힙·OOM 검증 문서](local-heap-oom-study.md) 참고.
