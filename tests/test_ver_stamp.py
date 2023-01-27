import copy
import sys
import os
import yaml
import shutil
import toml
import json
import stat
import pytest

sys.path.append("{0}/../version_stamp".format(os.path.dirname(__file__)))

import vmn
import stamp_utils


def _run_vmn_init():
    return vmn.vmn_run(["init"])[0]


def _init_app(app_name, starting_version="0.0.0"):
    cmd = ["init-app", "-v", starting_version, app_name]
    ret, vmn_ctx = vmn.vmn_run(cmd)

    _, ver_info = vmn_ctx.vcs.backend.get_first_reachable_version_info(
        app_name, type=stamp_utils.RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE
    )

    try:
        # Python3.9 only
        merged_dict = vmn_ctx.params | vmn_ctx.vcs.__dict__
    except:
        merged_dict = {**(vmn_ctx.params), **(vmn_ctx.vcs.__dict__)}

    return ret, ver_info, merged_dict


def _release_app(app_name, version):
    cmd = ["release", "-v", version, app_name]
    ret, vmn_ctx = vmn.vmn_run(cmd)
    vmn.initialize_backend_attrs(vmn_ctx)
    _, ver_info = vmn_ctx.vcs.backend.get_first_reachable_version_info(
        app_name, type=stamp_utils.RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE
    )

    try:
        # Python3.9 only
        merged_dict = vmn_ctx.params | vmn_ctx.vcs.__dict__
    except:
        merged_dict = {**(vmn_ctx.params), **(vmn_ctx.vcs.__dict__)}

    return ret, ver_info, merged_dict


def _stamp_app(app_name, release_mode=None, prerelease=None):
    args_list = ["stamp"]
    if release_mode is not None:
        args_list.extend(["-r", release_mode])

    if prerelease is not None:
        args_list.extend(["--pr", prerelease])

    args_list.append(app_name)

    ret, vmn_ctx = vmn.vmn_run(args_list)

    _, ver_info = vmn_ctx.vcs.backend.get_first_reachable_version_info(
        app_name, type=stamp_utils.RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE
    )

    try:
        # Python3.9 only
        merged_dict = vmn_ctx.params | vmn_ctx.vcs.__dict__
    except:
        merged_dict = {**(vmn_ctx.params), **(vmn_ctx.vcs.__dict__)}

    return ret, ver_info, merged_dict


def _show(
    app_name,
    version=None,
    verbose=None,
    raw=None,
    root=False,
    from_file=False,
    ignore_dirty=False,
    unique=False,
    display_type=False,
):
    args_list = ["show"]
    if verbose is not None:
        args_list.append("--verbose")
    if version is not None:
        args_list.extend(["--version", f"{version}"])
    if raw is not None:
        args_list.append("--raw")
    if root:
        args_list.append("--root")
    if from_file:
        args_list.append("--from-file")
    if ignore_dirty:
        args_list.append("--ignore-dirty")
    if unique:
        args_list.append("--unique")
    if display_type:
        args_list.append("--type")

    args_list.append(app_name)

    return vmn.vmn_run(args_list)[0]


def _gen(app_name, template, output, verify_version=False, version=None):
    args_list = ["--debug"]
    args_list.extend(["gen"])
    args_list.extend(["--template", template])
    args_list.extend(["--output", output])

    if version is not None:
        args_list.extend(["--version", f"{version}"])

    if verify_version:
        args_list.extend(["--verify-version"])

    args_list.append(app_name)

    return vmn.vmn_run(args_list)[0]


def _goto(app_name, version=None, root=False):
    args_list = ["goto"]
    if version is not None:
        args_list.extend(["--version", f"{version}"])
    if root:
        args_list.append("--root")

    args_list.append(app_name)

    return vmn.vmn_run(args_list)[0]


