#!/usr/bin/env python3
import sys
import os
import hglib
import git
import logging
from pathlib import Path


class VersionControlBackend(object):
    def __init__(self):
        pass

    def __del__(self):
        pass

    def tag(self, tags, user):
        raise NotImplementedError()

    def push(self):
        raise NotImplementedError()

    def pull(self):
        raise NotImplementedError()

    def commit(self, message, user, include=None):
        raise NotImplementedError()

    def root(self):
        raise NotImplementedError()

    def status(self, tag):
        raise NotImplementedError()

    def tags(self):
        raise NotImplementedError()

    def check_for_pending_changes(self):
        raise NotImplementedError()

    def check_for_outgoing_changes(self):
        raise NotImplementedError()

    def checkout_master(self, branch='master'):
        raise NotImplementedError()

    def checkout(self, rev):
        raise NotImplementedError()

    def parents(self):
        raise NotImplementedError()


class MercurialBackend(VersionControlBackend):
    def __init__(self, repo_path, revert=False, pull=False):
        VersionControlBackend.__init__(self)

        self._be = hglib.open(repo_path)

        if revert:
            self._be.revert([], all=True)
        if pull:
            self._be.pull(update=True)

    def __del__(self):
        self._be.close()

    def tag(self, tags, user):
        for tag in tags:
            self._be.tag(tag.encode(), user=user)

    def push(self):
        self._be.push()

    def pull(self):
        self._be.pull(update=True)

    def commit(self, message, user, include=None):
        if include is not None:
            for file in include:
                self._be.add(file.encode())

        self._be.commit(message=message, user=user)

    def root(self):
        return self._be.root().decode()

    def status(self, tag):
        status = self._be.status(change=tag)

        paths = []
        for item in status:
            paths.append(item[1].decode())

        return paths

    def tags(self):
        tags = []
        _tags = self._be.tags()

        for tag in _tags:
            tags.append(tag[0].decode())

        return tags

    def check_for_pending_changes(self):
        diff = self._be.diff()
        if diff != b'':
            err = 'Pending changes in {0}. Aborting'.format(self.root())
            return err

        return None

    def check_for_outgoing_changes(self):
        sum = self._be.summary()
        cur_branch = sum['branch'.encode('utf-8')].decode()
        out = self._be.outgoing(branch=cur_branch)
        if out:
            err = 'Outgoing changes in {0}. Aborting'.format(self.root())
            return err

        return None

    def checkout_master(self, branch='default'):
        heads = self._be.heads()
        tip_changeset = None
        for head in heads:
            if head[3].decode() != branch:
                continue

            tip_changeset = head[1]
            break

        self._be.update(rev=tip_changeset)

        return tip_changeset

    def checkout(self, rev):
        self._be.update(rev=rev)

    def parents(self):
        parents = []
        for p in self._be.parents():
            parents.append(p.rev)

    @staticmethod
    def clone(repos_path, repo, remote):
        hglib.clone(
            '{0}/{1}'.format(remote, repo),
            '{0}/{1}'.format(repos_path, repo)
        )


