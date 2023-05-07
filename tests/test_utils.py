import os
import sys

sys.path.append("{0}/../version_stamp".format(os.path.dirname(__file__)))

import vmn
import stamp_utils.py


def _run_vmn_init():
    stamp_utils.VMN_LOGGER = None
    ret = vmn.vmn_run(["init"])[0]
    return ret


def _init_app(app_name, starting_version="0.0.0"):
    cmd = ["init-app", "-v", starting_version, app_name]
    stamp_utils.VMN_LOGGER = None
    ret, vmn_ctx = vmn.vmn_run(cmd)

    tag_name, ver_infos = vmn_ctx.vcs.backend.get_first_reachable_version_info(
        app_name, type=stamp_utils.RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE
    )
    if tag_name not in ver_infos or ver_infos[tag_name]["ver_info"] is None:
        ver_info = None
    else:
        ver_info = ver_infos[tag_name]["ver_info"]

    try:
        # Python3.9 only
        merged_dict = vmn_ctx.params | vmn_ctx.vcs.__dict__
    except:
        merged_dict = {**(vmn_ctx.params), **(vmn_ctx.vcs.__dict__)}

    return ret, ver_info, merged_dict


def _release_app(app_name, version=None):
    cmd = ["release", app_name]
    if version:
        cmd.extend(["-v", version])

    stamp_utils.VMN_LOGGER = None
    ret, vmn_ctx = vmn.vmn_run(cmd)

    vmn_ctx.vcs.initialize_backend_attrs()
    tag_name, ver_infos = vmn_ctx.vcs.backend.get_first_reachable_version_info(
        app_name, type=stamp_utils.RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE
    )
    if tag_name not in ver_infos or ver_infos[tag_name]["ver_info"] is None:
        ver_info = None
    else:
        ver_info = ver_infos[tag_name]["ver_info"]

    try:
        # Python3.9 only
        merged_dict = vmn_ctx.params | vmn_ctx.vcs.__dict__
    except:
        merged_dict = {**(vmn_ctx.params), **(vmn_ctx.vcs.__dict__)}

    return ret, ver_info, merged_dict


def _stamp_app(app_name, release_mode=None, optional_release_mode=None, limited_release_mode=None, prerelease=None):
    args_list = ["stamp"]
    if release_mode is not None:
        args_list.extend(["-r", release_mode])

    if optional_release_mode is not None:
        args_list.extend(["--orm", optional_release_mode])

    if limited_release_mode is not None:
        args_list.extend(["--lrm", limited_release_mode])

    if prerelease is not None:
        args_list.extend(["--pr", prerelease])

    args_list.append(app_name)

    stamp_utils.VMN_LOGGER = None
    ret, vmn_ctx = vmn.vmn_run(args_list)

    tag_name, ver_infos = vmn_ctx.vcs.backend.get_first_reachable_version_info(
        app_name, type=stamp_utils.RELATIVE_TO_CURRENT_VCS_POSITION_TYPE
    )
    if tag_name not in ver_infos or ver_infos[tag_name]["ver_info"] is None:
        ver_info = None
    else:
        ver_info = ver_infos[tag_name]["ver_info"]

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

    stamp_utils.VMN_LOGGER = None
    ret = vmn.vmn_run(args_list)[0]

    return ret


def _gen(
    app_name, template, output, verify_version=False, version=None, custom_path=None
):
    args_list = ["--debug"]
    args_list.extend(["gen"])
    args_list.extend(["--template", template])
    args_list.extend(["--output", output])

    if version is not None:
        args_list.extend(["--version", f"{version}"])

    if verify_version:
        args_list.extend(["--verify-version"])

    if custom_path is not None:
        args_list.extend(["-c", f"{custom_path}"])

    args_list.append(app_name)

    stamp_utils.VMN_LOGGER = None
    ret = vmn.vmn_run(args_list)[0]

    return ret


def _goto(app_name, version=None, root=False):
    args_list = ["goto"]
    if version is not None:
        args_list.extend(["--version", f"{version}"])
    if root:
        args_list.append("--root")

    args_list.append(app_name)

    stamp_utils.VMN_LOGGER = None
    ret = vmn.vmn_run(args_list)[0]

    return ret


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

    stamp_utils.VMN_LOGGER = None
    ret = vmn.vmn_run(args_list)[0]

    return ret


def _configure_2_deps(
    app_layout, params, specific_branch=None, specific_hash=None, specific_tag=None
):
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
        if specific_branch:
            cur_branch = app_layout._repos[repo[0]]["_be"].be.get_active_branch()
            app_layout.checkout("new_branch", repo_name=repo[0], create_new=True)
            app_layout.write_file_commit_and_push(repo[0], "f1.file", "msg1")
            app_layout.write_file_commit_and_push(repo[0], "f1.file", "msg1")
            app_layout.checkout(cur_branch, repo_name=repo[0])
            conf["deps"]["../"][repo[0]].update({"branch": specific_branch})

        be.__del__()

    app_layout.write_conf(params["app_conf_path"], **conf)

    return conf


def _configure_empty_conf(app_layout, params):
    conf = {"deps": {}, "extra_info": False}
    app_layout.write_conf(params["app_conf_path"], **conf)

    return conf