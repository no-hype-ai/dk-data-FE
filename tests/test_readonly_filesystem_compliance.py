"""Validate readOnlyRootFilesystem CronJobs also mount writable /tmp."""

from pathlib import Path

import yaml


def test_cronjobs_with_readonly_rootfs_have_tmp_emptydir():
    base_dir = Path(__file__).resolve().parents[1] / "k8s" / "base" / "ingestion"
    violations = []

    for manifest in sorted(base_dir.glob("cronjob-*.yaml")):
        with manifest.open("r", encoding="utf-8") as handle:
            docs = list(yaml.safe_load_all(handle))

        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "CronJob":
                continue

            cronjob_name = doc.get("metadata", {}).get("name", manifest.name)
            pod_spec = (
                doc.get("spec", {})
                .get("jobTemplate", {})
                .get("spec", {})
                .get("template", {})
                .get("spec", {})
            )
            containers = pod_spec.get("containers", []) or []
            volumes = pod_spec.get("volumes", []) or []
            emptydir_volume_names = {
                vol.get("name")
                for vol in volumes
                if isinstance(vol, dict) and vol.get("emptyDir") is not None
            }

            for container in containers:
                if not isinstance(container, dict):
                    continue
                container_name = container.get("name", "<unnamed>")
                security_context = container.get("securityContext", {}) or {}
                if security_context.get("readOnlyRootFilesystem") is not True:
                    continue

                mounts = container.get("volumeMounts", []) or []
                tmp_mount = next(
                    (
                        mount
                        for mount in mounts
                        if isinstance(mount, dict) and mount.get("mountPath") == "/tmp"
                    ),
                    None,
                )

                if tmp_mount is None:
                    violations.append(
                        f"{cronjob_name} ({manifest.name}) container '{container_name}': "
                        "readOnlyRootFilesystem=true but no /tmp volumeMount"
                    )
                    continue

                if tmp_mount.get("name") not in emptydir_volume_names:
                    violations.append(
                        f"{cronjob_name} ({manifest.name}) container '{container_name}': "
                        "/tmp volumeMount does not reference an emptyDir volume"
                    )

    assert not violations, "Non-compliant CronJobs:\n" + "\n".join(violations)
