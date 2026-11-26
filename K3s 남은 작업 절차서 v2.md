---
created: 2026-11-26
type: runbook
tags: [k3s, ansible, worker]
---

# K3s 남은 작업 절차서 v2

- 기준일: 2026-11-26
- 대상: VMware `w1`, `w2`만
- 운영 기준: 보존 중인 VMware `m1` (`10.121.0.160`)
- 목표: 두 Worker를 기존 K3s Server에 Agent로 편입

## 작업 원칙

- `m1`은 정상 운영 기준 노드다. VMware inventory에 추가하거나 변경하지 않는다.
- Worker는 재생성 가능한 노드로 취급한다. 저장소 기준은 Rocky Linux 8.10, `w1`=`10.121.0.161`/`k3s-w1`, `w2`=`10.121.0.162`/`k3s-w2`, NIC `ens160`이다. VM 자원은 작업자가 정한다.
- 기존 Controller, venv, SSH 키를 재사용한다. DB·Vault 정책·앱·CI/CD·모니터링·중개기·AWS는 변경하지 않는다.
- 저장소 baseline은 SELinux Enforcing, swap 비활성화, firewalld 중지/비활성화다. 이 설정은 VMware inventory의 Worker에 적용된다.
- 아래 명령은 실제 작업 시점에 실행한다. 이 문서 갱신 과정에서는 playbook을 실행하거나 인프라를 변경하지 않았다.

## 1. Windows에서 기준 저장소 확보

프로젝트의 `IaC` 저장소에서 `main` 최신본을 사용한다.

```bash
cd ~/.codex/.chatgpt-projects/g-p-6ae9562511f48191951007aab941ec5a/IaC
git switch main
git pull origin main
git status --short --branch
```

이 문서 대조 시 확인한 기준은 `main`의 `3d46995` (`FEAT: add k3s automation`)이며, 로컬 작업 트리는 깨끗했다.

## 2. Controller와 Worker 준비

1. `k3s-hq`의 기존 프로젝트와 `/home/admin/dev312` 환경을 확인한다. 저장소 README는 기존 Controller 프로젝트를 `/home/admin/ansible-k3s`로 지칭한다. `/home/admin/IaC`라고 가정해 새로 복제하거나 기존 프로젝트 위에 덮어쓰지 말고, 실제 사용 중인 경로에서 변경사항을 비교·반영한다.
2. Worker VM 두 대를 원하는 자원으로 준비하고 표의 주소·호스트명·OS 기준을 맞춘다. SSH 접속 계정은 inventory의 `root` 기준을 맞춘다.
3. Controller의 기존 Ansible 키를 재사용한다. 키를 새로 만들거나 교체하지 않는다.
4. `inventory/vmware/group_vars/all.yml`의 SSH host fingerprint 자리는 현재 placeholder다. VMware 콘솔 등 신뢰할 수 있는 경로에서 실제 Worker fingerprint를 확인한 뒤 값을 반영한다. 검증되지 않은 `ssh-keyscan` 결과를 신뢰값으로 쓰지 않는다.

## 3. Controller에서 코드와 변수 준비

Controller에서 실제 기존 프로젝트 디렉터리와 venv를 사용한다. 기존 프로젝트와 로컬 저장소의 차이를 확인하고 필요한 변경을 반영한 뒤 실행한다.

```bash
cd <기존 Controller 프로젝트 경로>
source /home/admin/dev312/bin/activate
git status --short --branch
git pull origin main
```

기존 Controller 기준 기록은 Rocky Linux 9.8, Python 3.12.16, ansible-core 2.21.6, 키 `/home/admin/.ssh/id_ed25519_ansible`다. Controller 역할은 이 venv와 키가 이미 있는지 검사하고 없으면 자동 생성하지 않는다.

