#!/bin/sh
starttime=`date +'%Y-%m-%d %H:%M:%S'`
current_path=$(cd "$(dirname "$0")"; pwd)
shell_name=${0##*/}
model_region=${current_path##*/}
echo $current_path/$shell_name


python3 FRI_AnyP_demo.py

#计算运行时间
endtime=`date +'%Y-%m-%d %H:%M:%S'`
start_seconds=`date -d "$starttime" +%s`
end_seconds=`date -d "$endtime" +%s`
runtime=$((end_seconds-start_seconds))  #计算程序运行时间
echo $runtime"s"