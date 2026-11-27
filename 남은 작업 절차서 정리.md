---
title: KT_02 심화프로젝트 — Project Decisions & Scope
created: 2026-11-28
type: project
tags:
  - KT_02
  - Kubernetes
  - K3s
  - Ansible
  - IaC
  - Project-Management
---

# KT_02 심화프로젝트 — Project Decisions & Scope

## 1. 프로젝트 방향 및 목표

기존 K3s Server를 유지하면서 VMware Worker를 Ansible로 자동 구축하고 기존 클러스터에 편입하는 것이 핵심 목표다.

단순히 K3s 설치에 그치지 않고, VMware 환경에서 검증한 Ansible 자동화 구조를 향후 KT Cloud 환경에도 재사용할 수 있도록 공통 Role, 환경별 Inventory, 변수 구조를 정리한다.

핵심 방향:
- 기존 인프라를 유지하면서 Worker 구축 자동화
- Ansible 기반 반복 가능한 인프라 구성
- 환경별 설정과 공통 작업의 분리
- 구축 결과와 검증 절차의 문서화
- 향후 클라우드 환경으로 확장할 수 있는 구조 확보

## 2. 최종 구축 범위

| 구분 | 구축 범위 |
|---|---|
| Ansible | Worker 구성 및 설치 자동화 |
| VMware | w1, w2 대상 Inventory 및 변수 구성 |
| OS 설정 | Worker 기본 설정 자동화 |
| K3s | 지정 버전의 Agent 설치 및 기존 Server Join |
| 클러스터 | 기존 m1에 Worker 편입 |
| 검증 | 노드 등록 및 Ready 상태 확인 |
| 공통화 | 공통 Role과 환경별 Inventory·변수 분리 |
| 문서화 | 구축 절차, 실행 방법, 검증 결과 정리 |

**현재 진행 상태:** W1/W2 구축은 완료된 상태를 기준으로 관리한다. 과거 문서에 남아 있는 미구축·미검증 기록은 당시 상태로 구분하고, 최신 실제 실행 결과와 일치하도록 갱신한다.

## 3. 범위 축소 및 후속 프로젝트 이관

초기 구상에서 확장 가능했던 클러스터 운영 자동화와 클라우드 배포 기능은 이번 프로젝트의 필수 범위에서 제외한다.

| 항목 | 이번 프로젝트 | 후속 프로젝트 |
|---|---|---|
| VMware Worker 구축 | 수행 | 유지·개선 |
| Ansible 공통 Role | 기반 정리 | 환경 확장 |
| KT Cloud 실배포 | 필수 범위 제외 | 실제 배포 |
| 정기 실행 자동화 | 제외 | 확장 |
| 장애 감지 및 자동 복구 | 제외 | 확장 |
| Node Label / Taint 관리 자동화 | 제외 | 확장 |
| 상세 클러스터 운영 자동화 | 제외 | 확장 |
| 애플리케이션·DB 운영 변경 | 기존 구성 유지 | 별도 검토 |

이번 프로젝트에서는 **Worker 구축 자동화의 완성도와 재사용성 확보**에 집중한다. 클러스터 운영 자동화, 장애 대응, KT Cloud 실환경 배포는 후속 프로젝트의 확장 과제로 관리한다.

## 4. 확정된 기술 및 운영 결정

| 항목 | 확정 내용 |
|---|---|
| K3s Server | 기존 m1 유지 |
| VMware Worker | w1, w2 |
| K3s 버전 | `v1.37.2+k3s1` |
| SSH 접속 정책 | `accept-new` 사용 |
| SSH Host Key | 기존 등록 키 변경 시 자동 우회하지 않음 |
| Worker 방화벽 | firewalld 중지 및 비활성화 |
| Ansible SSH 키 | 기존 `/home/admin/.ssh/id_ed25519_ansible` 유지 |
| 실행 환경 | 기존 Controller 및 Python venv 유지 |

