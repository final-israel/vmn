#!/usr/bin/env python3
import argparse
import random
import time
from pathlib import Path
import copy
import yaml
import sys
import os
import pathlib
from filelock import FileLock
from multiprocessing import Pool
import re
import tomlkit
from packaging import version as pversion

CUR_PATH = "{0}/".format(os.path.dirname(__file__))
VER_FILE_NAME = "last_known_app_version.yml"
IGNORED_FILES = ["vmn.lock"]

sys.path.append(CUR_PATH)

import version as version_mod
from stamp_utils import HostState
import stamp_utils

LOGGER = stamp_utils.init_stamp_logger()


class VMNContextMAnagerManager(object):
    def __init__(self, command_line):
        self.args = parse_user_commands(command_line)
        global LOGGER
        LOGGER = stamp_utils.init_stamp_logger(self.args.debug)

        cwd = os.getcwd()
        if "VMN_WORKING_DIR" in os.environ:
            cwd = os.environ["VMN_WORKING_DIR"]

        root = False
        if "root" in self.args:
            root = self.args.root
        from_file = False
        if "from_file" in self.args and self.args.from_file:
            from_file = True
        initial_params = {
            "root": root,
            "cwd": cwd,
            "name": None,
            "from_file": from_file,
        }

        if "name" in self.args and self.args.name:
            validate_app_name(self.args)
            initial_params["name"] = self.args.name

        params = build_world(
            initial_params["name"],
            initial_params["cwd"],
            initial_params["root"],
            initial_params["from_file"],
        )

        if params is None:
            raise RuntimeError("params initialization failed")

        vmn_path = os.path.join(params["root_path"], ".vmn")
        lock_file_path = os.path.join(vmn_path, "vmn.lock")
        pathlib.Path(os.path.dirname(lock_file_path)).mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(lock_file_path)
        self.params = params
        self.vcs = None
        self.lock_file_path = lock_file_path

    def __enter__(self):
        self.lock.acquire()
        self.vcs = VersionControlStamper(self.params)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.vcs is not None:
            del self.vcs

        self.lock.release()


