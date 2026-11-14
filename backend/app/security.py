import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def mask_contact(identifier: str, identifier_type: str) -> str:
    if identifier_type == "email":
        local, domain = identifier.split("@", maxsplit=1)
        return f"{local[:1]}•••@{domain}"
    if len(identifier) <= 4:
        return "••••"
    return f"{identifier[:2]}••••{identifier[-2:]}"
