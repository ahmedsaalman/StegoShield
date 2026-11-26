"""Tests for the Hugging Face Space deploy script (deploy/hf_space.py); nothing is uploaded."""

import pytest

from deploy.hf_space import (
    PublishPermissionError,
    check_token_can_publish,
    main,
    space_app_url,
    stage_committed_files,
)


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


def identity(role="write", orgs=()):
    return {"name": "alice", "orgs": [{"name": org} for org in orgs], "auth": {"accessToken": {"role": role}}}


@pytest.mark.parametrize("space_id", ["alice/stegoshield", "Alice/stegoshield", "uni-lab/stegoshield"])
def test_token_may_publish_to_its_own_account_or_its_orgs(space_id):
    check_token_can_publish(identity(orgs=["uni-lab"]), space_id)


def test_token_from_another_account_is_named_in_the_error():
    with pytest.raises(PublishPermissionError, match=r"belongs to .*'alice'.*cannot publish under 'bob'"):
        check_token_can_publish(identity(), "bob/stegoshield")


def test_read_only_token_is_rejected_before_uploading():
    with pytest.raises(PublishPermissionError, match="read-only"):
        check_token_can_publish(identity(role="read"), "alice/stegoshield")
