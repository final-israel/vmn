#!/bin/bash

CUR_DIR="$(cd "$(dirname "$0")" && pwd)"

#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_git_hooks[git-post-commit]
#test_basic_show
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_git_hooks[git-pre-commit]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_git_hooks[git-pre-push]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_show_from_file[git]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_show_from_file_conf_changed[git]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_run_vmn_from_non_git_repo[git]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_basic_root_show[git]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_perf_show[git]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_add_bm[git]
#FAILED Users/pavelrogovoy/projects/vmn/tests/test_ver_stamp.py::test_rc_stamping[git]

${CUR_DIR}/build_vmn_xenial_tester.sh || exit 1
echo "docker run --init -t -v ${CUR_DIR}/..:${CUR_DIR}/.. vmn_tester:ubuntu_xenial ${CUR_DIR}/run_pytest.sh --specific_test test_basic_show"
docker run --init -t -v ${CUR_DIR}/..:${CUR_DIR}/.. vmn_tester:ubuntu_xenial ${CUR_DIR}/run_pytest.sh --specific_test test_basic_show --skip_test test_backward_compatability_with_previous_vmn || exit 1

${CUR_DIR}/build_vmn_tester.sh ubuntu bionic || exit 1
echo "docker run --init -t -v ${CUR_DIR}/..:${CUR_DIR}/.. vmn_tester:ubuntu_bionic ${CUR_DIR}/run_pytest.sh"
docker run --init -t -v ${CUR_DIR}/..:${CUR_DIR}/.. vmn_tester:ubuntu_bionic ${CUR_DIR}/run_pytest.sh --skip_test test_backward_compatability_with_previous_vmn || exit 1

${CUR_DIR}/build_vmn_tester.sh ubuntu focal || exit 1
echo "docker run --init -t -v ${CUR_DIR}/..:${CUR_DIR}/.. vmn_tester:ubuntu_focal ${CUR_DIR}/run_pytest.sh"
docker run --init -t -v ${CUR_DIR}/..:${CUR_DIR}/.. vmn_tester:ubuntu_focal ${CUR_DIR}/run_pytest.sh --skip_test test_backward_compatability_with_previous_vmn || exit 1

${CUR_DIR}/build_previous_vmn_stamper.sh || exit 1

${CUR_DIR}/run_pytest.sh || exit 1

exit 0
