#!/bin/bash

trap 'quit=1' INT QUIT TERM PIPE HUP	# sends execution to end tracing section


### process options
while getopts t:i:d: opt
do
	case "$opt" in
		t) duration=$OPTARG;;
        i) interval=$OPTARG;;
	esac
done

if [ ! -d "./data/raw" ];then
    mkdir -p ./data/raw/
fi

if [ ! -d "./data/parse" ];then
    mkdir -p ./data/parse/
fi

if [ ! -d "./data/pid" ];then
    mkdir -p ./data/pid
fi

echo $$ > ./data/pid/msprof
rm -rf ./data/raw/*
rm -rf ./data/parse/*

### summarize
quit=0; secs=0; 

while (( !quit && secs < duration )); do
    start_time=$(date +%s)
    nice -n -20 msprof --output=./data/raw --sys-devices=all --sys-period=$interval \
        --ai-core=on --aic-freq=1 --sys-hardware-mem=on --sys-hardware-mem-freq=1 \
        --sys-cpu-profiling=on --sys-cpu-freq=1  &
    msprof_pid=$!
    
    wait $msprof_pid
    end_time=$(date +%s)
    run_time=`echo "$end_time-$start_time" | bc`
    (( secs += run_time ))
done