class IVersionsStamper(object):
    '''
    name: str
    unit_price: float
    quantity_on_hand: int = 0
    '''
    def __init__(self, conf):
        self.backend = conf["be"]

        self.root_path = conf["root_path"]
        self.repo_name = '.'
        self.name = conf["name"]
        self.template = stamp_utils.VMN_DEFAULT_TEMPLATE
        self.extra_info = False
        self.create_verinfo_files = False
        self.hide_zero_hotfix = True
        self.version_backends = {}
        self.should_publish = True
        self.current_version_info = {
                "vmn_info": {
                    "description_message_version": "1.1",
                    "vmn_version": version_mod.version,
                },
                "stamping": {
                    "msg": "",
                    "app": {
                        "info": {},
                    },
                    "root_app": {},
                },
            }

        if self.name is None:
            self.tracked = False
            return

        self.last_user_changeset = self.backend.last_user_changeset(self.name)

        if conf["from_file"]:
            self.raw_configured_deps = {
                os.path.join("../"): {
                    os.path.basename(self.root_path):
                        {
                            "remote": None,
                            "vcs_type": None
                        }
                }
            }
        else:
            self.raw_configured_deps = {
                os.path.join("../"): {
                    os.path.basename(self.root_path):
                        {
                            "remote": self.backend.remote(),
                            "vcs_type": self.backend.type()
                        }
                }
            }

            deps = {}
            for rel_path, dep in self.raw_configured_deps.items():
                deps[os.path.join(self.root_path, rel_path)] = tuple(dep.keys())

            self.actual_deps_state = \
                HostState.get_actual_deps_state(deps, self.root_path)

            if self.name is not None:
                self.actual_deps_state["."]["hash"] = self.last_user_changeset

        self.initialize_paths(conf)
        self.update_attrs_from_app_conf_file(conf)

        self.flat_configured_deps = self.get_deps_changesets()

        # TODO: this is ugly
        root_context = self.root_app_name == self.name
        self.ver_info_from_repo = self.backend.get_vmn_version_info(
            self.name, root_context
        )
        self.tracked = self.ver_info_from_repo is not None

        if root_context:
            return

        self.current_version_info["stamping"]["app"]["name"] = \
            self.name
        if not conf["from_file"]:
            self.current_version_info["stamping"]["app"]["changesets"] = \
                self.actual_deps_state

        if self.root_app_name is not None:
            self.current_version_info["stamping"]["root_app"] = {
                "name": self.root_app_name,
                "latest_service": self.name,
                "services": {},
                "external_services": {},
            }

    def update_attrs_from_app_conf_file(self, conf):
        if os.path.isfile(self.app_conf_path):
            with open(self.app_conf_path, "r") as f:
                data = yaml.safe_load(f)
                self.template = data["conf"]["template"]
                self.extra_info = data["conf"]["extra_info"]
                self.raw_configured_deps = data["conf"]["deps"]
                if "hide_zero_hotfix" in data["conf"]:
                    self.hide_zero_hotfix = data["conf"]["hide_zero_hotfix"]
                if "version_backends" in data["conf"]:
                    self.version_backends = data["conf"]["version_backends"]
                if "create_verinfo_files" in data["conf"]:
                    self.create_verinfo_files = data["conf"]["create_verinfo_files"]

                self.set_template(self.template)

                if not conf["from_file"]:
                    deps = {}
                    for rel_path, dep in self.raw_configured_deps.items():
                        deps[os.path.join(self.root_path, rel_path)] = \
                            tuple(dep.keys())

                    self.actual_deps_state.update(
                        HostState.get_actual_deps_state(deps, self.root_path)
                    )
                    self.actual_deps_state["."]["hash"] = self.last_user_changeset

    def initialize_paths(self, conf):
        self.app_dir_path = os.path.join(
            self.root_path,
            ".vmn",
            self.name.replace("/", os.sep),
        )
        self.version_file_path = \
            os.path.join(self.app_dir_path, VER_FILE_NAME)
        self.app_conf_path = \
            os.path.join(self.app_dir_path, "conf.yml")
        if conf["root"]:
            self.root_app_name = self.name
        else:
            self.root_app_name = \
                stamp_utils.VMNBackend.get_root_app_name_from_name(
                    self.name
                )
        self.root_app_dir_path = self.app_dir_path
        self.root_app_conf_path = None
        if self.root_app_name is not None:
            self.root_app_dir_path = os.path.join(
                self.root_path,
                ".vmn",
                self.root_app_name,
            )

            self.root_app_dir_path = self.root_app_dir_path
            self.root_app_conf_path = \
                os.path.join(
                    self.root_app_dir_path,
                    "root_conf.yml"
                )

    def set_template(self, template):
        try:
            self.template = IVersionsStamper.parse_template(template)
            self.bad_format_template = False
        except:
            self.template = IVersionsStamper.parse_template(
                stamp_utils.VMN_DEFAULT_TEMPLATE
            )
            self.template_err_str = (
                "Failed to parse template: "
                f"{template}. "
                f"Falling back to default one: "
                f"{stamp_utils.VMN_DEFAULT_TEMPLATE}"
            )

            self.bad_format_template = True

    def __del__(self):
        del self.backend

    # Note: this function generates
    # a version (including prerelease)
    def gen_app_version(
        self, initial_version, initialprerelease, initialprerelease_count
    ):
        if initialprerelease == "release" and self.release_mode is None:
            LOGGER.error(
                "When stamping from a previous release version, "
                "a release mode must be specified"
            )
            raise RuntimeError()

        match = re.search(stamp_utils.VMN_REGEX, initial_version)
        gdict = match.groupdict()
        if gdict["hotfix"] is None:
            gdict["hotfix"] = str(0)

        match = re.search(
            stamp_utils.VMN_REGEX,
            self.ver_info_from_repo["stamping"]["app"]["_version"],
        )
        repo_gdict = match.groupdict()
        if repo_gdict["hotfix"] is None:
            repo_gdict["hotfix"] = str(0)

        major, minor, patch, hotfix = self._advance_version(gdict)

        prerelease = self.prerelease
        # If user did not specify a change in prerelease,
        # stay with the previous one
        if prerelease is None and self.release_mode is None:
            prerelease = initialprerelease
        prerelease_count = copy.deepcopy(initialprerelease_count)

        # Continue from last stamp prerelease information as long as
        # the last version is coherent with what is requested from
        # the version file or manual version (not yet implemented)
        prerelease, prerelease_count = self._advanceprerelease(
            prerelease, prerelease_count
        )

        verstr = self.gen_vmn_version(
            major,
            minor,
            patch,
            hotfix,
        )

        return verstr, prerelease, prerelease_count

    def _advanceprerelease(self, prerelease, prerelease_count):
        if prerelease is None:
            return None, {}
        if prerelease == "release":
            try:
                raise RuntimeError()
            except RuntimeError:
                LOGGER.error(
                    "prerelease equals to 'release' somehow. "
                    "Turn on debug mode to see traceback"
                )
                LOGGER.debug("Exception info: ", exc_info=True)

            return None, {}

        prerelease_count = copy.deepcopy(prerelease_count)
        counter_key = f"{prerelease}"
        if counter_key not in prerelease_count:
            prerelease_count[counter_key] = 0

        prerelease_count[counter_key] += 1

        if self.release_mode is not None:
            prerelease_count = {
                counter_key: 1,
            }

        return counter_key, prerelease_count

    def _advance_version(self, gdict):
        major = gdict["major"]
        minor = gdict["minor"]
        patch = gdict["patch"]
        hotfix = gdict["hotfix"]

        if self.release_mode == "major":
            major = str(int(major) + 1)
            minor = str(0)
            patch = str(0)
            hotfix = str(0)
        elif self.release_mode == "minor":
            minor = str(int(minor) + 1)
            patch = str(0)
            hotfix = str(0)
        elif self.release_mode == "patch":
            patch = str(int(patch) + 1)
            hotfix = str(0)
        elif self.release_mode == "hotfix":
            hotfix = str(int(hotfix) + 1)

        return major, minor, patch, hotfix

    def gen_vmn_version(
        self, major, minor, patch, hotfix=None, prerelease=None, prerelease_count={}
    ):
        if self.hide_zero_hotfix and hotfix == "0":
            hotfix = None

        vmn_version = f"{major}.{minor}.{patch}"
        if hotfix is not None:
            vmn_version = f"{vmn_version}.{hotfix}"
        if prerelease is not None and prerelease != "release":
            try:
                assert prerelease in prerelease_count
                vmn_version = (
                    f"{vmn_version}-{prerelease}{prerelease_count[prerelease]}"
                )
            except AssertionError:
                LOGGER.error(
                    f"{prerelease} doesn't appear in {prerelease_count} "
                    "Turn on debug mode to see traceback"
                )
                LOGGER.debug("Exception info: ", exc_info=True)

        return vmn_version

    def write_version_to_file(
        self,
        version_number: str,
        prerelease: str,
        prerelease_count: dict,
    ) -> None:
        self._write_version_to_vmn_version_file(
            prerelease, prerelease_count, version_number
        )

        if not self.version_backends:
            return

        verstr = self.gen_verstr(version_number, prerelease, prerelease_count)
        verstr = self.get_be_formatted_version(verstr)
        for backend in self.version_backends:
            try:
                if backend == "vmn_version_file":
                    LOGGER.warning(
                        "Remove vmn_version_file version backend from the configuration"
                    )
                    continue

                handler = getattr(self, f"_write_version_to_{backend}")
                handler(verstr)
            except AttributeError:
                LOGGER.warning(f"Unsupported version backend {backend}")
                continue

    def _write_version_to_cargo(self, verstr):
        backend_conf = self.version_backends["cargo"]
        file_path = os.path.join(self.root_path, backend_conf["path"])
        try:
            with open(file_path, "r") as f:
                data = tomlkit.loads(f.read())

            data["package"]["version"] = verstr
            with open(file_path, "w") as f:
                data = tomlkit.dumps(data)
                f.write(data)
        except IOError as e:
            LOGGER.error(f"Error writing cargo ver file: {file_path}\n")
            LOGGER.debug("Exception info: ", exc_info=True)

            raise IOError(e)
        except Exception as e:
            LOGGER.debug(e, exc_info=True)
            raise RuntimeError(e)

    def _write_version_to_vmn_version_file(
        self, prerelease, prerelease_count, version_number
    ):
        file_path = self.version_file_path
        if prerelease is None:
            prerelease = "release"
        # this method will write the stamped ver of an app to a file,
        # weather the file pre exists or not
        try:
            with open(file_path, "w") as fid:
                ver_dict = {
                    "version_to_stamp_from": version_number,
                    "prerelease": prerelease,
                    "prerelease_count": prerelease_count,
                }
                yaml.dump(ver_dict, fid)
        except IOError as e:
            LOGGER.error(f"Error writing ver file: {file_path}\n")
            LOGGER.debug("Exception info: ", exc_info=True)

            raise IOError(e)
        except Exception as e:
            LOGGER.debug(e, exc_info=True)
            raise RuntimeError(e)

    @staticmethod
    def parse_template(template: str) -> object:
        match = re.search(stamp_utils.VMN_TEMPLATE_REGEX, template)

        gdict = match.groupdict()

        return gdict

    def get_deps_changesets(self):
        flat_dependency_repos = []

        # resolve relative paths
        for rel_path, v in self.raw_configured_deps.items():
            for repo in v:
                flat_dependency_repos.append(
                    os.path.relpath(
                        os.path.join(self.backend.root(), rel_path, repo),
                        self.backend.root(),
                    ),
                )

        return flat_dependency_repos

    def get_be_formatted_version(self, version):
        return stamp_utils.VMNBackend.get_utemplate_formatted_version(
            version, self.template, self.hide_zero_hotfix
        )

    def create_config_files(self, params):
        # If there is no file - create it
        if not os.path.isfile(self.app_conf_path):
            pathlib.Path(os.path.dirname(self.app_conf_path)).mkdir(
                parents=True, exist_ok=True
            )

            ver_conf_yml = {
                "conf": {
                    "template": self.template,
                    "deps": self.raw_configured_deps,
                    "extra_info": self.extra_info,
                    "hide_zero_hotfix": True,
                },
            }

            with open(self.app_conf_path, "w+") as f:
                msg = (
                    "# Autogenerated by vmn. You can edit this " "configuration file\n"
                )
                f.write(msg)
                yaml.dump(ver_conf_yml, f, sort_keys=True)

        if self.root_app_name is None:
            return

        if os.path.isfile(self.root_app_conf_path):
            return

        pathlib.Path(os.path.dirname(self.app_conf_path)).mkdir(
            parents=True, exist_ok=True
        )

        ver_yml = {
            "conf": {"external_services": {}},
        }

        with open(self.root_app_conf_path, "w+") as f:
            f.write("# Autogenerated by vmn\n")
            yaml.dump(ver_yml, f, sort_keys=True)


