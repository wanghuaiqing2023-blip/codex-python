from pycodex.tui.chatwidget import turn_lifecycle
from pycodex.utils.sleep_inhibitor import SleepInhibitor
from pycodex.utils.sleep_inhibitor.dummy import SleepInhibitor as DummySleepInhibitor
from pycodex.utils.sleep_inhibitor.linux_inhibitor import LinuxSleepInhibitor
from pycodex.utils.sleep_inhibitor.macos import MacSleepInhibitor
from pycodex.utils.sleep_inhibitor.windows_inhibitor import WindowsSleepInhibitor


def test_sleep_inhibitor_items_follow_rust_module_owners() -> None:
    assert SleepInhibitor.__module__ == "pycodex.utils.sleep_inhibitor"
    assert DummySleepInhibitor.__module__ == "pycodex.utils.sleep_inhibitor.dummy"
    assert LinuxSleepInhibitor.__module__ == "pycodex.utils.sleep_inhibitor.linux_inhibitor"
    assert MacSleepInhibitor.__module__ == "pycodex.utils.sleep_inhibitor.macos"
    assert WindowsSleepInhibitor.__module__ == "pycodex.utils.sleep_inhibitor.windows_inhibitor"


def test_tui_turn_lifecycle_uses_the_crate_sleep_inhibitor() -> None:
    assert turn_lifecycle.SleepInhibitor is SleepInhibitor
