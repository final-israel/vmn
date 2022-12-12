#!/usr/bin/env python3
import sys
import os
import git
import logging
import glob
import re
import time
import yaml
import configparser
from logging.handlers import RotatingFileHandler

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
LOGGER = None


def resolve_root_path():
    cwd = os.getcwd()
    if "VMN_WORKING_DIR" in os.environ:
        cwd = os.environ["VMN_WORKING_DIR"]

    root_path = os.path.realpath(os.path.expanduser(cwd))
    """
            ".git" is the default app's backend in this case. If other backends will be added, 
            then it can be moved to the configuration file as a default_backend or similar. 
        """
    exist = os.path.exists(os.path.join(root_path, ".vmn")) or \
            os.path.exists(os.path.join(root_path, ".git"))
    while not exist:
        try:
            prev_path = root_path
            root_path = os.path.realpath(os.path.join(root_path, ".."))
            if prev_path == root_path:
                raise RuntimeError()

            exist = os.path.exists(os.path.join(root_path, ".vmn")) or \
                    os.path.exists(os.path.join(root_path, ".git"))
        except:
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


def init_stamp_logger(rotating_log_path, debug=False):
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

    stdout_handler.addFilter(
        LevelFilter(min_stdout_level, logging.INFO)
    )
    LOGGER.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)
    LOGGER.addHandler(stderr_handler)

    rotating_file_handler = RotatingFileHandler(
        rotating_log_path, maxBytes=1024 * 10, backupCount=1,
    )
    rotating_file_handler.setLevel(logging.DEBUG)

    bold_char = '\033[1m'
    end_char = '\033[0m'
    fmt = f"{bold_char}%(asctime)s - [%(levelname)s]{end_char} %(message)s"
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

    @staticmethod
    def app_name_to_git_tag_app_name(app_name):
        return app_name.replace("/", "-")

    @staticmethod
    def gen_unique_id(verstr, hash):
        return f"{verstr}+{hash}"

    @staticmethod
    def deserialize_vmn_tag_name(vmn_tag):
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

        match = re.search(VMN_ROOT_TAG_REGEX, vmn_tag)
        if match is not None:
            gdict = match.groupdict()
            if gdict["version"] is not None:
                int(gdict["version"])
                ret["root_version"] = gdict["version"]
                ret["app_name"] = gdict["app_name"]
                ret["type"] = "root"

            return ret

        match = re.search(VMN_TAG_REGEX, vmn_tag)
        if match is None:
            LOGGER.error(f"Tag {vmn_tag} doesn't comply to vmn version format")
            raise RuntimeError()

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


class LocalFileBackend(VMNBackend):
    def __init__(self, repo_path):
        VMNBackend.__init__(self, "local_file")

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
                return None

            latest_file = max(list_of_files, key=os.path.getctime)
            with open(latest_file, "r") as f:
                return yaml.safe_load(f)

        dir_path = os.path.join(self.repo_path, ".vmn", app_name, "verinfo")
        list_of_files = glob.glob(os.path.join(dir_path, "*.yml"))
        if not list_of_files:
            return None

        latest_file = max(list_of_files, key=os.path.getctime)

        with open(latest_file, "r") as f:
            return yaml.safe_load(f)