def _add_buildmetadata_to_version(
    app_layout, bm, version=None, file_path=None, url=None
):
    args_list = ["--debug"]
    args_list.extend(["add"])
    args_list.extend(["--bm", bm])
    app_name = app_layout.app_name

    if version is not None:
        args_list.extend(["--version", version])

    if file_path is not None:
        args_list.extend(
            [
                "--version-metadata-path",
                f"{os.path.join(app_layout.repo_path, file_path)}",
            ]
        )

    if url:
        args_list.extend(["--version-metadata-url", url])

    args_list.append(app_name)

    return vmn.vmn_run(args_list)[0]


def _configure_2_deps(app_layout, params):
    conf = {
        "deps": {
            "../": {
                "test_repo_0": {
                    "vcs_type": app_layout.be_type,
                    "remote": app_layout._app_backend.be.remote(),
                }
            }
        }
    }
    for repo in (("repo1", "git"), ("repo2", "git")):
        be = app_layout.create_repo(repo_name=repo[0], repo_type=repo[1])

        conf["deps"]["../"].update(
            {repo[0]: {"vcs_type": repo[1], "remote": be.be.remote()}}
        )

        be.__del__()

    app_layout.write_conf(params["app_conf_path"], **conf)

    return conf


def _configure_empty_conf(app_layout, params):
    conf = {"deps": {}, "extra_info": False}
    app_layout.write_conf(params["app_conf_path"], **conf)

    return conf


def test_basic_stamp(app_layout):
    res = _run_vmn_init()
    assert res == 0
    res = _run_vmn_init()
    assert res == 1

    _init_app(app_layout.app_name)

    for i in range(2):
        err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == "0.0.1"

    new_name = f"{app_layout.app_name}_2"
    _init_app(new_name, "1.0.0")

    for i in range(2):
        err, ver_info, _ = _stamp_app(new_name, "hotfix")
        assert err == 0
        assert ver_info["stamping"]["app"]["_version"] == "1.0.0.1"

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.1"

    app_layout.write_file_commit_and_push("test_repo_0", "a/b/c/f1.file", "msg1")
    os.environ["VMN_WORKING_DIR"] = f"{app_layout.repo_path}/a/b/c/"

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


