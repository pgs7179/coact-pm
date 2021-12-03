import subprocess
from cpufreq import cpuFreq
import sys,os
import time


class Action:
	def __init__(self, env):
		self.l_fd_alloc_T = list()
		self.l_fd_alloc_P = list()
		self.l_fd_alloc_freq = list()
		self.l_fd_alloc_be = list()
		self.l_fd_freezer_be = list()
		self.env = env
		self.init_action()

	def alloc_T(self, target_core):
		fd = self.l_fd_alloc_T[0]
		if target_core == 1:
			os.write(fd,'0'.encode())
		else:
			str_cpu='0-'+str(target_core-1)
			os.write(fd,str_cpu.encode())

		return

	def alloc_P(self, target_core):
		#rss
		ethtool_str = "ethtool -X " + str(self.env.net_name) + " equal " + str(target_core)
		subprocess.call(ethtool_str,shell=True)
		for core in range(self.env.max_core):
			fd = self.l_fd_alloc_P[core]
			if core < target_core:
				os.write(fd,'ff'.encode())
			else:
	 			os.write(fd,'00'.encode())

		return

	def alloc_be(self,target_core):
		fd = self.l_fd_alloc_be[0]

		self.be_core = target_core

		if target_core == 0:
			self.stop_be()
			return

		if target_core == 1:
			os.write(fd, str(self.env.max_core - 1).encode())
		else:
			str_cpu=str(self.env.max_core - target_core)+'-'+str(self.env.max_core - 1)
			os.write(fd,str_cpu.encode())

		self.start_be()

		for core in range(self.env.max_core - target_core - 1, self.env.max_core):
    		#change freq to max
			self.change_freq_to(self.env.l_freq[0],core)


	def change_freq_to(self, freq, core):
		fd = self.l_fd_alloc_freq[core]
		os.write(fd,str(freq).encode())

		return

	def init_action(self):
		app_tids_list = list()
		grep_str=""
		if self.env.lc_name == "memcached":
			grep_str="ps -eLF | grep " + self.env.lc_name  + "|awk '{print $4}' | awk '{if (NR!=1) {print}}'"
		if self.env.lc_name == "nginx":
			grep_str="ps -eLF | grep -e" + "\"" + self.env.lc_name + ": worker"+ "\"" + " -e " + "polkitd " + "-e dbus"  + "|awk '{print $4}'"

		app_tids_str = None
		app_tids_str = subprocess.check_output (grep_str, shell=True)
		app_tids_str = app_tids_str.split()



		#cgroup init
		#for lc
		cmd="cgcreate -g cpuset:"+ str(self.env.lc_name)
		print(cmd)
		subprocess.call(cmd, shell=True)
		subprocess.call("echo "+"0-"+str(self.env.max_core)+"> " + "/sys/fs/cgroup/cpuset/" +
						str(self.env.lc_name)+"/cpuset.cpus", shell=True)
		subprocess.call("echo "+"0 > "+"/sys/fs/cgroup/cpuset/" +
						str(self.env.lc_name)+"/cpuset.mems", shell=True)
		for tid in app_tids_list:
			subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuset/" +
							str(self.env.lc_name)+"/tasks", shell=True)

		cmd = "cgcreate -g cpuacct:" + str(self.env.lc_name)
		print(cmd)
		subprocess.call(cmd, shell=True)
		for tid in app_tids_list:
			subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuacct/" +
							str(self.env.lc_name)+"/tasks", shell=True)

		#for net
		ethtool_str = "ethtool -X " + str(self.env.net_name) + " equal " + str(self.env.max_core)
		subprocess.call(ethtool_str, shell=True)
		for i in range(self.env.max_core):
			ethtool_str = "echo ff > /sys/class/net/" + str(self.env.net_name) \
				+ "/queues/tx-" + str(i) + "/xps_cpus"
			subprocess.call(ethtool_str, shell=True)


		cpufreq = cpuFreq()
		print(cpufreq.available_frequencies)
		cpufreq.set_governors("userspace")

		for core in range(self.env.max_core):
			freq = self.env.l_freq[0]
			cpufreq.set_frequencies(freq, core)

		#file desciptor set
		fd_alloc_T = os.open("/sys/fs/cgroup/cpuset/"+str(self.env.lc_name)+"/cpuset.cpus", os.O_WRONLY)
		self.l_fd_alloc_T.append(fd_alloc_T)


		for core in range(self.env.max_core):
			fd_alloc_P = os.open("/sys/class/net/" + str(self.env.net_name) + "/queues/tx-" + str(core) + "/xps_cpus", os.O_WRONLY)
			fd_alloc_freq = os.open("/sys/devices/system/cpu/cpu"+str(core)+"/cpufreq/scaling_setspeed", os.O_WRONLY)
			self.l_fd_alloc_P.append(fd_alloc_P)
			self.l_fd_alloc_freq.append(fd_alloc_freq)

	def close_fd(self):
		os.close(self.l_fd_alloc_T[0])
		os.close(self.l_fd_alloc_be[0])
		os.close(self.l_fd_freezer_be[0])

		for core in range(self.env.max_core):
			os.close(self.l_fd_alloc_P[core])
			os.close(self.l_fd_alloc_freq[core])

	def init_be(self):
		be_tids_list = list()
		self.execute_be()
		time.sleep(3)
		grep_str="ps -eLF | grep " + self.env.be_name  + "|awk '{print $4}' | awk '{if (NR!=1) {print}}'"
		be_tids_str = subprocess.check_output (grep_str, shell=True)
		be_tids_str = be_tids_str.split()


		for tid in be_tids_str:
			try:
				be_tids_list.append(int(tid))
			except:
				break

		#for be
		cmd="cgcreate -g cpuset:"+ str(self.env.be_name)
		print(cmd)
		subprocess.call(cmd, shell=True)
		subprocess.call("echo "+"0-"+str(self.env.max_core)+"> " + "/sys/fs/cgroup/cpuset/" +
						str(self.env.be_name)+"/cpuset.cpus", shell=True)
		subprocess.call("echo "+"0 > "+"/sys/fs/cgroup/cpuset/" +
						str(self.env.be_name)+"/cpuset.mems", shell=True)
		for tid in be_tids_list:
			subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuset/" +
							str(self.env.be_name)+"/tasks", shell=True)

		cmd = "cgcreate -g cpuacct:" + str(self.env.be_name)
		print(cmd)
		subprocess.call(cmd, shell=True)
		for tid in be_tids_list:
			subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuacct/" +
							str(self.env.be_name)+"/tasks", shell=True)

		cmd = "cgcreate -g freezer:" + str(self.env.be_name)
		print(cmd)
		subprocess.call(cmd, shell=True)
		for tid in be_tids_list:
			subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/freezer/" +
							str(self.env.be_name)+"/tasks", shell=True)

		fd_alloc_be = os.open("/sys/fs/cgroup/cpuset/"+str(self.env.be_name)+"/cpuset.cpus", os.O_WRONLY)
		self.l_fd_alloc_be.append(fd_alloc_be)

		fd_freezer_be = os.open("/sys/fs/cgroup/freezer/"+str(self.env.be_name)+"/freezer.state", os.O_WRONLY)
		self.l_fd_freezer_be.append(fd_freezer_be)

        def measure_IPS(self, target_core):
                temp = subprocess.run("./perf_clite.sh " + str(target_core-1), shell=True, stdout=subprocess.PIPE)
                temp = str(temp.stdout)
                return float(temp.split("instructions")[0].split("b'")[1].strip().replace(',',''))/self.env.be_max_ips

	def start_be(self):
		fd = self.l_fd_freezer_be[0]
		os.write(fd,'THAWED'.encode())
		self.is_be_running = True
		return

	def stop_be(self):
		fd = self.l_fd_freezer_be[0]
		os.write(fd,'FROZEN'.encode())
		self.is_be_running = False
		return

	def execute_be(self):
		#TODO
		cmd = self.env.parsec_path +" -a run -p " + self.env.be_name + " -i native -n " + str(self.env.max_core) +" &"
		os.system(cmd)

		return

	def kill_be(self):
		cmd = 'pkill ' + str(self.env.be_name)
		os.system(cmd)

