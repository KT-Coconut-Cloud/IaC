---

created: 2026-11-28  
type: project  
tags:

- kt-cloud
    
- coconut
    
- network
    
- k3s
    
- tailscale
    

---

# Network Architecture

## 1. 설계 목적

KT_02 심화프로젝트의 네트워크 구조를 정리함.

프로젝트 환경은 여러 장소의 VM과 AWS Cloud가 연결되는 하이브리드 구조임.

네트워크는 목적에 따라 다음과 같이 구분함.

1. **VMnet9**: K3s 노드 및 내부 서비스 간 통신
    
2. **Tailscale**: 원격 VM 접근 및 관리
    
3. **AWS Cloud**: 데이터 반입, 검사, 분석 및 저장
    
4. **외부 접근 경로**: Cloudflare, Ingress, HTTPS 기반 서비스 접근
    

기존 SSH Reverse Tunnel은 Tailscale로 전환하는 방향이며, K3s 내부 통신망을 대체하는 것은 아님.

## 2. 전체 네트워크 구성

### 2.1 구성 요소

|영역|구성 요소|역할|
|---|---|---|
|On-premises|K3s Cluster|서비스 및 데이터 처리|
|On-premises|MySQL Primary|원본 데이터 저장|
|On-premises|MySQL Replica|복제 데이터 저장|
|KT Cloud|CI Server|Jenkins 기반 CI|
|KT Cloud|Monitoring Server|Prometheus, Grafana, Loki 등|
|AWS Cloud|S3|데이터 저장|
|AWS Cloud|EventBridge|이벤트 기반 작업 실행|
|AWS Cloud|Lambda, Step Functions|데이터 검사 및 분석 처리|
|AWS Cloud|Headscale|Tailscale 네트워크 제어 서버|

### 2.2 네트워크 구분

|구분|VMnet9|Tailscale|
|---|---|---|
|목적|내부 서비스 통신|원격 접근 및 관리|
|주소 체계|`10.121.0.0/24`|`100.64.0.0/10`|
|주요 대상|K3s 노드, DB VM|등록된 원격 VM|
|통신 방식|기존 가상 네트워크|WireGuard 기반 암호화 오버레이 네트워크|
|사용 범위|클러스터 및 내부 서비스|SSH 등 원격 관리|

두 네트워크는 서로 다른 목적을 가지므로 병행 사용함.

## 3. VMnet9 내부 네트워크

### 3.1 네트워크 대역

```
Network: 10.121.0.0/24
```

확인된 주요 노드 주소는 다음과 같음.

|노드|VMnet9 IP|역할|
|---|---|---|
|k3s-m1|`10.121.0.160`|K3s Server|
|k3s-w1|`10.121.0.161`|K3s Agent|
|k3s-w2|`10.121.0.162`|K3s Agent|
|Primary DB|`10.121.0.168`|MySQL Primary|
|Controller|`10.121.0.169`|Ansible 및 관리 작업|

※ Replica DB 등 나머지 VM의 주소와 역할은 실제 환경 기준으로 추가 확인 필요.

### 3.2 내부 통신 구조

K3s 노드 간 통신은 기존 VMnet9를 사용함.

주요 통신 항목:

- K3s Server와 Agent 간 클러스터 통신
    
- Flannel 기반 Pod 네트워크 통신
    
- Kubernetes API 접근
    
- K3s 내부 서비스와 외부 DB VM 간 통신
    

DB 연결 및 NetworkPolicy는 현재 구성된 VMnet9 IP를 기준으로 유지함.

### 3.3 DB 통신

Primary DB는 K3s 클러스터 외부 VM에 위치함.

|구분|주소|포트|
|---|---|---|
|Primary DB|`10.121.0.168`|`3306`|
|Replica DB|실제 VM 주소 확인 필요|실제 설정 확인 필요|

Kubernetes `database` 네임스페이스에서는 Service와 Endpoints를 이용해 외부 DB를 클러스터 내부 서비스처럼 연결함.

관련 매니페스트:

- `database/primary-db.yaml`
    
- `database/replica-db.yaml`
    

## 4. Tailscale 원격 관리 네트워크

### 4.1 도입 배경

기존에는 각 VM이 AWS EC2를 경유하는 SSH Reverse Tunnel 구조였음.

기존 구성의 문제:

- 각 VM에서 Reverse Tunnel을 유지해야 함
    
- EC2가 SSH 접속 경로의 중간 지점이 됨
    
- 터널 서비스 및 포트 관리가 필요함
    

이를 개선하기 위해 Headscale을 자체 호스팅 Control Plane으로 사용하고 각 VM에 Tailscale Client를 등록함.

### 4.2 구성 요소

|구성 요소|역할|
|---|---|
|Headscale|자체 호스팅 Tailscale Control Plane|
|Tailscale Client|각 VM에 설치하는 네트워크 클라이언트|
|WireGuard|암호화된 네트워크 통신 기반|
|Pre-auth Key|클라이언트 등록 인증|
|Tailscale IP|원격 노드 간 통신에 사용하는 주소|

### 4.3 Headscale 서버

|항목|구성|
|---|---|
|위치|AWS EC2|
|공인 IP|`3.34.216.95`|
|접속 주소|`https://3.34.216.95.sslip.io`|
|컨테이너|`headscale/headscale:latest`|
|내부 서비스|`127.0.0.1:8080`|
|리버스 프록시|Nginx|
|인증서|Let's Encrypt|
|데이터베이스|SQLite|
|주소 대역|`100.64.0.0/10`|
|사용자|`coconut` (ID: 1)|

### 4.4 클라이언트 등록 대상

|노드|Tailscale 등록|
|---|---|
|k3s-m1|등록 대상|
|k3s-w1|등록 대상|
|k3s-w2|등록 대상|
|db1|등록 대상|

