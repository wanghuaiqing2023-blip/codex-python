"""Persistent Windows Filtering Platform defense filters.

Rust owner: ``codex-windows-sandbox::wfp`` and ``wfp::filter_specs`` at fixed
commit ``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import ctypes
import os
import uuid
from ctypes import wintypes
from dataclasses import dataclass


class WindowsSandboxWfpError(OSError):
    pass


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def parse(cls, value: str) -> "GUID":
        parsed = uuid.UUID(value)
        fields = parsed.fields
        node = fields[5].to_bytes(6, "big")
        return cls(fields[0], fields[1], fields[2], (ctypes.c_ubyte * 8)(fields[3], fields[4], *node))


class FWP_BYTE_BLOB(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]


class FWP_VALUE_UNION(ctypes.Union):
    _fields_ = [
        ("uint8", ctypes.c_uint8),
        ("uint16", ctypes.c_uint16),
        ("uint32", ctypes.c_uint32),
        ("uint64", ctypes.POINTER(ctypes.c_uint64)),
        ("pointer", ctypes.c_void_p),
    ]


class FWP_VALUE0(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("value", FWP_VALUE_UNION)]


class FWP_CONDITION_VALUE_UNION(ctypes.Union):
    _fields_ = [
        ("uint8", ctypes.c_uint8),
        ("uint16", ctypes.c_uint16),
        ("uint32", ctypes.c_uint32),
        ("sd", ctypes.POINTER(FWP_BYTE_BLOB)),
        ("pointer", ctypes.c_void_p),
    ]


class FWP_CONDITION_VALUE0(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("value", FWP_CONDITION_VALUE_UNION)]


class FWPM_DISPLAY_DATA0(ctypes.Structure):
    _fields_ = [("name", wintypes.LPWSTR), ("description", wintypes.LPWSTR)]


class FWPM_SESSION0(ctypes.Structure):
    _fields_ = [
        ("sessionKey", GUID),
        ("displayData", FWPM_DISPLAY_DATA0),
        ("flags", ctypes.c_uint32),
        ("txnWaitTimeoutInMSec", ctypes.c_uint32),
        ("processId", wintypes.DWORD),
        ("sid", ctypes.c_void_p),
        ("username", wintypes.LPWSTR),
        ("kernelMode", wintypes.BOOL),
    ]


class TRUSTEE_W(ctypes.Structure):
    _fields_ = [
        ("pMultipleTrustee", ctypes.c_void_p),
        ("MultipleTrusteeOperation", ctypes.c_int),
        ("TrusteeForm", ctypes.c_int),
        ("TrusteeType", ctypes.c_int),
        ("ptstrName", ctypes.c_void_p),
    ]


class EXPLICIT_ACCESS_W(ctypes.Structure):
    _fields_ = [
        ("grfAccessPermissions", wintypes.DWORD),
        ("grfAccessMode", ctypes.c_int),
        ("grfInheritance", wintypes.DWORD),
        ("Trustee", TRUSTEE_W),
    ]


class FWPM_PROVIDER0(ctypes.Structure):
    _fields_ = [
        ("providerKey", GUID),
        ("displayData", FWPM_DISPLAY_DATA0),
        ("flags", ctypes.c_uint32),
        ("providerData", FWP_BYTE_BLOB),
        ("serviceName", wintypes.LPWSTR),
    ]


class FWPM_SUBLAYER0(ctypes.Structure):
    _fields_ = [
        ("subLayerKey", GUID),
        ("displayData", FWPM_DISPLAY_DATA0),
        ("flags", ctypes.c_uint32),
        ("providerKey", ctypes.POINTER(GUID)),
        ("providerData", FWP_BYTE_BLOB),
        ("weight", ctypes.c_uint16),
    ]


class FWPM_FILTER_CONDITION0(ctypes.Structure):
    _fields_ = [("fieldKey", GUID), ("matchType", ctypes.c_uint32), ("conditionValue", FWP_CONDITION_VALUE0)]


class FWPM_ACTION_UNION(ctypes.Union):
    _fields_ = [("filterType", GUID), ("calloutKey", GUID)]


class FWPM_ACTION0(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("value", FWPM_ACTION_UNION)]


class FWPM_FILTER_CONTEXT_UNION(ctypes.Union):
    _fields_ = [("rawContext", ctypes.c_uint64), ("providerContextKey", GUID)]


class FWPM_FILTER0(ctypes.Structure):
    _fields_ = [
        ("filterKey", GUID),
        ("displayData", FWPM_DISPLAY_DATA0),
        ("flags", ctypes.c_uint32),
        ("providerKey", ctypes.POINTER(GUID)),
        ("providerData", FWP_BYTE_BLOB),
        ("layerKey", GUID),
        ("subLayerKey", GUID),
        ("weight", FWP_VALUE0),
        ("numFilterConditions", ctypes.c_uint32),
        ("filterCondition", ctypes.POINTER(FWPM_FILTER_CONDITION0)),
        ("action", FWPM_ACTION0),
        ("context", FWPM_FILTER_CONTEXT_UNION),
        ("reserved", ctypes.POINTER(GUID)),
        ("filterId", ctypes.c_uint64),
        ("effectiveWeight", FWP_VALUE0),
    ]


FWP_EMPTY = 0
FWP_UINT8 = 1
FWP_UINT16 = 2
FWP_SECURITY_DESCRIPTOR_TYPE = 14
FWP_MATCH_EQUAL = 0
FWP_ACTION_BLOCK = 0x00001001
FWP_ACTRL_MATCH_FILTER = 0x00000001
GRANT_ACCESS = 1
FWPM_PROVIDER_FLAG_PERSISTENT = 1
FWPM_SUBLAYER_FLAG_PERSISTENT = 1
FWPM_FILTER_FLAG_PERSISTENT = 1
FWP_E_ALREADY_EXISTS = 0x80320009
FWP_E_FILTER_NOT_FOUND = 0x80320003
FWP_E_NOT_FOUND = 0x80320008

PROVIDER_KEY = GUID.parse("2e31d31c-3948-4753-9117-e5d1a6496f41")
SUBLAYER_KEY = GUID.parse("e65054fd-4d32-4c7c-95ef-621f0cf6431a")
LAYER_CONNECT_V4 = GUID.parse("c38d57d1-05a7-4c33-904f-7fbceee60e82")
LAYER_CONNECT_V6 = GUID.parse("4a72393b-319f-44bc-84c3-ba54dcb3b6b4")
LAYER_ASSIGN_V4 = GUID.parse("1247d66d-0b60-4a15-8d44-7155d0f53a0c")
LAYER_ASSIGN_V6 = GUID.parse("55a650e1-5f0a-4eca-a653-88f53b26aa8c")
CONDITION_USER = GUID.parse("af043a0a-b34d-4f86-979c-c90371af6e66")
CONDITION_PROTOCOL = GUID.parse("3971ef2b-623e-4f9a-8cb1-6e79b806b9a7")
CONDITION_REMOTE_PORT = GUID.parse("c35a604d-d22b-4e1a-91b4-68f674ee674b")


@dataclass(frozen=True)
class FilterSpec:
    key: str
    name: str
    description: str
    layer: GUID
    protocol: int | None = None
    remote_port: int | None = None


FILTER_SPECS = (
    FilterSpec("9f5f3812-79f0-4fe9-9615-4c2c92d2f0ff", "codex_wfp_icmp_connect_v4", "Block sandbox-account ICMP connect v4", LAYER_CONNECT_V4, protocol=1),
    FilterSpec("87498484-45ab-4510-845e-ece8b791b3bc", "codex_wfp_icmp_connect_v6", "Block sandbox-account ICMP connect v6", LAYER_CONNECT_V6, protocol=58),
    FilterSpec("af4751de-f874-4a7b-a34d-f0d0f22d1d9b", "codex_wfp_icmp_assign_v4", "Block sandbox-account ICMP resource assignment v4", LAYER_ASSIGN_V4, protocol=1),
    FilterSpec("ea10db66-a928-4b2e-a82e-a376a54f93ba", "codex_wfp_icmp_assign_v6", "Block sandbox-account ICMP resource assignment v6", LAYER_ASSIGN_V6, protocol=58),
    FilterSpec("83172805-f6be-4ae1-9dc6-6847aef04e7f", "codex_wfp_dns_53_v4", "Block sandbox-account DNS TCP or UDP port 53 v4", LAYER_CONNECT_V4, remote_port=53),
    FilterSpec("d23b2efb-1efb-46b2-96f3-b0ccda5690c8", "codex_wfp_dns_53_v6", "Block sandbox-account DNS TCP or UDP port 53 v6", LAYER_CONNECT_V6, remote_port=53),
    FilterSpec("420b026f-9dc9-4aea-88f4-0f2b9feab39a", "codex_wfp_dns_853_v4", "Block sandbox-account DNS-over-TLS port 853 v4", LAYER_CONNECT_V4, remote_port=853),
    FilterSpec("8d917c81-99cc-45e7-84d6-824df860cfb8", "codex_wfp_dns_853_v6", "Block sandbox-account DNS-over-TLS port 853 v6", LAYER_CONNECT_V6, remote_port=853),
    FilterSpec("e1d6e0af-ce5f-471b-b2d3-15ca00e966f3", "codex_wfp_smb_445_v4", "Block sandbox-account SMB port 445 v4", LAYER_CONNECT_V4, remote_port=445),
    FilterSpec("c2bceca4-66ef-4a0f-ba80-f4f761b8c6f0", "codex_wfp_smb_445_v6", "Block sandbox-account SMB port 445 v6", LAYER_CONNECT_V6, remote_port=445),
    FilterSpec("ba10c618-84e7-4b83-8f74-36e22b2fa1ff", "codex_wfp_smb_139_v4", "Block sandbox-account SMB port 139 v4", LAYER_CONNECT_V4, remote_port=139),
    FilterSpec("fe7f22b8-5cf5-4adb-b2aa-71fc0a8f5d44", "codex_wfp_smb_139_v6", "Block sandbox-account SMB port 139 v6", LAYER_CONNECT_V6, remote_port=139),
)


if os.name == "nt":
    _wfp = ctypes.WinDLL("fwpuclnt", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _wfp.FwpmEngineOpen0.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
    _wfp.FwpmEngineOpen0.restype = ctypes.c_uint32
    _wfp.FwpmEngineClose0.argtypes = [wintypes.HANDLE]
    _wfp.FwpmEngineClose0.restype = ctypes.c_uint32
    _wfp.FwpmTransactionBegin0.argtypes = [wintypes.HANDLE, ctypes.c_uint32]
    _wfp.FwpmTransactionBegin0.restype = ctypes.c_uint32
    _wfp.FwpmTransactionCommit0.argtypes = [wintypes.HANDLE]
    _wfp.FwpmTransactionCommit0.restype = ctypes.c_uint32
    _wfp.FwpmTransactionAbort0.argtypes = [wintypes.HANDLE]
    _wfp.FwpmTransactionAbort0.restype = ctypes.c_uint32
    _wfp.FwpmProviderAdd0.argtypes = [wintypes.HANDLE, ctypes.POINTER(FWPM_PROVIDER0), ctypes.c_void_p]
    _wfp.FwpmProviderAdd0.restype = ctypes.c_uint32
    _wfp.FwpmSubLayerAdd0.argtypes = [wintypes.HANDLE, ctypes.POINTER(FWPM_SUBLAYER0), ctypes.c_void_p]
    _wfp.FwpmSubLayerAdd0.restype = ctypes.c_uint32
    _wfp.FwpmFilterDeleteByKey0.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID)]
    _wfp.FwpmFilterDeleteByKey0.restype = ctypes.c_uint32
    _wfp.FwpmFilterAdd0.argtypes = [wintypes.HANDLE, ctypes.POINTER(FWPM_FILTER0), ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64)]
    _wfp.FwpmFilterAdd0.restype = ctypes.c_uint32
    _advapi32.BuildExplicitAccessWithNameW.argtypes = [
        ctypes.POINTER(EXPLICIT_ACCESS_W),
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    _advapi32.BuildExplicitAccessWithNameW.restype = None
    _advapi32.BuildSecurityDescriptorW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.POINTER(EXPLICIT_ACCESS_W),
        wintypes.ULONG,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.BuildSecurityDescriptorW.restype = wintypes.DWORD
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def install_wfp_filters_for_account(account: str) -> int:
    if os.name != "nt":
        raise WindowsSandboxWfpError("WFP is only available on Windows")
    engine = wintypes.HANDLE()
    session_name = ctypes.create_unicode_buffer("Codex Windows Sandbox WFP")
    session = FWPM_SESSION0()
    session.displayData = FWPM_DISPLAY_DATA0(ctypes.cast(session_name, wintypes.LPWSTR), None)
    session.txnWaitTimeoutInMSec = 0xFFFFFFFF
    _check(
        _wfp.FwpmEngineOpen0(None, 0xFFFFFFFF, None, ctypes.byref(session), ctypes.byref(engine)),
        "FwpmEngineOpen0",
    )
    committed = False
    descriptor = ctypes.c_void_p()
    try:
        _check(_wfp.FwpmTransactionBegin0(engine, 0), "FwpmTransactionBegin0")
        _ensure_provider(engine)
        _ensure_sublayer(engine)
        access = EXPLICIT_ACCESS_W()
        account_buffer = ctypes.create_unicode_buffer(account)
        _advapi32.BuildExplicitAccessWithNameW(
            ctypes.byref(access), account_buffer, FWP_ACTRL_MATCH_FILTER, GRANT_ACCESS, 0
        )
        descriptor_size = wintypes.ULONG()
        result = _advapi32.BuildSecurityDescriptorW(
            None,
            None,
            1,
            ctypes.byref(access),
            0,
            None,
            None,
            ctypes.byref(descriptor_size),
            ctypes.byref(descriptor),
        )
        _check(result, "BuildSecurityDescriptorW")
        blob = FWP_BYTE_BLOB(descriptor_size, ctypes.cast(descriptor, ctypes.POINTER(ctypes.c_ubyte)))
        for spec in FILTER_SPECS:
            key = GUID.parse(spec.key)
            result = _wfp.FwpmFilterDeleteByKey0(engine, ctypes.byref(key))
            if result not in {0, FWP_E_FILTER_NOT_FOUND, FWP_E_NOT_FOUND}:
                _check(result, f"FwpmFilterDeleteByKey0({spec.name})")
            _add_filter(engine, spec, blob)
        _check(_wfp.FwpmTransactionCommit0(engine), "FwpmTransactionCommit0")
        committed = True
        return len(FILTER_SPECS)
    finally:
        if engine.value and not committed:
            _wfp.FwpmTransactionAbort0(engine)
        if descriptor.value:
            _kernel32.LocalFree(descriptor)
        if engine.value:
            _wfp.FwpmEngineClose0(engine)


def _ensure_provider(engine: object) -> None:
    provider = FWPM_PROVIDER0(
        PROVIDER_KEY,
        FWPM_DISPLAY_DATA0("Codex Windows Sandbox WFP", "Persistent WFP provider for Codex Windows sandbox filters"),
        FWPM_PROVIDER_FLAG_PERSISTENT,
        FWP_BYTE_BLOB(),
        None,
    )
    result = _wfp.FwpmProviderAdd0(engine, ctypes.byref(provider), None)
    if result not in {0, FWP_E_ALREADY_EXISTS}:
        _check(result, "FwpmProviderAdd0")


def _ensure_sublayer(engine: object) -> None:
    provider_key = PROVIDER_KEY
    sublayer = FWPM_SUBLAYER0(
        SUBLAYER_KEY,
        FWPM_DISPLAY_DATA0("Codex Windows Sandbox WFP", "Persistent WFP sublayer for Codex Windows sandbox filters"),
        FWPM_SUBLAYER_FLAG_PERSISTENT,
        ctypes.pointer(provider_key),
        FWP_BYTE_BLOB(),
        0x8000,
    )
    result = _wfp.FwpmSubLayerAdd0(engine, ctypes.byref(sublayer), None)
    if result not in {0, FWP_E_ALREADY_EXISTS}:
        _check(result, "FwpmSubLayerAdd0")


def _add_filter(engine: object, spec: FilterSpec, user_blob: FWP_BYTE_BLOB) -> None:
    conditions = [
        FWPM_FILTER_CONDITION0(
            CONDITION_USER,
            FWP_MATCH_EQUAL,
            FWP_CONDITION_VALUE0(FWP_SECURITY_DESCRIPTOR_TYPE, FWP_CONDITION_VALUE_UNION(sd=ctypes.pointer(user_blob))),
        )
    ]
    if spec.protocol is not None:
        conditions.append(FWPM_FILTER_CONDITION0(CONDITION_PROTOCOL, FWP_MATCH_EQUAL, FWP_CONDITION_VALUE0(FWP_UINT8, FWP_CONDITION_VALUE_UNION(uint8=spec.protocol))))
    if spec.remote_port is not None:
        conditions.append(FWPM_FILTER_CONDITION0(CONDITION_REMOTE_PORT, FWP_MATCH_EQUAL, FWP_CONDITION_VALUE0(FWP_UINT16, FWP_CONDITION_VALUE_UNION(uint16=spec.remote_port))))
    condition_array = (FWPM_FILTER_CONDITION0 * len(conditions))(*conditions)
    provider_key = PROVIDER_KEY
    action = FWPM_ACTION0(FWP_ACTION_BLOCK, FWPM_ACTION_UNION(filterType=GUID()))
    filter_value = FWPM_FILTER0(
        GUID.parse(spec.key),
        FWPM_DISPLAY_DATA0(spec.name, spec.description),
        FWPM_FILTER_FLAG_PERSISTENT,
        ctypes.pointer(provider_key),
        FWP_BYTE_BLOB(),
        spec.layer,
        SUBLAYER_KEY,
        FWP_VALUE0(FWP_EMPTY, FWP_VALUE_UNION()),
        len(conditions),
        condition_array,
        action,
        FWPM_FILTER_CONTEXT_UNION(rawContext=0),
        None,
        0,
        FWP_VALUE0(FWP_EMPTY, FWP_VALUE_UNION()),
    )
    filter_id = ctypes.c_uint64()
    _check(_wfp.FwpmFilterAdd0(engine, ctypes.byref(filter_value), None, ctypes.byref(filter_id)), f"FwpmFilterAdd0({spec.name})")


def _check(result: int, operation: str) -> None:
    if result:
        raise WindowsSandboxWfpError(result, f"{operation} failed: 0x{result:08X}")


__all__ = ["FILTER_SPECS", "FilterSpec", "WindowsSandboxWfpError", "install_wfp_filters_for_account"]
