"""Static checks on the VM deployment files (deploy/vm/, .github/workflows/deploy.yml); nothing is deployed."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
VM_DIR = REPO_ROOT / "deploy" / "vm"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load((VM_DIR / "compose.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8"))


def test_only_caddy_is_reachable_from_outside(compose):
    """The app trusts X-Forwarded-For, which is only safe while Caddy is its sole client."""
    assert "ports" not in compose["services"]["app"]
    assert compose["services"]["app"]["environment"]["FORWARDED_ALLOW_IPS"] == "*"
    assert compose["services"]["caddy"]["ports"] == ["80:80", "443:443", "443:443/udp"]


def test_defaults_fit_a_one_gigabyte_vm(compose):
    app = compose["services"]["app"]

    assert "--workers=${APP_WORKERS:-1}" in app["command"]
    assert app["environment"]["STEGOSHIELD_MAX_CONCURRENT_JOBS"] == "${MAX_CONCURRENT_JOBS:-1}"
    assert app["environment"]["STEGOSHIELD_MAX_IMAGE_PIXELS"] == "${MAX_IMAGE_PIXELS:-1048576}"
    assert app["environment"]["STEGOSHIELD_ENABLE_HSTS"] == "1"


def test_vm_runs_the_image_the_workflow_publishes(compose, workflow):
    image = workflow["env"]["IMAGE"]

    assert compose["services"]["app"]["image"] == f"${{APP_IMAGE:-{image}}}:${{APP_IMAGE_TAG:-latest}}"


def test_deploy_waits_for_tests_and_image(workflow):
    assert workflow["jobs"]["image"]["needs"] == "test"
    assert workflow["jobs"]["deploy"]["needs"] == "image"


def test_caddy_proxies_to_the_app_port():
    assert "reverse_proxy app:8000" in (VM_DIR / "Caddyfile").read_text(encoding="utf-8")


def test_deploy_key_is_restricted_to_the_update_script():
    setup = (VM_DIR / "setup.sh").read_text(encoding="utf-8")

    assert 'command=\\"bash $APP_DIR/deploy/vm/update.sh\\"' in setup
    assert "no-port-forwarding" in setup and "no-pty" in setup


@pytest.mark.parametrize("argument", ["main; rm -rf ~", "abc123", "../../etc"])
def test_update_rejects_anything_but_a_full_commit_sha(argument, tmp_path):
    bash = shutil.which("bash")
    git = shutil.which("git")
    if bash is None or git is None:
        pytest.skip("bash and git required")
    repo = _repo_with_update_script(tmp_path, git)

    result = subprocess.run([bash, str(repo / "deploy/vm/update.sh"), argument], capture_output=True, text=True)

    assert result.returncode == 2
    assert "expected a 40-character commit sha" in result.stderr


@pytest.mark.parametrize("script", ["setup.sh", "update.sh"])
def test_shell_scripts_parse(script):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")

    subprocess.run([bash, "-n", str(VM_DIR / script)], check=True)


def _repo_with_update_script(tmp_path: Path, git: str) -> Path:
    """A clone whose origin has a main branch, so update.sh gets as far as validating its argument."""
    origin = tmp_path / "origin"
    (origin / "deploy" / "vm").mkdir(parents=True)
    shutil.copy(VM_DIR / "update.sh", origin / "deploy" / "vm" / "update.sh")
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    for command in (["init", "-q", "-b", "main"], ["add", "."], [*identity, "commit", "-q", "-m", "init"]):
        subprocess.run([git, *command], cwd=origin, check=True)
    clone = tmp_path / "clone"
    subprocess.run([git, "clone", "-q", str(origin), str(clone)], check=True)
    return clone
