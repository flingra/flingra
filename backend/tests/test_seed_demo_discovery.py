from collections import Counter
from datetime import date

import pytest
from sqlalchemy import text

from app.dependencies import db_session
from app import seed_demo_discovery
from app.seed_demo_discovery import build_demo_profiles, seed_demo_profiles


def test_demo_cohort_covers_all_nigerian_states_and_fct() -> None:
    profiles = build_demo_profiles("discover-nigeria-50", today=date(2026, 11, 24))

    state_counts = Counter(profile.state for profile in profiles)
    assert len(profiles) == 50
    assert len(state_counts) == 37
    assert sorted(state_counts.values()) == [1] * 24 + [2] * 13
    assert all(profile.email.endswith("@example.test") for profile in profiles)
    assert all(profile.display_name.startswith("Demo Member ") for profile in profiles)
    assert all(profile.birth_date < date(2005, 1, 1) for profile in profiles)
    assert {profile.identity for profile in profiles} == {"man", "woman"}


def test_demo_cohort_ids_are_validated_and_profiles_are_deterministic() -> None:
    first = build_demo_profiles("discover-nigeria-50", today=date(2026, 11, 24))
    second = build_demo_profiles("discover-nigeria-50", today=date(2026, 11, 24))

    assert [profile.account_id for profile in first] == [profile.account_id for profile in second]
    assert len({profile.email for profile in first}) == 50

    try:
        build_demo_profiles("Not a valid cohort")
    except ValueError as exc:
        assert "Cohort IDs" in str(exc)
    else:
        raise AssertionError("Invalid cohort ID should fail.")


def test_seed_demo_profiles_creates_test_records_and_is_idempotent(api_client, monkeypatch) -> None:
    client, _ = api_client
    monkeypatch.setattr("app.seed_demo_discovery.hash_password", lambda _: "test-password-hash")
    monkeypatch.setattr("app.seed_demo_discovery.generate_token", lambda: "test-token")
    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    try:
        created = seed_demo_profiles(db, client.app.state.settings, "discover-test")
        db.commit()
        assert created == 50

        assert (
            db.execute(
                text("SELECT COUNT(*) FROM accounts WHERE email_verified = TRUE")
            ).scalar_one()
            == 50
        )
        assert (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM profiles
                    WHERE demo_cohort_id = 'discover-test'
                      AND document_verification = 'verified'
                      AND moderation_status = 'approved'
                      AND onboarding_complete = TRUE
                    """
                )
            ).scalar_one()
            == 50
        )
        assert seed_demo_profiles(db, client.app.state.settings, "discover-test") == 0
    finally:
        db_generator.close()


def test_seed_command_defaults_to_dry_run_without_database_access(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        seed_demo_discovery,
        "get_engine",
        lambda *_: pytest.fail("A dry run must not connect to a database."),
    )
    seed_demo_discovery.main(["--cohort", "discover-test"])

    output = capsys.readouterr().out
    assert "Dry run: 50 synthetic profiles" in output
    assert "No database connection was opened." in output