※ 위 목록은 프로젝트 구성상 등록 대상이며, 실제 등록 완료 여부와 할당 IP는 Headscale 노드 목록에서 확인해야 함.

### 4.5 원격 SSH 접속

기존 방식:

```
ssh -p 22168 db1@3.34.216.95
```

변경 방식:

```
ssh -i <pem> <계정>@100.64.0.x
```

Headscale은 노드 등록 및 네트워크 제어를 담당하며, 실제 VM 간 통신은 Tailscale 네트워크를 통해 수행함.

## 5. 네트워크 통신 경로

### 5.1 원격 관리 경로

```
flowchart TD
    ADMIN["관리자 PC"]
    HEAD["AWS EC2<br/>Headscale"]
    M1["k3s-m1"]
    W1["k3s-w1"]
    W2["k3s-w2"]
    DB["db1"]

    ADMIN -. "Control Plane 연결 및 노드 정보" .-> HEAD

    ADMIN -->|"Tailscale SSH"| M1
    ADMIN -->|"Tailscale SSH"| W1
    ADMIN -->|"Tailscale SSH"| W2
    ADMIN -->|"Tailscale SSH"| DB
```

### 5.2 K3s 내부 통신 경로

```
flowchart TD
    M1["k3s-m1<br/>10.121.0.160"]
    W1["k3s-w1<br/>10.121.0.161"]
    W2["k3s-w2<br/>10.121.0.162"]
    DB["Primary DB<br/>10.121.0.168"]

    M1 <-->|"VMnet9"| W1
    M1 <-->|"VMnet9"| W2
    W1 <-->|"VMnet9"| W2

    M1 -->|"VMnet9 DB 연결"| DB
    W1 -->|"VMnet9 DB 연결"| DB
    W2 -->|"VMnet9 DB 연결"| DB
```

※ 실제 DB 연결 주체와 방화벽 정책은 서비스별 설정을 기준으로 확인함.

## 6. 접근 권한 및 관리 원칙

### 6.1 SSH와 Kubernetes 권한 구분

Linux SSH 접근 권한과 Kubernetes API 접근 권한은 별개임.

|접근 방식|관리 대상|권한 관리|
|---|---|---|
|SSH|VM 운영체제|Linux 계정 및 SSH 인증|
|Kubernetes API|Cluster 및 Namespace 리소스|Kubernetes RBAC|
|GitOps|배포 리소스|Git 저장소 및 Argo CD|

모든 팀원에게 Worker VM SSH 권한을 부여할 필요는 없음.

서비스 배포는 GitOps/Argo CD를 사용하고, Kubernetes 리소스 관리는 RBAC를 통해 수행함. OS 수준의 작업이 필요한 경우에만 SSH 접근을 허용하는 방향으로 관리함.

### 6.2 운영 원칙

- VMnet9는 K3s 내부 통신용으로 유지
    
- Tailscale은 원격 관리용으로 사용
    
- Kubernetes API 권한과 Linux SSH 권한을 분리
    
- 서비스 배포는 GitOps를 우선 사용
    
- DB 통신 경로는 별도 변경 작업 전까지 기존 VMnet9 주소 유지
    

## 7. 기존 SSH Reverse Tunnel 정리

Tailscale 기반 SSH 접속 검증 이후 기존 터널을 정리함.

|항목|기존 구성|변경 방향|
|---|---|---|
|접속 경로|EC2 경유|Tailscale IP|
|SSH 포트|`22160~22169`|Tailscale 네트워크를 통한 SSH|
|터널 유지|autossh/systemd|tailscaled|
|EC2 역할|SSH Tunnel 수신|Headscale Control Plane|

정리 순서:

1. Headscale 노드 등록 확인
    
2. Tailscale IP 확인
    
3. VM 간 통신 확인
    
4. Tailscale IP 기반 SSH 접속 검증
    
5. 기존 autossh 및 터널 서비스 비활성화
    
6. EC2 보안 그룹의 TCP `22160~22169` 포트 정리
    

## 8. DB 통신 경로 변경 시 고려사항

현재는 VMnet9 기반 DB 통신을 유지함.

추후 DB 통신까지 Tailscale IP로 전환하려는 경우 다음 파일의 IP 설정을 검토해야 함.

- `database/primary-db.yaml`
    
- `database/replica-db.yaml`
    
- `pii-job/networkpolicy.yaml`
    

이 작업은 원격 관리 네트워크 도입과 별개의 변경 사항임.

따라서 현재 단계에서는 DB 연결 경로를 임의로 변경하지 않음.

## 9. 후속 확인 항목

- 각 VM의 실제 Tailscale 등록 상태 확인
    
- 각 VM의 Tailscale IP 기록
    
- VM 간 `tailscale ping` 연결 확인
    
- SSH 접속 검증
    
- Headscale EC2 Elastic IP 연결 여부 확인
    
- 기존 Reverse Tunnel 서비스 정리 여부 확인
    
- EC2 보안 그룹의 기존 터널 포트 정리 여부 확인
    
- VMnet9 기반 K3s 및 DB 통신 유지 여부 확인
    
- 팀원별 SSH 및 Kubernetes RBAC 권한 확인
    

## 10. 관련 노트

### Concepts

- [[Headscale]]
    
- [[Tailscale]]
    
- [[Overlay Network]]
    
- [[VPN]]
    
- [[WireGuard]]
    
- [[Control Plane]]
    
- [[Data Plane]]
    

### Labs

- [[Headscale 서버 구축]]
    
- [[Tailscale 클라이언트 등록]]
    
- [[Tailscale 연결 및 SSH 검증]]
    

### Projects

- [[SSH Reverse Tunnel에서 Tailscale로 전환]]