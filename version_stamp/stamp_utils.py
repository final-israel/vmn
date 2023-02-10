#!/usr/bin/env python3
import configparser
import datetime
import glob
import logging
import os
import pathlib
import re
import sys
import time
from logging.handlers import RotatingFileHandler

import git
import yaml

INIT_COMMIT_MESSAGE = "Initialized vmn tracking"

VMN_VERSION_FORMAT = (
    "{major}.{minor}.{patch}[.{hotfix}][-{prerelease}][+{buildmetadata}]"
)
VMN_DEFAULT_TEMPLATE = (
    "[{major}][.{minor}][.{patch}][.{hotfix}]" "[-{prerelease}][+{buildmetadata}]"
)

_SEMVER_VER_REGEX = (
    "(?P<major>0|[1-9]\d*)\." "(?P<minor>0|[1-9]\d*)\." "(?P<patch>0|[1-9]\d*)"
)

_SEMVER_PRERELEASE_REGEX = "(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"

SEMVER_BUILDMETADATA_REGEX = (
    "(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
)

SEMVER_REGEX = (
    f"^{_SEMVER_VER_REGEX}{_SEMVER_PRERELEASE_REGEX}{SEMVER_BUILDMETADATA_REGEX}$"
)

_VMN_HOTFIX_REGEX = "(?:\.(?P<hotfix>0|[1-9]\d*))?"

_VMN_VER_REGEX = f"{_SEMVER_VER_REGEX}" f"{_VMN_HOTFIX_REGEX}"

VMN_VER_REGEX = f"^{_VMN_VER_REGEX}$"

_VMN_REGEX = (
    f"{_VMN_VER_REGEX}" f"{_SEMVER_PRERELEASE_REGEX}" f"{SEMVER_BUILDMETADATA_REGEX}$"
)

# Regex for matching versions stamped by vmn
VMN_REGEX = f"^{_VMN_REGEX}$"

# TODO: create an abstraction layer on top of tag names versus the actual Semver versions
VMN_TAG_REGEX = f"^(?P<app_name>[^\/]+)_{_VMN_REGEX}$"

_VMN_ROOT_REGEX = "(?P<version>0|[1-9]\d*)"
VMN_ROOT_REGEX = f"^{_VMN_ROOT_REGEX}$"

VMN_ROOT_TAG_REGEX = f"^(?P<app_name>[^\/]+)_{_VMN_ROOT_REGEX}$"

VMN_TEMPLATE_REGEX = (
    "^(?:\[(?P<major_template>[^\{\}]*\{major\}[^\{\}]*)\])?"
    "(?:\[(?P<minor_template>[^\{\}]*\{minor\}[^\{\}]*)\])?"
    "(?:\[(?P<patch_template>[^\{\}]*\{patch\}[^\{\}]*)\])?"
    "(?:\[(?P<hotfix_template>[^\{\}]*\{hotfix\}[^\{\}]*)\])?"
    "(?:\[(?P<prerelease_template>[^\{\}]*\{prerelease\}[^\{\}]*)\])?"
    "(?:\[(?P<buildmetadata_template>[^\{\}]*\{buildmetadata\}[^\{\}]*)\])?$"
)

RELATIVE_TO_CURRENT_VCS_POSITION_TYPE = "current"
RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE = "branch"
RELATIVE_TO_GLOBAL_TYPE = "global"

VMN_USER_NAME = "vmn"
VMN_BE_TYPE_GIT = "git"
VMN_BE_TYPE_LOCAL_FILE = "local_file"

LOGGER = None


class WrongTagFormatException(Exception):
    pass


def resolve_root_path():
    cwd = os.getcwd()
    if "VMN_WORKING_DIR" in os.environ:
        cwd = os.environ["VMN_WORKING_DIR"]

    root_path = os.path.realpath(os.path.expanduser(cwd))
    """
            ".git" is the default app's backend in this case. If other backends will be added, 
            then it can be moved to the configuration file as a default_backend or similar. 
        """
    exist = os.path.exists(os.path.join(root_path, ".vmn")) or os.path.exists(
        os.path.join(root_path, ".git")
    )
    while not exist:
        try:
            prev_path = root_path
            root_path = os.path.realpath(os.path.join(root_path, ".."))
            if prev_path == root_path:
                raise RuntimeError()

            exist = os.path.exists(os.path.join(root_path, ".vmn")) or os.path.exists(
                os.path.join(root_path, ".git")
            )
        except Exception as exc:
            LOGGER.debug(f"Logged exception: ", exc_info=True)
            root_path = None
            break
    if root_path is None:
        raise RuntimeError("Running from an unmanaged directory")

    return root_path


class LevelFilter(logging.Filter):
    def __init__(self, low, high):
        self._low = low
        self._high = high
        logging.Filter.__init__(self)

    def filter(self, record):
        if self._low <= record.levelno <= self._high:
            return True
        return False


