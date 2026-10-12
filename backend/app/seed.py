"""초기 데이터: 관리자 계정 1개 + 1차 대상 서비스 4종. 여러 번 실행해도 안전하다.

    uv run python -m app.seed
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import AiService, User, UserSettings
from app.security import hash_password

# connector 는 2~3주차에 커넥터가 구현되면 채운다
INITIAL_SERVICES = [
    {"id": "claude-code", "name": "Claude Code", "provider": "Anthropic", "collection_method": "cli"},
    {"id": "codex", "name": "Codex", "provider": "OpenAI", "collection_method": "cli"},
    {"id": "cursor", "name": "Cursor", "provider": "Anysphere", "collection_method": "manual"},
    {"id": "gemini-cli", "name": "Gemini CLI", "provider": "Google", "collection_method": "api"},
]


def seed(db: Session, admin_email: str | None, admin_password: str | None) -> None:
    for data in INITIAL_SERVICES:
        if db.get(AiService, data["id"]) is None:
            db.add(AiService(**data))

    if admin_email and admin_password:
        user = db.scalar(select(User).where(User.email == admin_email))
        if user is None:
            user = User(email=admin_email, password_hash=hash_password(admin_password))
            db.add(user)
            db.flush()
        if db.get(UserSettings, user.id) is None:
            db.add(UserSettings(user_id=user.id))
    db.commit()


if __name__ == "__main__":
    settings = get_settings()
    if not (settings.admin_email and settings.admin_password):
        raise SystemExit("ADMIN_EMAIL / ADMIN_PASSWORD 환경변수가 필요합니다")
    with get_sessionmaker()() as session:
        seed(session, settings.admin_email, settings.admin_password)
    print("seed 완료")
