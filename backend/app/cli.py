import argparse
from getpass import getpass

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import User
from .security import hash_password


def create_admin() -> None:
    email = input("Admin email: ").strip().lower()
    full_name = input("Admin name: ").strip()
    password = getpass("Password (at least 10 characters): ")
    if len(password) < 10:
        raise SystemExit("Password must contain at least 10 characters.")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("An account with that email already exists.")
        db.add(User(email=email, full_name=full_name, password_hash=hash_password(password), role="admin"))
        db.commit()
    print("Admin account created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FoodBridge administration commands")
    parser.add_argument("command", choices=["create-admin"])
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin()
