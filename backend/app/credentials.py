from sqlalchemy.orm import Session

from app.models import ServiceCredential
from app.security import decrypt_secret, encrypt_secret


def get_secret(db: Session, service_id: str) -> str | None:
    cred = db.get(ServiceCredential, service_id)
    return decrypt_secret(cred.encrypted_secret) if cred else None


def set_secret(db: Session, service_id: str, plain: str) -> ServiceCredential:
    cred = db.get(ServiceCredential, service_id)
    if cred is None:
        cred = ServiceCredential(service_id=service_id)
        db.add(cred)
    cred.encrypted_secret = encrypt_secret(plain)
    cred.hint = plain[-4:]
    db.commit()
    return cred


def delete_secret(db: Session, service_id: str) -> None:
    cred = db.get(ServiceCredential, service_id)
    if cred is not None:
        db.delete(cred)
        db.commit()
