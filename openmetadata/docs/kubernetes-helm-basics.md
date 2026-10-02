# Kubernetes / Helm 기초 — OpenMetadata 프로덕션 배포를 위한 선행 학습

## 목적

지금까지의 로컬 데모는 `docker-compose`로 단일 호스트에서 띄운 것이다. 만약 팀이 OpenMetadata를
사내/고객사 환경에 실제로 "솔루션"으로 배포하는 방향으로 간다면, 공식적으로 권장되는 프로덕션 배포
방식은 **Kubernetes + Helm**이다. 이 문서는 그 전환에 필요한 최소한의 개념과, OpenMetadata 공식
Helm Chart를 실제로 설치하는 절차를 코드 예제와 함께 정리한다.

`docker-compose`와의 근본적인 차이 하나를 먼저 짚고 가면: compose는 "이 호스트에 이 컨테이너들을 띄운다"는
선언인 반면, Kubernetes는 "이 상태(desired state)를 클러스터 전체에서 유지해달라"는 선언이다. 컨테이너가
죽으면 자동으로 재기동되고, 노드가 여러 대면 그 위에 자동으로 분산 배치된다 — compose에는 없는 개념이다.

## Kubernetes 핵심 개념

아래 개념들만 이해하면 대부분의 Helm Chart(`values.yaml`)를 읽을 수 있다.

### 0. Cluster / Node

가장 먼저 이해해야 하는 밑바탕 개념. **Node**는 컨테이너가 실제로 돌아가는 서버(물리 서버 또는 VM)
한 대를 말한다 — `docker-compose`로 치면 지금 컨테이너들을 다 띄우고 있는 맥북 한 대가 노드 하나인
셈이다. **Cluster**는 이런 Node 여러 대를 하나로 묶어서, 마치 하나의 거대한 컴퓨팅 자원 풀처럼 다룰 수
있게 만든 전체 집합이다.

Node는 역할에 따라 둘로 나뉜다.

- **Control Plane 노드(마스터)**: 클러스터 전체를 관리하는 두뇌. 어떤 Pod를 어느 Worker 노드에 배치할지
  스케줄링하고, 클러스터 상태를 계속 감시·복구한다. 애플리케이션 컨테이너는 보통 여기 올라가지 않는다.
- **Worker 노드**: 실제로 Pod(컨테이너)가 배치되어 돌아가는 서버들.

"Kubernetes에 배포한다"는 건 결국 "이 클러스터에 배포한다"는 뜻이고, 실제로 어느 Worker 노드에 컨테이너가
놓일지는 사용자가 직접 정하지 않는다 — 클러스터(Control Plane)가 알아서 스케줄링한다. `docker-compose`는
애초에 노드 1개(내 컴퓨터)만 다루는 도구라 이 개념 자체가 없었던 것이고, K8s는 "여러 대의 서버를
하나처럼 다루기 위해" 태어난 도구라서 Cluster/Node가 가장 먼저 나오는 개념이다. 뒤에 나오는 minikube는
편의상 **Node 1개짜리 클러스터**를 로컬에 흉내내주는 도구다.

### 1. Pod

컨테이너 하나 이상을 묶은 배포 최소 단위. 보통 컨테이너 1개 = Pod 1개로 생각해도 무방하다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: openmetadata-server
spec:
  containers:
    - name: openmetadata-server
      image: docker.getcollate.io/openmetadata/server:1.13.3
      ports:
        - containerPort: 8585
```

Pod를 직접 만들 일은 거의 없다 — 죽으면 자동으로 안 살아나기 때문에, 실제로는 항상 아래 **Deployment**를 통해 만든다.

### 2. Deployment

"이 Pod를 몇 개 유지해라"를 선언하는 컨트롤러. Pod가 죽으면 자동으로 다시 만들어준다(self-healing).
`docker-compose.yml`의 `services:` 항목 하나가 대략 Deployment 하나에 대응한다고 보면 된다.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openmetadata-server
spec:
  replicas: 2                     # 이 Pod를 2개 유지 (docker-compose엔 없는 개념)
  selector:
    matchLabels:
      app: openmetadata-server
  template:
    metadata:
      labels:
        app: openmetadata-server
    spec:
      containers:
        - name: openmetadata-server
          image: docker.getcollate.io/openmetadata/server:1.13.3
          ports:
            - containerPort: 8585
```

### 3. Service

Pod는 재생성될 때마다 IP가 바뀐다. Service는 "이 라벨을 가진 Pod들"에게 고정된 이름/IP로 접근할 수 있게
해주는 내부 로드밸런서다. `docker-compose`에서 컨테이너 이름으로 서로 접근하던 것의 K8s 버전.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: openmetadata-server
spec:
  selector:
    app: openmetadata-server      # 이 라벨을 가진 Pod들로 트래픽 전달
  ports:
    - port: 8585
      targetPort: 8585
  type: ClusterIP                 # 클러스터 내부에서만 접근 가능 (기본값)
