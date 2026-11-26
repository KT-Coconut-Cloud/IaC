---
created: 2026-11-26
type: runbook
tags: [k3s, ansible, worker]
---

# K3s 남은 작업 절차서 v3

- 기준일: 2026-11-26
- 저장소: `/home/admin/IaC`
- Controller: `k3s-hq` (`10.121.0.169`), Rocky Linux 9.8
- venv: `/home/admin/dev312` (Python 3.12.16, ansible-core 2.21.6)
- 대상: VMware `w1`, `w2` Worker만
- 제외: `m1` (`10.121.0.160`)의 SSH 및 관리 변경
- 코드 기준: 현재 `main` 작업 트리. HEAD의 코드 변경은 미커밋 상태이므로 실행 전 로컬 변경을 보존한다.

## 작업 원칙

- m1은 Server로 유지한다. Worker API 통신과 Kubernetes 상태의 읽기 전용 조회만 허용한다.
- w1과 w2는 재생성 가능한 실습 Worker다. Snapshot이나 identity 백업을 실행 전 필수조건으로 두지 않는다.
- 한 Worker 실행 시 다른 Worker를 SSH로 조회하거나 검증하지 않는다. 선택된 Worker들만 identity 비교 범위에 들어간다.
- SSH는 기존 `/home/admin/.ssh/id_ed25519_ansible`을 사용한다. 새 키를 만들지 않는다. 저장소 Ansible 연결은 첫 접속에 `accept-new`를 적용하고, 기존에 등록된 키 변경은 계속 거부한다.
- 실제 SSH 인증은 key 기반이다. Vault 암호는 `--ask-vault-pass` 프롬프트로 입력하고 토큰·암호·kubeconfig 내용을 출력하지 않는다.
- Agent 설치와 kubeconfig 사후 검증은 분리한다. kubeconfig가 없어도 설치 단계는 진행 가능하지만 사후 검증은 별도 실행해야 한다.
- 애플리케이션, DB, CI/CD, GitOps, Vault 운영정책, 모니터링, AWS 서비스는 이 절차에서 변경하지 않는다.

## 현재 코드와 v2 절차서 차이

v2의 Windows 프로젝트 경로와 `<기존 Controller 프로젝트 경로>`는 현재 Controller 실행 위치와 맞지 않는다. 현재 기준은 `/home/admin/IaC`다. v2에 있던 `-e @group_vars/all.yml`, `-e @group_vars/k3s_agents.yml` 경로도 현재 저장소에서는 맞지 않는다. 공통 변수는 `playbooks/group_vars/`에서 Playbook이 자동으로 찾으므로 실행 인자에 수동 전달하지 않는다.

v2는 VMware 설치와 kubeconfig 검증을 통합하고 fingerprint, 네트워크 smoke 조건을 포함했다. 현재 `vmware.yml`은 설치만 수행하며 검증은 `cluster_verify_vmware.yml`로 분리되어 있다. Network smoke test는 기본 비활성화다.

## 1. Controller 작업 위치 및 확인

```bash
cd /home/admin/IaC
source /home/admin/dev312/bin/activate
ansible --version
ansible-inventory -i inventory/vmware/hosts.ini --playbook-dir playbooks --graph
```

`ansible.cfg`는 저장소 루트에서 자동 적용된다. 기본 VMware inventory는 w1/w2만 포함하며 m1은 없다. 특정 Worker 명령은 아래의 `--limit`을 그대로 사용한다. `ansible-inventory`에서 공통 변수까지 표시할 때만 `--playbook-dir playbooks`가 필요하다.

SSH 접속을 확인할 때는 다음 read-only ping을 사용할 수 있다.

```bash
ansible w1 -i inventory/vmware/hosts.ini -m ansible.builtin.ping
ansible w2 -i inventory/vmware/hosts.ini -m ansible.builtin.ping
```

## 2. 설치 전 최소 조건

1. 실행할 Worker IP가 inventory와 맞고 Rocky Linux 8.10이며 SSH key 접속이 되는지 확인한다.
2. `group_vars/vault.yml`이 암호화 상태이고 `vault_k3s_tokens.vmware`가 유효한지 확인한다. 설치 명령은 Vault 암호를 대화형으로 묻고, playbook은 token 존재 및 최소 길이를 비밀 출력 없이 확인한다.
3. Worker에서 m1 API `10.121.0.160:6443`에 접근 가능해야 한다. `k3s_agent.yml`이 설치 role 전에 TCP 접근을 검사한다.
4. `/usr/local/bin/k3s`가 이미 있으면 기존 version이 pin과 같아야 한다. 기존 `/etc/rancher/k3s/config.yaml`이 이 저장소 관리 파일이 아니면 자동 덮어쓰기하지 않고 중단한다.

VMware 콘솔 fingerprint를 변수에 입력하는 단계는 없다. 첫 접속 키는 이 저장소의 SSH `accept-new` 설정으로 등록된다. 이미 등록된 IP의 키가 바뀌어 접속이 거부되면, Worker 재생성 여부를 확인한 후 그 IP의 기존 known_hosts 항목만 검토한다. 보안 검사를 전역 비활성화하지 않는다.

