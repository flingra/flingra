import argparse
import getpass
import re
import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import get_settings
from app.database import get_engine
from app.security import hash_password

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ADMIN_ROLES = ("super_admin", "admin", "reviewer", "safety_admin", "auditor")


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision an admin account.")
    parser.add_argument("--role", choices=ADMIN_ROLES)
    args = parser.parse_args()

    email = input("Admin email: ").strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise SystemExit("Enter a valid email address.")

    password = getpass.getpass("Admin password (minimum 14 characters): ")
    if len(password) < 14:
        raise SystemExit("The admin password must be at least 14 characters.")
    confirmation = getpass.getpass("Confirm admin password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    try:
        with Session(get_engine(get_settings())) as db, db.begin():
            admin_count = db.execute(text("SELECT COUNT(*) FROM admin_users")).scalar_one()
            if admin_count == 0 and args.role not in {None, "super_admin"}:
                raise SystemExit("The first admin account must have the super_admin role.")
            if args.role == "super_admin":
                active_super_admins = db.execute(
                    text(
                        "SELECT COUNT(*) FROM admin_users "
                        "WHERE role = 'super_admin' AND disabled_at IS NULL"
                    )
                ).scalar_one()
                if active_super_admins >= 1:
                    raise SystemExit("Only one active super admin account is allowed.")
            role = args.role or ("super_admin" if admin_count == 0 else "reviewer")
            admin_id = uuid.uuid4().hex
            db.execute(
                text(
                    """
                    INSERT INTO admin_users (id, email, password_hash, role)
                    VALUES (:id, :email, :password_hash, :role)
                    """
                ),
                {
                    "id": admin_id,
                    "email": email,
                    "password_hash": hash_password(password),
                    "role": role,
                },
            )
            record_audit_event(
                db,
                None,
                event_type="admin.account.created",
                actor_type="system",
                actor_id=None,
                subject_account_id=None,
                outcome="success",
                metadata={"adminId": admin_id, "role": role},
            )
    except IntegrityError:
        raise SystemExit("An admin account with that email already exists.") from None
    print(f"Admin account created with role {role}.")


if __name__ == "__main__":
    main()
