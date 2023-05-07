import yaml
from test_utils import _init_app, _stamp_app, _release_app, _show, _run_vmn_init, _add_buildmetadata_to_version
def test_add_bm(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        url="https://whateverlink.com",
    )
    assert err == 0

    # TODO assert matching version

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "file.txt",
        "str1",
    )

    captured = capfd.readouterr()
    assert not captured.err

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-not-okay",
        url="https://whateverlink.com",
    )
    assert err == 1

    captured = capfd.readouterr()
    assert (
        "[ERROR] When running vmn add and not on a version commit, "
        "you must specify a specific version using -v flag\n" in captured.err
    )

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        version="0.0.2",
        url="https://whateverlink.com",
    )
    assert err == 0

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.2\n" == captured.out

    err = _show(app_layout.app_name, raw=True, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    assert len(yaml.safe_load(captured.out)["versions"]) == 2

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "file.txt",
        "str1",
    )

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        version="0.0.2",
        url="https://whateverlink.com",
    )
    assert err == 0

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay2",
        version="0.0.2",
        url="https://whateverlink.com",
    )
    assert err == 0

    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True, verbose=True, version="0.0.2")
    assert err == 0

    captured = capfd.readouterr()
    assert len(yaml.safe_load(captured.out)["versions"]) == 3

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        version="0.0.3",
        url="https://whateverlink.com",
    )
    assert err == 1

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        version="999.999.999",
        url="https://whateverlink.com",
    )
    assert err == 1

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        version="0.0.3",
        url="https://whateverlink.com",
    )
    assert err == 0

    capfd.readouterr()
    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay+",
        version="0.0.3",
        url="https://whateverlink.com",
    )
    assert err == 1

    captured = capfd.readouterr()
    assert (
        "[ERROR] Tag test_app_0.0.3+build.1-aef.1-its-okay+ "
        "doesn't comply " in captured.err
    )

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "test.yml",
        yaml.dump({"build_flags": "-g", "build_time": "Debug"}),
        commit=False,
    )

    for i in range(2):
        err = _add_buildmetadata_to_version(
            app_layout,
            "build.1-aef.1-its-okay3",
            version="0.0.3",
            file_path="test.yml",
            url="https://whateverlink.com",
        )
        assert err == 0
        app_layout.write_file_commit_and_push(
            "test_repo_0",
            "test.yml",
            yaml.dump({"build_flags": "-g", "build_time": "Debug"}),
            commit=False,
        )

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "test.yml",
        yaml.dump({"build_flags": "-g2", "build_time": "Debug"}),
        commit=False,
    )

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay3",
        version="0.0.3",
        file_path="test.yml",
        url="https://whateverlink.com",
    )
    assert err == 1

    capfd.readouterr()
    err = _show(
        app_layout.app_name,
        raw=True,
        version="0.0.3+build.1-aef.1-its-okay3",
        verbose=True,
    )
    assert err == 0

    captured = capfd.readouterr()
    assert len(yaml.safe_load(captured.out)["versions"]) == 3
    assert yaml.safe_load(captured.out)["version_metadata"]["build_flags"] == "-g"
    assert yaml.safe_load(captured.out)["versions"][0] == "0.0.3"

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "test.tst",
        "bla",
    )

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch", prerelease="alpha")
    assert err == 0

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        version="0.0.4-alpha1",
        url="https://whateverlink.com",
    )
    assert err == 0

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "test.test",
        yaml.dump(
            {
                "bla": "-g2",
            }
        ),
    )

    err, ver_info, _ = _release_app(app_layout.app_name, "0.0.4-alpha1")
    assert err == 0