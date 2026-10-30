import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Donor
from app.security import hash_password


def create_admin(email: str, full_name: str) -> None:
    try:
        email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
    except ValidationError as exc:
        raise SystemExit("Enter a valid administrator email address.") from exc
    password = getpass("Admin password (12+ characters): ")
    confirmation = getpass("Confirm admin password: ")
    if len(password) < 12:
        raise SystemExit("Admin password must contain at least 12 characters.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    with SessionLocal() as db:
        existing = db.scalar(select(Donor).where(Donor.email == email.lower()))
        if existing is not None:
            raise SystemExit("An account with this email already exists.")
        db.add(
            Donor(
                email=email.lower(),
                full_name=full_name,
                password_hash=hash_password(password),
                is_admin=True,
            )
        )
        db.commit()
    print(f"Administrator account created for {email.lower()}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage donor API administrator accounts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    admin_parser = subparsers.add_parser("create-admin", help="Create an administrator account.")
    admin_parser.add_argument("--email", required=True)
    admin_parser.add_argument("--name", required=True)
    arguments = parser.parse_args()
    if arguments.command == "create-admin":
        create_admin(arguments.email, arguments.name)


if __name__ == "__main__":
    main()
