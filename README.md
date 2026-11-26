# IaC Ansible: Rocky Linux 8.10 K3s

This repository defines a guarded Ansible workflow for two separate K3s environments:

- VMware: the already-existing control-plane node k3s-m1 is external and is never inventoried or modified. Only VMware w1 and w2 are managed as agents.
- KT Cloud: a new m1 server and w1/w2 agents are managed from the KT Cloud inventory.

The latest project instruction disables and stops firewalld on managed workers and KT Cloud nodes. SELinux remains Enforcing. Cloud security-group rules are outside this repository and are not changed.

## Safety boundaries

- VMware inventory contains exactly w1 and w2. VMware m1 must not be added to it.
- Every mutating node playbook checks the exact environment allowlist and expected host address. Most use serial execution and fail fast.
- K3s installation is blocked until the pinned version is explicitly confirmed. Existing non-matching installations and unowned configuration files are preserved and cause a stop.
- Duplicate machine IDs or SSH host keys are repaired only when detected within the selected environment. New host keys are read over the existing authenticated session and recorded before SSH reconnects.
- Existing controller SSH keys are reused; this project does not create or replace private keys. Public-key and token tasks suppress secret-bearing output.
- K3s tokens belong only in an Ansible Vault encrypted file. Do not add private keys, kubeconfig, tokens, passwords, cloud credentials, or secret outputs to Git.
- Network smoke checks create temporary pods and a service in a uniquely named namespace, then remove that namespace. These checks are not read-only.
- No playbook has been run against a VM, EC2 instance, or controller as part of preparing this repository.

## Before using it on the controller

First review this directory against the existing /home/admin/ansible-k3s project. Do not copy over that project or overwrite its files. The intended controller already has Rocky Linux 9.8, the /home/admin/dev312 virtual environment, ansible-core 2.21.6, and the existing key pair at /home/admin/.ssh/id_ed25519_ansible. Keep those credentials outside this repository.

The controller setup playbook checks the existing venv and key pair, enforces private-key permissions, and adds a dedicated SSH config include while preserving existing config. SSH trust uses `accept-new` only for this repository's Ansible connections: the first key is recorded automatically, while a changed known key is still rejected. It may install the pinned ansible.posix collection if missing.

## Required values before a future run

1. Fill KT Cloud private IPs and the image's initial SSH login user in inventory/ktcloud/hosts.ini and bootstrap.ini. In bootstrap.ini, point to the existing initial access key without putting that key in this repository.
2. Fill the target addresses and login users in each inventory. SSH first-use trust is configured only for this repository; an existing changed host key still fails closed.
3. Set k3s_version_confirmed to true only after confirming that the release is available and that the VMware server's existing version is compatible. The current version value is a proposed pin, not a live-verified release.
4. Create an encrypted group_vars/vault.yml with the existing VMware join token and the new KT Cloud cluster token. Keep the vault password outside Git.
5. Set VMWARE_KUBECONFIG to the existing protected VMware kubeconfig path for VMware verification. Install/locate kubectl in the existing controller environment.
6. Confirm KT Cloud security groups allow required K3s API, node-to-node, overlay, DNS, and NodePort traffic. This project intentionally does not change cloud firewall rules.

Rocky Linux 8.10 nodes are expected to use Python 3.9.25 at /usr/bin/python3.9 for Ansible while leaving the system /usr/bin/python3 default untouched. The bootstrap uses raw commands until that interpreter is available.

## Suggested staged workflow

Run from the existing controller virtual environment after reviewing all external values. Use the bootstrap inventory for the first connection to KT Cloud; it uses the image's initial login identity. Once the existing dedicated public key has been installed and the dedicated-key login works, switch to the normal KT Cloud inventory.

    ansible-playbook -i inventory/ktcloud/bootstrap.ini playbooks/controller_setup.yml
    ansible-playbook -i inventory/ktcloud/bootstrap.ini playbooks/os_bootstrap.yml
    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/os_bootstrap.yml
    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/node_identity.yml
    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/os_baseline.yml
    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/k3s_server.yml --ask-vault-pass
    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/k3s_agent.yml --ask-vault-pass
    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/cluster_verify_ktcloud.yml

Run commands from the repository root so `ansible.cfg` relative paths resolve consistently. VMware Agent installation needs the vaulted existing VMware join token and reachable m1 API; kubeconfig is only needed for the separate post-install verification:

    ansible-playbook -i inventory/vmware/hosts.ini playbooks/controller_setup.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/os_bootstrap.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/node_identity.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/os_baseline.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/k3s_agent.yml --ask-vault-pass
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/cluster_verify_vmware.yml

