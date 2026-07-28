"""No-op sleep inhibitor owned by ``dummy.rs``."""


class SleepInhibitor:
    def acquire(self) -> None:
        return None

    def release(self) -> None:
        return None


__all__ = ["SleepInhibitor"]
