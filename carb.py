import re
import time
import threading
import multiprocessing
from multiprocessing import Process,Queue
import subprocess
import sysv_ipc
import math
import numpy as np
import os
import sys
import socket
from operator import itemgetter



############Configuration##################

class Global(object):
    def __init__(self):
        #self.app_name = "memcached"
        self.app_name = "xapian"
        self.period= 0.05  # s
        self.max_core = 8
        if self.app_name == "memcached":
            #nginx & memcached
            self.slo = 10.0
            self.sens_rps = 100000
            self.boost_rps = 300000

            

            self.sens_reptime = self.slo * 0.1
            self.step_size = 1

        if self.app_name == "nginx":

            self.slo = 10.0
            self.sens_rps = 5000
            self.boost_rps = 300000
            self.sens_reptime = 0.5
            self.step_size = 1

        if self.app_name == "xapian":
            self.slo = 10.0
            self.sens_rps = 1000
            self.boost_rps = 4000
            self.sens_reptime = self.slo * 0.1
            self.step_size = 1



        self.interface_name = "enp59s0f0"
        self.server_ip = "10.150.21.207" 
        self.server_port = 9999
        self.window_size = 5
        self.debug = True
        #self.debug = False

class Stat(object):
    def __init__(self,param):
        self.cur_rps = 0
        self.prev_rps = 0
        self.cur_reptime = 0
        self.prev_reptime = 0
        self.interface_name = param.interface_name
        self.server_ip = param.server_ip
        self.server_port = param.server_port
        self.window_size = param.window_size
        self.timestamp = 0
        self.debug = param.debug

        self.__prev_rx_pkt_num = 0

        self.q_reptime = Queue(maxsize=self.window_size)
        self.reptime_collector = Process(target=self.__reptime_collect_daemon)
        self.reptime_collector.deamon = True
        self.reptime_collector.start()

    
    def __readNetStat(self):
        #read the the number of rx_packet
        f = open("/sys/class/net/"+self.interface_name+"/statistics/rx_packets")
        for line in f.readlines():
            rx_pkt_num = int(line)
        f.close()
        return rx_pkt_num

    def __getReqCount(self):
        new_rx_pkt_num = self.__readNetStat()
        delta_rx_pkt_num = new_rx_pkt_num - self.__prev_rx_pkt_num
        self.__prev_rx_pkt_num = new_rx_pkt_num
        return delta_rx_pkt_num
    
    def __readReptime(self):
        #
        reptime = 0.0
        count = 0
        while self.q_reptime.qsize():
            reptime += self.q_reptime.get() 
            count += 1
        if count > 0:
            reptime = reptime / count

        return reptime
    
    def __updateRPS(self,time_gap):
        self.prev_rps = self.cur_rps
        self.cur_rps = self.__getReqCount() / time_gap

    def __updateReptime(self):
        self.prev_reptime = self.cur_reptime
        self.cur_reptime = self.__readReptime()

    def getCurRPS(self):
        return self.cur_rps

    def getCurReptime(self):
        return self.cur_reptime 
    
    def getPrevRPS(self):
        return self.prev_rps

    def getPrevReptime(self):
        return self.prev_reptime 

    def update(self):
        if self.timestamp == 0:
            #init phase
            self.timestamp = time.time()
            return

        time_gap = time.time() - self.timestamp
        self.__updateRPS(time_gap)
        self.__updateReptime()

        self.timestamp = time.time()
    
    def __reptime_collect_daemon(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)        
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print("ip: " + str(self.server_ip) + " port: " + str(self.server_port))
        server_socket.bind((self.server_ip, self.server_port))
        server_socket.listen()
        client_socket, addr = server_socket.accept()
        print('Connected by', addr)

        while True:
            reptime = 0.0
            
            #parsing:
            data = client_socket.recv(1024)
            data = str(data.decode())
            data = data.split(':')
            data = ' '.join(data).split()

            for reptime in data:
                self.q_reptime.put(float(reptime))

            #except:
            #    print('latnecy exception')
            #    latency = self.slo
            #print(float(data.decode()))
            #time.sleep(self.periode)
        
        client_socket.close()
        server_socket.close()
        sys.exit(0)