def init_stamp_logger(rotating_log_path=None, debug=False):
    global LOGGER

    LOGGER = logging.getLogger(VMN_USER_NAME)
    hlen = len(LOGGER.handlers)
    for h in range(hlen):
        LOGGER.handlers[0].close()
        LOGGER.removeHandler(LOGGER.handlers[0])
    flen = len(LOGGER.filters)
    for f in range(flen):
        LOGGER.removeFilter(LOGGER.filters[0])

    LOGGER.setLevel(logging.DEBUG)

    fmt = "[%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    min_stdout_level = logging.INFO
    if debug:
        min_stdout_level = logging.DEBUG

    stdout_handler.addFilter(LevelFilter(min_stdout_level, logging.INFO))
    LOGGER.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)
    LOGGER.addHandler(stderr_handler)

    if rotating_log_path is None:
        return LOGGER

    rotating_file_handler = RotatingFileHandler(
        rotating_log_path,
        maxBytes=1024 * 1024 * 10,
        backupCount=1,
    )
    rotating_file_handler.setLevel(logging.DEBUG)

    fmt = f"%(filename)s:%(lineno)d => %(asctime)s - [%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S")
    rotating_file_handler.setFormatter(formatter)
    LOGGER.addHandler(rotating_file_handler)

    return LOGGER