이전 실행 기록에는 `controller_venv_path is undefined` 오류가 보고되었다. 현재 저장소에는 필요한 변수가 `group_vars/all.yml`에 있지만, playbook 실행 때 이 파일들이 실제로 로드되는지는 이 작업에서 Controller에 접속해 확인하지 않았다. 실행 전 변수를 로드할 방법을 확정한다. 아래 명령은 프로젝트 루트의 공통 변수, Agent 변수, VMware 환경 변수를 명시적으로 전달해 자동 탐색 경로에 의존하지 않는다.

Vault 암호는 안전하게 준비하고 터미널·로그·문서에 토큰이나 암호를 출력하지 않는다. Agent playbook은 `group_vars/vault.yml`을 명시적으로 불러온다.

## 4. Worker 자동 구성과 필요한 상태 확인

`inventory/vmware/hosts.ini`에는 w1/w2만 등록되어 있다. 아래 실행은 inventory 전체를 대상으로 하며, 별도 `--limit`을 주지 않는다. VMware 확인 플레이는 Controller의 `localhost`에서 수행되므로 `--limit k3s_agents`를 지정하면 그 확인 플레이가 실행 대상에서 빠진다.

```bash
ansible-playbook \
  -i inventory/vmware/hosts.ini \
  playbooks/vmware.yml \
  -e @group_vars/all.yml \
  -e @group_vars/k3s_agents.yml \
  -e @inventory/vmware/group_vars/all.yml \
  -e k3s_verify_network_smoke_tests=false \
  --ask-vault-pass
```

진입 플레이북은 Controller/SSH 준비, Python bootstrap, node identity, OS baseline, K3s Agent 구성, VMware 상태 확인 순으로 진행한다. Worker 변경 플레이는 한 번에 한 노드씩 수행하고 인벤토리 허용 목록·주소·Rocky 8.10을 확인한다. `m1`은 inventory에 없으며 플레이 대상이 아니다.

위 명령은 저장소 기본값에서 임시 Pod/Service를 만드는 네트워크 smoke test만 건너뛴다. 마지막 상태 확인은 보호된 기존 kubeconfig로 정확한 세 노드와 Ready 상태, CoreDNS/Flannel 실행 상태를 조회한다. 이것은 Worker 편입에 필요한 확인이다. 이 절차에는 추가 반복 시험을 두지 않는다.

완료 결과는 `k3s-m1`, `k3s-w1`, `k3s-w2` 세 노드가 기대한 주소로 Ready인지로 판단한다. 기존 서비스 장애가 실제 관찰될 때만 해당 서비스 소유자와 복구 범위를 정한다. 정상 확인을 위해 앱·DB·Vault를 재배포하지 않는다.

## 5. Controller 변경 공유와 문서 마감

Controller에서 Ansible 파일을 수정한 경우, 변경 파일만 검토해 커밋하고 `main`으로 push한다. Vault 평문, 암호, 개인키, kubeconfig 및 실행 로그의 비밀값은 커밋하지 않는다.

```bash
git status --short
git diff --check
git add <검토한 변경 파일>
git commit -m "<변경 내용>"
git push origin main
```

Windows 작업 PC에서 최신 커밋을 가져와 현재 상태를 공유한다.

```bash
cd ~/.codex/.chatgpt-projects/g-p-6ae9562511f48191951007aab941ec5a/IaC
git pull origin main
git log -1 --oneline
git status --short --branch
```

Controller에서 바뀐 코드나 실제 수행 결과가 설계와 다르면 이 저장소 기준으로 두 문서를 다시 갱신한다. 문서 커밋/push는 내용을 확인한 뒤 별도로 수행한다.

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|---|---|---|
| v1 | 2026-11-25 | Worker 재구축과 KT Cloud 후속 작업을 포함한 상세 절차 |
| v2 | 2026-11-26 | 실제 Ansible main 코드에 맞춰 VMware Worker 절차 정리. Controller 변수 로딩 이력, localhost 확인과 limit 상호작용, 임시 네트워크 smoke test, Controller→Git→Windows 공유 흐름 반영 |