class VersionControlStamper(IVersionsStamper):
    def __init__(self, conf):
        IVersionsStamper.__init__(self, conf)

    def gen_verstr(self, current_version, prerelease, prerelease_count):
        match = re.search(stamp_utils.VMN_REGEX, current_version)
        gdict = match.groupdict()
        if gdict["hotfix"] is None:
            gdict["hotfix"] = str(0)
        verstr = self.gen_vmn_version(
            gdict["major"],
            gdict["minor"],
            gdict["patch"],
            gdict["hotfix"],
            prerelease,
            prerelease_count,
        )

        return verstr

    def find_matching_version(self, version, prerelease, prerelease_count):
        tag_formatted_app_name = stamp_utils.VMNBackend.get_tag_formatted_app_name(
            self.name,
            version,
            prerelease,
            prerelease_count,
        )

        # Try to find any version of the application matching the
        # user's repositories local state
        _, ver_info = self.backend.get_vmn_tag_version_info(tag_formatted_app_name)
        if ver_info is None:
            return None

        # Can happen if app's name is a prefix of another app
        if ver_info["stamping"]["app"]["name"] != self.name:
            return None

        if ver_info["stamping"]["app"]["release_mode"] == "init":
            return None

        found = True
        for k, v in ver_info["stamping"]["app"]["changesets"].items():
            if k not in self.actual_deps_state:
                found = False
                break

            # when k is the "main repo" repo
            if self.repo_name == k:
                user_changeset = self.backend.last_user_changeset(self.name)

                if v["hash"] != user_changeset:
                    found = False
                    break
            elif v["hash"] != self.actual_deps_state[k]["hash"]:
                found = False
                break

        if found:
            return ver_info

        return None

    @staticmethod
    def get_version_number_from_file(version_file_path) -> str or None:
        if not os.path.exists(version_file_path):
            return (None, None, None)

        with open(version_file_path, "r") as fid:
            ver_dict = yaml.safe_load(fid)
            if "version_to_stamp_from" in ver_dict:
                if "prerelease" not in ver_dict or "prerelease" not in ver_dict:
                    # Backward for 0.4.0-rc6
                    return (
                        ver_dict["version_to_stamp_from"],
                        "release",
                        {},
                    )

                return (
                    ver_dict["version_to_stamp_from"],
                    ver_dict["prerelease"],
                    ver_dict["prerelease_count"],
                )

            # Backward compatible vmn 0.3.9 code
            if "prerelease" not in ver_dict:
                return (
                    ver_dict["last_stamped_version"],
                    "release",
                    {},
                )

            return (
                ver_dict["last_stamped_version"],
                ver_dict["prerelease"],
                ver_dict["prerelease_count"],
            )

    def add_to_version(self):
        if not self.buildmetadata:
            raise RuntimeError("TODO xxx")

        old_version = VersionControlStamper.get_version_number_from_file(
            self.version_file_path
        )

        self.should_publish = False
        tag_name = stamp_utils.VMNBackend.get_tag_formatted_app_name(
            self.name, old_version
        )
        if self.backend.changeset() != self.backend.changeset(tag=tag_name):
            raise RuntimeError(
                "Releasing a release candidate is only possible when the repository "
                "state is on the exact version. Please vmn goto the version you'd "
                "like to release."
            )

        (
            _,
            _,
            version,
            hotfix,
            prerelease,
            _,
            _,
        ) = stamp_utils.VMNBackend.get_tag_properties(tag_name)

        if not self.hide_zero_hotfix:
            version = f"{version}.{hotfix}"
        elif hotfix != "0":
            version = f"{version}.{hotfix}"
        if prerelease is not None:
            version = f"{version}-{prerelease}"

        version = f"{version}+{self.buildmetadata}"

        tag_name = stamp_utils.VMNBackend.get_tag_formatted_app_name(
            self.name, version
        )

        messages = [
            yaml.dump({"key": "TODO "}, sort_keys=True),
        ]

        self.backend.tag([tag_name], messages)

        return version

    def release_app_version(self, verstr):
        tag_name = f'{self.name.replace("/", "-")}_{verstr}'
        props = stamp_utils.VMNBackend.get_tag_properties(tag_name)

        should_append_hotfix = props["hotfix"] is not None
        if should_append_hotfix and self.hide_zero_hotfix:
            should_append_hotfix = props["hotfix"] != "0"

        if should_append_hotfix:
            props["version"] = f'{props["version"]}.{props["hotfix"]}'

        release_tag_name = f'{self.name.replace("/", "-")}_{props["version"]}'
        match = re.search(stamp_utils.VMN_TAG_REGEX, release_tag_name)
        if match is None:
            LOGGER.error(f"Tag {release_tag_name} doesn't comply to vmn version format")
            raise RuntimeError()

        tag_name, tag_ver_info_form_repo = self.backend.get_vmn_tag_version_info(
            tag_name
        )
        ver_info = {
            "stamping": {
                "app": copy.deepcopy(tag_ver_info_form_repo["stamping"]["app"])
            },
            "vmn_info": self.current_version_info["vmn_info"],
        }
        ver_info["stamping"]["app"]["_version"] = props["version"]
        ver_info["stamping"]["app"]["prerelease"] = "release"

        messages = [
            yaml.dump(ver_info, sort_keys=True),
        ]

        self.backend.tag(
            [release_tag_name], messages, ref=self.backend.changeset(tag=tag_name)
        )

        return props["version"]

    def stamp_app_version(
        self,
        initial_version,
        initialprerelease,
        initialprerelease_count,
    ):
        # TODO: verify that can be called multiple times with same result
        current_version, prerelease, prerelease_count = self.gen_app_version(
            initial_version,
            initialprerelease,
            initialprerelease_count,
        )

        self.write_version_to_file(
            version_number=current_version,
            prerelease=prerelease,
            prerelease_count=prerelease_count,
        )

        info = {}
        if self.extra_info:
            info["env"] = dict(os.environ)

        release_mode = self.release_mode
        if prerelease is not None:
            release_mode = "prerelease"

        if prerelease is None:
            prerelease = "release"

        self.update_stamping_info(
            info,
            initial_version,
            initialprerelease,
            initialprerelease_count,
            current_version,
            prerelease,
            prerelease_count,
            release_mode,
        )

        return current_version, prerelease, prerelease_count

    def update_stamping_info(
        self,
        info,
        initial_version,
        initialprerelease,
        initialprerelease_count,
        current_version,
        prerelease,
        prerelease_count,
        release_mode,
    ):
        verstr = self.gen_verstr(current_version, prerelease, prerelease_count)
        self.current_version_info["stamping"]["app"]["_version"] = verstr
        self.current_version_info["stamping"]["app"]["prerelease"] = prerelease
        initial_verstr = self.gen_verstr(
            initial_version, initialprerelease, initialprerelease_count
        )
        self.current_version_info["stamping"]["app"][
            "previous_version"
        ] = initial_verstr
        self.current_version_info["stamping"]["app"]["release_mode"] = release_mode
        self.current_version_info["stamping"]["app"]["info"] = copy.deepcopy(info)
        self.current_version_info["stamping"]["app"][
            "stamped_on_branch"
        ] = self.backend.get_active_branch()
        self.current_version_info["stamping"]["app"][
            "prerelease_count"
        ] = copy.deepcopy(prerelease_count)

    def stamp_root_app_version(
        self,
        override_version=None,
    ):
        if self.root_app_name is None:
            return None

        if "version" not in self.ver_info_from_repo["stamping"]["root_app"]:
            LOGGER.error(
                f"Root app name is {self.root_app_name} and app name is {self.name}. "
                f"However no version information for root was found"
            )
            raise RuntimeError()

        old_version = self.ver_info_from_repo["stamping"]["root_app"]["version"]

        if override_version is None:
            override_version = old_version

        root_version = int(override_version) + 1

        with open(self.root_app_conf_path) as f:
            data = yaml.safe_load(f)
            # TODO: why do we need deepcopy here?
            external_services = copy.deepcopy(data["conf"]["external_services"])

        root_app = self.ver_info_from_repo["stamping"]["root_app"]
        services = copy.deepcopy(root_app["services"])

        self.current_version_info["stamping"]["root_app"].update(
            {
                "version": root_version,
                "services": services,
                "external_services": external_services,
            }
        )

        msg_root_app = self.current_version_info["stamping"]["root_app"]
        msg_app = self.current_version_info["stamping"]["app"]
        msg_root_app["services"][self.name] = msg_app["_version"]

        return "{0}".format(root_version)

    def get_files_to_add_to_index(self, paths):
        changed = [
            os.path.join(self.root_path, item.a_path.replace("/", os.sep))
            for item in self.backend._be.index.diff(None)
        ]
        untracked = [
            os.path.join(self.root_path, item.replace("/", os.sep))
            for item in self.backend._be.untracked_files
        ]

        version_files = []
        for path in paths:
            if path in changed or path in untracked:
                version_files.append(path)

        return version_files

    def publish_stamp(
        self, app_version, prerelease, prerelease_count, root_app_version
    ):
        if not self.should_publish:
            return 0

        verstr = self.gen_verstr(app_version, prerelease, prerelease_count)
        app_msg = {
            "vmn_info": self.current_version_info["vmn_info"],
            "stamping": {"app": self.current_version_info["stamping"]["app"]},
        }

        version_files = self.get_files_to_add_to_index(
            [
                self.app_conf_path,
                self.version_file_path,
            ]
        )

        for backend in self.version_backends:
            backend_conf = self.version_backends[backend]
            file_path = os.path.join(self.root_path, backend_conf["path"])
            version_files.append(file_path)

        if self.create_verinfo_files:
            dir_path = os.path.join(self.app_dir_path, "verinfo")
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            path = os.path.join(dir_path, f"{verstr}.yml")
            with open(path, "w") as f:
                data = yaml.dump(app_msg, sort_keys=True)
                f.write(data)

            version_files.append(path)

        if self.root_app_name is not None:
            root_app_msg = {
                "stamping": {
                    "root_app": self.current_version_info["stamping"]["root_app"]
                },
                "vmn_info": self.current_version_info["vmn_info"],
            }

            tmp = self.get_files_to_add_to_index([self.root_app_conf_path])
            if tmp:
                version_files.extend(tmp)

            if self.create_verinfo_files:
                dir_path = os.path.join(self.root_app_dir_path, "root_verinfo")
                Path(dir_path).mkdir(parents=True, exist_ok=True)
                path = os.path.join(dir_path, f"{root_app_version}.yml")
                with open(path, "w") as f:
                    data = yaml.dump(root_app_msg, sort_keys=True)
                    f.write(data)

                version_files.append(path)

        commit_msg = None
        if self.current_version_info["stamping"]["app"]["release_mode"] == "init":
            commit_msg = f"{self.name}: Stamped initial version {verstr}\n\n"
        else:
            commit_msg = f"{self.name}: Stamped version {verstr}\n\n"

        self.current_version_info["stamping"]["msg"] = commit_msg
        self.backend.commit(
            message=self.current_version_info["stamping"]["msg"],
            user="vmn",
            include=version_files,
        )

        tag = f'{self.name.replace("/", "-")}_{verstr}'
        match = re.search(stamp_utils.VMN_TAG_REGEX, tag)
        if match is None:
            LOGGER.error(
                f"Tag {tag} doesn't comply to vmn version format"
                f"Reverting vmn changes ..."
            )
            self.backend.revert_vmn_changes()

            return 3

        tags = [tag]
        msgs = [app_msg]

        if self.root_app_name is not None:
            msgs.append(root_app_msg)
            tag = f"{self.root_app_name}_{root_app_version}"
            match = re.search(stamp_utils.VMN_ROOT_TAG_REGEX, tag)
            if match is None:
                LOGGER.error(
                    f"Tag {tag} doesn't comply to vmn version format"
                    f"Reverting vmn changes ..."
                )
                self.backend.revert_vmn_changes()

                return 3

            tags.append(tag)

        all_tags = []
        all_tags.extend(tags)

        try:
            for t, m in zip(tags, msgs):
                self.backend.tag([t], [yaml.dump(m, sort_keys=True)])
        except Exception as exc:
            LOGGER.debug("Logged Exception message:", exc_info=True)
            LOGGER.info(f"Reverting vmn changes for tags: {tags} ... ")
            self.backend.revert_vmn_changes(all_tags)

            return 1

        try:
            self.backend.push(all_tags)
        except Exception:
            LOGGER.debug("Logged Exception message:", exc_info=True)
            LOGGER.info(f"Reverting vmn changes for tags: {tags} ...")
            self.backend.revert_vmn_changes(all_tags)

            return 2

        return 0

    def retrieve_remote_changes(self):
        self.backend.pull()


