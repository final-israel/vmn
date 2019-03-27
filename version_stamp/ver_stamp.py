#!/usr/bin/env python3
import argparse
import copy
import json
import sys
import os
import hglib
import git
import logging
import pathlib
import importlib.machinery
import types
from lockfile import LockFile

LOGGER = logging.getLogger()


def gen_main_version(main_ver_mod, release_mode):
    if release_mode != 'debug':
        main_ver = str(int(main_ver_mod.build_num) + 1)
    else:
        main_ver = str(int(main_ver_mod.build_num))

    main_date_ver = main_ver_mod.version

    import time
    strings = time.strftime("%y,%m")
    strings = strings.split(',')
    tmp_date_ver = '{0}.{1}'.format(strings[0], strings[1])
    if not main_date_ver.startswith(tmp_date_ver):
        main_ver = '1'
    formatted_main_ver = '{0}.{1}'.format(tmp_date_ver, main_ver)
    return formatted_main_ver, main_ver


def gen_app_version(current_version, release_mode, custom_major, custom_minor):
    try:
        major, minor, patch, micro = current_version.split('.')
    except ValueError:
        major, minor, patch = current_version.split('.')
        micro = str(0)

    if release_mode == 'major' and custom_major is not None:
        raise RuntimeError(
            'custom major version was specified in version_info file and '
            'version_manager was executed with release_mode equals to major. '
            'These two cannot exist together. Fix it and rerun'
        )
    if release_mode == 'minor' and custom_minor is not None:
        raise RuntimeError(
            'custom minor version was specified in version_info file and '
            'version_manager was executed with release_mode equals to minor. '
            'These two cannot exist together. Fix it and rerun'
        )

    if release_mode == 'major':
        major = str(int(major) + 1)
        minor = str(0)
        patch = str(0)
        micro = str(0)
    elif release_mode == 'minor':
        minor = str(int(minor) + 1)
        patch = str(0)
        micro = str(0)
    elif release_mode == 'patch':
        patch = str(int(patch) + 1)
        micro = str(0)
    elif release_mode == 'micro':
        micro = str(int(micro) + 1)

    if custom_major is not None:
        major = custom_major
    if custom_minor is not None:
        minor = custom_minor

    current_version = '{0}.{1}.{2}.{3}'.format(major, minor, patch, micro)

    return current_version


class HostState(object):
    @staticmethod
    def _get_mercurial_changeset(path):
        try:
            client = hglib.open(path)
        except hglib.error.ServerError as exc:
            LOGGER.error('Skipping "{0}" directory reason:\n{1}\n'.format(
                path, exc)
            )
            return None

        revision = client.parents()
        client.close()
        if revision is None:
            return None

        changeset = revision[0][1]
        return changeset.decode('utf-8')

    @staticmethod
    def get_changeset(path):
        try:
            client = git.Repo(path)
        except git.exc.InvalidGitRepositoryError:
            return HostState._get_mercurial_changeset(path), 'mercurial'

        try:
            hash = client.head.commit.hexsha
        except Exception:
            return None
        finally:
            client.close()

        return hash, 'git'

    @staticmethod
    def get_current_changeset(repos_path):
        repos = [name for name in os.listdir(repos_path)
                 if os.path.isdir(os.path.join(repos_path, name))]

        changesets = {}
        for repo in repos:
            cur_path = os.path.join(repos_path, repo)
            if not os.path.exists(cur_path) or repo == 'versions':
                continue

            changeset = HostState.get_changeset(cur_path)
            if changeset is None or changeset[0] is None:
                continue

            changesets[repo] = {
                'hash': changeset[0],
                'vcs_type': changeset[1],
            }

        return changesets