```

### 4. Ingress

클러스터 외부(사용자 브라우저)에서 Service로 들어오는 HTTP(S) 진입점. 도메인/경로 기반 라우팅과
TLS 종료를 담당한다. 별도로 Ingress Controller(예: nginx-ingress)를 클러스터에 미리 설치해야 동작한다.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: openmetadata-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod   # TLS 인증서 자동 발급 (cert-manager 설치 필요)
spec:
  rules:
    - host: catalog.company.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: openmetadata-server
                port:
                  number: 8585
  tls:
    - hosts: ["catalog.company.com"]
      secretName: openmetadata-tls
```

### 5. ConfigMap / Secret

환경변수·설정값을 코드/이미지와 분리해서 주입하는 방법. `docker-compose.yml`의 `environment:` 항목과
비슷하지만, **민감정보(비밀번호, API key)는 반드시 Secret으로 분리**한다(ConfigMap은 평문 저장).

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mysql-secrets
type: Opaque
stringData:
  openmetadata-mysql-password: "실제비밀번호는여기에직접넣지않고CI/CD나Vault에서주입"
```

### 6. PersistentVolumeClaim (PVC)

Pod는 재생성되면 로컬 디스크 내용이 사라진다(ephemeral). DB 데이터처럼 유지되어야 하는 데이터는
PVC로 별도의 영구 스토리지를 요청해서 붙인다. `docker-compose`의 `volumes:`에 대응.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mysql-data
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 20Gi
```

### Namespace

같은 클러스터 안에서 리소스를 논리적으로 분리하는 단위. 고객사별 배포를 같은 클러스터에서 격리하고
싶을 때(또는 dev/staging/prod 분리) 이 단위를 쓴다. (완전한 격리가 필요하면 네임스페이스가 아니라
클러스터 자체를 분리하는 게 정석이라는 점은 이전에 논의한 대로.)

```bash
kubectl create namespace openmetadata-prod
```

## kubectl 기본 명령어

```bash
kubectl get pods -n openmetadata-prod              # 현재 떠 있는 Pod 목록
kubectl get deployments -n openmetadata-prod        # Deployment 상태
kubectl describe pod <pod-name> -n openmetadata-prod  # 특정 Pod의 상세 상태 (에러 원인 확인 시 가장 먼저 볼 것)
kubectl logs <pod-name> -n openmetadata-prod -f     # 로그 실시간 확인 (docker logs -f 와 동일한 감각)
kubectl exec -it <pod-name> -n openmetadata-prod -- /bin/bash  # 컨테이너 안으로 진입
kubectl apply -f deployment.yaml                    # YAML 파일 기준으로 리소스 생성/갱신
kubectl delete -f deployment.yaml                   # 삭제
```

## Helm 핵심 개념

Helm은 "K8s YAML 묶음을 하나의 배포 단위로 패키징하고, 값만 바꿔서 재사용 가능하게" 해주는 패키지 매니저다.
`apt`/`brew`가 OS 패키지를 다루듯, Helm은 K8s 리소스 묶음(Chart)을 다룬다.

| 개념 | 설명 |
|---|---|
| **Chart** | Deployment/Service/Ingress 등 K8s YAML들을 템플릿화해서 묶어놓은 패키지 (예: `openmetadata` chart) |
| **values.yaml** | Chart 안의 템플릿에 주입할 실제 값들. 여기만 고객사별로 바꾸면 같은 Chart를 재사용 가능 |
| **Release** | 하나의 Chart를 특정 values로 실제 클러스터에 설치한 "인스턴스" (같은 chart를 이름 다르게 여러 번 install 가능) |
| **Repository** | Chart들을 모아둔 저장소 (예: `https://helm.open-metadata.org/`) |

## Helm 기본 명령어

```bash
helm repo add open-metadata https://helm.open-metadata.org/   # 저장소 등록
helm repo update                                               # 저장소 최신화
helm search repo open-metadata --versions                      # 사용 가능한 chart/버전 확인

helm install <release-name> open-metadata/openmetadata \
  -f my-values.yaml                                             # 설치 (my-values.yaml로 값 오버라이드)

helm upgrade <release-name> open-metadata/openmetadata \
  -f my-values.yaml                                             # 값 변경 또는 버전 업그레이드 적용

helm rollback <release-name> 1                                  # 이전 리비전으로 롤백 (compose엔 없는 기능)
helm list                                                        # 현재 설치된 release 목록
helm uninstall <release-name>                                    # 삭제
```

`helm upgrade`가 실패 없이 이전 상태로 되돌릴 수 있다(`rollback`)는 점이 compose 대비 실무에서 체감되는
가장 큰 이점 중 하나다 — compose는 "이전 이미지 태그로 다시 up" 하는 수동 작업이 필요하다.

## 실전: OpenMetadata 공식 Helm Chart 설치

공식 저장소는 `open-metadata/openmetadata-helm-charts` (GitHub)이며, 두 개의 Chart로 나뉜다.

