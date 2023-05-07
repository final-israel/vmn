import copy
import json
import os
import shutil
from git.exc import GitCommandError
import pytest
import toml
import yaml
from test_utils import _init_app, _stamp_app, _release_app, _goto, _show, _run_vmn_init, _configure_empty_conf, _configure_2_deps


def test_double_stamp_no_commit(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    for i in range(2):
        err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == "0.0.1"


def test_app2_and_app1_not_advance(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")

    new_name = f"{app_layout.app_name}_2"
    _init_app(new_name, "1.0.0")

    for i in range(2):
        err, ver_info, _ = _stamp_app(new_name, "hotfix")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == "1.0.0.1"

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"


def test_stamp_multiple_apps(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")

    new_name = f"{app_layout.app_name}_2"
    _init_app(new_name, "1.0.0")

    _stamp_app(new_name, "hotfix")

    repo_name = app_layout.repo_path.split(os.path.sep)[-1]
    app_layout.write_file_commit_and_push(
        f"{repo_name}", os.path.join("a", "b", "c", "f1.file"), "msg1"
    )
    os.environ[
        "VMN_WORKING_DIR"
    ] = f"{os.path.join(app_layout.repo_path, 'a', 'b', 'c')}"

    for i in range(2):
        err, ver_info, _ = _stamp_app(new_name, "hotfix")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == "1.0.0.2"

    for i in range(2):
        err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == "0.0.2"

    for i in range(2):
        err, ver_info, _ = _stamp_app(new_name, "hotfix")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == "1.0.0.2"

    _init_app("myapp")


@pytest.mark.parametrize("hook_name", ["pre-push", "post-commit", "pre-commit"])
def test_git_hooks(app_layout, capfd, hook_name):
    res = _run_vmn_init()
    assert res == 0
    res = _run_vmn_init()
    assert res == 1
    _, _, params = _init_app(app_layout.app_name)

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.txt", "connnntenctt")

    # More post-checkout, post-commit, post-merge, post-rewrite, pre-commit, pre-push
    app_layout.write_file_commit_and_push(
        "test_repo_0",
        f".git/hooks/{hook_name}",
        "#/bin/bash\nexit 1",
        add_exec=True,
        commit=False,
    )

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    tmp = yaml.safe_load(captured.out)
    assert tmp["out"] == "0.0.1"
    assert "modified" in tmp["dirty"]

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 1

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    tmp = yaml.safe_load(captured.out)
    assert tmp["out"] == "0.0.1"
    assert "modified" in tmp["dirty"]

    app_layout.remove_file(
        os.path.join(params["root_path"], f".git/hooks/{hook_name}"), from_git=False
    )

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 0

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.2\n" == captured.out




def test_multi_repo_dependency(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    conf = _configure_2_deps(app_layout, params)

    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1")
    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1", commit=False)

    capfd.readouterr()
    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 1
    captured = capfd.readouterr()
    assert "[ERROR] \nPending changes in" in captured.err
    assert "repo1" in captured.err
    app_layout.revert_changes("repo1")

    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1", push=False)

    capfd.readouterr()
    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 1
    captured = capfd.readouterr()
    assert "[ERROR] \nOutgoing changes in" in captured.err
    assert "repo1" in captured.err
    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1")

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"

    assert "." in ver_info["stamping"]["app"]["changesets"]
    assert os.path.join("..", "repo1") in ver_info["stamping"]["app"]["changesets"]
    assert os.path.join("..", "repo2") in ver_info["stamping"]["app"]["changesets"]

    # TODO:: remove this line (seems like the conf write is redundant
    app_layout.write_conf(params["app_conf_path"], **conf)

    with open(params["app_conf_path"], "r") as f:
        data = yaml.safe_load(f)
        assert "../" in data["conf"]["deps"]
        assert "test_repo_0" in data["conf"]["deps"]["../"]
        assert "repo1" in data["conf"]["deps"]["../"]
        assert "repo2" in data["conf"]["deps"]["../"]

    conf["deps"]["../"]["repo3"] = copy.deepcopy(conf["deps"]["../"]["repo2"])
    conf["deps"]["../"]["repo3"].pop("remote")

    app_layout.write_conf(params["app_conf_path"], **conf)
    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 1

    err = _goto(app_layout.app_name)
    assert err == 1

    app_layout.create_repo(repo_name="repo3", repo_type="git")

    err = _goto(app_layout.app_name)
    assert err == 0

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    err = _goto(app_layout.app_name)
    assert err == 0

    shutil.rmtree(app_layout._repos["repo3"]["path"])

    capfd.readouterr()
    err = _show(app_layout.app_name)
    assert err == 0

    captured = capfd.readouterr()
    assert captured.out == "dirty:\n- modified\nout: 0.0.3\n\n"

    err = _goto(app_layout.app_name)
    assert err == 0


def test_basic_root_stamp(app_layout):
    _run_vmn_init()

    app_name = "root_app/app1"
    _init_app(app_name)

    err, ver_info, params = _stamp_app(app_name, "patch")
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.0.1"

    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 1

    app_name = "root_app/app2"
    _init_app(app_name)
    err, ver_info, params = _stamp_app(app_name, "minor")
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.1.0"
    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 3

    app_name = "root_app/app3"
    _init_app(app_name)
    err, ver_info, params = _stamp_app(app_name, "patch")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.0.1"
    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 5

    app_name = "root_app/app1"
    err, ver_info, params = _stamp_app(app_name, "major")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.0.1"
    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 1

    app_name = "root_app/app2"
    err, ver_info, params = _stamp_app(app_name, "major")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.1.0"
    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 3

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "blabla")

    app_name = "root_app/app1"
    err, ver_info, params = _stamp_app(app_name, "major")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.0.0"
    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 6
    assert "root_app/app1" in data["services"]
    assert "root_app/app2" in data["services"]

    app_name = "root_app/app2"
    err, ver_info, params = _stamp_app(app_name, "major")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.0.0"
    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 7

    assert data["services"]["root_app/app1"] == "1.0.0"
    assert data["services"]["root_app/app2"] == "1.0.0"
    assert data["services"]["root_app/app3"] == "0.0.1"


def test_starting_version(app_layout, capfd):
    _run_vmn_init()
    capfd.readouterr()
    _init_app(app_layout.app_name, "1.2.3")
    captured = capfd.readouterr()

    path = f"{os.path.join(app_layout.repo_path, '.vmn', app_layout.app_name)}"
    assert f"[INFO] Initialized app tracking on {path}\n" == captured.out

    err, ver_info, _ = _stamp_app(app_layout.app_name, "minor")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0"


def test_rc_stamping(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-rc1"
    assert data["prerelease"] == "rc"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="rc")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-rc2"
    assert data["prerelease"] == "rc"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="beta")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-beta1"
    assert data["prerelease"] == "beta"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(app_layout.app_name)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-beta2"
    assert data["prerelease"] == "beta"

    capfd.readouterr()
    err, ver_info, _ = _release_app(app_layout.app_name, "1.3.0-beta2")
    capfd.readouterr()

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0"
    assert data["prerelease"] == "release"

    err, ver_info, _ = _release_app(app_layout.app_name, "1.3.0")

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0"
    assert data["prerelease"] == "release"

    tags_before = app_layout.get_all_tags()
    for t in tags_before:
        app_layout._app_backend.be._be.delete_tag(t)

    app_layout._app_backend.be._be.git.fetch("--tags")
    tags_after = app_layout.get_all_tags()

    assert tags_before == tags_after

    for item in ["2.0.0", "3.0.0"]:
        app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
        err, ver_info, _ = _stamp_app(
            app_layout.app_name, release_mode="major", prerelease="rc"
        )
        assert err == 0

        assert "vmn_info" in ver_info
        data = ver_info["stamping"]["app"]
        assert data["_version"] == f"{item}-rc1"
        assert data["prerelease"] == "rc"

        _, ver_info, _ = _release_app(app_layout.app_name, f"{item}-rc1")

        assert "vmn_info" in ver_info
        data = ver_info["stamping"]["app"]
        assert data["_version"] == item
        assert data["prerelease"] == "release"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="minor")
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.1.0"
    assert data["prerelease"] == "release"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.2.0-rc1"
    assert data["prerelease"] == "rc"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.3.0-rc1"
    assert data["prerelease"] == "rc"

    err, ver_info, _ = _stamp_app(app_layout.app_name)
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.3.0-rc1"
    assert data["prerelease"] == "rc"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(app_layout.app_name)
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.3.0-rc2"
    assert data["prerelease"] == "rc"

    for item in ["3.4.0", "3.5.0"]:
        app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

        err, ver_info, _ = _stamp_app(
            app_layout.app_name, release_mode="minor", prerelease="release"
        )
        assert err == 0

        data = ver_info["stamping"]["app"]
        assert data["_version"] == item
        assert data["prerelease"] == "release"
        assert not data["prerelease_count"]

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.6.0-rc1"
    assert data["prerelease"] == "rc"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(app_layout.app_name)
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.6.0-rc2"
    assert data["prerelease"] == "rc"

    capfd.readouterr()
    err = _show(app_layout.app_name)
    assert err == 0

    captured = capfd.readouterr()
    assert "3.6.0-rc2\n" == captured.out

    err = _show(app_layout.app_name, display_type=True)
    assert err == 0
    captured = capfd.readouterr()
    tmp = yaml.safe_load(captured.out)
    assert tmp["type"] == "rc"
    assert tmp["out"] == "3.6.0-rc2"

    _, ver_info, _ = _release_app(app_layout.app_name, f"3.6.0-rc1")

    capfd.readouterr()
    err = _show(app_layout.app_name)
    assert err == 0

    captured = capfd.readouterr()
    assert "3.6.0-rc2\n" == captured.out

    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="minor")
    assert err == 0

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )
    assert err == 0

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.7.0-rc1"
    assert data["prerelease"] == "rc"

    _, ver_info, _ = _release_app(app_layout.app_name, "3.7.0-rc1")

    assert "vmn_info" in ver_info
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "3.7.0"
    assert data["prerelease"] == "release"

    capfd.readouterr()
    err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="rc")

    captured = capfd.readouterr()
    assert "[INFO] 3.7.0\n" == captured.out

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )

    for i in range(2):
        app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
        err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="rc")

    _, ver_info, _ = _release_app(app_layout.app_name, "3.8.0-rc2")
    capfd.readouterr()
    err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="rc")
    assert err == 0

    captured = capfd.readouterr()
    assert "[INFO] 3.8.0-rc3\n" == captured.out

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="rc")
    assert err == 1

    captured = capfd.readouterr()
    assert captured.err.startswith("[ERROR] The version 3.8.0 was already ")