def handle_init(vmn_ctx):
    expected_status = {
        "repos_exist_locally",
    }
    try:
        status = _get_repo_status(vmn_ctx.vcs, expected_status)
    except:
        return 1

    be = vmn_ctx.vcs.backend

    vmn_path = os.path.join(vmn_ctx.params["root_path"], ".vmn")
    Path(vmn_path).mkdir(parents=True, exist_ok=True)
    vmn_init_path = os.path.join(vmn_path, "vmn.init")
    Path(vmn_init_path).touch()
    git_ignore_path = os.path.join(vmn_path, ".gitignore")

    with open(git_ignore_path, "w+") as f:
        for ignored_file in IGNORED_FILES:
            f.write(f"{ignored_file}{os.linesep}")

    be.commit(
        message=stamp_utils.INIT_COMMIT_MESSAGE,
        user="vmn",
        include=[vmn_init_path, git_ignore_path],
    )
    be.push()

    LOGGER.info(f'Initialized vmn tracking on {vmn_ctx.params["root_path"]}')

    return 0


def handle_init_app(vmn_ctx):
    # TODO: validate version number is of type major.minor.patch[.hotfix]
    err = _init_app(vmn_ctx.vcs, vmn_ctx.params, vmn_ctx.args.version)
    if err:
        return 1

    LOGGER.info(
        "Initialized app tracking on {0}".format(vmn_ctx.vcs.root_app_dir_path)
    )

    return 0


