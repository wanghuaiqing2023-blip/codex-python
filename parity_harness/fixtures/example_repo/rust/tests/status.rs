use parity_harness_fixture::render_status;

#[test]
fn renders_status() {
    assert_eq!(render_status("ready"), "status: ready");
}

