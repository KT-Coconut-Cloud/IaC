#!/usr/bin/env python3
"""Temporary K3s network smoke check; all created Kubernetes objects are cleaned up."""
import argparse
import json
import os
import subprocess
import sys
import uuid


def kubectl(*args, input_text=None):
    result = subprocess.run(
        ["kubectl", *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "kubectl command failed")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    workers = [name for name in args.workers.split(",") if name]
    if len(workers) != 2 or len(set(workers)) != 2:
        raise RuntimeError("Exactly two distinct worker node names are required.")

    nodes = json.loads(kubectl("get", "nodes", "-o", "json"))["items"]
    by_name = {node["metadata"]["name"]: node for node in nodes}
    missing = [name for name in workers if name not in by_name]
    if missing:
        raise RuntimeError("Expected worker nodes not found: " + ", ".join(missing))

    node_ips = {}
    for name in workers:
        addresses = by_name[name].get("status", {}).get("addresses", [])
        match = next((item["address"] for item in addresses if item["type"] == "InternalIP"), None)
        if not match:
            raise RuntimeError("No InternalIP found for " + name)
        node_ips[name] = match

    namespace = "ansible-net-smoke-" + uuid.uuid4().hex[:8]
    created = False
    try:
        kubectl("create", "namespace", namespace)
        created = True
        for index, node_name in enumerate(workers):
            pod_name = "smoke-" + str(index + 1)
            pod = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": pod_name,
                    "namespace": namespace,
                    "labels": {"app": "ansible-network-smoke"},
                },
                "spec": {
                    "nodeName": node_name,
                    "restartPolicy": "Never",
                    "containers": [{
                        "name": "http",
                        "image": args.image,
                        "imagePullPolicy": "IfNotPresent",
                        "command": [
                            "sh", "-c",
                            "mkdir -p /www && printf ok >/www/index.html && exec httpd -f -p 8080 -h /www",
                        ],
                        "ports": [{"containerPort": 8080}],
                    }],
                },
            }
            kubectl("apply", "-f", "-", input_text=json.dumps(pod))
            kubectl("wait", "--for=condition=Ready", "pod/" + pod_name, "-n", namespace, "--timeout=180s")

        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "smoke", "namespace": namespace},
            "spec": {
                "type": "NodePort",
                "selector": {"app": "ansible-network-smoke"},
                "ports": [{"name": "http", "port": 8080, "targetPort": 8080}],
            },
        }
        kubectl("apply", "-f", "-", input_text=json.dumps(service))
        service_obj = json.loads(kubectl("get", "service", "smoke", "-n", namespace, "-o", "json"))
        node_port = service_obj["spec"]["ports"][0]["nodePort"]
        pod_ips = []
        for index in range(2):
            pod = json.loads(kubectl("get", "pod", "smoke-" + str(index + 1), "-n", namespace, "-o", "json"))
            pod_ips.append(pod["status"]["podIP"])

        for source_index in range(2):
            source = "smoke-" + str(source_index + 1)
            peer_ip = pod_ips[1 - source_index]
            response = kubectl(
                "exec", source, "-n", namespace, "--",
                "wget", "-q", "-T", "10", "-O", "-", "http://" + peer_ip + ":8080/",
            )
            if response != "ok":
                raise RuntimeError("Cross-node Pod TCP response was unexpected.")
            response = kubectl(
                "exec", source, "-n", namespace, "--",
                "wget", "-q", "-T", "10", "-O", "-",
                "http://smoke." + namespace + ".svc.cluster.local:8080/",
            )
            if response != "ok":
                raise RuntimeError("Cluster DNS/Service response was unexpected.")
            for node_name in workers:
                response = kubectl(
                    "exec", source, "-n", namespace, "--",
                    "wget", "-q", "-T", "10", "-O", "-",
                    "http://" + node_ips[node_name] + ":" + str(node_port) + "/",
                )
                if response != "ok":
                    raise RuntimeError("NodePort response was unexpected.")

        print("Cross-node Pod TCP, cluster DNS/Service, and NodePort checks passed.")
    finally:
        if created:
            subprocess.run(
                ["kubectl", "delete", "namespace", namespace, "--wait=true", "--timeout=90s"],
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Network smoke check failed: " + str(exc), file=sys.stderr)
        sys.exit(1)
