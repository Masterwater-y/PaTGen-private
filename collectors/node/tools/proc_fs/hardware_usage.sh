#!/bin/bash


time=99999999
interval=1
trap 'quit=1' INT QUIT TERM PIPE HUP	# sends execution to end tracing section


while getopts t:d:n:i: opt
do
	case "$opt" in
		t) time=$OPTARG;;
        i) interval=$OPTARG;;
		d) disk_name=$OPTARG;;
		n) network_name=$OPTARG;;
	esac
done


function record_period(){
    current_time=`date +%s`
	echo -e "$current_time" >> ./data/collected_time

	cpu_util=`head -n 1 /proc/stat | cut -d ' ' -f 3-9`
	echo -e "$cpu_util" >> ./data/cpu_util
						    
	mem_util=`cat /proc/meminfo | awk 'BEGIN{ORS=" "}{print $2}'`
	echo -e "$mem_util" >> ./data/mem_util

	io_stat=`cat /proc/diskstats | grep -w $disk_name | awk '$1=$1' | cut -d ' ' -f 4-`
	echo -e "$io_stat" >> ./data/io_stat

	network_stat=`cat /proc/net/dev | grep $network_name | cut -d ':' -f 2-`
	echo -e "$network_stat" >> ./data/network_stat

	numa_stat=`numastat | tail -n +2`
	echo -e "$numa_stat" >> ./data/numa_stat

}

function main(){
	echo $$ > ./data/pid/hardware_usage
	cat /dev/null > ./data/collected_time
	cat /dev/null > ./data/cpu_util
	cat /dev/null > ./data/mem_util
	cat /dev/null > ./data/io_stat
	cat /dev/null > ./data/network_stat
	cat /dev/null > ./data/numa_stat

	secs=0; quit=0

	while (( !quit && secs<time )); do
		(( secs += interval ))
		run_time=`{ time record_period; } 2>&1 | grep real | cut -d 'm' -f 2 | sed 's/s//'`
		sleep_time=`echo $interval-$run_time | bc`
		sleep $sleep_time
	done
}

main