def test_version_template():
    formated_version = stamp_utils.VMNBackend.get_utemplate_formatted_version(
        "2.0.9", vmn.IVersionsStamper.parse_template("[{major}][-{prerelease}]"), True
    )

    assert formated_version == "2"

    formated_version = stamp_utils.VMNBackend.get_utemplate_formatted_version(
        "2.0.9.0", vmn.IVersionsStamper.parse_template("[{major}][-{hotfix}]"), True
    )

    assert formated_version == "2"

    formated_version = stamp_utils.VMNBackend.get_utemplate_formatted_version(
        "2.0.9.0", vmn.IVersionsStamper.parse_template("[{major}][-{hotfix}]"), False
    )

    assert formated_version == "2-0"


def test_stamp_on_branch_merge_squash(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    err, ver_info, _ = _stamp_app(app_layout.app_name, "minor")
    assert err == 0

    main_branch = app_layout._app_backend.be.get_active_branch()

    app_layout.checkout("new_branch", create_new=True)
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    app_layout._app_backend.selected_remote.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    app_layout._app_backend.selected_remote.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    app_layout.write_file_commit_and_push("test_repo_0", "f3.file", "msg3")
    app_layout._app_backend.selected_remote.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    app_layout._app_backend.be.checkout(main_branch)
    app_layout.merge(from_rev="new_branch", to_rev=main_branch, squash=True)
    app_layout._app_backend.selected_remote.pull(rebase=True)

    app_layout._app_backend.be.push()

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    data = ver_info["stamping"]["app"]

    assert data["_version"] == "1.3.3"


def test_get_version(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    main_branch = app_layout._app_backend.be.get_active_branch()

    app_layout.checkout("new_branch", create_new=True)
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    app_layout._app_backend.selected_remote.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    app_layout._app_backend.be.checkout(main_branch)
    app_layout.merge(from_rev="new_branch", to_rev=main_branch, squash=True)
    app_layout._app_backend.selected_remote.pull(rebase=True)
    app_layout._app_backend.be.push()
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.0.2"


def test_get_version_number_from_file(app_layout):
    _run_vmn_init()
    _, _, params = _init_app(app_layout.app_name, "0.2.1")

    assert vmn.VersionControlStamper.get_version_number_from_file(
        params["version_file_path"]
    ) == ("0.2.1", "release", {})


def test_read_version_from_file(app_layout):
    _run_vmn_init()
    _, _, params = _init_app(app_layout.app_name, "0.2.1")

    file_path = params["version_file_path"]

    assert vmn.VersionControlStamper.get_version_number_from_file(file_path) == (
        "0.2.1",
        "release",
        {},
    )

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    app_layout._app_backend.selected_remote.pull(rebase=True)
    with open(file_path, "r") as fid:
        ver_dict = yaml.load(fid, Loader=yaml.FullLoader)

    assert "0.2.1" == ver_dict["version_to_stamp_from"]


def test_manual_file_adjustment(app_layout):
    _run_vmn_init()
    _, _, params = _init_app(app_layout.app_name, "0.2.1")

    file_path = params["version_file_path"]

    app_layout.remove_file(file_path)
    verfile_manual_content = {
        "version_to_stamp_from": "0.2.3",
        "prerelease": "release",
        "prerelease_count": {},
    }
    # now we want to override the version by changing the file version:
    app_layout.write_file_commit_and_push(
        "test_repo_0",
        ".vmn/test_app/{}".format(vmn.VER_FILE_NAME),
        yaml.dump(verfile_manual_content),
    )

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    _version = ver_info["stamping"]["app"]["_version"]
    assert "0.2.4" == _version


def test_manual_file_adjustment_with_major_version(app_layout):
    _run_vmn_init()
    _, _, params = _init_app(app_layout.app_name, "0.2.1")

    file_path = params["version_file_path"]

    app_layout.remove_file(file_path)
    verfile_manual_content = {
        "version_to_stamp_from": "1.2.3",
        "prerelease": "release",
        "prerelease_count": {},
    }
    # now we want to override the version by changing the file version:
    app_layout.write_file_commit_and_push(
        "test_repo_0",
        ".vmn/test_app/{}".format(vmn.VER_FILE_NAME),
        yaml.dump(verfile_manual_content),
    )

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    _version = ver_info["stamping"]["app"]["_version"]
    assert "1.2.4" == _version

def test_version_backends_cargo(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "Cargo.toml",
        toml.dumps({"package": {"name": "test_app", "version": "some ignored string"}}),
    )

    conf = {
        "version_backends": {"cargo": {"path": "Cargo.toml"}},
        "deps": {
            "../": {
                "test_repo_0": {
                    "vcs_type": app_layout.be_type,
                    "remote": app_layout._app_backend.be.remote(),
                }
            }
        },
    }

    app_layout.write_conf(params["app_conf_path"], **conf)

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    full_path = os.path.join(
        params["root_path"], params["version_backends"]["cargo"]["path"]
    )

    with open(full_path, "r") as f:
        data = toml.load(f)
        assert data["package"]["version"] == "0.0.2"

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0


def test_version_backends_poetry(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "pyproject.toml",
        toml.dumps(
            {"tool": {"poetry": {"name": "test_app", "version": "some ignored string"}}}
        ),
    )

    conf = {
        "version_backends": {"poetry": {"path": "pyproject.toml"}},
    }

    app_layout.write_conf(params["app_conf_path"], **conf)

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    full_path = os.path.join(
        params["root_path"], params["version_backends"]["poetry"]["path"]
    )

    with open(full_path, "r") as f:
        data = toml.load(f)
        assert data["tool"]["poetry"]["version"] == "0.0.2"

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0


def test_conf(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    app_layout.write_file_commit_and_push("test_repo_0", "f1.txt", "text")

    conf = {
        "deps": {
            "../": {
                "test_repo_0": {
                    "vcs_type": app_layout.be_type,
                    "remote": app_layout._app_backend.be.remote(),
                }
            }
        },
        "extra_info": False,
    }

    app_layout.write_conf(params["app_conf_path"], **conf)

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    _configure_empty_conf(app_layout, params)

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    conf = _configure_2_deps(app_layout, params)
    conf["deps"]["../"]["repo1"]["branch"] = "new_branch"
    conf["deps"]["../"]["repo2"]["hash"] = "deadbeef"
    app_layout.write_conf(params["app_conf_path"], **conf)

    capfd.readouterr()
    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 1
    capfd.readouterr()

    app_layout.checkout("new_branch", repo_name="repo1", create_new=True)
    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1")
    conf["deps"]["../"]["repo2"]["hash"] = app_layout._repos["repo2"][
        "_be"
    ].be.changeset()
    app_layout.write_conf(params["app_conf_path"], **conf)

    capfd.readouterr()
    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    captured = capfd.readouterr()
    assert captured.out == "[INFO] 0.0.4\n"


def test_version_backends_npm(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "package.json",
        json.dumps({"name": "test_app", "version": "some ignored string"}),
    )

    conf = {
        "template": "[{major}][.{minor}][.{patch}]",
        "version_backends": {"npm": {"path": "package.json"}},
        "deps": {
            "../": {
                "test_repo_0": {
                    "vcs_type": app_layout.be_type,
                    "remote": app_layout._app_backend.be.remote(),
                }
            }
        },
        "extra_info": False,
    }

    app_layout.write_conf(params["app_conf_path"], **conf)

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    full_path = os.path.join(
        params["root_path"], params["version_backends"]["npm"]["path"]
    )

    with open(full_path, "r") as f:
        data = json.load(f)
        assert data["version"] == "0.0.2"

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0


def test_backward_compatability_with_previous_vmn(app_layout, capfd):
    app_layout.stamp_with_previous_vmn()
    capfd.readouterr()
    err, ver_info, _ = _stamp_app("app1", "major")
    captured = capfd.readouterr()
    assert err == 0
    assert "[INFO] 0.0.3\n" == captured.out

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app("app1", "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.4"

    err = _goto("app1", version="0.0.2")
    assert err == 0

    err = _goto("app1", version="0.0.3")
    assert err == 0

    err = _goto("app1", version="0.0.4")
    assert err == 0

    err = _goto("app1")
    assert err == 0

    err, ver_info, _ = _stamp_app("root_app/service1", "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


def test_remotes(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    import subprocess

    cmds = [
        ["git", "remote", "add", "or2", app_layout.repo_path],
        ["git", "remote", "rename", "origin", "or3"],
        ["git", "remote", "rename", "or2", "origin"],
        ["git", "remote", "remove", "or3"],
        ["git", "remote", "add", "or3", app_layout.repo_path],
        ["git", "remote", "remove", "origin"],
        ["git", "remote", "add", "or2", f"{app_layout.repo_path}2"],
    ]
    c = 2
    for cmd in cmds:
        subprocess.call(cmd, cwd=app_layout.repo_path)

        app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
        err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == f"0.0.{c}"
        c += 1


def test_shallow_vmn_commit_repo_stamp(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"

    clone_path = app_layout.create_new_clone("test_repo_0", depth=1)
    app_layout.set_working_dir(clone_path)
    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"


def test_shallow_non_vmn_commit_repo_stamp(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.txt", "connnntenctt")

    clone_path = app_layout.create_new_clone("test_repo_0", depth=1)
    app_layout.set_working_dir(clone_path)
    capfd.readouterr()
    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    captured = capfd.readouterr()
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


def test_shallow_vmn_commit_repo_stamp_pr(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch", prerelease="yuval")
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1-yuval1"

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "test.tst",
        "bla",
    )

    clone_path = app_layout.create_new_clone("test_repo_0", depth=1)
    app_layout.set_working_dir(clone_path)
    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1-yuval2"


def test_same_user_tag(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "test.tst",
        "bla",
    )

    app_layout.create_tag("HEAD~3", f"{app_layout.app_name}_2.0.0")

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0


def test_perf_show(app_layout):
    import subprocess
    import shutil

    base_cmd = [
        "wget",
        "https://github.com/final-israel/vmn/releases/download/vmn_stamping_action_0.0.1/perf.tgz",
    ]
    subprocess.call(base_cmd, cwd=app_layout.base_dir)
    shutil.rmtree(app_layout.test_app_remote)
    shutil.rmtree(app_layout.repo_path)
    base_cmd = ["tar", "-xzf", "./perf.tgz"]
    subprocess.call(base_cmd, cwd=app_layout.base_dir)
    base_cmd = ["git", "clone", app_layout.test_app_remote, app_layout.repo_path]
    subprocess.call(base_cmd, cwd=app_layout.base_dir)

    import time

    t1 = time.perf_counter()
    err = _show(app_layout.app_name, raw=True)
    assert err == 0
    t2 = time.perf_counter()
    diff = t2 - t1

    assert diff < 10


def test_run_vmn_from_non_git_repo(app_layout, capfd):
    _run_vmn_init()
    app_layout.set_working_dir(app_layout.base_dir)
    stamp_utils.VMN_LOGGER = None
    capfd.readouterr()
    ret = vmn.vmn_run([])[0]
    captured = capfd.readouterr()
    assert ret == 1


def test_bad_tag(app_layout, capfd):
    res = _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")

    app_layout.create_tag("HEAD", "Semver-foo-python3-1.1.1")

    # read to clear stderr and out
    capfd.readouterr()
    err = _show(app_layout.app_name, raw=True)
    captured = capfd.readouterr()

    assert err == 0

    app_layout.create_tag("HEAD", "app_name-1.1.1")

    # read to clear stderr and out
    capfd.readouterr()
    err = _show(app_layout.app_name, raw=True)
    captured = capfd.readouterr()

    assert err == 0


def test_stamp_with_removed_tags_no_commit(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")

    app_layout.remove_tag(f"{app_layout.app_name}_0.0.1")

    ret, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert ret == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


def test_stamp_with_removed_tags_with_commit(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")
    app_layout.write_file_commit_and_push("test_repo_0", "a/b/c/f1.file", "msg1")

    app_layout.remove_tag(f"{app_layout.app_name}_0.0.1")

    ret, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert ret == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


def test_shallow_removed_vmn_tag_repo_stamp(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"

    app_layout.remove_tag(f"{app_layout.app_name}_0.0.1")

    clone_path = app_layout.create_new_clone("test_repo_0", depth=1)
    app_layout.set_working_dir(clone_path)
    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


@pytest.mark.parametrize("manual_version", [("0.0.0", "0.0.1"), ("2.0.0", "2.0.1")])
def test_removed_vmn_tag_and_version_file_repo_stamp(app_layout, manual_version):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, ver_info, params = _stamp_app(f"{app_layout.app_name}", "patch")
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"

    app_layout.remove_tag(f"{app_layout.app_name}_0.0.1")

    file_path = params["version_file_path"]

    app_layout.remove_file(file_path)
    verfile_manual_content = {
        "version_to_stamp_from": manual_version[0],
        "prerelease": "release",
        "prerelease_count": {},
    }
    # now we want to override the version by changing the file version:
    app_layout.write_file_commit_and_push(
        "test_repo_0",
        ".vmn/test_app/{}".format(vmn.VER_FILE_NAME),
        yaml.dump(verfile_manual_content),
    )

    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == manual_version[1]


def test_conf_for_branch(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")

    branch = "b2"
    app_layout.write_conf(
        f"{app_layout.repo_path}/.vmn/{app_layout.app_name}/{branch}_conf.yml",
        template="[test_{major}][.{minor}][.{patch}]",
    )

    capfd.readouterr()
    err = _show(app_layout.app_name)
    captured = capfd.readouterr()

    tmp = yaml.safe_load(captured.out)
    assert tmp["out"] == "0.0.1"

    import subprocess

    base_cmd = ["git", "checkout", "-b", branch]
    subprocess.call(base_cmd, cwd=app_layout.repo_path)

    capfd.readouterr()
    err = _show(app_layout.app_name)
    captured = capfd.readouterr()

    tmp = yaml.safe_load(captured.out)
    assert tmp["out"] == "test_0.0.1"


def test_conf_for_branch_removal_of_conf(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")

    main_branch = app_layout._app_backend.be.get_active_branch()
    branch = "b2"
    branch_conf_path = os.path.join(
        f"{app_layout.repo_path}",
        ".vmn",
        f"{app_layout.app_name}",
        f"{branch}_conf.yml",
    )
    app_layout.write_conf(
        branch_conf_path, template="[test_{major}][.{minor}][.{patch}]"
    )

    assert os.path.exists(branch_conf_path)

    import subprocess

    base_cmd = ["git", "checkout", "-b", branch]
    subprocess.call(base_cmd, cwd=app_layout.repo_path)

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "a.txt",
        "bv",
    )

    err, ver_info, params = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 0

    assert os.path.exists(branch_conf_path)

    base_cmd = ["git", "checkout", main_branch]
    subprocess.call(base_cmd, cwd=app_layout.repo_path)

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "b.txt",
        "bv",
    )

    assert os.path.exists(branch_conf_path)

    err, ver_info, params = _stamp_app(f"{app_layout.app_name}", "patch")
    assert err == 0

    assert not os.path.exists(branch_conf_path)


def test_stamp_no_ff_rebase(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "minor")

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")

    main_branch = app_layout._app_backend.be.get_active_branch()
    other_branch = "topic"

    app_layout.checkout(other_branch, create_new=True)

    app_layout.write_file_commit_and_push("test_repo_0", "f2.file", "msg1")
    _stamp_app(app_layout.app_name, "patch")
    app_layout.write_file_commit_and_push("test_repo_0", "f2.file", "msg2")
    _stamp_app(app_layout.app_name, "patch")
    app_layout.write_file_commit_and_push("test_repo_0", "f2.file", "msg2")

    app_layout.rebase(main_branch, other_branch, no_ff=True)

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    res = yaml.safe_load(captured.out)
    assert "0.1.2" == res["out"]


def test_missing_local_branch(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    main_branch = app_layout._app_backend.be.get_active_branch()

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    cur_hex = app_layout._app_backend.be.changeset()
    app_layout.checkout(cur_hex)

    app_layout.delete_branch(main_branch)

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0


def test_missing_local_branch_error_scenarios(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    main_branch = app_layout._app_backend.be.get_active_branch()
    cur_hex = app_layout._app_backend.be._be.head.commit.hexsha

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    app_layout.checkout(cur_hex)
    app_layout.delete_branch(main_branch)

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 1

    cur_hex = app_layout._app_backend.be._be.head.commit.hexsha
    app_layout.checkout(cur_hex)

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 1


def test_double_release_works(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rc"
    )
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-rc1"
    assert data["prerelease"] == "rc"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="rc")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-rc2"
    assert data["prerelease"] == "rc"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(app_layout.app_name, prerelease="beta")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-beta1"
    assert data["prerelease"] == "beta"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(app_layout.app_name)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-beta2"
    assert data["prerelease"] == "beta"

    for i in range(2):
        capfd.readouterr()
        err, ver_info, _ = _release_app(app_layout.app_name, "1.3.0-beta2")
        captured = capfd.readouterr()

        assert err == 0
        assert captured.out == "[INFO] 1.3.0\n"
        assert captured.err == ""

    err, ver_info, _ = _release_app(app_layout.app_name, "1.3.0")
    captured = capfd.readouterr()

    assert err == 0
    assert captured.out == "[INFO] 1.3.0\n"
    assert captured.err == ""

    err, ver_info, _ = _release_app(app_layout.app_name, "1.3.0-beta1")
    captured = capfd.readouterr()

    assert err == 1
    assert captured.err == "[ERROR] Failed to release 1.3.0-beta1\n"
    assert captured.out == ""

    err, ver_info, _ = _release_app(app_layout.app_name)
    captured = capfd.readouterr()

    assert err == 0
    assert captured.out == "[INFO] 1.3.0\n"
    assert captured.err == ""

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0"
    assert data["prerelease"] == "release"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg2")
    err, ver_info, _ = _release_app(app_layout.app_name)
    captured = capfd.readouterr()

    assert err == 1
    assert captured.out == ""
    assert (
        captured.err == "[ERROR] When running vmn release and not on a version commit, "
        "you must specify a specific version using -v flag\n"
    )


@pytest.mark.parametrize(
    "branch_name", [("new_branch", "new_branch2"), ("new_branch/a", "new_branch2/b")]
)
def test_change_of_tracking_branch(app_layout, capfd, branch_name):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    app_layout.checkout(branch_name[0], create_new=True)
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    app_layout.checkout(branch_name[1], create_new=True)

    app_layout.delete_branch(branch_name[0])

    app_layout._app_backend.be._be.git.branch(
        f"--set-upstream-to=origin/{branch_name[0]}", branch_name[1]
    )

    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="patch")
    assert err == 0


@pytest.mark.parametrize("branch_name", ["new_branch", "new_branch/a"])
def test_no_upstream_branch_stamp(app_layout, capfd, branch_name):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    app_layout.checkout(branch_name, create_new=True)
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="minor")
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0"

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    main_branch = app_layout._app_backend.be.get_active_branch()
    assert branch_name == main_branch

    app_layout._app_backend.be._be.git.branch("--unset-upstream", main_branch)

    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="patch")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.1"


def test_multi_repo_dependency_goto_and_stamp(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    conf = _configure_2_deps(app_layout, params)

    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1")

    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    prev_ver = ver_info["stamping"]["app"]["_version"]

    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1")
    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    assert prev_ver != ver_info["stamping"]["app"]["_version"]

    err = _goto(app_layout.app_name, version=prev_ver)
    assert err == 0

    # TODO:: for each stamp add capfd assertions
    err, ver_info, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == prev_ver


def test_dirty_no_ff_rebase(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "minor")

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")

    main_branch = app_layout._app_backend.be.get_active_branch()
    other_branch = "topic"

    app_layout.checkout(other_branch, create_new=True)

    app_layout.write_file_commit_and_push("test_repo_0", "f2.file", "msg1")
    _stamp_app(app_layout.app_name, "patch")
    app_layout.write_file_commit_and_push("test_repo_0", "f2.file", "msg2")
    _stamp_app(app_layout.app_name, "patch")

    app_layout.rebase(main_branch, other_branch, no_ff=True)

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    res = yaml.safe_load(captured.out)
    assert "0.1.2" == res["out"]
    assert len(res["dirty"]) == 2
    assert "modified" in res["dirty"]
    assert "outgoing" in res["dirty"]


def test_no_fetch_branch_configured(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "minor")

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")

    app_layout.git_cmd(args=["config", "--unset", "remote.origin.fetch"])

    err, ver_info, _ = _stamp_app(app_layout.app_name, "minor")
    assert err == 0


def test_no_fetch_branch_configured_for_deps(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    err, _, params = _stamp_app(app_layout.app_name, "minor")

    captured = capfd.readouterr()

    _configure_2_deps(app_layout, params)

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")

    app_layout.git_cmd("repo1", ["config", "--unset", "remote.origin.fetch"])

    err, ver_info, _ = _stamp_app(app_layout.app_name, "minor")
    assert err == 0


# TODO:: add test for app release. merge squash and show. expect the newly released version

def test_two_prs_from_same_origin(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "patch")
    main_branch = app_layout._app_backend.be.get_active_branch()
    first_branch = "first"

    app_layout.checkout(first_branch, create_new=True)

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=first_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.2-{first_branch}1"
    assert data["prerelease"] == first_branch
    app_layout.checkout(main_branch, create_new=False)
    second_branch = "second"

    app_layout.checkout(second_branch, create_new=True)
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=second_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.2-{second_branch}1"
    assert data["prerelease"] == second_branch



def test_marge_and_check_for_conflicts(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "patch")
    main_branch = app_layout._app_backend.be.get_active_branch()
    pr_branch = "pr"

    app_layout.checkout(pr_branch, create_new=True)
    for i in range(10):
        app_layout.write_file_commit_and_push("test_repo_0", "f1.file", f"msg{i}")
        err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=pr_branch)
        assert err == 0
        data = ver_info["stamping"]["app"]
        assert data["_version"] == f"0.0.2-{pr_branch}{i+1}"
        assert data["prerelease"] == pr_branch
    app_layout.checkout(main_branch, create_new=False)
    second_branch = "second"

    app_layout.checkout(second_branch, create_new=True)
    for i in range(10):
        app_layout.write_file_commit_and_push("test_repo_0", "f1.file", f"msg{i}")
        err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=second_branch)
        assert err == 0
        data = ver_info["stamping"]["app"]
        assert data["_version"] == f"0.0.2-{second_branch}{i+1}"
        assert data["prerelease"] == second_branch
    result = app_layout._app_backend.be._be.git.status()
    assert "conflict" not in result
    try:
        app_layout._app_backend.be._be.git.merge(pr_branch)
    except GitCommandError as err:
        pass
    result = app_layout._app_backend.be._be.git.status()
    assert "conflict" in result


def test_two_prs_from_same_origin_after_release(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "patch")
    main_branch = app_layout._app_backend.be.get_active_branch()
    first_branch = "first"

    app_layout.checkout(first_branch, create_new=True)

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=first_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.2-{first_branch}1"
    assert data["prerelease"] == first_branch
    app_layout.checkout(main_branch, create_new=False)
    second_branch = "second"

    app_layout.checkout(second_branch, create_new=True)
    app_layout.checkout(main_branch)
    _release_app(app_layout.app_name, f"0.0.2-{first_branch}1")
    app_layout.checkout(second_branch)
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    capfd.readouterr()
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=second_branch)
    c = capfd.readouterr()
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.3-{second_branch}1"
    assert data["prerelease"] == second_branch


def test_one_branch_two_prs(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "patch")
    main_branch = app_layout._app_backend.be.get_active_branch()
    pr_branch = "pr"

    app_layout.checkout(pr_branch, create_new=True)

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=pr_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.2-{pr_branch}1"
    assert data["prerelease"] == pr_branch
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=pr_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.2-{pr_branch}2"
    assert data["prerelease"] == pr_branch
    app_layout.checkout(main_branch, create_new=False)
    second_branch = "second"

    app_layout.checkout(second_branch, create_new=True)
    app_layout.checkout(main_branch)
    _release_app(app_layout.app_name, f"0.0.2-{pr_branch}2")
    app_layout.checkout(second_branch)
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg2")
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=second_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.3-{second_branch}1"
    assert data["prerelease"] == second_branch
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg2")
    err, ver_info, _ = _stamp_app(app_layout.app_name, optional_release_mode="patch", prerelease=second_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.3-{second_branch}2"
    assert data["prerelease"] == second_branch


def test_all_release_modes(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(app_layout.app_name, "patch")
    main_branch = app_layout._app_backend.be.get_active_branch()
    c1_branch = "c1"
    app_layout.checkout(c1_branch, create_new=True)

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg0")
    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="patch", prerelease=c1_branch)
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == f"0.0.2-{c1_branch}1"
    assert data["prerelease"] == c1_branch
    app_layout.checkout(main_branch, create_new=False)