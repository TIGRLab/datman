#!/bin/bash
# Submits a single command to qbatch (like sge_batch)
#
# Usage: 
#     qbatchsub.sh [qbatch options] -- command [options]
# 
# For example, 
#   qbatchsub -o '-l walltime=30:00' --ppj 8 -- ./process.sh "hello world"
#
# This submits the command "./process.sh 'hello world'"

qbatch_args=()
cmd=()
dashdash_unseen="no"

while [[ $# > 0 ]]; do
    if [[ $1 = "--" ]]; then
        dashdash_unseen="yes"
    elif [[ ${dashdash_unseen} = "no" ]]; then
        qbatch_args+=("$1")
    else
        cmd+=( $(printf '%q' "$1") )
    fi
    shift;
done

echo "${cmd[@]}" | qbatch "${qbatch_args[@]}" -
