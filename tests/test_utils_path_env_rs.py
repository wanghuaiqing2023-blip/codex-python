from pycodex.utils.path_utils import env
from pycodex.utils.path_utils import is_wsl


def test_env_rs_owns_is_wsl_and_lib_reexports_it() -> None:
    assert is_wsl is env.is_wsl
    assert env.is_wsl(
        env={"WSL_DISTRO_NAME": "Ubuntu"},
        platform="linux",
    ) is True
    assert env.is_wsl(
        env={},
        proc_version_path="missing-proc-version",
        platform="linux",
    ) is False