def test_jinja2_gen(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    # read to clear stderr and out
    capfd.readouterr()

    app_layout.write_file_commit_and_push("test_repo_0", "f1.txt", "content")

    jinja2_content = (
        "VERSION: {{version}}\n"
        "NAME: {{name}}\n"
        "BRANCH: {{stamped_on_branch}}\n"
        "RELEASE_MODE: {{release_mode}}\n"
        "{% for k,v in changesets.items() %}\n"
        "{{k}}:\n"
        "  hash: {{v.hash}}\n"
        "  remote: {{v.remote}}\n"
        "  vcs_type: {{v.vcs_type}}\n"
        "  state: {{v.state}}\n"
        "{% endfor %}\n"
    )
    app_layout.write_file_commit_and_push(
        "test_repo_0", "f1.jinja2", jinja2_content, commit=False
    )

    tpath = os.path.join(app_layout._repos["test_repo_0"]["path"], "f1.jinja2")
    opath = os.path.join(app_layout._repos["test_repo_0"]["path"], "jinja_out.txt")
    err = _gen(app_layout.app_name, tpath, opath)
    assert err == 0

    m_time = os.path.getmtime(opath)

    err = _gen(app_layout.app_name, tpath, opath)
    assert err == 0

    m_time_after = os.path.getmtime(opath)

    assert m_time == m_time_after

    # read to clear stderr and out
    capfd.readouterr()

    err = _gen(app_layout.app_name, tpath, opath, verify_version=True)
    assert err == 1

    captured = capfd.readouterr()

    assert (
        "[ERROR] The repository and maybe"
        " some of its dependencies are in dirty state.Dirty states"
        " found: {'modified'}" in captured.err
    )

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    capfd.readouterr()

    err = _gen(app_layout.app_name, tpath, opath, verify_version=True, version="0.0.1")
    assert err == 1

    captured = capfd.readouterr()

    assert (
        "[ERROR] The repository is not exactly at "
        "version: 0.0.1. You can use `vmn goto` in order "
        "to jump to that version.\nRefusing to gen." in captured.err
    )

    app_layout.write_file_commit_and_push("test_repo_0", "f1.txt", "content")

    err = _goto(app_layout.app_name, version="0.0.1")
    assert err == 0

    err = _gen(app_layout.app_name, tpath, opath, verify_version=True)
    assert err == 0

    err = _goto(app_layout.app_name)
    assert err == 0

    err = _gen(app_layout.app_name, tpath, opath, verify_version=True)
    assert err == 1

    err = _gen(app_layout.app_name, tpath, opath)
    assert err == 0

    new_name = f"{app_layout.app_name}2/s1"
    _init_app(new_name)

    err, _, _ = _stamp_app(new_name, "patch")
    assert err == 0

    err = _gen(app_layout.app_name, tpath, opath)
    assert err == 0

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    _configure_2_deps(app_layout, params)
    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg1")
    app_layout.write_file_commit_and_push("repo1", "f1.file", "msg2", commit=False)
    app_layout.write_file_commit_and_push("repo2", "f1.file", "msg1", push=False)

    err = _gen(app_layout.app_name, tpath, opath)
    assert err == 0

    with open(opath, "r") as f:
        data = yaml.safe_load(f)
        assert data["VERSION"] == "0.0.3"
        assert data["RELEASE_MODE"] == "patch"
        assert "dirty_deps" in data["."]["state"]
        assert "modified" in data["."]["state"]
        assert "pending" in data["../repo1"]["state"]
        assert "outgoing" in data["../repo2"]["state"]


def test_basic_show(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.1\n" == captured.out

    err = _show(app_layout.app_name, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    try:
        tmp = yaml.safe_load(captured.out)
        assert "dirty" not in tmp
    except Exception:
        assert False

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")

    err = _show(app_layout.app_name)
    assert err == 0

    app_layout.write_file_commit_and_push(
        "test_repo_0", "f1.file", "msg1", commit=False
    )

    err = _show(app_layout.app_name)
    assert err == 0

    captured = capfd.readouterr()
    assert "dirty" in captured.out

    err = _show(app_layout.app_name, ignore_dirty=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.1\n" == captured.out

    err = _show(app_layout.app_name, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    try:
        tmp = yaml.safe_load(captured.out)
        assert "modified" in tmp["dirty"]
        assert "pending" in tmp["dirty"]
        assert len(tmp["dirty"]) == 2
    except Exception:
        assert False

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1", push=False)
    err = _show(app_layout.app_name, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    try:
        tmp = yaml.safe_load(captured.out)
        assert "modified" in tmp["dirty"]
        assert "outgoing" in tmp["dirty"]
        assert len(tmp["dirty"]) == 2
    except Exception:
        assert False

    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    err = _show(app_layout.app_name, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    try:
        tmp = yaml.safe_load(captured.out)
        assert "modified" in tmp["dirty"]
        assert len(tmp["dirty"]) == 1
    except Exception:
        assert False

    err = _goto(app_layout.app_name, version="0.0.1")
    assert err == 0

    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.1\n" == captured.out

    err = _goto(app_layout.app_name)
    assert err == 0

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        url="https://whateverlink.com",
    )
    assert err == 0

    err = _add_buildmetadata_to_version(
        app_layout,
        "build.1-aef.1-its-okay",
        version="0.0.1",
        url="https://whateverlink.com",
    )
    assert err == 0

    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.2\n" == captured.out

    err = _show(app_layout.app_name, raw=True, version="0.0.1+build.1-aef.1-its-okay")
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.1+build.1-aef.1-its-okay\n" == captured.out

    err = _show(
        app_layout.app_name, display_type=True, version="0.0.1+build.1-aef.1-its-okay"
    )
    assert err == 0
    captured = capfd.readouterr()
    tmp = yaml.safe_load(captured.out)
    assert tmp["type"] == "metadata"
    assert tmp["out"] == "0.0.1+build.1-aef.1-its-okay"

    err = _show(app_layout.app_name, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    tmp = yaml.safe_load(captured.out)
    assert f'0.0.2+{tmp["changesets"]["."]["hash"]}'.startswith(tmp["unique_id"])

    err = _show(app_layout.app_name, unique=True)
    assert err == 0
    captured = capfd.readouterr()
    assert f'0.0.2+{tmp["changesets"]["."]["hash"]}'.startswith(captured.out[:-1])

    err = _show(app_layout.app_name, display_type=True)
    assert err == 0
    captured = capfd.readouterr()
    tmp = yaml.safe_load(captured.out)
    assert tmp["type"] == "release"
    assert tmp["out"] == "0.0.2"


def test_show_from_file(app_layout, capfd):
    _run_vmn_init()
    _, _, params = _init_app(app_layout.app_name)
    capfd.readouterr()

    err = _show(app_layout.app_name, verbose=True, from_file=True)
    assert err == 1
    captured = capfd.readouterr()
    assert (
        captured.out == f"[INFO] Version information was not "
        f"found for {app_layout.app_name}.\n"
    )

    conf = {
        "template": "[{major}][.{minor}][.{patch}]",
        "create_verinfo_files": True,
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

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.1\n" == captured.out

    err = _show(app_layout.app_name, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    show_res = yaml.safe_load(captured.out)

    err = _show(app_layout.app_name, verbose=True, from_file=True)
    assert err == 0
    captured = capfd.readouterr()
    show_file_res_empty_ver = yaml.safe_load(captured.out)

    err = _show(app_layout.app_name, version="0.0.1", verbose=True, from_file=True)
    assert err == 0

    captured = capfd.readouterr()
    show_file_res = yaml.safe_load(captured.out)

    assert show_file_res_empty_ver == show_file_res

    show_res.pop("versions")

    assert show_res == show_file_res

    app_name = "root_app/app1"
    _, _, params = _init_app(app_name)
    conf = {
        "template": "[{major}][.{minor}][.{patch}]",
        "create_verinfo_files": True,
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

    err, ver_info, params = _stamp_app(app_name, "patch")
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.0.1"

    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 1

    capfd.readouterr()
    err = _show(app_name, verbose=True)
    assert err == 0

    captured = capfd.readouterr()
    show_res = yaml.safe_load(captured.out)

    err = _show(app_name, version="0.0.1", verbose=True, from_file=True)
    assert err == 0

    captured = capfd.readouterr()
    show_file_res = yaml.safe_load(captured.out)

    show_res.pop("versions")

    assert show_res == show_file_res

    capfd.readouterr()
    # TODO: Improve stdout in such a case
    err = _show(app_name, verbose=True, root=True)
    assert err == 1
    captured = capfd.readouterr()

    err = _show("root_app", verbose=True, root=True)
    assert err == 0

    captured = capfd.readouterr()
    show_root_res = yaml.safe_load(captured.out)

    err = _show("root_app", version="1", from_file=True, verbose=True, root=True)
    assert err == 0

    captured = capfd.readouterr()
    show_file_res = yaml.safe_load(captured.out)

    assert show_root_res == show_file_res

    err = _show(app_name)
    assert err == 0
    captured = capfd.readouterr()
    show_minimal_res = yaml.safe_load(captured.out)

    def rmtree(top):
        for root, dirs, files in os.walk(top, topdown=False):
            for name in files:
                filename = os.path.join(root, name)
                os.chmod(filename, stat.S_IWUSR)
                os.remove(filename)
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(top)

    rmtree(os.path.join(app_layout.repo_path, ".git"))

    err = _show("root_app", version="1", from_file=True, verbose=True, root=True)
    assert err == 0

    captured = capfd.readouterr()
    show_file_res = yaml.safe_load(captured.out)
    assert show_file_res == show_root_res

    err = _show(app_name, version="0.0.1", verbose=True, from_file=True)
    assert err == 0

    captured = capfd.readouterr()
    show_file_res = yaml.safe_load(captured.out)
    assert show_file_res == show_res

    err = _show(app_name, version="0.0.1", from_file=True)
    assert err == 0
    captured = capfd.readouterr()
    show_file = yaml.safe_load(captured.out)

    assert show_minimal_res == show_file

    err = _show(app_name, version="0.0.1", verbose=True, from_file=True)
    assert err == 0

    captured = capfd.readouterr()
    show_file_res = yaml.safe_load(captured.out)

    err = _show(app_name, version="0.0.1", from_file=True, unique=True)
    assert err == 0
    captured = capfd.readouterr()
    assert f'0.0.1+{show_file_res["changesets"]["."]["hash"]}'.startswith(
        captured.out[:-1]
    )


def test_show_from_file_conf_changed(app_layout, capfd):
    _run_vmn_init()
    _, _, params = _init_app(app_layout.app_name)
    capfd.readouterr()

    conf = {
        "template": "[{major}][.{minor}][.{patch}]",
        "create_verinfo_files": True,
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

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0
    captured = capfd.readouterr()
    assert "0.0.1\n" == captured.out

    err = _show(app_layout.app_name, from_file=True)
    assert err == 0
    captured = capfd.readouterr()
    assert "0.0.1\n" == captured.out

    conf = {
        "template": "[{major}][.{minor}][.{patch}]",
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

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    # read to clear stderr and out
    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "0.0.2\n" == captured.out

    err = _show(app_layout.app_name, from_file=True, raw=True)
    assert err == 0
    captured = capfd.readouterr()
    assert "0.0.1\n" == captured.out

    err = _show(app_layout.app_name, from_file=True, raw=True, version="0.0.2")
    assert err == 1
    captured = capfd.readouterr()
    assert (
        f"[INFO] Version information was not found for "
        f"{app_layout.app_name}.\n" == captured.out
    )


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

    err = _goto(app_layout.app_name)
    assert err == 0


def test_goto_deleted_repos(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    _configure_2_deps(app_layout, params)

    err, _, params = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    dir_path = app_layout._repos["repo2"]["path"]
    # deleting repo_b
    shutil.rmtree(dir_path)

    err = _goto(app_layout.app_name, version="0.0.2")
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


def test_starting_version(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

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


def test_rc_goto(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    try:
        err, ver_info, _ = _stamp_app(
            app_layout.app_name, release_mode="minor", prerelease="rc_aaa"
        )
        assert err == 0
    except AssertionError:
        pass

    err, ver_info, _ = _stamp_app(
        app_layout.app_name, release_mode="minor", prerelease="rcaaa"
    )
    assert err == 0

    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.0-rcaaa1"

    err = _goto(app_layout.app_name, version="1.3.0-rcaaa1")
    assert err == 0


def test_goto_print(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="minor")

    app_layout.write_file_commit_and_push("test_repo_0", "my.js", "some text")

    err, ver_info, _ = _stamp_app(app_layout.app_name, release_mode="major")

    capfd.readouterr()

    err = _goto(app_layout.app_name, version="1.3.0")
    assert err == 0

    sout, serr = capfd.readouterr()
    assert f"[INFO] You are at version 1.3.0 of {app_layout.app_name}\n" == sout

    err = _goto(app_layout.app_name)
    assert err == 0


    sout, serr = capfd.readouterr()
    assert (
        f"[INFO] You are at the tip of the branch of version 2.0.0 for {app_layout.app_name}\n"
        == sout
    )


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


def test_basic_goto(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    err, ver_info, _ = _stamp_app(app_layout.app_name, "minor")
    assert err == 0

    app_layout.write_file_commit_and_push("test_repo_0", "a.yxy", "msg")

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.3.1"

    c1 = app_layout._app_backend.be.changeset()
    err = _goto(app_layout.app_name, version="0.0.2")
    assert err == 1

    err = _goto(app_layout.app_name, version="1.3.0")
    assert err == 0

    # read to clear stderr and out
    capfd.readouterr()

    err, _, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    captured = capfd.readouterr()
    assert "[INFO] 1.3.0\n" == captured.out

    c2 = app_layout._app_backend.be.changeset()
    assert c1 != c2
    err = _goto(app_layout.app_name, version="1.3.1")
    assert err == 0
    c3 = app_layout._app_backend.be.changeset()
    assert c1 == c3

    err = _goto(app_layout.app_name)
    assert err == 0

    c4 = app_layout._app_backend.be.changeset()
    assert c1 == c4

    root_app_name = "some_root_app/service1"
    _init_app(root_app_name, "1.2.3")

    err, ver_info, _ = _stamp_app(root_app_name, "minor")
    assert err == 0

    rc1 = app_layout._app_backend.be.changeset()

    app_layout.write_file_commit_and_push("test_repo_0", "a.yxy", "msg")

    err, ver_info, _ = _stamp_app(root_app_name, "minor")
    assert err == 0

    rc2 = app_layout._app_backend.be.changeset()

    assert rc1 != rc2

    err = _goto(root_app_name, version="1.3.0")
    assert err == 0

    assert rc1 == app_layout._app_backend.be.changeset()

    err = _goto(root_app_name)
    assert err == 0

    assert rc2 == app_layout._app_backend.be.changeset()

    err, ver_info, _ = _stamp_app(root_app_name, "minor")
    assert err == 0

    assert rc2 == app_layout._app_backend.be.changeset()

    app_layout.write_file_commit_and_push("test_repo_0", "a.yxy", "msg")

    err, ver_info, _ = _stamp_app(root_app_name, "minor")
    assert err == 0
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "1.5.0"

    rc3 = app_layout._app_backend.be.changeset()

    root_name = root_app_name.split("/")[0]

    err = _goto(root_name, version="1", root=True)
    assert err == 0

    assert rc1 == app_layout._app_backend.be.changeset()

    err = _goto(root_name, root=True)
    assert err == 0

    assert rc3 == app_layout._app_backend.be.changeset()

    err, ver_info, _ = _stamp_app(root_app_name, "minor")
    assert err == 0

    deps = ver_info["stamping"]["app"]["changesets"]

    err = _goto(
        root_app_name,
        version=f"1.5.0+{deps['.']['hash']}",
    )
    assert err == 0

    err = _goto(
        root_app_name,
        version=f"1.5.0+{deps['.']['hash'][:-10]}",
    )
    assert err == 0

    capfd.readouterr()

    err = _goto(
        root_app_name,
        version=f"1.5.0+{deps['.']['hash'][:-10]}X",
    )
    assert err == 1

    captured = capfd.readouterr()
    assert "[ERROR] Wrong unique id\n" == captured.err


def test_stamp_on_branch_merge_squash(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name, "1.2.3")

    err, ver_info, _ = _stamp_app(app_layout.app_name, "minor")
    assert err == 0

    main_branch = app_layout._app_backend.be.get_active_branch()

    app_layout._app_backend.be.checkout(("-b", "new_branch"))
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    app_layout._app_backend._origin.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0

    app_layout._app_backend._origin.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    app_layout.write_file_commit_and_push("test_repo_0", "f3.file", "msg3")
    app_layout._app_backend._origin.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    app_layout._app_backend.be.checkout(main_branch)
    app_layout.merge(from_rev="new_branch", to_rev=main_branch, squash=True)
    app_layout._app_backend._origin.pull(rebase=True)

    app_layout._app_backend.be.push()

    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    data = ver_info["stamping"]["app"]

    assert data["_version"] == "1.3.3"


def test_get_version(app_layout):
    _run_vmn_init()
    _init_app(app_layout.app_name)

    main_branch = app_layout._app_backend.be.get_active_branch()

    app_layout._app_backend.be.checkout(("-b", "new_branch"))
    app_layout.write_file_commit_and_push("test_repo_0", "f1.file", "msg1")
    app_layout._app_backend._origin.pull(rebase=True)
    err, ver_info, _ = _stamp_app(app_layout.app_name, "patch")
    assert err == 0
    app_layout._app_backend.be.checkout(main_branch)
    app_layout.merge(from_rev="new_branch", to_rev=main_branch, squash=True)
    app_layout._app_backend._origin.pull(rebase=True)
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
    app_layout._app_backend._origin.pull(rebase=True)
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


def test_basic_root_show(app_layout, capfd):
    _run_vmn_init()
    app_name = "root_app/app1"
    ret, ver_info, params = _init_app(app_name, "0.2.1")
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.2.1"

    data = ver_info["stamping"]["root_app"]
    assert data["version"] == 0

    app_name = "root_app/app2"
    _init_app(app_name, "0.2.1")

    capfd.readouterr()
    err = _show("root_app", root=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "1\n" == captured.out

    err = _show("root_app", verbose=True, root=True)
    assert err == 0

    captured = capfd.readouterr()
    out_dict = yaml.safe_load(captured.out)
    assert app_name == out_dict["latest_service"]
    assert len(out_dict["services"]) == 2
    assert app_name in out_dict["services"]
    assert out_dict["services"][app_name] == "0.2.1"

    err, _, _ = _stamp_app(app_name)
    assert err == 1
    captured = capfd.readouterr()
    assert (
        "[ERROR] When not in release candidate mode, a release mode must be "
        "specified - use -r/--release-mode with one of major/minor/patch/hotfix\n"
        == captured.err
    )

    err, ver_info, _ = _stamp_app(app_name, release_mode="patch")
    assert err == 0
    captured = capfd.readouterr()
    assert "[INFO] 0.2.2\n" == captured.out
    data = ver_info["stamping"]["app"]
    assert data["_version"] == "0.2.2"

    err = _show("root_app", verbose=True, root=True)
    assert err == 0

    captured = capfd.readouterr()
    out_dict = yaml.safe_load(captured.out)
    assert app_name == out_dict["latest_service"]
    assert app_name in out_dict["services"]
    assert out_dict["services"][app_name] == "0.2.2"


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

    app_layout._repos["repo1"]["_be"].be.checkout(("-b", "new_branch"))
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

    app_layout.write_file_commit_and_push(
        "test_repo_0",
        "f1.txt",
        "connnntenctt"
    )

    clone_path = app_layout.create_new_clone("test_repo_0", depth=1)
    app_layout.set_working_dir(clone_path)
    capfd.readouterr()
    err, ver_info, _ = _stamp_app(f"{app_layout.app_name}", "patch")
    captured = capfd.readouterr()
    assert err == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


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

    assert diff < 2


def test_run_vmn_from_non_git_repo(app_layout, capfd):
    _run_vmn_init()
    app_layout.set_working_dir(app_layout.base_dir)
    vmn.LOGGER = None
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

    ret, ver_info, _ =_stamp_app(f"{app_layout.app_name}", "patch")
    assert ret == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


def test_stamp_with_removed_tags_with_commit(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")
    app_layout.write_file_commit_and_push("test_repo_0", "a/b/c/f1.file", "msg1")

    app_layout.remove_tag(f"{app_layout.app_name}_0.0.1")

    ret, ver_info, _ =_stamp_app(f"{app_layout.app_name}", "patch")
    assert ret == 0
    assert ver_info["stamping"]["app"]["_version"] == "0.0.2"


def test_show_removed_tags(app_layout, capfd):
    _run_vmn_init()
    _init_app(app_layout.app_name)
    _stamp_app(f"{app_layout.app_name}", "patch")
    app_layout.write_file_commit_and_push("test_repo_0", "a/b/c/f1.file", "msg1")

    app_layout.remove_tag(f"{app_layout.app_name}_0.0.1")

    capfd.readouterr()

    err = _show(app_layout.app_name, raw=True)
    assert err == 0

    captured = capfd.readouterr()
    assert "dirty:\n- modified\nout: 0.0.0\n\n" == captured.out


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