class VMNBackend(object):
    def __init__(self, type):
        self._type = type

    def __del__(self):
        pass

    def type(self):
        return self._type

    def get_first_reachable_version_info(
        self, app_name, root=False, type=RELATIVE_TO_GLOBAL_TYPE
    ):
        return {}

    def get_active_branch(self, raise_on_detached_head=True):
        return "none"

    def remote(self):
        return "none"

    def last_user_changeset(self):
        return "none"

    @staticmethod
    def app_name_to_git_tag_app_name(app_name):
        return app_name.replace("/", "-")

    @staticmethod
    def gen_unique_id(verstr, hash):
        return f"{verstr}+{hash}"

    @staticmethod
    def get_utemplate_formatted_version(raw_vmn_version, template, hide_zero_hotfix):
        match = re.search(VMN_REGEX, raw_vmn_version)

        gdict = match.groupdict()
        if gdict["hotfix"] == "0" and hide_zero_hotfix:
            gdict["hotfix"] = None

        octats = (
            "major",
            "minor",
            "patch",
            "hotfix",
            "prerelease",
            "buildmetadata",
        )

        formatted_version = ""
        for octat in octats:
            if gdict[octat] is None:
                continue

            if (
                f"{octat}_template" in template
                and template[f"{octat}_template"] is not None
            ):
                d = {octat: gdict[octat]}
                formatted_version = (
                    f"{formatted_version}"
                    f"{template[f'{octat}_template'].format(**d)}"
                )

        return formatted_version

    @staticmethod
    def get_root_app_name_from_name(name):
        root_app_name = name.split("/")
        if len(root_app_name) == 1:
            return None

        return "/".join(root_app_name[:-1])

    @staticmethod
    def serialize_vmn_tag_name(
        app_name,
        version,
        hide_zero_hotfix,
        prerelease=None,
        prerelease_count=None,
        buildmetadata=None,
    ):
        app_name = VMNBackend.app_name_to_git_tag_app_name(app_name)

        verstr = VMNBackend.serialize_vmn_version(
            version,
            prerelease,
            prerelease_count,
            hide_zero_hotfix,
            buildmetadata,
        )

        verstr = f"{app_name}_{verstr}"

        match = re.search(VMN_TAG_REGEX, verstr)
        if match is None:
            err = f"Tag {verstr} doesn't comply with: " f"{VMN_TAG_REGEX} format"
            LOGGER.error(err)

            raise RuntimeError(err)

        return verstr

    @staticmethod
    def serialize_vmn_version(
        current_version,
        prerelease,
        prerelease_count,
        hide_zero_hostfix,
        buildmetadata=None,
    ):
        vmn_version = VMNBackend.get_base_vmn_version(
            current_version, hide_zero_hostfix
        )

        if prerelease is None or prerelease == "release":
            if buildmetadata is not None:
                vmn_version = f"{vmn_version}+{buildmetadata}"

            return vmn_version

        try:
            assert prerelease in prerelease_count
            # TODO: here try to use VMN_VERSION_FORMAT somehow
            vmn_version = f"{vmn_version}-{prerelease}{prerelease_count[prerelease]}"

            match = re.search(VMN_REGEX, vmn_version)
            if match is None:
                err = (
                    f"Tag {vmn_version} doesn't comply with: "
                    f"{VMN_VERSION_FORMAT} format"
                )
                LOGGER.error(err)

                raise RuntimeError(err)
        except AssertionError:
            LOGGER.error(
                f"{prerelease} doesn't appear in {prerelease_count} "
                "Turn on debug mode to see traceback"
            )
            LOGGER.debug("Exception info: ", exc_info=True)

        if buildmetadata is not None:
            vmn_version = f"{vmn_version}+{buildmetadata}"

            match = re.search(VMN_REGEX, vmn_version)
            if match is None:
                err = (
                    f"Tag {vmn_version} doesn't comply with: "
                    f"{VMN_VERSION_FORMAT} format"
                )
                LOGGER.error(err)
                raise RuntimeError(err)

        return vmn_version

    @staticmethod
    def serialize_vmn_version_hotfix(
        hide_zero_hotfix, major, minor, patch, hotfix=None
    ):
        if hide_zero_hotfix and hotfix == "0":
            hotfix = None

        vmn_version = f"{major}.{minor}.{patch}"
        if hotfix is not None:
            vmn_version = f"{vmn_version}.{hotfix}"

        return vmn_version

    @staticmethod
    def get_base_vmn_version(current_version, hide_zero_hotfix):
        match = re.search(VMN_REGEX, current_version)
        gdict = match.groupdict()
        if gdict["hotfix"] is None:
            gdict["hotfix"] = str(0)
        vmn_version = VMNBackend.serialize_vmn_version_hotfix(
            hide_zero_hotfix,
            gdict["major"],
            gdict["minor"],
            gdict["patch"],
            gdict["hotfix"],
        )

        return vmn_version

    @staticmethod
    def deserialize_tag_name(some_tag):
        ret = {
            "app_name": None,
            "type": "version",
            "version": None,
            "root_version": None,
            "major": None,
            "minor": None,
            "patch": None,
            "hotfix": None,
            "prerelease": None,
            "buildmetadata": None,
        }

        match = re.search(VMN_ROOT_TAG_REGEX, some_tag)
        if match is not None:
            gdict = match.groupdict()

            int(gdict["version"])
            ret["root_version"] = gdict["version"]
            ret["app_name"] = gdict["app_name"]
            ret["type"] = "root"

            return ret

        match = re.search(VMN_TAG_REGEX, some_tag)
        if match is None:
            raise WrongTagFormatException()

        gdict = match.groupdict()
        ret["app_name"] = gdict["app_name"].replace("-", "/")
        ret["version"] = f'{gdict["major"]}.{gdict["minor"]}.{gdict["patch"]}'
        ret["major"] = gdict["major"]
        ret["minor"] = gdict["minor"]
        ret["patch"] = gdict["patch"]
        ret["hotfix"] = "0"

        if gdict["hotfix"] is not None:
            ret["hotfix"] = gdict["hotfix"]

        # TODO: Think about what it means that we have the whole
        #  prerelease string here (with the prerelease count).
        #  At least rename other prerelease prefixes to
        #  something like "prerelease mode" or "prerelease prefix"
        if gdict["prerelease"] is not None:
            ret["prerelease"] = gdict["prerelease"]
            ret["type"] = "prerelease"

        if gdict["buildmetadata"] is not None:
            ret["buildmetadata"] = gdict["buildmetadata"]
            ret["type"] = "buildmetadata"

        return ret

    @staticmethod
    def deserialize_vmn_tag_name(vmn_tag):
        try:
            return VMNBackend.deserialize_tag_name(vmn_tag)
        except WrongTagFormatException as exc:
            LOGGER.error(
                f"Tag {vmn_tag} doesn't comply to vmn version format",
                exc_info=True,
            )

            raise exc
        except Exception as exc:
            LOGGER.error(
                f"Failed to deserialize tag {vmn_tag}",
                exc_info=True,
            )

            raise exc