class VersionsBackend(object):
    def __init__(self, conf):
        self._backend = None
        self._app_name = conf['app_name']
        self._release_mode = conf['release_mode']
        self._repos_path = conf['repos_path']
        self._starting_version = conf['starting_version']
        self._version_template, self._version_template_octats_count = \
            VersionsBackend.parse_template(conf['version_template'])

        self._main_system_name = None
        if 'main_system_name' in conf:
            self._main_system_name = conf['main_system_name']

    @staticmethod
    def parse_template(template):
        placeholders = (
            '{0}', '{1}', '{2}', '{3}', '{NON_EXISTING_PLACEHOLDER}'
        )
        templates = [None, None, None, None]

        if len(template) > 30:
            raise RuntimeError('Template too long: max 30 chars')

        pos = template.find(placeholders[0])
        if pos < 0:
            raise RuntimeError('Invalid template must include {0} at least')

        prefix = template[:pos]
        for placeholder in placeholders:
            prefix = prefix.replace(placeholder, '')

        for i in range(len(placeholders) - 1):
            cur_pos = template.find(placeholders[i])
            next_pos = template.find(placeholders[i + 1])
            if next_pos < 0:
                next_pos = None

            tmp = template[cur_pos:next_pos]
            for placeholder in placeholders:
                tmp = tmp.replace(placeholder, '')

            tmp = '{0}{1}'.format(placeholders[i], tmp)

            templates[i] = tmp

            if next_pos is None:
                break

        ver_format = ''
        octats_count = 0
        templates[0] = '{0}{1}'.format(prefix, templates[0])
        for template in templates:
            if template is None:
                break

            ver_format += template
            octats_count += 1

        return ver_format, octats_count

    @staticmethod
    def get_formatted_version(version, version_template, octats_count):
        octats = version.split('.')
        if len(octats) > 4:
            raise RuntimeError('Version is too long. Maximum is 4 octats')

        for i in range(4 - len(octats)):
            octats.append('0')

        return version_template.format(
            *(octats[:octats_count])
        )

    def get_be_formatted_version(self, version):
        return VersionsBackend.get_formatted_version(
            version,
            self._version_template,
            self._version_template_octats_count
        )

    def allocate_backend(self):
        raise NotImplementedError('Please implement this method')

    def deallocate_backend(self):
        raise NotImplementedError('Please implement this method')

    def find_version(self, current_changesets):
        raise NotImplementedError('Please implement this method')


