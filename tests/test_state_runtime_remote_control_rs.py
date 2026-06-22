import asyncio
import sqlite3

import pytest

from pycodex.state.runtime.remote_control import (
    REMOTE_CONTROL_APP_SERVER_CLIENT_NAME_NONE,
    RemoteControlEnrollmentRecord,
    app_server_client_name_from_key,
    delete_remote_control_enrollment,
    get_remote_control_enrollment,
    remote_control_app_server_client_name_key,
    upsert_remote_control_enrollment,
)


REMOTE_CONTROL_URL = "wss://example.com/backend-api/wham/remote/control/server"


def _create_remote_control_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
CREATE TABLE remote_control_enrollments (
    websocket_url TEXT NOT NULL,
    account_id TEXT NOT NULL,
    app_server_client_name TEXT NOT NULL,
    server_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    server_name TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (websocket_url, account_id, app_server_client_name)
)
        """
    )
    connection.commit()


def _record(
    account_id: str,
    *,
    app_server_client_name: str | None,
    server_id: str,
    environment_id: str,
    server_name: str,
) -> RemoteControlEnrollmentRecord:
    return RemoteControlEnrollmentRecord(
        websocket_url=REMOTE_CONTROL_URL,
        account_id=account_id,
        app_server_client_name=app_server_client_name,
        server_id=server_id,
        environment_id=environment_id,
        server_name=server_name,
    )


def test_remote_control_enrollment_round_trips_by_target_and_account() -> None:
    # Rust: codex-state/src/runtime/remote_control.rs
    # Test: remote_control_enrollment_round_trips_by_target_and_account
    connection = sqlite3.connect(":memory:")
    _create_remote_control_schema(connection)

    asyncio.run(
        upsert_remote_control_enrollment(
            connection,
            _record(
                "account-a",
                app_server_client_name="desktop-client",
                server_id="srv_e_first",
                environment_id="env_first",
                server_name="first-server",
            ),
        )
    )
    asyncio.run(
        upsert_remote_control_enrollment(
            connection,
            _record(
                "account-b",
                app_server_client_name="desktop-client",
                server_id="srv_e_second",
                environment_id="env_second",
                server_name="second-server",
            ),
        )
    )

    assert asyncio.run(
        get_remote_control_enrollment(
            connection,
            REMOTE_CONTROL_URL,
            "account-a",
            "desktop-client",
        )
    ) == _record(
        "account-a",
        app_server_client_name="desktop-client",
        server_id="srv_e_first",
        environment_id="env_first",
        server_name="first-server",
    )
    assert (
        asyncio.run(
            get_remote_control_enrollment(
                connection,
                REMOTE_CONTROL_URL,
                "account-missing",
                "desktop-client",
            )
        )
        is None
    )
    assert (
        asyncio.run(
            get_remote_control_enrollment(
                connection,
                REMOTE_CONTROL_URL,
                "account-a",
                "other-client",
            )
        )
        is None
    )


def test_delete_remote_control_enrollment_removes_only_matching_entry() -> None:
    # Rust: codex-state/src/runtime/remote_control.rs
    # Test: delete_remote_control_enrollment_removes_only_matching_entry
    connection = sqlite3.connect(":memory:")
    _create_remote_control_schema(connection)

    asyncio.run(
        upsert_remote_control_enrollment(
            connection,
            _record(
                "account-a",
                app_server_client_name=None,
                server_id="srv_e_first",
                environment_id="env_first",
                server_name="first-server",
            ),
        )
    )
    asyncio.run(
        upsert_remote_control_enrollment(
            connection,
            _record(
                "account-b",
                app_server_client_name=None,
                server_id="srv_e_second",
                environment_id="env_second",
                server_name="second-server",
            ),
        )
    )

    assert (
        asyncio.run(
            delete_remote_control_enrollment(
                connection,
                REMOTE_CONTROL_URL,
                "account-a",
                None,
            )
        )
        == 1
    )
    assert (
        asyncio.run(
            get_remote_control_enrollment(
                connection,
                REMOTE_CONTROL_URL,
                "account-a",
                None,
            )
        )
        is None
    )
    assert asyncio.run(
        get_remote_control_enrollment(
            connection,
            REMOTE_CONTROL_URL,
            "account-b",
            None,
        )
    ) == _record(
        "account-b",
        app_server_client_name=None,
        server_id="srv_e_second",
        environment_id="env_second",
        server_name="second-server",
    )


def test_upsert_updates_existing_composite_key() -> None:
    # Rust: ON CONFLICT(websocket_url, account_id, app_server_client_name)
    # updates server_id, environment_id, server_name, and updated_at.
    connection = sqlite3.connect(":memory:")
    _create_remote_control_schema(connection)

    asyncio.run(
        upsert_remote_control_enrollment(
            connection,
            _record(
                "account-a",
                app_server_client_name="desktop-client",
                server_id="srv_e_first",
                environment_id="env_first",
                server_name="first-server",
            ),
            updated_at=10,
        )
    )
    asyncio.run(
        upsert_remote_control_enrollment(
            connection,
            _record(
                "account-a",
                app_server_client_name="desktop-client",
                server_id="srv_e_updated",
                environment_id="env_updated",
                server_name="updated-server",
            ),
            updated_at=20,
        )
    )

    assert asyncio.run(
        get_remote_control_enrollment(
            connection,
            REMOTE_CONTROL_URL,
            "account-a",
            "desktop-client",
        )
    ) == _record(
        "account-a",
        app_server_client_name="desktop-client",
        server_id="srv_e_updated",
        environment_id="env_updated",
        server_name="updated-server",
    )
    rows = connection.execute(
        """
SELECT server_id, environment_id, server_name, updated_at
FROM remote_control_enrollments
WHERE websocket_url = ? AND account_id = ? AND app_server_client_name = ?
        """,
        (REMOTE_CONTROL_URL, "account-a", "desktop-client"),
    ).fetchall()
    assert rows == [("srv_e_updated", "env_updated", "updated-server", 20)]


def test_none_client_key_round_trip_and_validation() -> None:
    # Rust stores None app-server client names as an empty-string lookup key.
    assert REMOTE_CONTROL_APP_SERVER_CLIENT_NAME_NONE == ""
    assert remote_control_app_server_client_name_key(None) == ""
    assert remote_control_app_server_client_name_key("desktop-client") == "desktop-client"
    assert app_server_client_name_from_key("") is None
    assert app_server_client_name_from_key("desktop-client") == "desktop-client"

    with pytest.raises(TypeError):
        remote_control_app_server_client_name_key(1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        app_server_client_name_from_key(None)  # type: ignore[arg-type]


def test_path_database_mode_preserves_remote_control_contract(tmp_path) -> None:
    # Python compatibility shim: async helpers may open a SQLite path directly
    # while keeping Rust's table and composite-key behavior.
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    try:
        _create_remote_control_schema(connection)
    finally:
        connection.close()

    asyncio.run(
        upsert_remote_control_enrollment(
            db_path,
            _record(
                "account-a",
                app_server_client_name=None,
                server_id="srv_e_first",
                environment_id="env_first",
                server_name="first-server",
            ),
            updated_at=30,
        )
    )

    assert asyncio.run(
        get_remote_control_enrollment(db_path, REMOTE_CONTROL_URL, "account-a", None)
    ) == _record(
        "account-a",
        app_server_client_name=None,
        server_id="srv_e_first",
        environment_id="env_first",
        server_name="first-server",
    )
    assert asyncio.run(
        delete_remote_control_enrollment(db_path, REMOTE_CONTROL_URL, "account-a", None)
    ) == 1