### 네트워크 구성 관련 결정

- 기존 SSH Reverse Tunnel 방식에서 Headscale 기반 Tailscale WireGuard P2P 방식으로 전환.
- Headscale EC2: `3.34.216.95`
- 접속 도메인: `https://3.34.216.95.sslip.io`
- Tailscale 주소 대역: `100.64.0.0/10`
- 각 VM의 Tailscale 연결 상태는 `tailscale status`, `tailscale ping` 등으로 확인.

※ Tailscale 연결 구성과 실제 K3s API 통신 경로는 구분해서 기록한다. 별도 검증 없이 K3s API가 Tailscale을 경유한다고 단정하지 않는다.

## 5. 기존 인프라 보호 원칙

### K3s Server m1
- 기존 m1은 정상 운영 상태를 유지한다.
- m1에 대한 SSH 접속 및 관리 작업을 수행하지 않는다.
- OS 설정, 패키지, 서비스, K3s Server 설정 변경 금지.
- 재설치, 초기화, 재부팅, 업그레이드 금지.
- 승인된 인증을 통한 Kubernetes API 읽기 전용 조회만 허용.

### 기존 자동화 및 비밀정보
- 기존 SSH 키를 재생성하지 않는다.
- 기존 Inventory, Ansible Role, 실행 환경을 임의로 초기화하거나 덮어쓰지 않는다.
- Vault 암호, Join Token, kubeconfig, 개인키 등 민감정보를 평문으로 출력하거나 Git에 저장하지 않는다.
- 사용자 변경사항을 사전 확인 없이 덮어쓰지 않는다.
- `sources/` 아래 프로젝트 참고파일은 읽기 전용으로 취급한다.

### 기존 서비스
- DB, CI/CD, ArgoCD, Vault, 모니터링 등 기존 서비스의 설정과 운영 상태를 임의로 변경하지 않는다.
- 애플리케이션 및 서비스 팀의 담당 영역과 Kubernetes 인프라 담당 영역을 구분한다.

## 6. 구축 및 검증 기록 원칙

- 최신 실제 구축 결과를 과거 계획 문서보다 우선한다.
- 과거의 미완료 기록은 당시 상태로 구분한다.
- 실제 실행·검증하지 않은 항목은 완료로 표시하지 않는다.
- 설치 작업과 검증 작업을 구분한다.
- 구축 결과는 실행 시점, 대상 노드, 실행 결과를 함께 기록한다.
- VMware에서 검증된 공통 Role과 환경별 변수를 후속 환경 확장의 기반으로 활용한다.

## 7. 후속 프로젝트 확장 방향

이번 프로젝트에서 확보한 Ansible 자동화 기반을 다음 단계로 확장한다.

1. KT Cloud 환경에 공통 Role 및 Inventory 적용
2. 클라우드 환경별 변수와 설정 분리
3. 반복 실행 및 정기 실행 자동화
4. Kubernetes 노드 운영 자동화 확대
5. 장애 감지 및 자동 복구 체계 구축
6. 클러스터 운영·모니터링 체계 고도화

## 8. 의사결정 변경 이력

| 날짜 | 변경 내용 |
|---|---|
| 2026-11-27 | SSH Reverse Tunnel에서 Headscale + Tailscale WireGuard P2P 방식으로 전환 |
| 2026-11-28 | 프로젝트 범위를 Worker 구축 자동화 중심으로 정리하고 클라우드 실배포 및 고급 운영 자동화는 후속 과제로 분리 |
| 추후 기록 | 확정 결정 변경 시 변경 사유와 영향 범위를 함께 기록 |

---

**문서 관리 원칙:** 본 문서는 KT_02 심화프로젝트의 방향, 확정 의사결정, 구축 범위를 판단하는 상위 기준 문서다. 상세 아키텍처, Ansible 코드, 설치 명령 및 실행 절차는 각각의 설계 명세서와 실행 문서에서 관리한다.