The shared `group_vars/all.yml`, `group_vars/k3s_agents.yml`, and `group_vars/k3s_servers.yml` are stored under `playbooks/group_vars/`, where Ansible's `host_group_vars` plugin discovers them for playbooks in this directory. Environment-specific values stay under each inventory's `group_vars/` and remain separate. The encrypted vault remains at repository-root `group_vars/vault.yml` and is loaded explicitly by the server and agent plays. `vmware.yml` runs controller setup, bootstrap, identity, baseline, and agent installation; cluster verification is a separate required step. With `--limit w1` or `--limit w2`, identity collection only contacts selected workers. A batch run targets both. `ktcloud.yml` retains its integrated flow. A fresh KT Cloud deployment must use the staged bootstrap flow first, because its initial connection uses the image-provided login key.

The optional reboot recovery playbook reboots one node at a time and requires the explicit extra variable reboot_recovery_authorized=true. Use it only after a separate maintenance approval:

    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/reboot_verify.yml -e reboot_recovery_authorized=true

### VMware w1-only staged execution

Run from the repository root in the existing controller virtual environment. `--limit w1` restricts all remote play targets to w1; identity facts are compared among selected hosts only. The pre-install check requires the existing K3s API to be reachable from the worker. Then run the separate controller-side cluster verification after configuring kubeconfig. It reads Kubernetes state, and network smoke resources are disabled by default. Agent join and cluster reads use the existing m1 API endpoint without managing m1 over SSH or changing its OS, K3s configuration, or workloads.

    ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml --limit w1 --ask-vault-pass
    VMWARE_KUBECONFIG=/protected/path/to/kubeconfig ansible-playbook -i inventory/vmware/hosts.ini playbooks/cluster_verify_vmware.yml

K3s agent installation does not require a kubeconfig. The separate verification command does. Network smoke tests remain disabled by default. Failed joins may leave local agent files or a Kubernetes Node object; removal is a separate recovery operation.

## Local validation

On the controller, install the pinned collection and parse the inventories before any execution:

    ansible-galaxy collection install -r collections/requirements.yml
    ansible-inventory -i inventory/vmware/hosts.ini --playbook-dir playbooks --graph
    ansible-inventory -i inventory/ktcloud/bootstrap.ini --playbook-dir playbooks --graph
    ansible-inventory -i inventory/ktcloud/hosts.ini --playbook-dir playbooks --graph

For `ansible-inventory`, pass `--playbook-dir playbooks` so the shared group variables beside the playbooks are loaded too. To inspect only the non-secret values needed for the VMware worker run:

    ansible-inventory -i inventory/vmware/hosts.ini --playbook-dir playbooks --host w1 | python3 -c 'import json,sys; d=json.load(sys.stdin); keys=("controller_venv_path","target_environment","k3s_service_name","k3s_node_role","k3s_server_url"); print(json.dumps({k:d.get(k) for k in keys}, indent=2))'

Then run syntax checks for each playbook using the matching inventory. For example:

    ansible-playbook -i inventory/vmware/hosts.ini playbooks/vmware.yml --syntax-check
    ansible-playbook -i inventory/ktcloud/bootstrap.ini playbooks/os_bootstrap.yml --syntax-check
    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/ktcloud.yml --syntax-check

These checks do not contact or modify managed nodes. On `k3s-hq`, run Ansible from `/home/admin/IaC` with the existing `/home/admin/dev312` environment. The VMware inventory variable probe and `playbooks/vmware.yml --syntax-check` have been verified in that environment; shared variables such as `controller_venv_path` load from `playbooks/group_vars/` for playbook runs. When using `ansible-inventory`, pass `--playbook-dir playbooks` to load those same variables. The VMware worker playbooks have not been run. Read-only SSH checks found both worker addresses reporting `localhost.localdomain` and `k3s-agent` inactive, while `VMWARE_KUBECONFIG` was unavailable and the inventory still requires console-verified host fingerprints. Confirm worker identities and cluster state before any mutating run. The KT Cloud inventory still contains placeholders and requires real addresses, login users, verified host fingerprints, and the encrypted vault before use.

Changes should be reviewed locally and then committed/pushed manually by the repository owner. Never commit secret files.
