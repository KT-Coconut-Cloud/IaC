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

The controller setup playbook checks the existing venv and key pair, enforces private-key permissions, verifies SSH host fingerprints against values supplied from trusted consoles, and adds a dedicated SSH config include while preserving existing config. It may install the pinned ansible.posix collection if missing. Review the task before running it on the controller.

## Required values before a future run

1. Fill KT Cloud private IPs and the image's initial SSH login user in inventory/ktcloud/hosts.ini and bootstrap.ini. In bootstrap.ini, point to the existing initial access key without putting that key in this repository.
2. Fill SHA256 Ed25519 SSH host-key fingerprints in each inventory's `group_vars/all.yml` after checking them through a trusted VMware or EC2 console. VMware values remain in `inventory/vmware/group_vars/all.yml`; shared controller and cluster defaults are in `playbooks/group_vars/all.yml`. Do not trust an unverified ssh-keyscan result.
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

Run commands from the repository root so `ansible.cfg` relative paths resolve consistently. For VMware, set VMWARE_KUBECONFIG and supply the vaulted existing VMware join token before agent installation:

    ansible-playbook -i inventory/vmware/hosts.ini playbooks/controller_setup.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/os_bootstrap.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/node_identity.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/os_baseline.yml
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/k3s_agent.yml --ask-vault-pass
    ansible-playbook -i inventory/vmware/hosts.ini playbooks/cluster_verify_vmware.yml

The shared `group_vars/all.yml`, `group_vars/k3s_agents.yml`, and `group_vars/k3s_servers.yml` are stored under `playbooks/group_vars/`, where Ansible's `host_group_vars` plugin discovers them for playbooks in this directory. Environment-specific values stay under each inventory's `group_vars/` and remain separate. The encrypted vault remains at repository-root `group_vars/vault.yml` and is loaded explicitly by the server and agent plays. The combined vmware.yml and ktcloud.yml entry points run these stages in order for nodes that already accept the dedicated key. A fresh KT Cloud deployment must use the staged bootstrap flow first, because its initial connection uses the image-provided login key. Staged commands are recommended for review between changes. Both paths change node state. Do not run until all placeholders, tokens, host fingerprints, release confirmation, and network prerequisites have been reviewed.

The optional reboot recovery playbook reboots one node at a time and requires the explicit extra variable reboot_recovery_authorized=true. Use it only after a separate maintenance approval:

    ansible-playbook -i inventory/ktcloud/hosts.ini playbooks/reboot_verify.yml -e reboot_recovery_authorized=true

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

These checks do not contact or modify managed nodes. The KT Cloud inventory must contain real host addresses/users before it can be used for connection checks; required SHA256 fingerprints and the encrypted vault file must be supplied before a run. The Python smoke verifier can be syntax parsed with Python 3 on the controller. Local preparation on this Windows workstation could not run Ansible or Python syntax parsers because those tools are not installed here.

Changes should be reviewed locally and then committed/pushed manually by the repository owner. Never commit secret files.