class LocalFileBackend(VMNBackend):
    def __init__(self, repo_path):
        VMNBackend.__init__(self, VMN_BE_TYPE_LOCAL_FILE)

        vmn_dir_path = os.path.join(repo_path, ".vmn")
        if not os.path.isdir(vmn_dir_path):
            raise RuntimeError(
                "LocalFile backend needs to be initialized with a local"
                " path containing .vmn dir in it"
            )

        self.repo_path = repo_path

    def __del__(self):
        pass

    def get_first_reachable_version_info(
        self, app_name, root=False, type=RELATIVE_TO_GLOBAL_TYPE
    ):
        if root:
            dir_path = os.path.join(self.repo_path, ".vmn", app_name, "root_verinfo")
            list_of_files = glob.glob(os.path.join(dir_path, "*.yml"))
            if not list_of_files:
                return None, None

            latest_file = max(list_of_files, key=os.path.getctime)
            with open(latest_file, "r") as f:
                return None, yaml.safe_load(f)

        dir_path = os.path.join(self.repo_path, ".vmn", app_name, "verinfo")
        list_of_files = glob.glob(os.path.join(dir_path, "*.yml"))
        if not list_of_files:
            return None, None

        latest_file = max(list_of_files, key=os.path.getctime)

        with open(latest_file, "r") as f:
            return None, yaml.safe_load(f)

    def get_actual_deps_state(self, vmn_root_path, paths):
        actual_deps_state = {
            ".": {
                "hash": "0xdeadbeef",
                "remote": "none",
                "vcs_type": VMN_BE_TYPE_LOCAL_FILE,
            }
        }

        return actual_deps_state

    def get_tag_version_info(self, tag_name):
        tagd = VMNBackend.deserialize_vmn_tag_name(tag_name)
        if tagd["type"] == "root":
            dir_path = os.path.join(
                self.repo_path, ".vmn", tagd["app_name"], "root_verinfo"
            )
            path = os.path.join(dir_path, f"{tagd['root_version']}.yml")
        else:
            dir_path = os.path.join(self.repo_path, ".vmn", tagd["app_name"], "verinfo")
            path = os.path.join(dir_path, f"{tagd['version']}.yml")

        try:
            with open(path, "r") as f:
                ver_info = yaml.safe_load(f)
        except Exception as exc:
            LOGGER.error("Logged Exception message:", exc_info=True)
            ver_info = None

        return tag_name, ver_info