def handle_stamp(vmn_ctx):
    vmn_ctx.vcs.prerelease = vmn_ctx.args.pr
    vmn_ctx.vcs.buildmetadata = None
    vmn_ctx.vcs.release_mode = vmn_ctx.args.release_mode
    # For backward compatability
    if vmn_ctx.vcs.release_mode == "micro":
        vmn_ctx.vcs.release_mode = "hotfix"

    if vmn_ctx.vcs.tracked and vmn_ctx.vcs.release_mode is None:
        vmn_ctx.vcs.current_version_info["stamping"]["app"][
            "release_mode"
        ] = vmn_ctx.vcs.ver_info_from_repo["stamping"]["app"]["release_mode"]

    optional_status = {"modified", "detached"}
    expected_status = {
        "repos_exist_locally",
        "repo_tracked",
        "app_tracked",
    }
    try:
        status = _get_repo_status(vmn_ctx.vcs, expected_status, optional_status)
    except:
        return 1

    if status["matched_version_info"] is not None:
        # Good we have found an existing version matching
        # the actual_deps_state
        version = vmn_ctx.vcs.get_be_formatted_version(
            status["matched_version_info"]["stamping"]["app"]["_version"]
        )

        LOGGER.info(version)

        return 0

    if "detached" in status["state"]:
        LOGGER.error("In detached head. Will not stamp new version")
        return 1

    # We didn't find any existing version
    if vmn_ctx.args.pull:
        try:
            vmn_ctx.vcs.retrieve_remote_changes()
        except Exception as exc:
            LOGGER.error("Failed to pull, run with --debug for more details")
            LOGGER.debug("Logged Exception message:", exc_info=True)

            return 1

    (
        initial_version,
        prerelease,
        prerelease_count,
    ) = VersionControlStamper.get_version_number_from_file(
        vmn_ctx.vcs.version_file_path
    )

    try:
        version = _stamp_version(
            vmn_ctx.vcs,
            vmn_ctx.args.pull,
            initial_version,
            prerelease,
            prerelease_count,
        )
    except Exception as exc:
        LOGGER.debug("Logged Exception message:", exc_info=True)

        return 1

    LOGGER.info(version)

    return 0


def handle_release(vmn_ctx):
    expected_status = {
        "repos_exist_locally",
        "repo_tracked",
        "app_tracked",
    }
    optional_status = {
        "detached",
        "modified",
        "dirty_deps",
    }
    try:
        status = _get_repo_status(vmn_ctx.vcs, expected_status, optional_status)
    except:
        return 1

    try:
        LOGGER.info(vmn_ctx.vcs.release_app_version(vmn_ctx.args.version))
    except Exception as exc:
        LOGGER.error(f"Failed to release {vmn_ctx.args.version}")
        LOGGER.debug("Logged Exception message:", exc_info=True)

        return 1

    return 0


def _handle_add(vmn_ctx):
    vmn_ctx.params["buildmetadata"] = vmn_ctx.args.build_metadata
    vmn_ctx.params["releasenotes"] = vmn_ctx.args.releasenotes

    expected_status = {
        "repos_exist_locally",
    }
    optional_status = {
        "detached",
    }
    try:
        status = _get_repo_status(vmn_ctx.vcs, expected_status, optional_status)
    except:
        return 1

    try:
        raise NotImplementedError("Adding metadata to versions is not supported yet")
    except Exception as exc:
        LOGGER.debug("Logged Exception message:", exc_info=True)

        return 1

    return 0


def handle_show(vmn_ctx):
    # root app does not have raw version number
    if vmn_ctx.params["root"]:
        vmn_ctx.params["raw"] = False
    else:
        vmn_ctx.params["raw"] = vmn_ctx.args.raw

    vmn_ctx.params["ignore_dirty"] = vmn_ctx.args.ignore_dirty

    vmn_ctx.params["verbose"] = vmn_ctx.args.verbose
    if vmn_ctx.args.template is not None:
        vmn_ctx.vcs.set_template(vmn_ctx.args.template)
    try:
        out = show(vmn_ctx.vcs, vmn_ctx.params, vmn_ctx.args.version)
    except:
        return 1

    return 0


def handle_goto(vmn_ctx):
    vmn_ctx.params["deps_only"] = vmn_ctx.args.deps_only

    return goto_version(vmn_ctx.vcs, vmn_ctx.params, vmn_ctx.args.version)