class Carb(object):
    def __init__(self,param):
        self.state = 2
        self.max_core = param.max_core
        self.min_core = 1
        self.active_core = param.max_core
        self.step_size = param.step_size
        self.sens_rps = param.sens_rps
        self.sens_reptime = param.sens_reptime
        self.app_name = param.app_name
        self.boost_rps = param.boost_rps
        self.debug = param.debug

    def __incActiveCore(self):
        self.active_core += self.step_size
        if self.active_core > self.max_core:
            self.active_core = self.max_core
        
        if self.debug:
            print("inc active core\n")
    
    def __decActiveCore(self):
        self.active_core -= self.step_size
        if self.active_core < self.min_core:
            self.active_core = self.min_core
        
        if self.debug:
            print("dec active core\n")

    
    def manage(self, stat):
        cur_active_core = self.active_core
        #control logic at S0
        cur_rps = stat.getCurRPS()
        prev_rps = stat.getPrevRPS()
        cur_reptime = stat.getCurReptime()
        prev_reptime = stat.getPrevReptime()

        
        if self.state == 0:
            if cur_rps > prev_rps + self.sens_rps:
                self.__incActiveCore()
                self.state = 1
            elif cur_rps < prev_rps - self.sens_rps:
                self.state = 2
            elif cur_reptime > prev_reptime + self.sens_reptime:
                self.__incActiveCore()
                self.state = 1
            else:
                self.state = 0

        #control logic at S1
        elif self.state == 1:
            if cur_reptime < prev_reptime - self.sens_reptime:
                self.__incActiveCore()
                self.state = 1
            else:
                self.__decActiveCore()
                self.state = 0

        #control logic at S2
        elif self.state == 2:
            if cur_reptime < prev_reptime + self.sens_reptime:
                self.__decActiveCore()
                self.state = 2
            else:
                self.__incActiveCore()
                self.state = 0

        if cur_rps > self.boost_rps:
            self.active_core = self.max_core
        
        #when the number of core is changed
        if cur_active_core != self.active_core: 
            self.__changeCore()

        if self.debug:
            print("**************************************************")
            print("cur state: " + str(self.state))
            print("cur active core: " + str(cur_active_core))
            print("cur_rps: " + str(cur_rps))
            print("prev_rps: " + str(prev_rps))
            print("cur_reptime: " + str(cur_reptime))
            print("prev_reptime: " + str(prev_reptime))

        
    def __changeCore(self):
        procs = []
        min_cpu = 0
        max_cpu = -1
        proc = None

        logfile = open("log",'w')
        if self.active_core > 1:
            proc = subprocess.Popen("echo "+"0-"+str(self.active_core - 1)+"> " + "/sys/fs/cgroup/cpuset/"+str(self.app_name)+"/cpuset.cpus",shell=True, universal_newlines = True, stderr=subprocess.STDOUT, stdout=logfile)
        else:
            proc = subprocess.Popen("echo "+"0"+" > " + "/sys/fs/cgroup/cpuset/"+str(self.app_name)+"/cpuset.cpus",shell=True, universal_newlines = True, stderr=subprocess.STDOUT, stdout=logfile)
        procs.append(proc)

        for proc in procs:
            proc.communicate()

def initCgroup(param):
    app_tids_list = list()

    grep_str=""
    #get tid
    if param.app_name == "memcached":
        grep_str="ps -eLF | grep " + param.app_name  + "|awk '{print $4}' | awk '{if (NR!=1) {print}}'"
    if param.app_name == "nginx":
        grep_str="ps -eLF | grep -e" + "\"" + param.app_name + "\"" + " -e " + "polkitd "  + "|awk '{print $4}'"
    app_tids_str = subprocess.check_output (grep_str, shell=True)
    app_tids_str = app_tids_str.split()

    for tid in app_tids_str:
        try:
            app_tids_list.append(int(tid))
        except:
            break
    print("tid list: "+str(app_tids_list))

    if param.app_name == "memcached":
        #switch position because first thread in list is not memcached worker
        temp_tid = app_tids_list[0]
        del app_tids_list[0]
        app_tids_list.append(temp_tid)

    #cgroup init
    cmd="cgcreate -g cpuset:"+ str(param.app_name)
    print(cmd)
    subprocess.call(cmd, shell=True)
    subprocess.call("echo "+"0-"+str(param.max_core)+"> " + "/sys/fs/cgroup/cpuset/"+str(param.app_name)+"/cpuset.cpus",shell=True)
    subprocess.call("echo "+"0 > "+"/sys/fs/cgroup/cpuset/"+str(param.app_name)+"/cpuset.mems",shell=True)
    for tid in app_tids_list:
        subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuset/"+str(param.app_name)+"/tasks",shell=True)

    cmd="cgcreate -g cpuacct:"+ str(param.app_name)
    print(cmd)
    subprocess.call(cmd, shell=True)
    for tid in app_tids_list:
        subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuacct/"+str(param.app_name)+"/tasks",shell=True)


def main():
    param = Global()
    initCgroup(param)
    stat = Stat(param)
    carb = Carb(param)
    mainLoop(stat, param, carb)


def mainLoop(stat, param ,carb):
    stat.update()
    carb.manage(stat)
    threading.Timer(param.period, mainLoop,[stat,param,carb]).start()

if __name__ == '__main__':
    main()