- `openmetadata` — 애플리케이션 서버 본체
- `openmetadata-dependencies` — MySQL, OpenSearch, Airflow(ingestion) 등 의존 스택

**사전 요구사항**: Kubernetes 클러스터(EKS/GKE/AKS 또는 로컬 minikube 등), `kubectl`, **Helm 3**(2는 미지원),
최소 4GB RAM.

### 1) 의존성부터 클러스터 안에 설치 (실습/데모용 — 클러스터 내부에 DB/검색엔진까지 같이 띄움)

```bash
helm repo add open-metadata https://helm.open-metadata.org/
helm repo update

helm install openmetadata-dependencies open-metadata/openmetadata-dependencies \
  -n openmetadata --create-namespace
```

### 2) OpenMetadata 본체 설치

```bash
helm install openmetadata open-metadata/openmetadata \
  -n openmetadata
```

### 3) 실제 운영 배포 — 외부 관리형 DB/검색엔진에 연결하는 values.yaml 예시

프로덕션에서는 보통 위 1번(클러스터 내부 dependencies)을 생략하고, RDS 같은 관리형 MySQL과 별도
OpenSearch 클러스터에 연결한다. 아래는 실제 Helm Chart의 `values.yaml` 스키마를 기준으로 한 예시다.

```yaml
# values-prod.yaml
replicaCount: 2                     # 가용성을 위해 서버 Pod 2개 이상 유지

openmetadata:
  config:
    database:
      enabled: true
      host: my-rds-instance.xxxx.ap-northeast-2.rds.amazonaws.com
      port: 3306
      driverClass: com.mysql.cj.jdbc.Driver
      dbScheme: mysql
      databaseName: openmetadata_db
      auth:
        username: openmetadata_user
        password:
          secretRef: mysql-secrets          # 비밀번호는 위에서 만든 K8s Secret 참조 (평문 금지)
          secretKey: openmetadata-mysql-password

    elasticsearch:
      enabled: true
      host: my-opensearch-domain.ap-northeast-2.es.amazonaws.com
      searchType: opensearch
      port: 9200
      scheme: https

resources:
  limits:
    cpu: "1"
    memory: 2048Mi
  requests:
    cpu: 500m
    memory: 1024Mi
```

```bash
kubectl create secret generic mysql-secrets \
  --from-literal=openmetadata-mysql-password='실제비밀번호' \
  -n openmetadata

helm install openmetadata open-metadata/openmetadata \
  -n openmetadata -f values-prod.yaml
```

이 흐름이 이전에 논의했던 "고객사마다 배포"의 실질적 실체다: **같은 Chart를 재사용하고, 고객사마다
`values-<customer>.yaml`만 바꿔서 `helm install`** 하는 것 — 이게 갖춰져야 "매번 처음부터 수작업"이 아닌
반복 가능한 배포가 된다.

## 로컬에서 리스크 없이 연습하기 (minikube)

실제 클러스터/고객사 환경을 건드리기 전에, 로컬 1-노드 클러스터로 위 과정을 먼저 연습하는 걸 권장한다.

```bash
brew install minikube kubectl helm     # macOS

minikube start --cpus=4 --memory=8192  # 로컬 가상 클러스터 기동 (OpenMetadata 최소 요구치 감안)
kubectl get nodes                       # 클러스터 정상 기동 확인

# 이후 위 "실전: OpenMetadata 공식 Helm Chart 설치" 절차를 그대로 이 클러스터에 적용해보면 됨

minikube stop                           # 종료
```

## 참고한 공식 문서

- [OpenMetadata Helm Charts (GitHub, 공식 저장소)](https://github.com/open-metadata/openmetadata-helm-charts) — Chart 이름(`openmetadata`, `openmetadata-dependencies`), `helm repo add`/`helm install` 명령어, 사전 요구사항(Helm 3, 최소 4GB RAM) 확인
- [openmetadata chart의 `values.yaml` (GitHub raw, main 브랜치)](https://raw.githubusercontent.com/open-metadata/openmetadata-helm-charts/main/charts/openmetadata/values.yaml) — `database`/`elasticsearch`/`pipelineServiceClientConfig`/`resources` 등 실제 키 경로와 기본값 확인
- [Kubernetes 공식 문서 — Concepts](https://kubernetes.io/docs/concepts/) — Pod/Deployment/Service/Ingress/ConfigMap·Secret/PVC 정의
- [Helm 공식 문서](https://helm.sh/docs/) — Chart/Release/Repository 개념, `helm` CLI 명령어

## 이 폴더의 다른 문서와의 관계

이 문서는 지금 로컬 데모(`docker-compose.yml` 기반)를 프로덕션으로 확장하고 싶을 때 참고할 **선행 학습
자료**다. 실제로 특정 고객사/사내 환경에 배포하게 되면, 그 환경에 맞는 `values-<대상>.yaml`과 배포
절차를 별도 문서로 새로 만드는 게 맞다 — 이 문서는 "매번 다시 검색하지 않아도 되는 기초 레퍼런스" 역할로
유지한다.
