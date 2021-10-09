<p align="center">
  <img width="100" src="https://i.imgur.com/4gUaVKW.png">
  <br>
<h1 align="center">Version managment package</h1>
</p>
A simple package for auto increasing version numbers of any application agnostic to language or architecture.

`vmn` is compliant with `Semver` (https://semver.org) semantics

### Key features

- [x] Stamping of versions of type: **`major`. `minor`.`patch`** , e.g.,` 1.6.0` [`Semver` compliant]
- [x] Stamping of versions of type: `major`. `minor`.`patch`**-`prerelease`** , e.g.,` 1.6.0-rc23` [`Semver` compliant]
- [x] Stamping of versions of type: `major`. `minor`.`patch`.**`hotfix`** , e.g.,` 1.6.7.4` [`Semver` extension]
- [x] Bringing back the repository / repositories state to the state they were when the project was stamped (see `goto` section)
- [x] Stamping of micro-services like project topologies (see `Root apps` section)
- [x] Stamping of a project depending on multiple git repositories (see `Configuration: deps` section)
- [x] Version auto-embedding to supported backends (`npm`, `cargo`) during the `vmn stamp` phase (see `Version auto-embedding` section)
- [ ] `WIP` Addition of `buildmetadata` for an existing version, e.g.,` 1.6.0-rc23+build01.Info` [`Semver` compliant]
- [ ] `WIP` Addition of `releasenotes` for an existing version [`Semver` extension]

## Usage
### cd into your git repository
```sh
cd to/your/repository
```

### Init phase
```sh
## Needed only once per repository.
vmn init
```

### Start stamping
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

### Release candidates

`vmn` supports `Semver`'s `prerelease` notion of version stamping, enabling you to release non-mature versions and only then release the final version.

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
### Show

Use `vmn show` for displaying version information of previous `vmn stamp` commands

```sh
vmn show <app-name>
vmn show --verbose <app-name>
vmn show -v 1.0.1 <app-name>
```

### Goto 

Similar to `git checkout` but also supports checking out all configured dependencies. This way you can easily go back to the **exact** state of you entire code for a specific version even when multiple git repositories are involved. 

```sh
vmn goto -v 1.0.1 <app-name>
```

### Version auto-embedding

| Backend | Description |
| :-: | :-: |
| ![alt text](https://user-images.githubusercontent.com/5350434/136626161-2a7bdc4a-5d42-4012-ae42-b460ddf7ea88.png) | Will embed Semver version string to your `package.json` file during the `vmn stamp` command |
| ![alt text](https://user-images.githubusercontent.com/5350434/136626484-0a8e4890-42f1-4437-b306-28f190d095ee.png) | Will embed Semver version string to your `Cargo.toml` file during the `vmn stamp` command |

## Installation

```sh
pip3 install vmn
```

## Why `vmn` is agnostic to application language?
It is the application's responsibility to actually set the version number at build time. The version string can be retrieved from
```sh
vmn show <app-name>
```
and be injected via a custom script to the application's code during its build phase (see **`Version auto-embedding`** section above).
Actually `vmn` uses this technique for itself.

## Advanced features
### Root apps

`vmn` supports stamping of something called a "root app" which can be useful for managing version of multiple services that are logically located under same solution. 

##### For example:

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

### Configuration
`vmn` auto generates a `conf.yml` file that can be modified later by the user. 

An example of a possible `conf.yml` file:

```yaml
# Autogenerated by vmn. You can edit this configuration file
conf:
  template: '[{major}][.{minor}]'
  deps:
    ../:
      <repo dir name>:
        remote: <remote url>
        vcs_type: git
  extra_info: false
  create_verinfo_files: false
  create_verinfo_files: true
  version_backends: 
    npm:
      path: "relative_path/to/Cargo.toml"
```

#### Configuration: template

The template configuration string can be customized and will be applied on the "raw" vmn version.
`vmn` will display the version based on the `template`. In this case the output version will be `0.0`.

For example:
`vmn show my_root_app/service3` will output `0.0`

however running:
`vmn show --raw my_root_app/service3` will output `0.0.1`


#### Configuration: deps
In `deps` you can specify other repositories as your dependencies and `vmn` will consider them when stamping and performing `goto`.

#### Configuration: extra_info
Setting this to `true` will make `vmn` output usefull data about the host on which `vmn` has stamped the version.
This feature is not very popular and may be remove / altered in the future

[![codecov](https://codecov.io/gh/final-israel/vmn/branch/master/graph/badge.svg)](https://codecov.io/gh/final-israel/vmn)
