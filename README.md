<h1 align="center" style="border-bottom: none;">🥇🏷️Automatic version management solution</h1>
<h3 align="center">Automatic version management and state recovery solution for any application agnostic to language or architecture</h3>

<p align="center">

[![Project Status: Active – The project has reached a stable, usable state and is being actively developed.](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)
[![codecov](https://codecov.io/gh/final-israel/vmn/branch/master/graph/badge.svg)](https://codecov.io/gh/final-israel/vmn)
<a href="#badge">
<img alt="vmn" src="https://img.shields.io/github/pipenv/locked/python-version/final-israel/vmn">
</a>
<a href="#badge">
<img alt="vmn: pypi downloads" src="https://img.shields.io/pypi/dw/vmn">
</a>
<a href="#badge">
<img alt="vmn: supported platfroms" src="https://img.shields.io/badge/vmn-linux%20%7C%20macos%20%7C%20windows%20-brightgreen">
</a>

`vmn` is compliant with `Semver` (https://semver.org) semantics

</p>

### Badge

Let people know that your repository is managed by **vmn** by including this badge in your readme.

[![vmn: automatic versioning](https://img.shields.io/badge/vmn-automatic%20versioning-blue)](https://github.com/final-israel/vmn)

```md
[![vmn: automatic versioning](https://img.shields.io/badge/vmn-automatic%20versioning-blue)](https://github.com/final-israel/vmn)
```

<p align="center">
  <br>
  <img width="800" src="https://i.imgur.com/dwmhs3v.png">
  <br>
</p>

# What is `vmn`?

`vmn` is a CLI tool and a Python library that is used for handling project versioning needs.

Now go ahead and read `vmn`'s docs :)

# Play around with `vmn`

## Create a playground

```sh
# Install vmn
pip install vmn

# Create fake remote
mkdir remote
cd remote
git init --bare

# Clone from fake remote
cd ..
git clone ./remote ./local
cd local

# Mimic user commit
echo a >> ./a.txt ; git add ./a.txt ; git commit -m "wip" ; git push origin master

# Initialize vmn for first time
vmn init
# Initialize app for first time
vmn init-app my_cool_app

# First stamp
vmn stamp -r patch my_cool_app

# Mimic user commit
echo a >> ./a.txt ; git add ./a.txt ; git commit -m "wip" ; git push origin master

# Second stamp
vmn stamp -r patch my_cool_app
```

# Contribute

## Create a dev environment

```sh
# After cloning vmn repo:
cd ./vmn
# For Ubuntu:
#   sudo apt install python3-venv
python3 -m venv ./venv
source ./venv/bin/activate

pip install -r  ./tests/requirements.txt 
pip install -r  ./tests/test_requirements.txt 
pip install -e  ./
vmn --version # Should see 0.0.0 if installed successfully
```

## Run tests

``` sh
# install Docker 
#   For Ubuntu - sudo apt install docker.io
# Then run:
./tests/run_pytest.sh
# If it runs successfully, you are good to go
```

# Key features

- [x] Stamping of versions of type: **`major`. `minor`.`patch`** , e.g., `1.6.0` [`Semver` compliant]
- [x] Stamping of versions of type: `major`. `minor`.`patch`**-`prerelease`** , e.g., `1.6.0-rc23` [`Semver` compliant]
- [x] Stamping of versions of type: `major`. `minor`.`patch`.**`hotfix`** , e.g., `1.6.7.4` [`Semver` extension]
- [x] Bringing back the repository / repositories state to the state they were when the project was stamped (
  see [`goto`](https://github.com/final-israel/vmn#goto) section)
- [x] Stamping of micro-services-like project topologies (
  see [`Root apps`](https://github.com/haimhm/vmn/blob/master/README.md#root-apps) section)
- [x] Stamping of a project depending on multiple git repositories (
  see [`Configuration: deps`](https://github.com/haimhm/vmn/blob/master/README.md#configuration) section)
- [x] Version auto-embedding into supported backends (`npm`, `cargo`) during the `vmn stamp` phase (
  see [`Version auto-embedding`](https://github.com/haimhm/vmn/blob/master/README.md#version-auto-embedding) section)
- [x]  Addition of `buildmetadata` for an existing version, e.g., `1.6.0-rc23+build01.Info` [`Semver` compliant]
- [ ] `WIP` Support "root apps" that are located in different repositories

# Usage

## 1. Installation

```sh
pip3 install vmn

# Another option (and a better one) is to use pipX (https://github.com/pypa/pipx):
pipx install vmn
```

## 2. `cd` into your git repository

```sh
cd to/your/repository
```

## 3. `vmn init`

```sh
## Needed only once per repository.
vmn init
```

## 4. `vmn stamp`

```sh
## Needed only once per app-name
# will start from 0.0.0
vmn init-app <app-name>

# will stamp 0.0.1
vmn stamp -r patch <app-name>

# example for starting from version 1.6.8
vmn init-app -v 1.6.8 <app-name2>

# will stamp 1.7.0
vmn stamp -r minor <app-name2>
```

### Note

`init-app` and `stamp` both support `--dry-run` flag

## You can also use vmn as a python lib by importing it

``` python
from contextlib import redirect_stdout, redirect_stderr
import io
import version_stamp.vmn as vmn

out = io.StringIO()
err = io.StringIO()
with redirect_stdout(out), redirect_stderr(err):
    ret, vmn_ctx = vmn.vmn_run(["show", "vmn"])
out_s = out.getvalue()
err_s = err.getvalue()
```

explore `vmn_ctx` object to see what you can get from it. Vars starting with `_` are private and may change with time

## Supported env vars

`VMN_WORKING_DIR` - Set it and `vmn` will run from this directory

`VMN_LOCK_FILE_PATH` - Set this to make `vmn` use this lockfile
  when it runs. The default is to use a lock file per repo to avoid running multiple `vmn` commands simultaneously.

# Detailed Documentation

## `vmn stamp` for release candidates

`vmn` supports `Semver`'s `prerelease` notion of version stamping, enabling you to release non-mature versions and only
then release the final version.

```sh
# will start from 1.6.8
vmn init-app -v 1.6.8 <app-name>

# will stamp 2.0.0-alpha1
vmn stamp -r major --pr alpha <app-name>

# will stamp 2.0.0-alpha2
vmn stamp --pr alpha <app-name>

# will stamp 2.0.0-mybeta1
vmn stamp --pr mybeta <app-name>

# Run release when you ready - will stamp 2.0.0 (from the same commit)
vmn release -v 2.0.0-mybeta1 <app-name>
```

## `vmn stamp` for "root apps" or microservices

`vmn` supports stamping of something called a "root app" which can be useful for managing version of multiple services
that are logically located under the same solution.

### Example

```sh
vmn init-app my_root_app/service1
vmn stamp -r patch my_root_app/service1
```

```sh
vmn init-app my_root_app/service2
vmn stamp -r patch my_root_app/service2
```

```sh
vmn init-app my_root_app/service3
vmn stamp -r patch my_root_app/service3
```

Next we'll be able to use `vmn show` to display everything we need:

`vmn show --verbose my_root_app/service3`

```yml
vmn_info:
  description_message_version: '1'
  vmn_version: <the version of vmn itself that has stamped the application>
stamping:
  msg: 'my_root_app/service3: update to version 0.0.1'
  app:
    name: my_root_app/service3
    _version: 0.0.1
    release_mode: patch
    prerelease: release
    previous_version: 0.0.0
    stamped_on_branch: master
    changesets:
      .:
        hash: 8bbeb8a4d3ba8499423665ba94687b551309ea64
        remote: <remote url>
        vcs_type: git
    info: {}
  root_app:
    name: my_root_app
    version: 5
    latest_service: my_root_app/service3
    services:
      my_root_app/service1: 0.0.1
      my_root_app/service2: 0.0.1
      my_root_app/service3: 0.0.1
    external_services: {}
```

`vmn show my_root_app/service3` will output `0.0.1`

`vmn show --root my_root_app` will output `5`

## `vmn show`

Use `vmn show` for displaying version information of previous `vmn stamp` commands

```sh
vmn show <app-name>
vmn show --verbose <app-name>
vmn show -v 1.0.1 <app-name>
```

## `vmn goto`

Similar to `git checkout` but also supports checking out all configured dependencies. This way you can easily go back to
the **exact** state of you entire code for a specific version even when multiple git repositories are involved.

```sh
vmn goto -v 1.0.1 <app-name>
```

## `vmn gen`

Generates version output file based on jinja2 template

`vmn gen -t path/to/jinja_template.j2 -o path/to/output.txt app_name`

### Available jinja2 keywords

```json
{
 "_version": "0.0.1",
 "base_version": "0.0.1",
 "changesets": {".": {"hash": "d6377170ae767cd025f6c623b838c7a99efbe7f8",
                      "remote": "../test_repo_remote",
                      "state": {"modified"},
                      "vcs_type": "git"}},
 "info": {},
 "name": "test_app2/s1",
 "prerelease": "release",
 "prerelease_count": {},
 "previous_version": "0.0.0",
 "release_mode": "patch",
 "stamped_on_branch": "main",
 "version": "0.0.1",
 "root_latest_service": "test_app2/s1",
 "root_name": "test_app2",
 "root_services": 
 {
   "test_app2/s1": "0.0.1"
 }, 
 "root_version": 1,
}
```

#### `vmn gen` jinja template example

``` text
"VERSION: {{version}} \n" \
"NAME: {{name}} \n" \
"BRANCH: {{stamped_on_branch}} \n" \
"RELEASE_MODE: {{release_mode}} \n" \
"{% for k,v in changesets.items() %} \n" \
"    <h2>REPO: {{k}}\n" \
"    <h2>HASH: {{v.hash}}</h2> \n" \
"    <h2>REMOTE: {{v.remote}}</h2> \n" \
"    <h2>VCS_TYPE: {{v.vcs_type}}</h2> \n" \
"{% endfor %}\n"
```

#### `vmn gen` output example

``` text
VERSION: 0.0.1
NAME: test_app2/s1
BRANCH: master
RELEASE_MODE: patch

    <h2>REPO: .
    <h2>HASH: ef4c6f4355d0190e4f516230f65a79ec24fc7396</h2>
    <h2>REMOTE: ../test_repo_remote</h2>
    <h2>VCS_TYPE: git</h2>
```

## Version auto-embedding

`vmn` supports auto-embedding the version string during the `vmn stamp` phase for supported backends:

| Backend | Description | | :-: | :-: |
| ![alt text](https://user-images.githubusercontent.com/5350434/136626161-2a7bdc4a-5d42-4012-ae42-b460ddf7ea88.png) |
Will embed version string to `package.json` file within the `vmn stamp` command |
| ![alt text](https://user-images.githubusercontent.com/5350434/136626484-0a8e4890-42f1-4437-b306-28f190d095ee.png) |
Will embed version string to `Cargo.toml` file within the `vmn stamp` command |

## Configuration

`vmn` auto generates a `conf.yml` file that can be modified later by the user.

An example of a possible `conf.yml` file:

```yaml
# Autogenerated by vmn. You can edit this configuration file
conf:
  template: '[{major}][.{minor}]'
  deps:
    ../:
      <repo dir name>:
        vcs_type: git
        # branch: branch_name
        # tag: tag_name
        # hash: specific_hash
  extra_info: false
  create_verinfo_files: false
  hide_zero_hotfix: true
  version_backends: 
    npm:
      path: "relative_path/to/package.json"
```

|         Field          | Description                                                  | Example                                                      |
| :--------------------: | ------------------------------------------------------------ | ------------------------------------------------------------ |
|       `template`       | The template configuration string can be customized and will be applied on the "raw" vmn version.<br>`vmn` will display the version based on the `template`. | `vmn show my_root_app/service3` will output `0.0` <br>however running:<br>`vmn show --raw my_root_app/service3` will output `0.0.1` |
|         `deps`         | In `deps` you can specify other repositories as your dependencies and `vmn` will consider them when stamping and performing `goto`. | See example `conf.yml` file above                            |
|      `extra_info`      | Setting this to `true` will make `vmn` output usefull data about the host on which `vmn` has stamped the version.<br>**`Note`** This feature is not very popular and may be remove / altered in the future. | See example `conf.yml` file above                            |
| `create_verinfo_files` | Tells `vmn` to create file for each stamped version. `vmn show --from-file` will work with these files instead of working with `git tags`. | See example `conf.yml` file above                            |
|   `hide_zero_hotfix`   | Tells `vmn` to hide the fourth version octa when it is equal to zero. This way you will never see the fourth octa unless you will specifically stamp with `vmn stamp -r hotfix`. `True` by default. | See example `conf.yml` file above                            |
|   `version_backends`   | Tells `vmn` to auto-embed the version string into one of the supported backends' files during the `vmn stamp` command. For instance, `vmn` will auto-embed the version string into `package.json` file if configured for `npm` projects. | See example `conf.yml` file above                            |
