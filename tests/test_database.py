from unittest.mock import MagicMock

from react_agent.db import database


def test_get_db_yields_session_and_closes_it(monkeypatch):
    mock_session = MagicMock()
    monkeypatch.setattr(
        database,
        "SessionLocal",
        lambda: mock_session,
    )

    generator = database.get_db()

    session = next(generator)
    assert session is mock_session
    mock_session.close.assert_not_called()

    try:
        next(generator)
    except StopIteration:
        pass

    mock_session.close.assert_called_once_with()


def test_get_db_closes_session_after_exception(monkeypatch):
    mock_session = MagicMock()
    monkeypatch.setattr(
        database,
        "SessionLocal",
        lambda: mock_session,
    )

    generator = database.get_db()
    next(generator)

    try:
        generator.throw(RuntimeError("Database error"))
    except RuntimeError:
        pass

    mock_session.close.assert_called_once_with()