def _get_repo_status(versions_be_ifc, expected_status, optional_status=set()):
    be = versions_be_ifc.backend
    default_status = {
        "pending": False,
        "detached": False,
        "outgoing": False,
        "state": set(),
    }
    status = copy.deepcopy(default_status)
    status.update(
        {
            "repos_exist_locally": True,
            # TODO: rename to on_stamped_version and turn to True
            "modified": False,
            "dirty_deps": False,
            "repo_tracked": True,
            "app_tracked": True,
            "err_msgs": {
                "dirty_deps": "",
                "repo_tracked": "vmn repo tracking is already initialized",
                "app_tracked": "vmn app tracking is already initialized",
            },
            "repos": {},
            "matched_version_info": None,
            "state": {"repos_exist_locally", "repo_tracked", "app_tracked"},
            "local_repos_diff": set(),
        }
    )

    path = os.path.join(versions_be_ifc.root_path, ".vmn", "vmn.init")
    if not versions_be_ifc.backend.is_path_tracked(path):
        # Backward compatability with vmn 0.3.9 code:
        file_path = backward_compatible_initialized_check(versions_be_ifc.root_path)

        if file_path is None or not versions_be_ifc.backend.is_path_tracked(file_path):
            status["repo_tracked"] = False
            status["err_msgs"][
                "repo_tracked"
            ] = "vmn tracking is not yet initialized. Run vmn init on the repository"
            status["state"].remove("repo_tracked")

    if not versions_be_ifc.tracked:
        status["app_tracked"] = False
        status["err_msgs"]["app_tracked"] = "Untracked app. Run vmn init-app first"
        status["state"].remove("app_tracked")

    err = be.check_for_pending_changes()
    if err:
        status["pending"] = True
        status["err_msgs"]["pending"] = err
        status["state"].add("pending")

    if be.in_detached_head():
        status["detached"] = True
        status["err_msgs"]["detached"] = err
        status["state"].add("detached")
    else:
        # Outgoing changes cannot be in detached head
        # TODO: is it really?
        err = be.check_for_outgoing_changes()
        if err:
            status["outgoing"] = True
            status["err_msgs"]["outgoing"] = err
            status["state"].add("outgoing")

    if "name" in versions_be_ifc.current_version_info["stamping"]["app"]:
        (
            initial_version,
            prerelease,
            prerelease_count,
        ) = VersionControlStamper.get_version_number_from_file(
            versions_be_ifc.version_file_path
        )
        matched_version_info = versions_be_ifc.find_matching_version(
            initial_version,
            prerelease,
            prerelease_count,
        )
        if matched_version_info is None:
            status["modified"] = True
            status["state"].add("modified")
        else:
            status["matched_version_info"] = matched_version_info

        configured_repos = set(versions_be_ifc.flat_configured_deps)
        local_repos = set(versions_be_ifc.actual_deps_state.keys())

        if configured_repos - local_repos:
            paths = []
            for path in configured_repos - local_repos:
                paths.append(os.path.join(versions_be_ifc.backend.root(), path))

            status["repos_exist_locally"] = False
            status["err_msgs"]["repos_exist_locally"] = (
                f"Dependency repository were specified in conf.yml file. "
                f"However repos: {paths} does not exist. Please clone and rerun"
            )
            status["local_repos_diff"] = configured_repos - local_repos

        err = 0
        for repo in configured_repos & local_repos:
            if repo == ".":
                continue

            status["repos"][repo] = copy.deepcopy(default_status)
            full_path = os.path.join(versions_be_ifc.root_path, repo)

            be, err = stamp_utils.get_client(full_path)

            err = be.check_for_pending_changes()
            if err:
                status["dirty_deps"] = True
                status["err_msgs"][
                    "dirty_deps"
                ] = f"{status['err_msgs']['dirty_deps']}\n{err}"
                status["state"].add("dirty_deps")
                status["repos"][repo]["pending"] = True
                status["repos"][repo]["state"].add("pending")

            if not be.in_detached_head():
                err = be.check_for_outgoing_changes()
                if err:
                    status["dirty_deps"] = True
                    status["err_msgs"][
                        "dirty_deps"
                    ] = f"{status['err_msgs']['dirty_deps']}\n{err}"
                    status["state"].add("dirty_deps")
                    status["repos"][repo]["outgoing"] = True
                    status["repos"][repo]["state"].add("outgoing")
            else:
                status["repos"][repo]["detached"] = True
                status["repos"][repo]["state"].add("detached")

    if (expected_status & status["state"]) != expected_status:
        for msg in expected_status - status["state"]:
            if msg in status["err_msgs"] and status["err_msgs"][msg]:
                LOGGER.error(status["err_msgs"][msg])

        raise RuntimeError()

    if ((optional_status | status["state"]) - expected_status) != optional_status:
        for msg in (optional_status | status["state"]) - expected_status:
            if msg in status["err_msgs"] and status["err_msgs"][msg]:
                LOGGER.error(status["err_msgs"][msg])

        raise RuntimeError()

    return status


def _init_app(versions_be_ifc, params, starting_version):
    expected_status = {"repos_exist_locally", "repo_tracked", "modified"}
    try:
        status = _get_repo_status(versions_be_ifc, expected_status)
    except Exception as exc:
        return 1

    versions_be_ifc.create_config_files(params)
    versions_be_ifc.write_version_to_file(
        version_number=starting_version,
        prerelease="release",
        prerelease_count={},
    )

    info = {}
    versions_be_ifc.update_stamping_info(
        info,
        starting_version,
        "release",
        {},
        starting_version,
        "release",
        {},
        "init",
    )

    root_app_version = 0
    services = {}
    if versions_be_ifc.root_app_name is not None:
        with open(versions_be_ifc.root_app_conf_path) as f:
            data = yaml.safe_load(f)
            # TODO: why do we need deepcopy here?
            external_services = copy.deepcopy(data["conf"]["external_services"])

        ver_info = versions_be_ifc.backend.get_vmn_version_info(
            versions_be_ifc.root_app_name, root=True
        )
        if ver_info:
            root_app_version = int(ver_info["stamping"]["root_app"]["version"]) + 1
            root_app = ver_info["stamping"]["root_app"]
            services = copy.deepcopy(root_app["services"])

        versions_be_ifc.current_version_info["stamping"]["root_app"].update(
            {
                "version": root_app_version,
                "services": services,
                "external_services": external_services,
            }
        )

        msg_root_app = versions_be_ifc.current_version_info["stamping"]["root_app"]
        msg_app = versions_be_ifc.current_version_info["stamping"]["app"]
        msg_root_app["services"][versions_be_ifc.name] = msg_app["_version"]

    err = versions_be_ifc.publish_stamp(
        starting_version, "release", {}, root_app_version
    )
    if err:
        LOGGER.error("Failed to init app")
        raise RuntimeError()

    return 0


def backward_compatible_initialized_check(root_path):
    path = os.path.join(root_path, ".vmn")
    file_path = None
    for f in os.listdir(path):
        if os.path.isfile(os.path.join(path, f)):
            if f not in IGNORED_FILES:
                file_path = os.path.join(path, f)
                break

    return file_path


def _stamp_version(
    versions_be_ifc, pull, initial_version, initialprerelease, initialprerelease_count
):
    stamped = False
    retries = 3
    override_initial_version = initial_version
    override_initialprerelease = initialprerelease
    override_initialprerelease_count = initialprerelease_count
    override_main_current_version = None

    newer_stamping = version_mod.version != "dev" and (
        pversion.parse(versions_be_ifc.ver_info_from_repo["vmn_info"]["vmn_version"])
        > pversion.parse(version_mod.version)
    )
    if newer_stamping:
        LOGGER.error("Refusing to stamp with old vmn. Please upgrade")
        raise RuntimeError()

    if versions_be_ifc.bad_format_template:
        LOGGER.warning(versions_be_ifc.template_err_str)

    while retries:
        retries -= 1

        (
            current_version,
            prerelease,
            prerelease_count,
        ) = versions_be_ifc.stamp_app_version(
            override_initial_version,
            override_initialprerelease,
            override_initialprerelease_count,
        )
        main_ver = versions_be_ifc.stamp_root_app_version(
            override_main_current_version,
        )

        err = versions_be_ifc.publish_stamp(
            current_version, prerelease, prerelease_count, main_ver
        )
        if not err:
            stamped = True
            break

        if err == 1:
            override_initial_version = current_version
            override_initialprerelease = prerelease
            override_initialprerelease_count = prerelease_count
            override_main_current_version = main_ver

            LOGGER.warning(
                "Failed to publish. Trying to auto-increase "
                "from {0} to {1}".format(
                    current_version,
                    versions_be_ifc.gen_app_version(
                        override_initial_version,
                        override_initialprerelease,
                        override_initialprerelease_count,
                    )[0],
                )
            )
        elif err == 2:
            if not pull:
                break

            time.sleep(random.randint(1, 5))
            versions_be_ifc.retrieve_remote_changes()
        else:
            break

    if not stamped:
        LOGGER.error("Failed to stamp")
        raise RuntimeError()

    verstr = versions_be_ifc.gen_verstr(current_version, prerelease, prerelease_count)

    return versions_be_ifc.get_be_formatted_version(verstr)