class GitBackend(VersionControlBackend):
    def __init__(self, repo_path, revert=False, pull=False):
        VersionControlBackend.__init__(self)

        self._be = git.Repo(repo_path, search_parent_directories=True)
        self._origin = self._be.remote(name='origin')

        if len(self._be.heads) == 0:
            with open(os.path.join(repo_path, 'init.txt'), 'w+') as f:
                f.write('# init\n')

            self._be.index.add(
                os.path.join(repo_path, 'init.txt')
            )
            self._be.index.commit('first commit')

            self._origin.push()

        if revert:
            self._be.head.reset(working_tree=True)
        if pull:
            self.pull()

    def __del__(self):
        self._be.close()

    def tag(self, tags, user):
        for item in tags:
            new_tag = self._be.create_tag(
                item,
                message='Automatic tag "{0}"'.format(item)
            )

            self._origin.push(new_tag)

    def push(self):
        self._origin.push()

    def pull(self):
        for branch in self._be.branches:
            self._origin.pull(branch)

    def commit(self, message, user, include=None):
        if include is not None:
            for file in include:
                self._be.index.add(file)

        self._be.index.commit(message=message)

    def root(self):
        return self._be.working_dir

    def status(self, tag):
        found_tag = None
        for _tag in self._be.tags:
            if _tag.name != tag:
                continue

            found_tag = _tag
            break

        return list(found_tag.commit.stats.files)

    def tags(self):
        tags = []
        _tags = self._be.tags

        for tag in _tags:
            tags.append(tag.name)

        return tags[::-1]

    def check_for_pending_changes(self):
        if self._be.is_dirty():
            err = 'Pending changes in {0}.'.format(self.root())
            return err

        return None

    def check_for_outgoing_changes(self):
        for branch in self._be.branches:
            outgoing = list(self._be.iter_commits(
                'origin/{0}..{0}'.format(branch))
            )

            if len(outgoing) > 0:
                err = 'Outgoing changes in {0}'.format(self.root())
                return err

        return None

    def checkout_master(self, branch='master'):
        self.checkout(branch)

        return branch

    def checkout(self, rev):
        self._be.git.checkout(rev)

    def parents(self):
        parents = []
        for p in self._be.head.commit.parents:
            parents.append(p.hexsha)

        return tuple(parents)

    @staticmethod
    def clone(repos_path, repo, remote):
        git.Repo().clone_from(
            '{0}/{1}'.format(remote, repo),
            '{0}/{1}'.format(repos_path, repo)
        )


class HostState(object):
    @staticmethod
    def _get_mercurial_changeset(path):
        try:
            client = hglib.open(path)
        except hglib.error.ServerError as exc:
            logging.getLogger().error('Skipping "{0}" directory reason:\n{1}\n'.format(
                path, exc)
            )
            return None

        revision = client.parents()
        if revision is None:
            revision = client.log()

            if revision is None:
                client.close()
                return None

        changeset = revision[0][1]

        client.close()
        return changeset.decode('utf-8')

    @staticmethod
    def get_changeset(path):
        try:
            client = git.Repo(path, search_parent_directories=True)
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
    def get_current_changeset(paths):
        changesets = {}
        for path,lst in paths.items():
            repos = [
                name for name in lst
                if os.path.isdir(os.path.join(path, name))
            ]

            for repo in repos:
                changeset = HostState.get_changeset(os.path.join(path, repo))
                if changeset is None:
                    continue

                changesets[repo] = {
                    'hash': changeset[0],
                    'vcs_type': changeset[1],
                }

        return changesets


def init_stamp_logger():
    LOGGER = logging.getLogger('vmn')
    LOGGER.setLevel(logging.DEBUG)
    format = '[%(asctime)s.%(msecs)03d] [%(name)s] [%(levelname)s] ' \
             '%(message)s'

    formatter = logging.Formatter(format, '%Y-%m-%d %H:%M:%S')

    cons_handler = logging.StreamHandler(sys.stdout)
    cons_handler.setFormatter(formatter)
    LOGGER.addHandler(cons_handler)

    return LOGGER


def get_versions_repo_path(root_path):
    versions_repo_path = os.getenv('VER_STAMP_VERSIONS_PATH', None)
    if versions_repo_path is not None:
        versions_repo_path = os.path.abspath(versions_repo_path)
    else:
        versions_repo_path = os.path.abspath('{0}/.vmn/versions'.format(root_path))
        Path(versions_repo_path).mkdir(parents=True, exist_ok=True)

    return versions_repo_path


def get_client(path, revert=False, pull=False):
    be_type = None
    try:
        client = git.Repo(path, search_parent_directories=True)
        client.close()

        be_type = 'git'
    except git.exc.InvalidGitRepositoryError:
        try:
            client = hglib.open(path)
            client.close()

            be_type = 'mercurial'
        except hglib.error.ServerError:
            err = 'repository path: {0} is not a functional git ' \
                  'or mercurial repository.'.format(path)
            return None, err

    be = None
    if be_type == 'mercurial':
        be = MercurialBackend(path, revert, pull)
    elif be_type == 'git':
        be = GitBackend(path, revert, pull)

    return be, None
