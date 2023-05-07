from test_utils import _run_vmn_init


def test_vmn_init(app_layout, capfd):
    res = _run_vmn_init()
    assert res == 0
    captured = capfd.readouterr()

    assert (
        f"[INFO] Initialized vmn tracking on {app_layout.repo_path}\n" == captured.out
    )
    assert "" == captured.err

    res = _run_vmn_init()
    assert res == 1

    captured = capfd.readouterr()
    assert captured.err.startswith("[ERROR] vmn repo tracking is already initialized")
    assert "" == captured.out