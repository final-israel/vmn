import sys
import os
import copy
import yaml
import shutil

sys.path.append('{0}/../version_stamp'.format(os.path.dirname(__file__)))

import vmn
import stamp_utils

vmn.LOGGER = stamp_utils.init_stamp_logger(True)


def _init_vmn_in_repo():
    with vmn.VMNContextMAnagerManager(['init']) as vmn_ctx:
        err = vmn._handle_init(vmn_ctx)
        assert err == 0


def _init_app(app_name, starting_version='0.0.0'):
    with vmn.VMNContextMAnagerManager(
            [
                'init-app',
                '-v', starting_version,
                app_name,
            ]
    ) as vmn_ctx:
        err = vmn._handle_init_app(vmn_ctx)
        assert err == 0
        assert len(vmn_ctx.vcs.actual_deps_state) == 1


def _stamp_app(app_name, expected_version, release_mode=None, prerelease=None):
    args_list = ['stamp']
    if release_mode is not None:
        args_list.extend(['-r', release_mode])

    if prerelease is not None:
        args_list.extend([
            '--pr', prerelease
        ])

    args_list.append(app_name)

    with vmn.VMNContextMAnagerManager(args_list) as vmn_ctx:
        err = vmn._handle_stamp(vmn_ctx)
        assert err == 0

        ver_info = vmn_ctx.vcs.backend.get_vmn_version_info(app_name)
        data = ver_info['stamping']['app']
        assert data['_version'] == expected_version


def _show(app_name, verbose=None, raw=None):
    args_list = ['show']
    if verbose is not None:
        args_list.append('--verbose')
    if raw is not None:
        args_list.append('--raw')

    args_list.append(app_name)

    with vmn.VMNContextMAnagerManager(args_list) as vmn_ctx:
        err = vmn._handle_show(vmn_ctx)
        assert err == 0


def test_basic_stamp(app_layout):
    _init_vmn_in_repo()
    _init_app(app_layout.app_name)

    for i in range(2):
        _stamp_app(app_layout.app_name, '0.0.1', 'patch')

    new_name = '{0}_{1}'.format(app_layout.app_name, '2')
    _init_app(new_name, '1.0.0')

    for i in range(2):
        _stamp_app(new_name, '1.0.1', 'patch')

    _stamp_app(app_layout.app_name, '0.0.1', 'patch')


def test_basic_show(app_layout, capfd):
    _init_vmn_in_repo()
    _init_app(app_layout.app_name)

    _stamp_app(app_layout.app_name, '0.0.1', 'patch')

    # read to clear stderr and out
    out, err = capfd.readouterr()
    assert not err

    _show(app_layout.app_name, raw=True)

    out, err = capfd.readouterr()
    assert '0.0.1\n' == out

    _show(app_layout.app_name, verbose=True)

    out, err = capfd.readouterr()
    try:
        yaml.safe_load(out)
    except Exception as we:
        assert False


