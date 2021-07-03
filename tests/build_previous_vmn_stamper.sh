#!/bin/bash

CUR_DIR="$(cd "$(dirname "$0")" && pwd)"

docker build -t previous_vmn_stamper:latest -f ${CUR_DIR}/previous_vmn_stamper_dockerfile ${CUR_DIR}
