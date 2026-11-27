import argparse
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings, get_settings
from app.database import get_engine
from app.security import generate_token, hash_password

COHORT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
INTERESTS = (
    "Afrobeats",
    "Photography",
    "Football",
    "Cooking",
    "Tech",
    "Fashion",
    "Hiking",
    "Movies",
    "Books",
    "Travel",
    "Fitness",
    "Gaming",
    "Comedy",
    "Dancing",
    "Art",
    "Music festivals",
    "Nightlife",
    "Fine dining",
    "Volunteering",
    "Faith & spirituality",
    "Entrepreneurship",
    "Cars",
    "Pets",
    "Wine & cocktails",
    "Yoga",
    "Poetry",
    "Anime",
    "Politics & current affairs",
)
LOCATIONS = (
    ("Abia", "Umuahia", 5.532, 7.486, None),
    ("Adamawa", "Yola", 9.203, 12.495, None),
    ("Akwa Ibom", "Uyo", 5.037, 7.912, ("Eket", 4.642, 7.924)),
    ("Anambra", "Awka", 6.212, 7.071, ("Onitsha", 6.150, 6.785)),
    ("Bauchi", "Bauchi", 10.316, 9.844, None),
    ("Bayelsa", "Yenagoa", 4.924, 6.264, None),
    ("Benue", "Makurdi", 7.732, 8.539, None),
    ("Borno", "Maiduguri", 11.833, 13.151, None),
    ("Cross River", "Calabar", 4.951, 8.323, None),
    ("Delta", "Asaba", 6.198, 6.734, ("Warri", 5.516, 5.750)),
    ("Ebonyi", "Abakaliki", 6.324, 8.113, None),
    ("Edo", "Benin City", 6.335, 5.603, ("Auchi", 7.068, 6.263)),
    ("Ekiti", "Ado-Ekiti", 7.623, 5.220, None),
    ("Enugu", "Enugu", 6.458, 7.546, ("Nsukka", 6.856, 7.395)),
    ("Gombe", "Gombe", 10.290, 11.167, None),
    ("Imo", "Owerri", 5.484, 7.035, None),
    ("Jigawa", "Dutse", 11.706, 9.339, None),
    ("Kaduna", "Kaduna", 10.510, 7.416, ("Zaria", 11.111, 7.722)),
    ("Kano", "Kano", 12.002, 8.592, ("Nassarawa", 11.986, 8.530)),
    ("Katsina", "Katsina", 12.990, 7.601, None),
    ("Kebbi", "Birnin Kebbi", 12.454, 4.197, None),
    ("Kogi", "Lokoja", 7.802, 6.734, None),
    ("Kwara", "Ilorin", 8.496, 4.542, None),
    ("Lagos", "Ikeja", 6.601, 3.351, ("Lekki", 6.470, 3.585)),
    ("Nasarawa", "Lafia", 8.493, 8.516, None),
    ("Niger", "Minna", 9.613, 6.556, None),
    ("Ogun", "Abeokuta", 7.147, 3.361, ("Sagamu", 6.848, 3.646)),
    ("Ondo", "Akure", 7.252, 5.193, None),
    ("Osun", "Osogbo", 7.782, 4.541, None),
    ("Oyo", "Ibadan", 7.378, 3.947, ("Ogbomosho", 8.134, 4.243)),
    ("Plateau", "Jos", 9.897, 8.858, ("Bukuru", 9.790, 8.870)),
    ("Rivers", "Port Harcourt", 4.815, 7.049, ("Eleme", 4.780, 7.120)),
    ("Sokoto", "Sokoto", 13.062, 5.243, None),
    ("Taraba", "Jalingo", 8.900, 11.363, None),
    ("Yobe", "Damaturu", 11.746, 11.960, None),
    ("Zamfara", "Gusau", 12.170, 6.664, None),
    ("FCT", "Wuse, Abuja", 9.076, 7.493, ("Garki, Abuja", 9.039, 7.496)),
)


@dataclass(frozen=True)
class DemoProfile:
    sequence: int
    account_id: str
    email: str
    display_name: str
    birth_date: date
    identity: str
    state: str
    area: str
    latitude: float
    longitude: float
    age_range: str
    interests: tuple[str, ...]


def _birth_date(age: int, today: date) -> date:
    try:
        return today.replace(year=today.year - age)
    except ValueError:
        return today.replace(year=today.year - age, day=28)


def build_demo_profiles(cohort_id: str, today: date | None = None) -> list[DemoProfile]:
    if not COHORT_PATTERN.fullmatch(cohort_id):
        raise ValueError("Cohort IDs must use lowercase letters, digits, or hyphens.")
    reference_date = today or date.today()
    locations = []
    for state, city, latitude, longitude, secondary in LOCATIONS:
        locations.append((state, city, latitude, longitude))
        if secondary is not None:
            secondary_city, secondary_latitude, secondary_longitude = secondary
            locations.append((state, secondary_city, secondary_latitude, secondary_longitude))
    if len(LOCATIONS) != 37 or len(locations) != 50:
        raise RuntimeError("The Nigeria demo location list must cover 37 locations and 50 profiles.")

    profiles = []
    for sequence, (state, city, latitude, longitude) in enumerate(locations, start=1):
        age = 22 + (sequence * 7 % 29)
        lower_age = (age // 5) * 5
        interests = tuple(INTERESTS[(sequence + offset * 3) % len(INTERESTS)] for offset in range(3))
        profiles.append(
            DemoProfile(
                sequence=sequence,
                account_id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"flingra-demo:{cohort_id}:{sequence}",
                ).hex,
                email=f"discover-{cohort_id}-{sequence:02d}@example.test",
                display_name=f"Demo Member {sequence:02d}",
                birth_date=_birth_date(age, reference_date),
                identity="woman" if sequence % 2 else "man",
                state=state,
                area=f"{city}, {state}",
                latitude=latitude,
                longitude=longitude,
                age_range=f"{lower_age}–{lower_age + 5}",
                interests=interests,
            )
        )
    return profiles


