#!/bin/bash
#/home/caslab/linux-5.13.1/tools/perf/perf stat -e instructions -C $1\-7 sleep 0.1 2> >(grep inst)
perf stat -e instructions -C $1\-7 sleep 0.1 2> >(grep inst)

