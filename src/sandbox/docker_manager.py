import asyncio
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
from docker.errors import APIError, BuildError, DockerException

from src.config import settings


@dataclass
class SandboxConfig:
    image: str = "code-reviewer-sandbox:latest"
    timeout_seconds: int = 300
    memory_limit: str = "2g"
    cpu_limit: str = "2"
    workdir: str = "/workspace/repo"
    network_disabled: bool = True


@dataclass
class SandboxResult:
    sandbox_id: str
    container_id: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class DockerSandboxManager:
    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._client: docker.DockerClient | None = None
        self._containers: dict[str, Any] = {}

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def create_sandbox(self, sandbox_id: str | None = None) -> str:
        sandbox_id = sandbox_id or str(uuid.uuid4())[:12]

        try:
            container = self.client.containers.create(
                self.config.image,
                command="tail -f /dev/null",
                detach=True,
                name=f"code-reviewer-{sandbox_id}",
                mem_limit=self.config.memory_limit,
                nano_cpus=int(float(self.config.cpu_limit) * 1e9),
                network_disabled=self.config.network_disabled,
                working_dir=self.config.workdir,
                labels={"sandbox_id": sandbox_id, "created_by": "code-reviewer"},
            )

            self._containers[sandbox_id] = container
            return sandbox_id

        except DockerException as e:
            raise RuntimeError(f"Failed to create sandbox: {e}") from e

    def start_sandbox(self, sandbox_id: str) -> bool:
        container = self._get_container(sandbox_id)
        if container is None:
            return False

        try:
            container.start()
            return True
        except DockerException:
            return False

    def stop_sandbox(self, sandbox_id: str) -> bool:
        container = self._get_container(sandbox_id)
        if container is None:
            return True

        try:
            container.stop(timeout=10)
            return True
        except DockerException:
            return False

    def remove_sandbox(self, sandbox_id: str) -> bool:
        container = self._get_container(sandbox_id)
        if container is None:
            return True

        try:
            container.remove(force=True)
            if sandbox_id in self._containers:
                del self._containers[sandbox_id]
            return True
        except DockerException:
            return False

    def copy_files_to_sandbox(
        self, sandbox_id: str, source_path: Path, dest_path: str | None = None
    ) -> bool:
        container = self._get_container(sandbox_id)
        if container is None:
            return False

        dest_path = dest_path or self.config.workdir

        try:
            if source_path.is_file():
                with tempfile.NamedTemporaryFile() as tmp:
                    shutil.copy(source_path, tmp.name)
                    with open(tmp.name, "rb") as f:
                        container.put_archive(str(Path(dest_path).parent), self._create_tar(f, source_path.name))
            else:
                with tempfile.NamedTemporaryFile() as tmp:
                    tar_path = self._create_tar_from_dir(source_path, tmp.name)
                    with open(tar_path, "rb") as f:
                        container.put_archive(dest_path, f.read())

            return True
        except Exception:
            return False

    def _create_tar(self, file_obj: Any, name: str) -> bytes:
        import io
        import tarfile

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name=name)
            content = file_obj.read()
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

        return tar_stream.getvalue()

    def _create_tar_from_dir(self, source_dir: Path, dest_path: str) -> str:
        import tarfile

        with tarfile.open(dest_path, "w") as tar:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(source_dir)
                    tar.add(file_path, arcname=arcname)

        return dest_path

    def execute_in_sandbox(
        self,
        sandbox_id: str,
        command: list[str],
        workdir: str | None = None,
        timeout: int | None = None,
    ) -> SandboxResult:
        container = self._get_container(sandbox_id)
        if container is None:
            return SandboxResult(
                sandbox_id=sandbox_id,
                container_id="",
                success=False,
                exit_code=-1,
                stdout="",
                stderr="Container not found",
                duration_ms=0,
            )

        timeout = timeout or self.config.timeout_seconds
        workdir = workdir or self.config.workdir

        import time

        start_time = time.time()

        try:
            exit_code, output = container.exec_run(
                cmd=command,
                workdir=workdir,
                demux=True,
            )

            stdout = (output[0] or b"").decode("utf-8", errors="replace")
            stderr = (output[1] or b"").decode("utf-8", errors="replace")

            duration_ms = int((time.time() - start_time) * 1000)

            return SandboxResult(
                sandbox_id=sandbox_id,
                container_id=container.id,
                success=exit_code == 0,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return SandboxResult(
                sandbox_id=sandbox_id,
                container_id=container.id if container else "",
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
            )

    def _get_container(self, sandbox_id: str) -> Any:
        if sandbox_id in self._containers:
            return self._containers[sandbox_id]

        try:
            containers = self.client.containers.list(
                all=True,
                filters={"name": f"code-reviewer-{sandbox_id}"},
            )
            if containers:
                self._containers[sandbox_id] = containers[0]
                return containers[0]
        except DockerException:
            pass

        return None

    def build_sandbox_image(self, dockerfile_path: Path | None = None) -> bool:
        dockerfile_path = dockerfile_path or Path("docker/sandbox/Dockerfile.sandbox")

        if not dockerfile_path.exists():
            raise FileNotFoundError(f"Dockerfile not found: {dockerfile_path}")

        try:
            self.client.images.build(
                path=str(dockerfile_path.parent),
                dockerfile=str(dockerfile_path),
                tag=self.config.image,
                rm=True,
            )
            return True
        except (BuildError, APIError) as e:
            raise RuntimeError(f"Failed to build sandbox image: {e}") from e

    def list_sandboxes(self) -> list[dict[str, Any]]:
        try:
            containers = self.client.containers.list(
                all=True,
                filters={"label": "created_by=code-reviewer"},
            )

            return [
                {
                    "sandbox_id": c.labels.get("sandbox_id", ""),
                    "container_id": c.id,
                    "status": c.status,
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else "",
                }
                for c in containers
            ]
        except DockerException:
            return []

    def cleanup_all_sandboxes(self) -> int:
        containers = self.list_sandboxes()
        cleaned = 0

        for container_info in containers:
            if self.remove_sandbox(container_info["sandbox_id"]):
                cleaned += 1

        return cleaned


class LocalExecutor:
    def __init__(self, workdir: Path | None = None):
        self.workdir = workdir or Path.cwd()

    def execute(
        self,
        command: list[str],
        timeout: int = 300,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        import time

        start_time = time.time()

        merged_env = subprocess.os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            result = subprocess.run(
                command,
                cwd=str(self.workdir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=merged_env,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            return SandboxResult(
                sandbox_id="local",
                container_id="local",
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return SandboxResult(
                sandbox_id="local",
                container_id="local",
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return SandboxResult(
                sandbox_id="local",
                container_id="local",
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
            )