class GitBackend(VMNBackend):
    def __init__(self, repo_path):
        VMNBackend.__init__(self, "git")

        self._be = git.Repo(repo_path, search_parent_directories=True)
        self.add_git_user_cfg_if_missing()
        self._origin = self._be.remotes[0]

        self._be.git.fetch("--tags")

    def __del__(self):
        self._be.close()

    def is_path_tracked(self, path):
        try:
            self._be.git.execute(["git", "ls-files", "--error-unmatch", path])
            return True
        except:
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
        except:
            return None

    def tags(self, filter, type=RELATIVE_TO_GLOBAL_TYPE):
        if type == RELATIVE_TO_CURRENT_VCS_BRANCH_TYPE:
            cmd_suffix = f"refs/heads/{self.get_active_branch(raise_on_detached_head=False)}"
        elif type == RELATIVE_TO_CURRENT_VCS_POSITION_TYPE:
            cmd_suffix = "HEAD"
        else:
            cmd_suffix = f"--branches"

        cmd = [
            f"--grep={filter}",
            f"-1",
            f"--author={VMN_USER_NAME}",
            "--pretty=%H,,,%D",
            "--decorate=short",
            cmd_suffix
        ]

        tag_names = self._be.git.log(*cmd).split("\n")
        if len(tag_names) == 1 and tag_names[0] == "":
            tag_names.pop(0)

        if not tag_names:
            return tag_names

        items = tag_names[0].split(',,,')
        tag_names[0].split(',,,')[1].split(',')

        tag_objects = []
        for t in items[1].split(','):
            if not "tag:" in t:
                continue

            tname = t.split("tag:")[1].strip()
            o = self.get_tag_object_from_tag_name(tname)
            if o:
                tag_objects.append(o)

        tag_objects = sorted(tag_objects, key=lambda t: t.object.tagged_date)

        final_list_of_tag_names = []
        for tag_object in tag_objects:
            final_list_of_tag_names.append(tag_object.name)

        idx_release = -1
        idx_prerelease = -1
        for i in range(len(final_list_of_tag_names)):
            tagd = VMNBackend.deserialize_vmn_tag_name(
                final_list_of_tag_names[i]
            )
            if tagd["prerelease"] and not tagd["buildmetadata"]:
                idx_prerelease = i
            if not tagd["prerelease"] and not tagd["buildmetadata"]:
                idx_release = i

        if idx_prerelease != -1 and idx_release != -1:
            final_list_of_tag_names[idx_release], final_list_of_tag_names[idx_prerelease] = final_list_of_tag_names[idx_prerelease], final_list_of_tag_names[idx_release]

        return final_list_of_tag_names

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

    def get_all_commit_tags(self, hexsha):
        cmd = ["--points-at", hexsha]
        tags = self._be.git.tag(*cmd).split("\n")

        if len(tags) == 1 and tags[0] == "":
            tags.pop(0)

        return tags

    def get_all_brother_tags(self, tag_name):
        return self.get_all_commit_tags(self.changeset(tag=tag_name))

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
            err = f"Outgoing changes in {self.root()} " \
                  f"from branch {branch_name} " \
                  f"({self._origin.name}/{branch_name}..{branch_name})\n" \
                  f"The commits that are outgoing are: {outgoing}"

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
            self.checkout(branch="master")

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

    # TODO:: Missing impl in LocalFileBackend
    def last_user_changeset(self):
        p = self._be.head.commit
        if p.author.name == VMN_USER_NAME:
            if p.message.startswith(INIT_COMMIT_MESSAGE):
                return p.hexsha

            tags = self.get_all_commit_tags(p.hexsha)
            for t in tags:
                _, verinfo = self.get_version_info_from_tag_name(t)
                if "stamping" in verinfo:
                    return verinfo["stamping"]["app"]["changesets"]["."]["hash"]

            return None

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
        except:
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
            self, app_name, root=False, type=RELATIVE_TO_GLOBAL_TYPE
    ):
        if root:
            regex = VMN_ROOT_TAG_REGEX
            f = f"{app_name}/.*: Stamped"
        else:
            regex = VMN_TAG_REGEX
            f = f"{app_name}: Stamped"

        app_tags = self.tags(f, type)
        cleaned_app_tag = None
        for tag in app_tags:
            match = re.search(regex, tag)
            if match is None:
                continue

            gdict = match.groupdict()

            if gdict["app_name"] != app_name.replace("/", "-"):
                continue

            cleaned_app_tag = tag
            break

        if cleaned_app_tag is None:
            return None

        _, verinfo = self.get_version_info_from_tag_name(cleaned_app_tag)

        return verinfo

    def get_version_info_from_tag_name(self, tag_name):
        try:
            commit_tag_obj = self._be.commit(tag_name)
        except:
            # Backward compatability code for vmn 0.3.9:
            try:
                _tag_name = f"{tag_name}.0"
                commit_tag_obj = self._be.commit(_tag_name)
                tag_name = _tag_name
            except:
                return tag_name, None

        if commit_tag_obj.author.name != VMN_USER_NAME:
            LOGGER.debug(f"Corrupted tag {tag_name}: author name is not vmn")
            return tag_name, None

        # TODO:: Check API commit version

        # safe_load discards any text before the YAML document (if present)
        tag_msg = yaml.safe_load(self._be.tag(f"refs/tags/{tag_name}").object.message)

        if type(tag_msg) is not dict and tag_msg.startswith("Automatic"):
            # Code from vmn 0.3.9
            # safe_load discards any text before the YAML document (if present)
            commit_msg = yaml.safe_load(self._be.commit(tag_name).message)

            if commit_msg is None or "stamping" not in commit_msg:
                return tag_name, None

            commit_msg["stamping"]["app"]["prerelease"] = "release"
            commit_msg["stamping"]["app"]["prerelease_count"] = {}

            return tag_name, commit_msg

        if not tag_msg:
            LOGGER.debug(f"Corrupted tag msg of tag {tag_name}")
            return tag_name, None

        all_tags = {}

        tags = self.get_all_brother_tags(tag_name)
        for tag in tags:
            tagd = VMNBackend.deserialize_vmn_tag_name(tag)
            tagd.update({"tag": tag})
            tagd["message"] = self._be.tag(f"refs/tags/{tag}").object.message

            all_tags[tagd["type"]] = tagd

            # TODO:: Check API commit version

        if "root_app" not in tag_msg["stamping"] and "root" in all_tags:
            tag_msg["stamping"].update(
                yaml.safe_load(all_tags["root"]["message"])["stamping"]
            )
        elif "app" not in tag_msg["stamping"] and "version" in all_tags:
            tag_msg["stamping"].update(
                yaml.safe_load(all_tags["version"]["message"])["stamping"]
            )

        return tag_name, tag_msg

    @staticmethod
    def clone(path, remote):
        git.Repo.clone_from(f"{remote}", f"{path}")


class HostState(object):
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

    @staticmethod
    def get_actual_deps_state(vmn_root_path, paths):
        actual_deps_state = {}
        for path in paths:
            full_path = os.path.join(vmn_root_path, path)
            details = HostState.get_repo_details(full_path)
            if details is None:
                continue

            actual_deps_state[path] = {
                "hash": details[0],
                "remote": details[1],
                "vcs_type": details[2],
            }

        return actual_deps_state


def get_client(path):
    try:
        client = git.Repo(path, search_parent_directories=True)
        client.close()

        be = GitBackend(path)
        return be, None
    except git.exc.InvalidGitRepositoryError:
        err = f"repository path: {path} is not a functional git or repository.\n"
        return None, err
