"""Tests for the Hugging Face Space deploy script (deploy/hf_space.py); nothing is uploaded."""

import pytest

from deploy.hf_space import main, space_app_url, stage_committed_files


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    return stage_committed_files(tmp_path_factory.mktemp("space"))


def test_stage_contains_everything_the_dockerfile_copies(staged):
    for path in (
        "Dockerfile",
        "requirements.txt",
        "api/main.py",
        "core/crypto.py",
        "ml/features.py",
        "models/detector.joblib",
        "experiments/results/split.csv",
        "frontend/package-lock.json",
    ):
        assert (staged / path).is_file(), path


def test_stage_leaves_out_tests_docs_and_data(staged):
    for path in ("tests", "docs", "data", "notebooks", ".claude", "frontend/node_modules"):
        assert not (staged / path).exists(), path


def test_space_card_replaces_readme_and_points_hf_at_the_app_port(staged):
    card = (staged / "README.md").read_text(encoding="utf-8")

    assert card.startswith("---\n")
    assert "sdk: docker" in card
    assert "app_port: 8000" in card
    assert "EXPOSE 8000" in (staged / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("space_id", "url"),
    [
        ("Owner/StegoShield", "https://owner-stegoshield.hf.space"),
        ("my_org/stego.demo", "https://my-org-stego-demo.hf.space"),
    ],
)
def test_app_url_follows_the_hf_space_subdomain_rule(space_id, url):
    assert space_app_url(space_id) == url


def test_malformed_space_id_is_rejected_before_anything_runs(capsys):
    with pytest.raises(SystemExit):
        main(["--space", "no-slash", "--dry-run"])

    assert "expected OWNER/NAME" in capsys.readouterr().err
