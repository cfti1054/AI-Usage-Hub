from app import erd


def test_erd_document_matches_models():
    """models.py 를 바꾸고 `uv run python -m app.erd` 를 실행하지 않으면 실패한다."""
    assert erd.main(["--check"]) == 0