class MercurialVersionsBackend(VersionsBackend):
    def __init__(self, conf=None):
        VersionsBackend.__init__(self, conf)

        self._versions_repo_path = os.path.join(self._repos_path, 'versions')

        self._app_version_file = None
        if 'app_version_file' in conf:
            self._app_version_file = conf['app_version_file']

        self._main_version_file = None
        if 'main_version_file' in conf:
            self._main_version_file = conf['main_version_file']

    def allocate_backend(self):
        self._backend = hglib.open(self._versions_repo_path)
        self._backend.revert([], all=True)
        self._backend.pull(update=True)

    def deallocate_backend(self):
        if self._backend is None:
            return

        self._backend.close()
        self._backend = None

    def find_version(self, changesets_dict):
        root = self._backend.root().decode()
        tags = self._backend.tags()
        current_changesets = {}
        hist_changesets = {}

        tag_ver = None
        ver_path = None

        # Find the first tag with app_name and its version file path
        for tag in tags:
            if not tag[0].decode().startswith(self._app_name):
                continue

            for path in self._backend.status(change=tag[0]):
                if not path[1].decode().endswith(os.sep + 'version.py'):
                    continue

                ver_path = path
                break

            if ver_path is None:
                continue

            tag_ver = tag[0].decode().split('{0}_'.format(self._app_name))[1]
            break

        # We probably have a new application
        if ver_path is None:
            return None

        if tag_ver is None:
            raise RuntimeError(
                "CRITICAL: Version file path: {0} found but "
                "app tag not found. This requires manual "
                "intervention. Probably someone removed app's "
                "tag".format(ver_path)
            )

        app_ver_path = os.path.join(root, *(ver_path[1].decode().split('/')))
        app_ver_dir_path = os.path.dirname(app_ver_path)
        app_hist_ver_path = os.path.join(app_ver_dir_path,
                                         '_version_history.py')

        loader = importlib.machinery.SourceFileLoader(
            'version', app_ver_path)
        mod_ver = types.ModuleType(loader.name)
        try:
            loader.exec_module(mod_ver)
        except FileNotFoundError:
            # Means that this service has been removed once and now
            # it is back
            LOGGER.info(
                'Service {0} was deleted and now '
                'it is back'.format(self._app_name)
            )
            self._starting_version = tag_ver

            return None

        try:
            current_changesets = mod_ver.changesets
        except AttributeError:
            pass

        # From now on we will try to find any existing version of
        # the application in our local repositories.
        # Means that if any previous version of the application will match
        # our local repository, we will return this version
        found = True
        for k, v in current_changesets.items():
            if k not in changesets_dict:
                found = False
                break
            if v['hash'] != changesets_dict[k]['hash']:
                found = False
                break

        if found and current_changesets:
            return tag_ver

        if os.path.isfile(app_hist_ver_path):
            loader = importlib.machinery.SourceFileLoader(
                '_version_history', app_hist_ver_path)
            mod_ver = types.ModuleType(loader.name)
            loader.exec_module(mod_ver)

            try:
                hist_changesets = mod_ver.changesets
            except AttributeError:
                pass

        # If the history is empty - bye bye
        if not hist_changesets:
            return None

        for tag in hist_changesets:
            found = True
            for k, v in hist_changesets[tag].items():
                if k not in changesets_dict:
                    found = False
                    break
                if v['hash'] != changesets_dict[k]['hash']:
                    found = False
                    break

            if found and hist_changesets[tag]:
                return tag

        return None

    def stamp_app_version(self, current_changesets):
        dir_path = os.path.dirname(self._app_version_file)

        # If there is no file - create it
        if not os.path.isfile(self._app_version_file):
            pathlib.Path(dir_path).mkdir(parents=True, exist_ok=True)
            with open(self._app_version_file, 'w+') as f:
                f.write('# Autogenerated by version stamper. Do not edit\n')
                f.write('name = "{0}"\n'.format(self._app_name))
                f.write(
                    'version = "{0}"\n'.format(
                        VersionsBackend.get_formatted_version(
                            self._starting_version,
                            self._version_template,
                            self._version_template_octats_count)
                    )
                )
                f.write('_version = "{0}"\n'.format(self._starting_version))
                f.write('template = "{0}"\n'.format(self._version_template))
                f.write('changesets = {}\n')

            commit_msg = \
                '{0}: add first version file with version {1}'.format(
                    self._app_name, self._starting_version
                )

            self._backend.add(self._app_version_file.encode())
            self._backend.commit(
                message=commit_msg,
                user='version_manager',
                include=self._app_version_file.encode(),
            )

        hist_version_file = os.path.join(dir_path, '_version_history.py')
        # If there is no file - create it
        if not os.path.isfile(hist_version_file):
            with open(hist_version_file, 'w+') as f:
                f.write('# Autogenerated by version stamper. Do not edit\n')
                f.write('changesets = {}\n')

            self._backend.add(hist_version_file.encode())
            self._backend.commit(
                message='{0}: add first history version file'.format(
                    self._app_name
                ),
                user='version_manager',
                include=hist_version_file.encode(),
            )

        custom_major = None
        custom_minor = None
        custom_repos = None
        version_info_file = os.path.join(dir_path, 'version_info.py')
        if os.path.isfile(version_info_file):
            loader = importlib.machinery.SourceFileLoader(
                'version_info', version_info_file)
            mod_ver = types.ModuleType(loader.name)
            loader.exec_module(mod_ver)

            try:
                if hasattr(mod_ver, '_version'):
                    split_ver = mod_ver._version.split('.')
                else:
                    split_ver = mod_ver.version.split('.')

                if len(split_ver) == 1:
                    custom_major = split_ver[0]
                elif len(split_ver) == 2:
                    custom_major = split_ver[0]
                    custom_minor = split_ver[0]
            except Exception:
                pass

            try:
                custom_repos = mod_ver.repos
            except Exception:
                pass

        loader = importlib.machinery.SourceFileLoader(
            'version', self._app_version_file)
        mod_ver = types.ModuleType(loader.name)
        loader.exec_module(mod_ver)
        if hasattr(mod_ver, '_version'):
            old_version = mod_ver._version
        else:
            old_version = mod_ver.version

        old_changesets = copy.deepcopy(mod_ver.changesets)

        loader = importlib.machinery.SourceFileLoader(
            '_version_history', hist_version_file)
        mod_ver = types.ModuleType(loader.name)
        loader.exec_module(mod_ver)
        hist_changesets = mod_ver.changesets

        current_version = gen_app_version(
            old_version, self._release_mode, custom_major, custom_minor
        )

        if self._release_mode == 'debug':
            return current_version

        if custom_repos is not None:
            for repo in custom_repos:
                if repo in current_changesets:
                    continue

                raise RuntimeError(
                    'Dependency repositories were specified in '
                    'version_info file. However repo: {0} does not exist '
                    'in your repos_path. Please fix and rerun'.format(repo)
                )

        info = {
            'env': dict(os.environ),
        }

        # write service version
        with open(self._app_version_file, "w+") as f:
            f.write('# Autogenerated by version stamper. Do not edit\n')
            f.write('{0} = "{1}"\n'.format('name', self._app_name))
            f.write('{0} = "{1}"\n'.format('_version', current_version))
            f.write('template = "{0}"\n'.format(self._version_template))
            f.write('{0} = "{1}"\n'.format(
                'version', VersionsBackend.get_formatted_version(
                    current_version,
                    self._version_template,
                    self._version_template_octats_count
                    )
                )
            )

            f.write('{0} = "{1}"\n'.format('release_mode', self._release_mode))

            changesets_to_file = current_changesets
            if custom_repos:
                changesets_to_file = {}
                for k in custom_repos:
                    changesets_to_file[k] = current_changesets[k]

            f.write('changesets = ')
            f.write(json.dumps(changesets_to_file))
            f.write('\n')

            f.write('info = ')
            f.write(json.dumps(info))
            f.write('\n')

        # may happen in case of recurring version
        if not old_changesets:
            return current_version

        hist_changesets[old_version] = old_changesets

        # write service version history
        with open(hist_version_file, "w+") as f:
            f.write('# Autogenerated by version stamper. Do not edit\n')
            f.write('changesets = {\n')
            f.write(json.dumps(hist_changesets)[1:-1])
            f.write('}\n')

        return current_version

    def stamp_main_system_version(self, service_version):
        if self._main_system_name is None:
            return None

        dir_path = os.path.dirname(self._main_version_file)
        if not os.path.isfile(self._main_version_file):
            pathlib.Path(dir_path).mkdir(parents=True, exist_ok=True)
            with open(self._main_version_file, 'w+') as f:
                f.write('# Autogenerated by version stamper. Do not edit\n')
                f.write('name = "{0}"\n'.format(self._main_system_name))
                f.write('build_num = "{0}"\n'.format('1'))
                f.write('version = "{0}"\n'.format('0.0.0'))
                f.write('services = {}\n')
                f.write('external_services = {}\n')

            self._backend.add(self._main_version_file.encode())
            self._backend.commit(
                message='{0}: add first main version file'.format(
                    self._main_system_name),
                user='version_manager',
                include=self._main_version_file.encode(),
            )

        hist_version_file = os.path.join(dir_path, '_main_version_history.py')
        if not os.path.isfile(hist_version_file):
            pathlib.Path(dir_path).mkdir(parents=True, exist_ok=True)
            with open(hist_version_file, 'w+') as f:
                f.write('# Autogenerated by version stamper. Do not edit\n')
                f.write('services = {}\n')
                f.write('external_services = {}\n')

            self._backend.add(hist_version_file.encode())
            self._backend.commit(
                message='{0}: add first main history version file'.format(
                    self._main_system_name),
                user='version_manager',
                include=hist_version_file.encode(),
            )

        loader = importlib.machinery.SourceFileLoader(
            'main_version', self._main_version_file)
        main_ver_mod = types.ModuleType(loader.name)
        loader.exec_module(main_ver_mod)
        old_version = main_ver_mod.version
        old_services = copy.deepcopy(main_ver_mod.services)
        old_external_services = copy.deepcopy(main_ver_mod.external_services)

        loader = importlib.machinery.SourceFileLoader(
            '_main_version_history', hist_version_file)
        mod_ver = types.ModuleType(loader.name)
        loader.exec_module(mod_ver)
        hist_services = mod_ver.services
        hist_external_services = mod_ver.external_services

        formatted_main_ver, main_ver = \
            gen_main_version(main_ver_mod, self._release_mode)

        if self._release_mode == 'debug':
            return formatted_main_ver

        root = self._backend.root().decode()
        services = {}
        try:
            services = main_ver_mod.services
        except AttributeError:
            pass

        external_services = {}
        try:
            external_services = main_ver_mod.external_services
        except AttributeError:
            pass

        keys_to_pop = []
        for k in services.keys():
            joined_path = services[k]['path'].split('/')
            if not os.path.isfile(os.path.join(root, *joined_path)):
                keys_to_pop.append(k)

        for k in keys_to_pop:
            services.pop(k)

        services[self._app_name] = {
            'path': self._app_version_file.split(root)[1],
            'version': service_version
        }

        with open(self._main_version_file, 'w+') as f:
            f.write('# Autogenerated by version stamper. Do not edit\n')
            f.write('name = "{0}"\n'.format(self._main_system_name))
            f.write('build_num = "{0}"\n'.format(main_ver))
            f.write('version = "{0}"\n'.format(formatted_main_ver))

            f.write('services = {\n')
            f.write(json.dumps(services)[1:-1])
            f.write('}\n')

            f.write('external_services = {\n')
            f.write(json.dumps(external_services)[1:-1])
            f.write('}\n')

        # may happen in case of recurring version
        if not old_services:
            return '{0}'.format(formatted_main_ver)

        hist_services[old_version] = old_services
        hist_external_services[old_version] = old_external_services

        # write service main version history
        with open(hist_version_file, "w+") as f:
            f.write('# Autogenerated by version stamper. Do not edit\n')
            f.write('services = {\n')
            f.write(json.dumps(hist_services)[1:-1])
            f.write('}\n')

            f.write('external_services = {\n')
            f.write(json.dumps(hist_external_services)[1:-1])
            f.write('}\n')

        return '{0}'.format(formatted_main_ver)

    def publish(self, app_version, main_version=None):
        if self._release_mode == 'debug':
            # We may push new files here so give it a try
            try:
                pass
                self._backend.push()
            except hglib.error.CommandError as exc:
                LOGGER.error(exc)

            return

        self._backend.commit(
            message='{0}: update to version {1}'.format(
                self._app_name, app_version),
            user='version_manager'
        )

        tags = ['{0}_{1}'.format(self._app_name, app_version).encode()]
        if main_version is not None:
            tags.append(
                '{0}_{1}'.format(self._main_system_name, main_version).encode()
            )

        self._backend.tag(tags, user='version_manager')

        self._backend.push()


