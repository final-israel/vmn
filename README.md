<p align="center">
  <img width="100" src="https://i.imgur.com/4gUaVKW.png">
  <br>
  <h1 align="center">Version MaNaging package - VMN</h1>
</p>

A simple package for auto increasing version numbers of any application agnostic to language or architecture.

`vmn` is fully compliant with https://semver.org semantics

[![codecov](https://codecov.io/gh/final-israel/vmn/branch/master/graph/badge.svg)](https://codecov.io/gh/final-israel/vmn)

[![Build Status](https://travis-ci.com/final-israel/vmn.svg?branch=master)](https://travis-ci.com/final-israel/vmn)

## Usage

```sh
cd to/your/repository
vmn -h


## Needed only once per repository.
vmn init

# Examples:
vmn stamp --release-mode patch <app-name>
# example for starting from version 1.6.8
vmn stamp -r minor --starting-version 1.6.8 <app-name>
vmn stamp -r major <app-name>
vmn show <app-name>
vmn show --verbose <app-name>

vmn goto -v 1.0.1 <app-name>
```

### Concurrent builds
`vmn`  supports simultaneous builds. You can safely run multiple instances of `vmn`


## Installation

```sh
pip3 install vmn
```

## Why `vmn` is agnostic to application language?
It is the application's reposibility to actualy set the version number that can be retreived from
```sh
vmn show <app-name>
```
and be injected via a custom script to the application's code during its build phase.
Actually `vmn` uses this technique for itself.

## Advanced features
### Root apps

`vmn` supports stamping of something called a "root app". For example:

`vmn stamp --release-mode patch my_root_app/service1`

`vmn stamp --release-mode patch my_root_app/service2`

`vmn stamp --release-mode patch my_root_app/service3`

Next we'll be able to use `show` to display everything we need:

`vmn show --verbose my_root_app/service3`

```yml
vmn_info:
  description_message_version: '1'
  vmn_version: <the version of vmn itself that has stamped the application>
stamping:
  msg: 'my_root_app/service3: update to version 0.0.1'
  app:
    name: my_root_app/service3
    version: 0.0.1
    _version: 0.0.1
    release_mode: patch
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
    version: 3
    latest_service: my_root_app/service3
    services:
      my_root_app/service1: 0.0.1
      my_root_app/service2: 0.0.1
      my_root_app/service3: 0.0.1
    external_services: {}
```

`vmn show my_root_app/service3` will output `0.0.1`
`vmn show --root my_root_app` will output `3`

### Configuration
vmn auto generates a `conf.yml` file that can be modified later by the user. An example of `conf.yml` file:
```yml
# Autogenerated by vmn. You can edit this configuration file
conf:
  template: '{0}.{1}.{2}'
  deps:
    ../:
      <repo dir name>:
        remote: <remote url>
        vcs_type: git
  extra_info: false
```

#### Configuration: template
The template configuration string can be customized and will be applied on the actual version of 4 octas: `x1.x2.x3.x4`
by `vmn` and will be displayed based on the `template`. In this case the output version will be `x1.x2.x3`.

For example:
`vmn show my_root_app/service3` will output `0.0.1`
however running:
`vmn show --raw my_root_app/service3` will output `0.0.1`

#### Configuration: deps
In `deps` you can specify other repositories as your dependencies and `vmn` will consider them when stamping and performing `goto`.

#### Configuration: extra_info
Setting this to `true` will make `vmn` output lots of usefull data about the host on which `vmn` has stamped the version

## Contributing

If you want to contribute to version-stamp development:

1. Make a fresh fork of the repository

2. Test your work

4. Pull Request

This project is just a small side project that I've started, decided to share it. We'll see if it will ramp up.

We will thank you for every contribution :)