def show(vcs, params, verstr=None):
    dirty_states = None
    ver_info = None
    if params["from_file"]:
        if verstr is None:
            ver_info = vcs.ver_info_from_repo
        else:
            if params["root"]:
                dir_path = os.path.join(vcs.root_app_dir_path, "root_verinfo")
                path = os.path.join(dir_path, f"{verstr}.yml")
            else:
                dir_path = os.path.join(vcs.app_dir_path, "verinfo")
                path = os.path.join(dir_path, f"{verstr}.yml")

            try:
                with open(path, "r") as f:
                    ver_info = yaml.safe_load(f)
            except:
                ver_info = None
    else:
        expected_status = {
            "repos_exist_locally",
            "repo_tracked",
            "app_tracked",
        }
        optional_status = {
            "detached",
            "pending",
            "outgoing",
            "modified",
            "dirty_deps",
        }
        tag_name, ver_info, status = _retrieve_version_info(
            params, vcs, verstr, expected_status, optional_status
        )
        if ver_info is not None:
            dirty_states = ((optional_status & status["state"]) | {"detached"}) - {
                "detached"
            }

            if params["ignore_dirty"]:
                dirty_states = None

    if ver_info is None:
        LOGGER.info(
            "Version information was not found "
            "for {0}.".format(
                params["name"],
            )
        )

        raise RuntimeError()

    # TODO: refactor
    if params["root"]:
        data = ver_info["stamping"]["root_app"]
        if not data:
            LOGGER.info(
                "App {0} does not have a root app ".format(
                    params["name"],
                )
            )

            raise RuntimeError()

        out = None

        if params.get("verbose"):
            out = yaml.dump(data)
        else:
            out = data["version"]

        if dirty_states:
            out = f"{out} (dirty): {dirty_states}"

        print(out)

        return 0

    data = ver_info["stamping"]["app"]
    data["version"] = stamp_utils.VMNBackend.get_utemplate_formatted_version(
        data["_version"], vcs.template, vcs.hide_zero_hotfix
    )
    if params.get("verbose"):
        if dirty_states:
            data["dirty"] = dirty_states
        out = yaml.dump(data)
    elif params.get("raw"):
        out = data["_version"]
        if dirty_states:
            out = f"{out} (dirty): {dirty_states}"
    else:
        out = data["version"]
        if dirty_states:
            out = f"{out} (dirty): {dirty_states}"

    print(out)

    return out


def goto_version(vcs, params, version):
    expected_status = {
        "repo_tracked",
        "app_tracked",
    }
    optional_status = {
        "detached",
        "repos_exist_locally",
        "modified",
    }
    tag_name, ver_info, _ = _retrieve_version_info(
        params, vcs, version, expected_status, optional_status
    )

    if ver_info is None:
        LOGGER.error("No such app: {0}".format(params["name"]))
        return 1

    data = ver_info["stamping"]["app"]
    deps = data["changesets"]
    deps.pop(".")
    if deps:
        if version is None:
            for rel_path, v in deps.items():
                v["hash"] = None

        _goto_version(deps, params["root_path"])

    if version is None and not params["deps_only"]:
        vcs.backend.checkout_branch()
    elif not params["deps_only"]:
        try:
            vcs.backend.checkout(tag=tag_name)
        except Exception:
            LOGGER.error(
                "App: {0} with version: {1} was "
                "not found".format(params["name"], version)
            )

            return 1

    return 0


def _retrieve_version_info(params, vcs, verstr, expected_status, optional_status):
    try:
        status = _get_repo_status(vcs, expected_status, optional_status)
    except:
        return None, None, None

    tag_name = f'{params["name"].replace("/", "-")}'
    if verstr is not None:
        tag_name = f"{tag_name}_{verstr}"

    if verstr is None:
        try:
            ver_info = vcs.backend.get_vmn_version_info(
                params["name"],
                params["root"],
            )
        except:
            return None, None, None
    else:
        if params["root"]:
            try:
                int(verstr)
                tag_name, ver_info = vcs.backend.get_vmn_tag_version_info(tag_name)
            except Exception:
                LOGGER.error("wrong version specified: root version must be an integer")

                return None, None, None
        else:
            try:
                stamp_utils.VMNBackend.get_tag_properties(tag_name)
                tag_name, ver_info = vcs.backend.get_vmn_tag_version_info(tag_name)
            except:
                LOGGER.error(f"Wrong version specified: {verstr}")

                return None, None, None

    if ver_info is None:
        return None, None, None

    return tag_name, ver_info, status


def _update_repo(args):
    path, rel_path, changeset = args

    client = None
    try:
        client, err = stamp_utils.get_client(path)
        if client is None:
            return {"repo": rel_path, "status": 0, "description": err}
    except Exception as exc:
        LOGGER.exception(
            "Unexpected behaviour:\nAborting update " f"operation in {path} Reason:\n"
        )

        return {"repo": rel_path, "status": 1, "description": None}

    try:
        err = client.check_for_pending_changes()
        if err:
            LOGGER.info("{0}. Aborting update operation ".format(err))
            return {"repo": rel_path, "status": 1, "description": err}

    except Exception as exc:
        LOGGER.debug(f'Skipping "{path}"')
        LOGGER.debug("Exception info: ", exc_info=True)

        return {"repo": rel_path, "status": 0, "description": None}

    try:
        if not client.in_detached_head():
            err = client.check_for_outgoing_changes()
            if err:
                LOGGER.info("{0}. Aborting update operation".format(err))
                return {"repo": rel_path, "status": 1, "description": err}

        LOGGER.info("Updating {0}".format(rel_path))
        if changeset is None:
            if not client.in_detached_head():
                client.pull()

            rev = client.checkout_branch()

            LOGGER.info("Updated {0} to {1}".format(rel_path, rev))
        else:
            cur_changeset = client.changeset()
            if not client.in_detached_head():
                client.pull()

            client.checkout(rev=changeset)

            LOGGER.info("Updated {0} to {1}".format(rel_path, changeset))
    except Exception as exc:
        LOGGER.exception(
            f"Unexpected behaviour:\nAborting update operation in {path} " "Reason:\n"
        )

        try:
            client.checkout(rev=cur_changeset)
        except Exception:
            LOGGER.exception("Unexpected behaviour:")

        return {"repo": rel_path, "status": 1, "description": None}

    return {"repo": rel_path, "status": 0, "description": None}


