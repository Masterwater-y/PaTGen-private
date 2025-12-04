#!/bin/bash

tracing=/sys/kernel/debug/tracing
trap 'quit=1' INT QUIT TERM PIPE HUP	# sends execution to end tracing section


interval=1
### process options
while getopts t:i:e: opt
do
	case "$opt" in
		t) opt_duration=1;duration=$OPTARG;;
        i) interval=$OPTARG;;
		e) target_functions=$OPTARG;;
	esac
done


function warn {
	if ! eval "$@"; then
		echo >&2 "WARNING: command failed \"$@\""
	fi
}

function die {
	echo >&2 "$@"
	exit 1
}

function record {
	echo 0 > function_profile_enabled
	echo 1 > function_profile_enabled
	sleep $next_sleep
	now_timestamp=$(date +%s)
	if [ "$last_timestamp" != "$now_timestamp" ];then
		echo $now_timestamp >> $work_dir/data/function_trace
		cat trace_stat/function* | awk '$2 ~ /[0-9]/ {a[$1]+=$2}END{for (i in a) print i,a[i]}'  >> $work_dir/data/function_trace	
		last_timestamp=$now_timestamp
	else
		sleep 0.3
	fi
}


cat /dev/null > ./data/function_trace 
echo $$ > ./data/pid/ftrace
work_dir=`pwd`

### check permissions
cd $tracing || die "ERROR: accessing tracing. Root user? Kernel has FTRACE?
    debugfs mounted? (mount -t debugfs debugfs /sys/kernel/debug)"

### enable tracing
sysctl -q kernel.ftrace_enabled=1	# doesn't set exit status


printf $target_functions > set_ftrace_filter || die "ERROR: tracing functions fails. Exiting."
warn "echo nop > current_tracer"
if ! echo 1 > function_profile_enabled; then
	echo > set_ftrace_filter
	die "ERROR: enabling function profiling. Have CONFIG_FUNCTION_PROFILER? Exiting."
fi


### summarize
quit=0; secs=0; next_sleep=`echo $interval | bc`; last_timestamp=0;

while (( !quit && (!opt_duration || secs < duration) )); do
	(( secs += interval ))
	start_time=$(date +%s%3N)
	record
	end_time=$(date +%s%3N)
	run_time=$(echo "scale=3; ($end_time - $start_time) / 1000" | bc)
	next_sleep=`echo "$interval+$next_sleep-$run_time" | bc`
done

### end tracing
warn "echo 0 > function_profile_enabled"
warn "echo > set_ftrace_filter"
