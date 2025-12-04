#!/bin/bash

trap 'quit=1' INT QUIT TERM PIPE HUP	# sends execution to end tracing section


### process options
while getopts t:i:d: opt
do
	case "$opt" in
		t) duration=$OPTARG;;
        i) interval=$OPTARG;;
		d) target_device=$OPTARG;;
	esac
done


echo $$ > ./data/pid/blktrace
rm -rf data/raw/*
rm -rf data/parse/*

### summarize
quit=0; secs=0; 

while (( !quit && secs < duration )); do
    start_time=$(date +%s%3N)
    start_time_int=$(date +%s)
	(( secs += interval ))
	mkdir -p ./data/raw/${start_time_int}
    nice -n -20 blktrace -d ${target_device} -D ./data/raw/${start_time_int} &
    blktrace_pid=$!

	end_time=$(date +%s%3N)
	run_time=$(echo "scale=3; ($end_time - $start_time) / 1000" | bc)
	sleep_time=`echo "$interval-$run_time" | bc`
    sleep ${sleep_time}
    kill $blktrace_pid
    wait $blktrace_pid
done