def _clone_repo(args):
    path, rel_path, remote, vcs_type = args
    if os.path.exists(path):
        return {"repo": rel_path, "status": 0, "description": None}

    LOGGER.info("Cloning {0}..".format(rel_path))
    try:
        if vcs_type == "git":
            stamp_utils.GitBackend.clone(path, remote)
    except Exception as exc:
        try:
            str = "already exists and is not an empty directory."
            if str in exc.stderr:
                return {"repo": rel_path, "status": 0, "description": None}
        except Exception:
            pass

        err = "Failed to clone {0} repository. " "Description: {1}".format(
            rel_path, exc.args
        )
        return {"repo": rel_path, "status": 1, "description": err}

    return {"repo": rel_path, "status": 0, "description": None}


def _goto_version(deps, root):
    args = []
    for rel_path, v in deps.items():
        if v["remote"].startswith("."):
            v["remote"] = os.path.join(root, v["remote"])
        args.append(
            (os.path.join(root, rel_path), rel_path, v["remote"], v["vcs_type"])
        )
    with Pool(min(len(args), 10)) as p:
        results = p.map(_clone_repo, args)

    for res in results:
        if res["status"] == 1:
            if res["repo"] is None and res["description"] is None:
                continue

            msg = "Failed to clone "
            if res["repo"] is not None:
                msg += "from {0} ".format(res["repo"])
            if res["description"] is not None:
                msg += "because {0}".format(res["description"])

            LOGGER.info(msg)

    args = []
    for rel_path, v in deps.items():
        args.append((os.path.join(root, rel_path), rel_path, v["hash"]))

    with Pool(min(len(args), 20)) as p:
        results = p.map(_update_repo, args)

    err = False
    for res in results:
        if res["status"] == 1:
            err = True
            if res["repo"] is None and res["description"] is None:
                continue

            msg = "Failed to update "
            if res["repo"] is not None:
                msg += " {0} ".format(res["repo"])
            if res["description"] is not None:
                msg += "because {0}".format(res["description"])

            LOGGER.warning(msg)

    if err:
        LOGGER.error(
            "Failed to update one or more " "of the required repos. See log above"
        )
        raise RuntimeError()


def build_world(name, working_dir, root_context, from_file):
    params = {
        "name": name,
        "working_dir": working_dir,
        "root": root_context,
        "from_file": from_file,
    }

    be, err = stamp_utils.get_client(
        params["working_dir"],
        params["from_file"],
    )
    params["be"] = be
    if err:
        LOGGER.error("Failed to create backend {0}. Exiting".format(err))
        return None

    root_path = os.path.join(be.root())
    params["root_path"] = root_path

    return params


def main(command_line=None):
    try:
        return vmn_run(command_line)
    except Exception as exc:
        LOGGER.info("vmn_run raised exception. Run vmn --debug for details")
        LOGGER.debug("Exception info: ", exc_info=True)

        return 1


def vmn_run(command_line):
    err = 0
    with VMNContextMAnagerManager(command_line) as vmn_ctx:
        if vmn_ctx.args.command == "init":
            err = handle_init(vmn_ctx)
        elif vmn_ctx.args.command == "init-app":
            err = handle_init_app(vmn_ctx)
        elif vmn_ctx.args.command == "show":
            err = handle_show(vmn_ctx)
        elif vmn_ctx.args.command == "stamp":
            err = handle_stamp(vmn_ctx)
        elif vmn_ctx.args.command == "goto":
            err = handle_goto(vmn_ctx)
        elif vmn_ctx.args.command == "release":
            err = handle_release(vmn_ctx)
        else:
            LOGGER.info("Run vmn -h for help")
            err = 0

    return err


def validate_app_name(args):
    if args.name.startswith("/"):
        LOGGER.error("App name cannot start with /")
        raise RuntimeError()
    if "-" in args.name:
        LOGGER.error("App name cannot start with -")
        raise RuntimeError()


def parse_user_commands(command_line):
    parser = argparse.ArgumentParser("vmn")
    parser.add_argument(
        "--version", "-v", action="version", version=version_mod.version
    )
    parser.add_argument("--debug", required=False, action="store_true")
    parser.set_defaults(debug=False)
    subprasers = parser.add_subparsers(dest="command")
    subprasers.add_parser(
        "init",
        help="initialize version tracking for the repository. "
        "This command should be called only once per repository",
    )
    pinitapp = subprasers.add_parser(
        "init-app",
        help="initialize version tracking for application. "
        "This command should be called only once per application",
    )
    pinitapp.add_argument(
        "-v",
        "--version",
        default="0.0.0",
        help="The version to init from. Must be specified in the raw version format: "
        "{major}.{minor}.{patch}",
    )
    pinitapp.add_argument(
        "name", help="The application's name to initialize version tracking for"
    )
    pshow = subprasers.add_parser("show", help="show app version")
    pshow.add_argument("name", help="The application's name to show the version for")
    pshow.add_argument(
        "-v",
        "--version",
        default=None,
        help=f"The version to show. Must be specified in the raw version format:"
        f" {stamp_utils.VMN_VERSION_FORMAT}",
    )
    pshow.add_argument(
        "-t", "--template", default=None, help="The template to use in show"
    )
    pshow.add_argument("--root", dest="root", action="store_true")
    pshow.set_defaults(root=False)
    pshow.add_argument("--verbose", dest="verbose", action="store_true")
    pshow.set_defaults(verbose=False)
    pshow.add_argument("--raw", dest="raw", action="store_true")
    pshow.set_defaults(raw=False)
    pshow.add_argument("--from-file", dest="from_file", action="store_true")
    pshow.set_defaults(from_file=False)
    pshow.add_argument("--ignore-dirty", dest="ignore_dirty", action="store_true")
    pshow.set_defaults(ignore_dirty=False)
    pstamp = subprasers.add_parser("stamp", help="stamp version")
    pstamp.add_argument(
        "-r",
        "--release-mode",
        choices=["major", "minor", "patch", "hotfix", "micro"],
        default=None,
        help="major / minor / patch / hotfix",
    )
    pstamp.add_argument(
        "--pr",
        "--prerelease",
        default=None,
        help="Prerelease version. Can be anything really until you decide "
        "to release the version",
    )
    pstamp.add_argument("--pull", dest="pull", action="store_true")
    pstamp.set_defaults(pull=False)
    pstamp.add_argument("name", help="The application's name")
    pgoto = subprasers.add_parser("goto", help="go to version")
    pgoto.add_argument(
        "-v",
        "--version",
        default=None,
        required=False,
        help=f"The version to go to in the format: "
        f" {stamp_utils.VMN_VERSION_FORMAT}",
    )
    pgoto.add_argument("--root", dest="root", action="store_true")
    pgoto.set_defaults(root=False)
    pgoto.add_argument("--deps-only", dest="deps_only", action="store_true")
    pgoto.set_defaults(deps_only=False)
    pgoto.add_argument("name", help="The application's name")
    prelease = subprasers.add_parser("release", help="Release app version")
    prelease.add_argument(
        "-v",
        "--version",
        required=True,
        help=f"The version to release in the format: "
        f" {stamp_utils.VMN_VERSION_FORMAT}",
    )
    prelease.add_argument("name", help="The application's name")
    args = parser.parse_args(command_line)

    return args


if __name__ == "__main__":
    err = main()
    if err:
        sys.exit(1)

    sys.exit(0)
