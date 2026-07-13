import ctypes

from pycodex.windows_sandbox.wfp import (
    EXPLICIT_ACCESS_W,
    FILTER_SPECS,
    FWPM_SESSION0,
    FWP_SECURITY_DESCRIPTOR_TYPE,
    GUID,
)


def test_fixed_rust_wfp_filter_keys_and_names_are_unique() -> None:
    # Rust source: windows-sandbox-rs/src/wfp/filter_specs.rs.
    assert len({spec.key for spec in FILTER_SPECS}) == len(FILTER_SPECS) == 12
    assert len({spec.name for spec in FILTER_SPECS}) == len(FILTER_SPECS)


def test_guid_layout_round_trips_fixed_provider_key() -> None:
    value = GUID.parse("2e31d31c-3948-4753-9117-e5d1a6496f41")
    assert value.Data1 == 0x2E31D31C
    assert value.Data2 == 0x3948
    assert bytes(value.Data4) == bytes.fromhex("9117e5d1a6496f41")


def test_wfp_ctypes_structs_have_windows_x64_abi_sizes() -> None:
    # Windows SDK: fwpmtypes.h::FWPM_SESSION0 and AccCtrl.h::EXPLICIT_ACCESS_W.
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(GUID) == 16
        assert ctypes.sizeof(FWPM_SESSION0) == 72
        assert ctypes.sizeof(EXPLICIT_ACCESS_W) == 48


def test_wfp_security_descriptor_type_matches_windows_sdk_enum() -> None:
    # Windows SDK fwptypes.h: FWP_SID=13, FWP_SECURITY_DESCRIPTOR_TYPE=14.
    assert FWP_SECURITY_DESCRIPTOR_TYPE == 14
