#!/bin/bash

while getopts "r:l:i:" opt
do
    case "$opt" in
        r) remote_path=$OPTARG;;
        l) local_path=$OPTARG;;
        i) ip_list=$OPTARG;;
    esac
done

# show parameters for debug
echo "[TauCollector]: Pull tau file to $local_path"

# create log path.
IFS=',' read -r -a ip_list <<< "$ip_list"

for ip in "${ip_list[@]}"
do
    mkdir -p "$local_path/$ip"
    scp_output=$(scp -r -p "$ip:$remote_path/profile*" "$local_path/$ip" 2>&1)
    scp_status=$?
    if [ $scp_status -eq 0 ]; then
        echo "[TauCollector]: Pull $remote_path from remote $ip"
    else
        echo "[TauCollector]: $scp_output"
    fi
done
