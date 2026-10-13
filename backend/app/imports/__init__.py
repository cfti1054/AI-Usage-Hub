"""사용량 CSV 가져오기. 서비스별 파서를 PARSERS 에 등록한다."""

from app.imports.cursor_csv import parse_cursor_csv

PARSERS = {"cursor": parse_cursor_csv}