def seed_demo_profiles(db: Session, settings: Settings, cohort_id: str) -> int:
    profiles = build_demo_profiles(cohort_id)
    existing_count = db.execute(
        text("SELECT COUNT(*) FROM profiles WHERE demo_cohort_id = :cohort_id"),
        {"cohort_id": cohort_id},
    ).scalar_one()
    if existing_count == len(profiles):
        return 0
    if existing_count:
        raise RuntimeError(
            f"Cohort {cohort_id!r} is only partially present; refusing to alter existing records."
        )

    for profile in profiles:
        db.execute(
            text(
                """
                INSERT INTO accounts (
                    id, email, identifier, identifier_type, password_hash, date_of_birth,
                    gender, terms_version, privacy_version, email_verified, account_state
                )
                VALUES (
                    :id, :email, :email, 'email', :password_hash, :birth_date,
                    :identity, :terms_version, :privacy_version, TRUE, 'active'
                )
                """
            ),
            {
                "id": profile.account_id,
                "email": profile.email,
                "password_hash": hash_password(generate_token()),
                "birth_date": profile.birth_date,
                "identity": profile.identity,
                "terms_version": settings.terms_version,
                "privacy_version": settings.privacy_version,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO profiles (
                    account_id, username, display_name, bio, photos, videos, age_range, area,
                    distance_km, interests, discoverable_by, wants_to_discover,
                    identity, show_identity, subscription_tier, moderation_status,
                    onboarding_complete, document_verification, demo_cohort_id,
                    latitude, longitude
                )
                VALUES (
                    :account_id, :username, :display_name, :bio, '[]', NULL, :age_range, :area,
                    0, :interests, 'everyone', 'everyone', :identity, TRUE, 'free',
                    'approved', TRUE, 'verified', :cohort_id, :latitude, :longitude
                )
                """
            ),
            {
                "account_id": profile.account_id,
                "username": f"demo_{profile.account_id}",
                "display_name": profile.display_name,
                "bio": "Synthetic test profile for Discover.",
                "age_range": profile.age_range,
                "area": profile.area,
                "interests": json.dumps(profile.interests),
                "identity": profile.identity,
                "cohort_id": cohort_id,
                "latitude": profile.latitude,
                "longitude": profile.longitude,
            },
        )
        record_audit_event(
            db,
            None,
            event_type="test_profile.seeded",
            actor_type="system",
            actor_id=None,
            subject_account_id=profile.account_id,
            outcome="success",
            metadata={"cohortId": cohort_id, "sequence": profile.sequence},
        )
    return len(profiles)


def refresh_demo_profile_interests(db: Session, cohort_id: str) -> int:
    profiles = build_demo_profiles(cohort_id)
    expected_account_ids = {profile.account_id for profile in profiles}
    existing_account_ids = set(
        db.execute(
            text("SELECT account_id FROM profiles WHERE demo_cohort_id = :cohort_id"),
            {"cohort_id": cohort_id},
        ).scalars()
    )
    if existing_account_ids != expected_account_ids:
        raise RuntimeError(
            f"Cohort {cohort_id!r} is missing or inconsistent; refusing to refresh interests."
        )

    for profile in profiles:
        db.execute(
            text(
                """
                UPDATE profiles
                SET interests = :interests
                WHERE account_id = :account_id AND demo_cohort_id = :cohort_id
                """
            ),
            {
                "interests": json.dumps(profile.interests),
                "account_id": profile.account_id,
                "cohort_id": cohort_id,
            },
        )
    return len(profiles)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Preview or seed a clearly marked synthetic Discover cohort."
    )
    parser.add_argument("--cohort", default="discover-nigeria-50")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the cohort to the configured MySQL database; preview is the default.",
    )
    parser.add_argument(
        "--confirm-private-database",
        action="store_true",
        help="Confirm that the configured database is private and not serving real users.",
    )
    parser.add_argument(
        "--refresh-interests",
        action="store_true",
        help="Update interests on an existing complete demo cohort.",
    )
    arguments = parser.parse_args(argv)
    profiles = build_demo_profiles(arguments.cohort)
    if not arguments.apply:
        if arguments.refresh_interests:
            raise SystemExit("--refresh-interests requires --apply.")
        print(
            f"Dry run: {len(profiles)} synthetic profiles across "
            f"{len({profile.state for profile in profiles})} Nigerian states/FCT. "
            "No database connection was opened."
        )
        return

    settings = get_settings()
    if not settings.demo_profiles_enabled:
        raise SystemExit("Set FLINGRA_DEMO_PROFILES_ENABLED=true only in the private test environment.")
    if not arguments.confirm_private_database:
        raise SystemExit("Re-run with --confirm-private-database after checking the configured database.")
    engine = get_engine(settings)
    if engine.dialect.name != "mysql":
        raise SystemExit("Demo profiles can only be seeded into the configured MySQL database.")

    if arguments.refresh_interests:
        with Session(engine) as db, db.begin():
            refreshed_count = refresh_demo_profile_interests(db, arguments.cohort)
        print(
            f"Refreshed interests for {refreshed_count} demo profiles "
            f"in cohort {arguments.cohort!r}."
        )
        return

    with Session(engine) as db, db.begin():
        created_count = seed_demo_profiles(db, settings, arguments.cohort)
    if created_count:
        print(f"Seeded {created_count} demo profiles in cohort {arguments.cohort!r}.")
    else:
        print(f"Cohort {arguments.cohort!r} already exists; no records were changed.")


if __name__ == "__main__":
    main()
