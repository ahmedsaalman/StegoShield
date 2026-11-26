"""Static checks on the Oracle Cloud deployment files (deploy/oracle/); nothing is deployed."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ORACLE_DIR = Path(__file__).resolve().parent.parent / "deploy" / "oracle"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load((ORACLE_DIR / "compose.yaml").read_text(encoding="utf-8"))


def test_app_builds_the_project_dockerfile(compose):
    assert (ORACLE_DIR / compose["services"]["app"]["build"]["context"] / "Dockerfile").is_file()


def test_only_caddy_is_reachable_from_outside(compose):
    """The app trusts X-Forwarded-For, which is only safe while Caddy is its sole client."""
    assert "ports" not in compose["services"]["app"]
    assert compose["services"]["app"]["environment"]["FORWARDED_ALLOW_IPS"] == "*"
    assert compose["services"]["caddy"]["ports"] == ["80:80", "443:443", "443:443/udp"]


def test_app_runs_with_hsts_and_a_cpu_job_cap(compose):
    environment = compose["services"]["app"]["environment"]

    assert environment["STEGOSHIELD_ENABLE_HSTS"] == "1"
    assert int(environment["STEGOSHIELD_MAX_CONCURRENT_JOBS"]) >= 1


def test_caddy_proxies_to_the_app_port():
    assert "reverse_proxy app:8000" in (ORACLE_DIR / "Caddyfile").read_text(encoding="utf-8")


def test_deploy_key_is_restricted_to_the_update_script():
    setup = (ORACLE_DIR / "setup.sh").read_text(encoding="utf-8")

    assert 'command=\\"bash $APP_DIR/deploy/oracle/update.sh\\"' in setup
    assert "no-port-forwarding" in setup and "no-pty" in setup


@pytest.mark.parametrize("script", ["setup.sh", "update.sh"])
def test_shell_scripts_parse(script):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")

    subprocess.run([bash, "-n", str(ORACLE_DIR / script)], check=True)