## 3. Worker 설치 명령

모든 명령은 `/home/admin/IaC`에서 기존 venv를 활성화한 상태로 실행한다. `--ask-vault-pass` 프롬프트에 Vault 암호를 입력한다. m1은 inventory에 없고, `--limit`에 지정한 Worker만 변경 대상으로 삼는다.

### w1 단독 설치

```bash
ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml \
  --limit w1 --ask-vault-pass
```

### w2 단독 설치

```bash
ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml \
  --limit w2 --ask-vault-pass
```

### w1/w2 일괄 설치

```bash
ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml \
  --ask-vault-pass
```

일괄 실행에서는 bootstrap, identity, baseline, Agent 각 play가 `serial: 1`로 Worker를 순차 처리한다. w1 완료 후 w2 설치를 시작하려면 단독 명령 두 개를 차례로 실행한다.

설치 전 대상만 확인하려면 해당 명령에 `--list-hosts`를 붙인다. w1/w2 단독 확인은 각각 `--limit w1`, `--limit w2`를 사용한다. 실제 설치 명령에는 `--list-hosts`를 붙이지 않는다.

## 4. 설치 후 검증

설치 후 검증에는 Controller에서 접근 가능한 보호된 kubeconfig와 `kubectl`이 필요하다. 문서 작성 당시 Controller에서는 두 항목 모두 사용할 수 없는 상태였다. kubeconfig는 저장소 밖에 두고, 파일 내용을 터미널·문서에 출력하거나 Git에 추가하지 않는다. 승인된 기존 kubeconfig를 보호된 경로에 준비하고, kubectl을 기존 환경에서 사용할 수 있게 한 뒤 검증한다.

```bash
export VMWARE_KUBECONFIG=/보호된/경로/kubeconfig
ansible-playbook -i inventory/vmware/hosts.ini playbooks/cluster_verify_vmware.yml
```

검증 playbook은 `hosts: localhost`이므로 별도 `--limit localhost`가 필요하지 않다. API에서 정확한 `k3s-m1`, `k3s-w1`, `k3s-w2` 노드 집합, 각 노드 Ready 상태, CoreDNS 및 Flannel 실행 여부를 조회한다. 기본 smoke test는 꺼져 있어 임시 Pod/Service를 만들지 않는다. kubeconfig가 준비되지 않으면 설치는 진행할 수 있지만, 사후 검증은 미완료로 남는다.

## 5. 실제 코드가 적용하는 설정

- Python 3.9.25 검사 및 필요 시 package bootstrap
- Controller 공개키를 선택된 Worker에 추가
- 선택된 대상 집합에서 machine-id/SSH host key 중복 검사; 중복일 때 대상 Worker에서만 identity 갱신
- hostname을 `k3s-w1` 또는 `k3s-w2`로 설정
- Rocky Linux 8.10 baseline: SELinux enforcing, swap 비활성화, firewalld 중지/비활성화, chronyd, timezone, K3s kernel modules/sysctl, 필요 패키지 및 profile completion
- Worker에서 m1 API TCP 접근성 확인 후 고정 버전 `v1.37.2+k3s1` Agent 설치 및 서비스 시작
- 기존 binary 버전 불일치 또는 미관리 K3s config 발견 시 자동 교체하지 않고 중단

예상치 못한 실패 후 재생성 가능한 Worker는 OS 기준 이미지로 다시 준비한 뒤 해당 Worker 단독 명령을 재실행할 수 있다. 실패한 join으로 Node 객체가 남은 경우에만 실제 node 상태를 확인하고 API에서 해당 Worker 항목을 별도로 정리한다. m1 OS/SSH/K3s 설정을 변경하거나 기존 애플리케이션을 재배포하지 않는다.

## 6. 코드 정적 확인 명령

```bash
ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml --syntax-check
ansible-playbook -i inventory/vmware/hosts.ini playbooks/cluster_verify_vmware.yml --syntax-check
ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml --list-hosts --limit w1
ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml --list-hosts --limit w2
ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml --list-hosts
```

이 문서 작성 중에는 Ansible 배포 playbook을 실행하지 않았다. 현재 기록된 SSH ping과 w1 API TCP 확인은 기존 read-only 점검 결과이며, K3s Agent 설치 및 Kubernetes Ready 검증이 완료됐다는 뜻은 아니다.

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|---|---|---|
| v1 | 2026-11-25 | Worker 재구축과 KT Cloud 후속 작업을 포함한 상세 절차 |
| v2 | 2026-11-26 | 당시 저장소 기준 VMware Worker 절차 및 Controller-Git 공유 흐름 반영 |
| v3 | 2026-11-26 | 현재 Controller 경로·변수 위치·SSH `accept-new`·Worker별 실행·API 검사·분리 검증에 맞춰 갱신 |
