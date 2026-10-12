"""커넥터 레지스트리. ai_services.connector 값으로 구현체를 찾는다.

2주차에 Claude Code / Codex 커넥터를 추가할 때 이 파일에 등록한다.
"""

from app.connectors.base import Connector

_registry: dict[str, Connector] = {}


def register(connector: Connector) -> None:
    _registry[connector.key] = connector


def get_connector(key: str | None) -> Connector | None:
    return _registry.get(key) if key else None


def available_connectors() -> list[str]:
    return sorted(_registry)