class GitBackend(VMNBackend):
    def __init__(self, repo_path):
        VMNBackend.__init__(self, VMN_BE_TYPE_GIT)

        self._be = git.Repo(repo_path, search_parent_directories=True)
        self.add_git_user_cfg_if_missing()
        self._origin = self._be.remotes[0]

        vmn_cache_path = os.path.join(repo_path, ".vmn", "vmn.cache")
        if not os.path.exists(vmn_cache_path):
            pathlib.Path(os.path.join(repo_path, ".vmn")).mkdir(
                parents=True, exist_ok=True
            )
            pathlib.Path(vmn_cache_path).touch()

            self._be.git.execute(["git", "fetch", "--tags"])
        else:
            minutes_ago = datetime.datetime.now() - datetime.timedelta(minutes=30)
            filemtime = datetime.datetime.fromtimestamp(
                os.path.getmtime(vmn_cache_path)
            )
            # file is more than 30 minutes old
            if filemtime < minutes_ago:
                pathlib.Path(vmn_cache_path).touch()
                self._be.git.execute(["git", "fetch", "--tags"])

    def __del__(self):
        self._be.close()

    @staticmethod
    def get_repo_details(path):
        try:
            client = git.Repo(path, search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError as exc:
            LOGGER.debug(f'Skipping "{path}" directory reason:\n', exc_info=True)
            return None
        except Exception as exc:
            LOGGER.debug(f'Skipping "{path}" directory reason:\n', exc_info=True)
            return None

        try:
            hash = client.head.commit.hexsha
            remote = tuple(client.remotes[0].urls)[0]
            if os.path.isdir(remote):
                remote = os.path.relpath(remote, client.working_dir)
        except Exception as exc:
            LOGGER.debug(f'Skipping "{path}" directory reason:\n', exc_info=True)
            return None
        finally:
            client.close()

        return hash, remote, "git"

    def is_path_tracked(self, path):
        try:
            self._be.git.execute(["git", "ls-files", "--error-unmatch", path])
            return True
        except Exception as exc:
            LOGGER.debug(f"Logged exception for path {path}: ", exc_info=True)
            return False

    def tag(self, tags, messages, ref="HEAD", push=False):
        for tag, message in zip(tags, messages):
            # This is required in order to preserver chronological order when
            # listing tags since the taggerdate field is in seconds resolution
            time.sleep(1.1)
            self._be.create_tag(tag, ref=ref, message=message)

            if not push:
                continue

            try:
                self._origin.push(f"refs/tags/{tag}", o="ci.skip")
            except Exception:
                self._origin.push(f"refs/tags/{tag}")

    def push(self, tags=()):
        try:
            ret = self._origin.push(
                f"refs/heads/{self.get_active_branch()}", o="ci.skip"
            )
        except Exception:
            ret = self._origin.push(f"refs/heads/{self.get_active_branch()}")

        if ret[0].old_commit is None:
            if "up to date" in ret[0].summary:
                LOGGER.warning(
                    "GitPython library has failed to push because we are "
                    "up to date already. How can it be? "
                )
            else:
                LOGGER.error("Push has failed. Please verify that 'git push' works")
                raise Warning(
                    f"Push has failed because: {ret[0].summary}.\n"
                    "Please verify that 'git push' works"
                )

        for tag in tags:
            try:
                self._origin.push(f"refs/tags/{tag}", o="ci.skip")
            except Exception:
                self._origin.push(f"refs/tags/{tag}")

    def pull(self):
        self._origin.pull()

    def commit(self, message, user, include=None):
        if include is not None:
            for file in include:
                self._be.index.add(file)
        author = git.Actor(user, user)

        self._be.index.commit(message=message, author=author)

    def root(self):
        return self._be.working_dir

    def status(self, tag):
        found_tag = self._be.tag(f"refs/tags/{tag}")
        try:
            return tuple(found_tag.commit.stats.files)
        except Exception as exc:
            LOGGER.debug(f"Logged exception: ", exc_info=True)
            return None

    def get_latest_stamp_tags(
        self, app_name, root_context, type=RELATIVE_TO_GLOBAL_TYPE
    ):
        if root_context:
            msg_filter = f"^{app_name}/.*: Stamped"
        else:
            msg_filter = f"^{app_name}: Stamped"

        if type == RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE:
            cmd_suffix = (
                f"refs/heads/{self.get_active_branch(raise_on_detached_head=False)}"
            )
        elif type == RELATIVE_TO_CURRENT_VCS_POSITION_TYPE:
            cmd_suffix = "HEAD"
        else:
            cmd_suffix = f"--branches"

        shallow = os.path.exists(os.path.join(self._be.common_dir, "shallow"))
        if shallow:
            tag_names = self._get_shallow_first_reachable_vmn_stamp_tag_list(
                app_name,
                cmd_suffix,
                msg_filter,
            )
        else:
            tag_names = self._get_first_reachable_vmn_stamp_tag_list(
                app_name,
                cmd_suffix,
                msg_filter
            )

        return tag_names

    def _get_first_reachable_vmn_stamp_tag_list(self, app_name, cmd_suffix, msg_filter):
        res = self._get_top_vmn_commit(app_name, cmd_suffix, msg_filter)
        tag_objects = res[1]
        bug_limit = 0
        while not tag_objects and bug_limit < 100:
            if res[0] is None:
                break

            cmd_suffix = f"{res[0].hexsha}~1"
            res = self._get_top_vmn_commit(app_name, cmd_suffix, msg_filter)
            tag_objects = res[1]

            bug_limit += 1
            if bug_limit == 100:
                LOGGER.warning(
                    f"Probable bug: vmn failed to find "
                    f"vmn's commit after 100 interations."
                )
                tag_objects = []
                break

        # We want the newest tag on top because we skip "buildmetadata tags"
        # TODO:: solve the weird coupling between here and get_first_reachable_version_info
        tag_objects = sorted(
            tag_objects, key=lambda t: t.object.tagged_date, reverse=True
        )
        tag_names = []
        for tag_object in tag_objects:
            tag_names.append(tag_object.name)

        return tag_names

    def _get_shallow_first_reachable_vmn_stamp_tag_list(
        self, app_name, cmd_suffix, msg_filter
    ):
        res = self._get_top_vmn_commit(app_name, cmd_suffix, msg_filter)

        if res[1]:
            # We want the newest tag on top because we skip "buildmetadata tags"
            # TODO:: solve the weird coupling between here and get_first_reachable_version_info
            res[1] = sorted(
                res[1], key=lambda t: t.object.tagged_date, reverse=True
            )
            tag_names = []
            for tag_object in res[1]:
                tag_names.append(tag_object.name)

            return tag_names

        tag_name_prefix = VMNBackend.app_name_to_git_tag_app_name(app_name)
        cmd = ["--sort", "taggerdate", "--list", f"{tag_name_prefix}_*"]
        tag_names = self._be.git.tag(*cmd).split("\n")

        if len(tag_names) == 1 and tag_names[0] == "":
            tag_names.pop(0)

        if not tag_names:
            return tag_names

        latest_tag = tag_names[-1]
        head_date = self._be.head.commit.committed_date
        for tname in reversed(tag_names):
            o = self.get_tag_object_from_tag_name(tname)
            if o:
                if (
                    self._be.head.commit.hexsha != o.commit.hexsha
                    and head_date < o.object.tagged_date
                ):
                    continue

                latest_tag = tname
                break

        try:
            found_tag = self._be.tag(f"refs/tags/{latest_tag}")
        except Exception as exc:
            LOGGER.error(f"Failed to get tag object from tag name: {latest_tag}")
            return []

        head_tags = self.get_all_commit_tags(found_tag.commit.hexsha)
        tag_objects = []

        for tname in head_tags:
            o = self.get_tag_object_from_tag_name(tname)
            if o:
                tag_objects.append(o)

        # We want the newest tag on top because we skip "buildmetadata tags"
        # TODO:: solve the weird coupling between here and get_first_reachable_version_info
        tag_objects = sorted(
            tag_objects, key=lambda t: t.object.tagged_date, reverse=True
        )

        final_list_of_tag_names = []
        for tag_object in tag_objects:
            final_list_of_tag_names.append(tag_object.name)

        return final_list_of_tag_names

    def _get_top_vmn_commit(self, app_name, cmd_suffix, msg_filter):
        cmd = [
            f"--grep={msg_filter}",
            f"-1",
            f"--author={VMN_USER_NAME}",
            "--pretty=%H,,,%D",
            "--decorate=short",
            cmd_suffix,
        ]
        LOGGER.debug(f"Going to run: git log {' '.join(cmd)}")
        res = self._be.git.log(*cmd).split("\n")
        if len(res) == 1 and res[0] == "":
            res.pop(0)

        if not res:
            return [None, []]

        items = res[0].split(",,,")
        _tag_objects = []

        commit_hex = items[0]
        commit_obj = self.get_commit_object_from_commit_hex(commit_hex)

        for t in items[1].split(","):
            if "tag:" not in t:
                # Maybe rebase or tag was removed. Will handle the rebase case here
                try:
                    verstr = commit_obj.message.split(" version ")[1].strip()
                    tagname = f"{app_name}_{verstr}"
                    o = self.get_tag_object_from_tag_name(tagname)
                    if o:
                        _tag_objects.append(o)
                except Exception as exc:
                    LOGGER.debug(f"Skipped on {commit_hex} commit")

                continue

            tname = t.split("tag:")[1].strip()
            # TODO:: add call desearilize here
            o = self.get_tag_object_from_tag_name(tname)
            if o:
                _tag_objects.append(o)

        return [commit_obj, _tag_objects]

    def get_latest_available_tag(self, tag_prefix_filter):
        cmd = ["--sort", "taggerdate", "--list", tag_prefix_filter]
        tag_names = self._be.git.tag(*cmd).split("\n")

        if len(tag_names) == 1 and tag_names[0] == "":
            return None

        return tag_names[-1]

    def get_commit_object_from_branch_name(self, bname):
        # TODO:: Unfortunately, need to spend o(N) here
        for branch in self._be.branches:
            if bname != branch.name:
                continue

            # yay, we found the tag's commit object
            return branch.commit

        raise RuntimeError(
            f"Somehow did not find a branch commit object for branch: {bname}"
        )

    def get_tag_object_from_tag_name(self, tname):
        o = self._be.tag(f"refs/tags/{tname}")
        try:
            if o.commit.author.name != "vmn":
                return None
        except Exception as exc:
            LOGGER.debug("Exception info: ", exc_info=True)
            return None

        if o.tag is None:
            return None

        if o is None:
            LOGGER.debug(f"Somehow did not find a tag object for tag: {tname}")

        return o

    def get_all_commit_tags(self, hexsha="HEAD"):
        if hexsha is None:
            hexsha = "HEAD"

        cmd = ["--points-at", hexsha]
        tags = self._be.git.tag(*cmd).split("\n")

        if len(tags) == 1 and tags[0] == "":
            tags.pop(0)

        final_tags = []
        for t in tags:
            tag_msg = self.get_tag_message(t)
            if tag_msg is None:
                LOGGER.debug(
                    f"Probably non-vmn tag - {t} with tag msg: {tag_msg}. Skipping ",
                    exc_info=True,
                )
                continue

            final_tags.append(t)

        return final_tags

    def get_all_brother_tags(self, tag_name):
        try:
            sha = self.changeset(tag=tag_name)
            tags = self.get_all_commit_tags(sha)
        except Exception as exc:
            LOGGER.debug(
                f"Failed to get brother tags for tag: {tag_name}. "
                f"Logged exception: ",
                exc_info=True,
            )
            return []

        return tags

    def in_detached_head(self):
        return self._be.head.is_detached

    def add_git_user_cfg_if_missing(self):
        try:
            self._be.config_reader().get_value("user", "name")
            self._be.config_reader().get_value("user", "email")
        except (configparser.NoSectionError, configparser.NoOptionError):
            # git user name or email configuration is missing, add default override
            self._be.git.set_persistent_git_options(
                c=[f'user.name="{VMN_USER_NAME}"', f'user.email="{VMN_USER_NAME}"']
            )

    def check_for_pending_changes(self):
        if self._be.is_dirty():
            err = f"Pending changes in {self.root()}."
            return err

        return None

    def check_for_outgoing_changes(self):
        if self.in_detached_head():
            err = f"Detached head in {self.root()}."
            return err

        branch_name = self._be.active_branch.name
        try:
            self._be.git.rev_parse("--verify", f"{self._origin.name}/{branch_name}")
        except Exception:
            err = (
                f"Branch {self._origin.name}/{branch_name} does not exist. "
                "Please push or set-upstream branch to "
                f"{self._origin.name}/{branch_name} of branch {branch_name}"
            )
            return err

        outgoing = tuple(
            self._be.iter_commits(f"{self._origin.name}/{branch_name}..{branch_name}")
        )

        if len(outgoing) > 0:
            err = (
                f"Outgoing changes in {self.root()} "
                f"from branch {branch_name} "
                f"({self._origin.name}/{branch_name}..{branch_name})\n"
                f"The commits that are outgoing are: {outgoing}"
            )

            return err

        return None

    def checkout_branch(self, branch_name=None):
        try:
            if branch_name is None:
                branch_name = self.get_active_branch(raise_on_detached_head=False)

            self.checkout(branch=branch_name)
        except Exception:
            logging.info("Failed to get branch name. Trying to checkout to master")
            LOGGER.debug("Exception info: ", exc_info=True)
            # TODO:: change to some branch name that can be retreived from repo
            try:
                self.checkout(branch="master")
            except Exception as exc:
                self.checkout(branch="main")

        return self._be.active_branch.commit.hexsha

    def get_active_branch(self, raise_on_detached_head=True):
        # TODO:: return the full ref name: refs/heads/..
        if not self.in_detached_head():
            active_branch = self._be.active_branch.name
        else:
            if raise_on_detached_head:
                LOGGER.error("Active branch cannot be found in detached head")
                raise RuntimeError()

            active_branch = self.get_branch_from_changeset(self._be.head.commit.hexsha)

        return active_branch

    def get_branch_from_changeset(self, hexsha):
        out = self._be.git.branch("--contains", hexsha)
        out = out.split("\n")[1:]
        if not out:
            # TODO:: add debug print here
            out = self._be.git.branch().split("\n")[1:]

        active_branches = []
        for item in out:
            active_branches.append(item.strip())
        if len(active_branches) > 1:
            LOGGER.info(
                "In detached head. Commit hash: "
                f"{self._be.head.commit.hexsha} is "
                f"related to multiple branches: {active_branches}. "
                "Using the first one as the active branch"
            )

        active_branch = active_branches[0]
        return active_branch

    def checkout(self, rev=None, tag=None, branch=None):
        if tag is not None:
            # TODO:: maybe it issafer to
            rev = f"refs/tags/{tag}"
        elif branch is not None:
            # TODO:: : f"refs/heads/{branch}"
            rev = f"{branch}"

        assert rev is not None

        self._be.git.checkout(rev)

    @staticmethod
    def get_actual_deps_state(vmn_root_path, paths):
        actual_deps_state = {}
        for path in paths:
            full_path = os.path.join(vmn_root_path, path)
            details = GitBackend.get_repo_details(full_path)
            if details is None:
                continue

            actual_deps_state[path] = {
                "hash": details[0],
                "remote": details[1],
                "vcs_type": details[2],
            }

        return actual_deps_state

    def last_user_changeset(self):
        p = self._be.head.commit
        if p.author.name == VMN_USER_NAME:
            if p.message.startswith(INIT_COMMIT_MESSAGE):
                return p.hexsha

            tags = self.get_all_commit_tags(p.hexsha)
            if not tags:
                LOGGER.warning(
                    f"Somehow vmn's commit {p.hexsha} has no tags. "
                    f"Check your repo. Assuming this commit is a user commit"
                )
                return p.hexsha

            for t in tags:
                _, verinfo = self.get_tag_version_info(t)
                if "stamping" in verinfo:
                    return verinfo["stamping"]["app"]["changesets"]["."]["hash"]

            LOGGER.warning(
                f"Somehow vmn's commit {p.hexsha} has no tags that are parsable. "
                f"Check your repo. Assuming this commit is a user commit"
            )
            return p.hexsha

        return p.hexsha

    def remote(self):
        remote = tuple(self._origin.urls)[0]

        if os.path.isdir(remote):
            remote = os.path.relpath(remote, self.root())

        return remote

    def changeset(self, tag=None, short=False):
        if tag is None:
            return self._be.head.commit.hexsha

        found_tag = self._be.tag(f"refs/tags/{tag}")

        try:
            return found_tag.commit.hexsha
        except Exception as exc:
            LOGGER.debug(f"Logged exception: ", exc_info=True)
            return None

    def revert_local_changes(self, files=[]):
        if files:
            try:
                try:
                    for f in files:
                        self._be.git.reset(f)
                except Exception as exc:
                    LOGGER.debug(f"Failed to git reset files: {files}", exc_info=True)

                self._be.index.checkout(files, force=True)
            except Exception as exc:
                LOGGER.debug(f"Failed to git checkout files: {files}", exc_info=True)

    def revert_vmn_commit(self, prev_changeset, version_files, tags=[]):
        self.revert_local_changes(version_files)

        # TODO: also validate that the commit is
        #  currently worked on app name
        if self.changeset() == prev_changeset:
            return

        if self._be.active_branch.commit.author.name != VMN_USER_NAME:
            LOGGER.error("BUG: Will not revert non-vmn commit.")
            raise RuntimeError()

        self._be.git.reset("--hard", "HEAD~1")
        for tag in tags:
            try:
                self._be.delete_tag(tag)
            except Exception:
                LOGGER.info(f"Failed to remove tag {tag}")
                LOGGER.debug("Exception info: ", exc_info=True)

                continue

        try:
            self._be.git.fetch("--tags")
        except Exception:
            LOGGER.info("Failed to fetch tags")
            LOGGER.debug("Exception info: ", exc_info=True)

    def get_first_reachable_version_info(
        self, app_name, root_context=False, type=RELATIVE_TO_GLOBAL_TYPE
    ):
        app_tags = self.get_latest_stamp_tags(app_name, root_context, type)
        cleaned_app_tag = None

        if root_context:
            regex = VMN_ROOT_TAG_REGEX
        else:
            regex = VMN_TAG_REGEX

        for tag in app_tags:
            # skip buildmetadata versions
            if "+" in tag:
                continue

            match = re.search(regex, tag)
            if match is None:
                continue

            gdict = match.groupdict()

            if gdict["app_name"] != app_name.replace("/", "-"):
                continue

            cleaned_app_tag = tag
            break

        if cleaned_app_tag is None:
            return None, None

        return self.get_tag_version_info(cleaned_app_tag)

    def get_tag_version_info(self, tag_name):
        tag_name, commit_tag_obj = self.get_commit_object_from_tag_name(tag_name)

        if commit_tag_obj is None or commit_tag_obj.author.name != VMN_USER_NAME:
            LOGGER.debug(f"Corrupted tag {tag_name}: author name is not vmn")
            return tag_name, None

        tag_msg = self.get_tag_message(tag_name)
        if not tag_msg:
            LOGGER.debug(f"Corrupted tag msg of tag {tag_name}")
            return tag_name, None

        all_tags = {}

        tags = self.get_all_brother_tags(tag_name)
        for tag in tags:
            tagd = VMNBackend.deserialize_vmn_tag_name(tag)
            tagd.update({"tag": tag})
            tagd["message"] = self.get_tag_message(tag)

            all_tags[tagd["type"]] = tagd

            # TODO:: Check API commit version

        if "root_app" not in tag_msg["stamping"] and "root" in all_tags:
            tag_msg["stamping"].update(all_tags["root"]["message"]["stamping"])
        elif "app" not in tag_msg["stamping"] and "version" in all_tags:
            tag_msg["stamping"].update(all_tags["version"]["message"]["stamping"])

        return tag_name, tag_msg

    def get_tag_message(self, tag_name):
        tag_exists = True
        try:
            o = self._be.tag(f"refs/tags/{tag_name}").object
        except Exception as exc:
            tag_exists = False

        if not tag_exists:
            return None

        # TODO:: Check API commit version
        # safe_load discards any text before the YAML document (if present)
        tag_msg = yaml.safe_load(self._be.tag(f"refs/tags/{tag_name}").object.message)
        if tag_msg is None:
            return None

        if type(tag_msg) is not dict and tag_msg.startswith("Automatic"):
            # Code from vmn 0.3.9
            # safe_load discards any text before the YAML document (if present)
            commit_msg = yaml.safe_load(self._be.commit(tag_name).message)

            if commit_msg is not None and "stamping" in commit_msg:
                commit_msg["stamping"]["app"]["prerelease"] = "release"
                commit_msg["stamping"]["app"]["prerelease_count"] = {}

            tag_msg = commit_msg
            if tag_msg is None:
                return None

        if "vmn_info" not in tag_msg:
            LOGGER.debug(f"vmn_info key was not found in tag {tag_name}")
            return None

        return tag_msg

    def get_commit_object_from_commit_hex(self, hex):
        return self._be.commit(hex)

    def get_commit_object_from_tag_name(self, tag_name):
        try:
            commit_tag_obj = self._be.commit(tag_name)
        except Exception as exc:
            LOGGER.debug(f"Logged exception: ", exc_info=True)
            # Backward compatability code for vmn 0.3.9:
            try:
                _tag_name = f"{tag_name}.0"
                commit_tag_obj = self._be.commit(_tag_name)
                tag_name = _tag_name
            except Exception as exc:
                LOGGER.debug(f"Logged exception: ", exc_info=True)
                return tag_name, None

        return tag_name, commit_tag_obj

    @staticmethod
    def clone(path, remote):
        git.Repo.clone_from(f"{remote}", f"{path}")


def get_client(root_path, be_type):
    if be_type == "local_file":
        be = LocalFileBackend(root_path)
        return be, None

    try:
        client = git.Repo(root_path, search_parent_directories=True)
        client.close()

        be = GitBackend(root_path)
        return be, None
    except git.exc.InvalidGitRepositoryError:
        err = f"repository path: {root_path} is not a functional git or repository.\n"
        return None, err