def get_version(versions_be_ifc, current_changesets):
    ver = versions_be_ifc.find_version(current_changesets)
    if ver is not None:
        # Good we have found an existing version matching
        # the current_changesets
        return versions_be_ifc.get_be_formatted_version(ver)

    # We didn't find any existing version - generate new one
    current_version = versions_be_ifc.stamp_app_version(current_changesets)
    formatted_main_ver = versions_be_ifc.stamp_main_system_version(
        current_version
    )
    versions_be_ifc.publish(current_version, formatted_main_ver)

    return versions_be_ifc.get_be_formatted_version(current_version)


def run_with_mercurial_versions_be(**params):
    lock = LockFile(os.path.join(params['repos_path'], 'versions', 'ver.lock'))
    with lock:
        LOGGER.error('Locked: {0}'.format(lock.path))

        params['repos_path'] = os.path.abspath(params['repos_path'])

        if (params['main_system_name'] is None and
            params['main_version_file'] is not None):
            raise RuntimeError(
                'Main system name was not specified but its main_version '
                'file was specified "'
            )

        if (params['main_system_name'] is not None and
            params['main_version_file'] is None):
            raise RuntimeError('Main system name was specified but main '
                               'version file path was not')

        params['app_version_file'] = os.path.abspath(
            params['app_version_file']
        )
        if not params['app_version_file'].startswith(params['repos_path']):
            raise RuntimeError(
                'App version file must be within versions repository'
            )
        if not params['app_version_file'].endswith(os.sep + 'version.py'):
            raise RuntimeError(
                'App version file must be named "version.py"'
            )

        if params['main_version_file'] is not None:
            params['main_version_file'] = \
                os.path.abspath(params['main_version_file'])
            main_version_file = params['main_version_file']
            if not main_version_file.startswith(params['repos_path']):
                raise RuntimeError(
                    'Main app version file must be within versions repository'
                )

            if (not params['main_version_file'].endswith(
                    os.sep + 'main_version.py')):
                raise RuntimeError(
                    'Main version file must be named "main_version.py"')

        mbe = MercurialVersionsBackend(params)
        mbe.allocate_backend()
        changesets = HostState.get_current_changeset(params['repos_path'])

        print(get_version(mbe, changesets), file=sys.stdout)

        mbe.deallocate_backend()

    LOGGER.error('Released locked: {0}'.format(lock.path))
    return 0


