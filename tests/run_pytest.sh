#!/bin/bash
CUR_DIR="$(cd "$(dirname "$0")" && pwd)"

set -o pipefail


usage()
{
cat << EOF
    Usage: run_pytest.sh [--color] [--base_log_dir (the default is /tmp)]
           [--specific_test <test_name>]
           [--module_name <module_name> (the default is just the current directory)]
           [-h or --help for this usage message]
    Default values: --base_log_dir='/tmp'
EOF
}

color='no'
base_log_dir='/tmp/'
specific_test='none'
module_name=${CUR_DIR}

while [ "$1" != "" ]; do
    case $1 in
        --base_log_dir )   shift
                           base_log_dir=$1
                           ;;
        --module_name )    shift
                           module_name=$1
                           ;;
        --specific_test )   shift
                           specific_test=$1
                           ;;
        --color )          color='yes'
                           ;;
        -h | --help )      usage
                           exit 0
                           ;;
        * )                usage
                           exit 1
    esac
    shift
done


COLOR=''
if [ ${color} = 'yes' ]; then
	COLOR='--color=yes'
fi

SPECIFIC_TEST=''
if [ ${specific_test} != 'none' ]; then
	SPECIFIC_TEST="-k ${specific_test}"
fi

DATE=$(date +%Y-%m-%d_%H-%M-%S)
OUT_PATH=${base_log_dir}

echo "Will run:"
echo "pytest -vv ${COLOR} ${SPECIFIC_TEST} \
--junit-xml=${OUT_PATH}/docker_registry_system_tests_results.xml \
${module_name} | tee ${OUT_PATH}/docker_registry_system_tests_output.log"

PYTHONPATH=${CUR_DIR}:${CUR_DIR}../ \
pytest -vv ${COLOR} ${SPECIFIC_TEST} \
--junit-xml=${OUT_PATH}/docker_registry_system_tests_results.xml \
${module_name} | tee ${OUT_PATH}/docker_registry_system_tests_output.log

RET_CODE=$?

exit ${RET_CODE}
