from demo.status import render_status


def test_renders_status() -> None:
    assert render_status("ready") == "status: ready"