def main():
    args = sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--repos_path',
        required=True,
        help='The path to the repos base dir for changesets generation'
    )
    parser.add_argument(
        '--release_mode',
        choices=['major', 'minor', 'patch', 'micro', 'debug'],
        default='debug',
        help='major / minor / patch / micro / debug'
    )
    parser.add_argument(
        '--app_name', required=True, help="The application's name"
    )
    parser.add_argument(
        '--starting_version',
        default='0.0.0.0',
        help='The desired starting version (default is 0.0.0.0).'
             'Note that this value represents and already existing version '
             'and version_manager will handle it from this value'
    )
    parser.add_argument(
        '--app_version_file',
        required=True,
        help='The version python file path of the module being built'
    )
    parser.add_argument(
        '--main_system_name',
        default=None,
        help='The name of the whole system'
    )
    parser.add_argument(
        '--main_version_file',
        default=None,
        help='The version file of the whole system'
    )
    parser.add_argument(
        '--version_template',
        default='{0}.{1}.{2}',
        help='A template for the desired version output.\n'
             'The default is: {0}.{1}.{2}\n'
             'example:\n'
             '1. {0}.{1}.{2}.{3}\n'
             '2. {0}.{1}.{2}\n'
             '3. text1{0}text2text3{1}text4text5{2}text6'
    )

    LOGGER.error(' '.join(args))

    args = parser.parse_args(args)
    params = copy.deepcopy(vars(args))

    return run_with_mercurial_versions_be(**params)


if __name__ == '__main__':
    main()