def test_multi_repo_dependency(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    assert len(params['actual_deps_state']) == 1
    vmn._handle_init(params)

    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    conf = {
        'semver_template': '{major}.{minor}.{patch}',
        'hotfix_template': '_{hotfix}',
        'prerelease_template': '-{prerelease}',
        'buildmetadata_template': '+{buildmetadata}',
        'deps': {'../': {
            'test_repo': {
                'vcs_type': app_layout.be_type,
                'remote': app_layout._app_backend.be.remote(),
            }
        }},
        'extra_info': False
    }
    for repo in (('repo1', 'git'), ('repo2', 'git')):
        be = app_layout.create_repo(
            repo_name=repo[0], repo_type=repo[1]
        )

        conf['deps']['../'].update({
            repo[0]: {
                'vcs_type': repo[1],
                'remote': be.be.remote(),
            }
        })

    app_layout.write_conf(**conf)

    params = vmn.build_world(params['name'], params['working_dir'])
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '0.0.2'

    assert data['version'] == '0.0.2'
    assert '.' in data['changesets']
    assert os.path.join('..', 'repo1') in data['changesets']
    assert os.path.join('..', 'repo2') in data['changesets']

    with open(params['app_conf_path'], 'r') as f:
        data = yaml.safe_load(f)
        assert '../' in data['conf']['deps']
        assert 'test_repo' in data['conf']['deps']['../']
        assert 'repo1' in data['conf']['deps']['../']
        assert 'repo2' in data['conf']['deps']['../']


def test_goto_deleted_repos(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    assert len(params['actual_deps_state']) == 1
    vmn._handle_init(params)

    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    conf = {
        'semver_template': '{major}.{minor}.{patch}',
        'hotfix_template': '_{hotfix}',
        'prerelease_template': '-{prerelease}',
        'buildmetadata_template': '+{buildmetadata}',
        'deps': {'../': {
            'test_repo': {
                'vcs_type': app_layout.be_type,
                'remote': app_layout._app_backend.be.remote(),
            }
        }},
        'extra_info': False
    }
    for repo in (('repo1', 'git'), ('repo2', 'git')):
        be = app_layout.create_repo(
            repo_name=repo[0], repo_type=repo[1]
        )

        conf['deps']['../'].update({
            repo[0]: {
                'vcs_type': repo[1],
                'remote': be.be.remote(),
            }
        })

        be.__del__()

    app_layout.write_conf(**conf)

    params = vmn.build_world(params['name'], params['working_dir'])
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    dir_path = app_layout._repos['repo2']['path']
    shutil.rmtree(dir_path)  # deleting repo_b
    params['deps_only'] = False
    vcs = vmn.VersionControlStamper(params)
    assert vmn.goto_version(vcs, params, '0.0.2') == 0


def test_basic_root_stamp(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world('root_app/app1', params['working_dir'])
    assert len(params['actual_deps_state']) == 1
    vmn._handle_init(params)

    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '0.0.1'

    data = ver_info['stamping']['root_app']
    assert data['version'] == 1

    app2_params = vmn.build_world('root_app/app2', params['working_dir'])
    assert len(app2_params['actual_deps_state']) == 1

    app2_params['release_mode'] = 'minor'
    app2_params['prerelease'] = 'release'
    app2_params['buildmetadata'] = None
    app2_params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(app2_params)
    vmn.stamp(vcs, app2_params)

    ver_info = vcs.get_vmn_version_info(app_name=app2_params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '0.1.0'
    data = ver_info['stamping']['root_app']
    assert data['version'] == 2


def test_starting_version(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    assert len(params['actual_deps_state']) == 1
    vmn._handle_init(params)

    params['release_mode'] = 'minor'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '1.2.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '1.3.0'


def test_rc_stamping(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    assert len(params['actual_deps_state']) == 1
    vmn._handle_init(params)

    params['prerelease'] = 'rc'
    params['buildmetadata'] = None
    for i in range(2):
        params['release_mode'] = 'minor'
        params['starting_version'] = '1.2.0'
        vcs = vmn.VersionControlStamper(params)
        vmn.stamp(vcs, params)

        ver_info = vcs.get_vmn_version_info(app_name=params['name'])
        del vcs
        data = ver_info['stamping']['app']
        assert data['version'] == '1.3.0-rc1'

    app_layout.write_file_commit_and_push(
        'test_repo', 'f1.file', 'msg1'
    )
    params['prerelease'] = 'rc'
    params['buildmetadata'] = None
    params['release_mode'] = None
    params['starting_version'] = '1.2.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '1.3.0-rc2'

    app_layout.write_file_commit_and_push(
        'test_repo', 'f1.file', 'msg1'
    )
    params['prerelease'] = 'beta'
    params['buildmetadata'] = None
    params['release_mode'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '1.3.0-beta1'

    app_layout.write_file_commit_and_push(
        'test_repo', 'f1.file', 'msg1'
    )
    params['prerelease'] = None
    params['buildmetadata'] = None
    params['release_mode'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])

    data = ver_info['stamping']['app']
    assert data['version'] == '1.3.0-beta2'

    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['release_mode'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)
    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '1.3.0'


def test_version_template(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    vmn._handle_init(params)

    params['release_mode'] = 'minor'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '1.2.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    configured_template = None
    with open(params['app_conf_path'], 'r') as f:
        data = yaml.safe_load(f)
        semver_template = data['conf']['semver_template']
        hotfix_template = data['conf']['hotfix_template']
        prerelease_template = data['conf']['prerelease_template']
        buildmetadata_template = data['conf']['buildmetadata_template']

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '1.3.0'
    vcs._version_template, \
    vcs._semver_template, \
    vcs._hotfix_template, \
    vcs._prerelease_template, \
    vcs._buildmetadata_template = vmn.IVersionsStamper.parse_template(
        semver_template,
        hotfix_template,
        prerelease_template,
        buildmetadata_template,
    )
    formated_version = vcs.get_utemplate_formatted_version('1.3.0')
    assert data['version'] == formated_version

    semver_template = 'ap{major}xx{major}XX{minor}AC@{major}{patch}C'
    hotfix_template = '_{hotfix}'
    prerelease_template = '-{prerelease}'
    buildmetadata_template = '+{buildmetadata}'
    vcs._version_template, \
    vcs._semver_template, \
    vcs._hotfix_template, \
    vcs._prerelease_template, \
    vcs._buildmetadata_template = vmn.IVersionsStamper.parse_template(
        semver_template,
        hotfix_template,
        prerelease_template,
        buildmetadata_template,
    )

    formated_version = vcs.get_utemplate_formatted_version('2.0.9')
    assert formated_version == 'ap2xxXX0AC@9C'

    app_layout.write_file_commit_and_push(
        'test_repo', 'f1.file', 'msg1'
    )
    params['release_mode'] = 'minor'
    params['prerelease'] = 'dev'
    params['buildmetadata'] = None
    vcs = vmn.VersionControlStamper(params)
    semver_template = 'ap{major}.{minor}.@{patch}'
    hotfix_template = '_{hotfix}'
    prerelease_template = '-{prerelease}'
    buildmetadata_template = '+{buildmetadata}'
    vcs._version_template, \
    vcs._semver_template, \
    vcs._hotfix_template, \
    vcs._prerelease_template, \
    vcs._buildmetadata_template = vmn.IVersionsStamper.parse_template(semver_template,
        hotfix_template,
        prerelease_template,
        buildmetadata_template,
    )
    vmn.stamp(vcs, params)
    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == 'ap1.4.@0-dev1'

    params['release_mode'] = None
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    vcs = vmn.VersionControlStamper(params)
    semver_template = 'ap{major}.{minor}.@{patch}'
    hotfix_template = '_{hotfix}'
    prerelease_template = '-{prerelease}'
    buildmetadata_template = '+{buildmetadata}'
    vcs._version_template, \
    vcs._semver_template, \
    vcs._hotfix_template, \
    vcs._prerelease_template, \
    vcs._buildmetadata_template = vmn.IVersionsStamper.parse_template(
        semver_template,
        hotfix_template,
        prerelease_template,
        buildmetadata_template,
    )
    vmn.stamp(vcs, params)
    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == 'ap1.4.@0'

    app_layout.write_file_commit_and_push(
        'test_repo', 'f1.file', 'msg2'
    )
    params['release_mode'] = 'minor'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)
    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '1.5.0'

    semver_template = 'ap{major}xx{minor}XX{patch}AC@{major}'
    hotfix_template = '-{hotfix}'
    prerelease_template = 'ABC{prerelease}'
    buildmetadata_template = 'AA{buildmetadata}C'
    vcs._version_template, \
    vcs._semver_template, \
    vcs._hotfix_template, \
    vcs._prerelease_template, \
    vcs._buildmetadata_template = vmn.IVersionsStamper.parse_template(semver_template,
        hotfix_template,
        prerelease_template,
        buildmetadata_template,
    )
    formated_version = vcs.get_utemplate_formatted_version('2.0.9-alpha.3')
    assert formated_version == 'ap2xx0XX9AC@ABCalpha.3'


def test_basic_goto(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    assert len(params['actual_deps_state']) == 1
    vmn._handle_init(params)

    params = vmn.build_world(params['name'], params['working_dir'])
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '0.0.1'

    app_layout.write_file_commit_and_push('test_repo', 'a.yxy', 'msg')

    params = vmn.build_world(params['name'], params['working_dir'])
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '1.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '0.0.2'

    c1 = app_layout._app_backend.be.changeset()
    params['deps_only'] = False
    vcs = vmn.VersionControlStamper(params)
    assert vmn.goto_version(vcs, params, '1.0.1') == 1
    assert vmn.goto_version(vcs, params, '0.0.1') == 0
    c2 = app_layout._app_backend.be.changeset()
    assert c1 != c2
    assert vmn.goto_version(vcs, params, '0.0.2') == 0
    c3 = app_layout._app_backend.be.changeset()
    assert c1 == c3

    assert vmn.goto_version(vcs, params, None) == 0
    c4 = app_layout._app_backend.be.changeset()
    assert c1 == c4


def test_stamp_on_branch_merge_squash(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    assert len(params['actual_deps_state']) == 1
    vmn._handle_init(params)
    params = vmn.build_world(params['name'], params['working_dir'])
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    app_layout._app_backend.be.checkout(('-b', 'new_branch'))
    app_layout.write_file_commit_and_push('test_repo', 'f1.file', 'msg1')
    app_layout._app_backend._origin.pull(rebase=True)
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)  # first stamp 0.0.1
    app_layout.write_file_commit_and_push('test_repo', 'f2.file', 'msg2')
    app_layout._app_backend._origin.pull(rebase=True)
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)  # 0.0.2
    app_layout.write_file_commit_and_push('test_repo', 'f3.file', 'msg3')
    app_layout._app_backend._origin.pull(rebase=True)
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)  # 0.0.3
    app_layout._app_backend.be.checkout('master')
    app_layout.merge(from_rev='new_branch', to_rev='master', squash=True)
    app_layout._app_backend._origin.pull(rebase=True)

    app_layout._app_backend.be.push()
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']

    assert data['version'] == '0.0.4'


def test_get_version(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    vmn._handle_init(params)
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    app_layout._app_backend.be.checkout(('-b', 'new_branch'))
    app_layout.write_file_commit_and_push('test_repo', 'f1.file', 'msg1')
    app_layout._app_backend._origin.pull(rebase=True)
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)  # first stamp 0.0.1
    app_layout._app_backend.be.checkout('master')
    app_layout.merge(from_rev='new_branch', to_rev='master', squash=True)
    app_layout._app_backend._origin.pull(rebase=True)
    app_layout._app_backend.be.push()
    vmn.stamp(vcs, params)
    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '0.0.2'


def test_get_version_number_from_file(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    vmn._handle_init(params)
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.2.0'
    # just to create the relative folder tree,
    # I.E: .vmn/app_name/last_known_app_version.yml
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)
    assert vcs.get_version_number_from_file() == '0.2.1'


def test_read_version_from_file(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    vmn._handle_init(params)
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.1.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)
    file_path = '{}/{}'.format(params.get('app_dir_path'), vmn.VER_FILE_NAME)
    app_layout.write_file_commit_and_push('test_repo', 'f1.file', 'msg1')
    app_layout._app_backend._origin.pull(rebase=True)
    vmn.stamp(vcs, params)
    with open(file_path, 'r') as fid:
        ver_dict = yaml.load(fid)
    assert '0.1.2' == ver_dict.get('last_stamped_version')


def test_system_backward_comp_file_vs_commit(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    vmn._handle_init(params)
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.1.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)
    file_path = '{}/{}'.format(params.get('app_dir_path'), vmn.VER_FILE_NAME)
    app_layout.remove_app_version_file(file_path)
    # in this point we simulate the case were using an old vmn that searches for version numbers in commit message,
    # but stamping with the new method (write and read from file)
    vmn.stamp(vcs, params)
    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    _version = ver_info['stamping']['app']['_version']
    assert '0.1.2' == _version
    with open(file_path, 'r') as fid:
        ver_dict = yaml.load(fid)
    assert '0.1.2' == ver_dict.get('last_stamped_version')


def test_manual_file_adjustment(app_layout):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world(params['name'], params['working_dir'])
    vmn._handle_init(params)
    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.1.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)
    file_path = '{}/{}'.format(params.get('app_dir_path'), vmn.VER_FILE_NAME)
    app_layout.remove_app_version_file(file_path)
    # now we want to override the version by changing the file version:
    app_layout.write_file_commit_and_push('test_repo',
                                          '.vmn/test_app/{}'.format(vmn.VER_FILE_NAME),
                                          'last_stamped_version: 0.2.3')
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)
    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    _version = ver_info['stamping']['app']['_version']
    assert '0.2.4' == _version


def test_basic_root_show(app_layout,capfd):
    params = copy.deepcopy(app_layout.params)
    params = vmn.build_world('root_app/app1', params['working_dir'])
    vmn._handle_init(params)

    params['release_mode'] = 'patch'
    params['prerelease'] = 'release'
    params['buildmetadata'] = None
    params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(params)
    vmn.stamp(vcs, params)

    ver_info = vcs.get_vmn_version_info(app_name=params['name'])
    data = ver_info['stamping']['app']
    assert data['version'] == '0.0.1'

    data = ver_info['stamping']['root_app']
    assert data['version'] == 1

    app2_params = vmn.build_world('root_app/app2', params['working_dir'])

    app2_params['release_mode'] = 'minor'
    app2_params['prerelease'] = 'release'
    app2_params['buildmetadata'] = None
    app2_params['starting_version'] = '0.0.0'
    vcs = vmn.VersionControlStamper(app2_params)
    vmn.stamp(vcs, app2_params)

    params['root'] = True
    vcs = vmn.VersionControlStamper(params)
    vmn.show(vcs, params)
    out, err = capfd.readouterr()
    assert '2\n' == out
