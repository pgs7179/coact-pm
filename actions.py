import subprocess
from cpufreq import cpuFreq
import sys,os


class Action:
	def __init__(self, env):
		self.l_fd_alloc_T = list()
		self.l_fd_alloc_P = list()
		self.l_fd_alloc_freq = list()
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

	def change_freq_to(self, freq, core):
		fd = self.l_fd_alloc_freq[core]
		os.write(fd,str(freq).encode())

		return

	def init_action(self):
		app_tids_list = list()
		if self.env.app_name == "memcached":
			grep_str="ps -eLF | grep " + self.env.app_name  + "|awk '{print $4}' | awk '{if (NR!=1) {print}}'"
		if self.env.app_name == "nginx":
			grep_str="ps -eLF | grep -e" + "\"" + self.env.app_name + ": worker"+ "\"" + " -e " + "polkitd " + "-e dbus"  + "|awk '{print $4}'"

		app_tids_str = subprocess.check_output (grep_str, shell=True)
		app_tids_str = app_tids_str.split()

		for tid in app_tids_str:
			try:
				app_tids_list.append(int(tid))
			except:
				break
		print("tid list: "+str(app_tids_list))


		#cgroup init
		cmd="cgcreate -g cpuset:"+ str(self.env.app_name)
		print(cmd)
		subprocess.call(cmd, shell=True)
		subprocess.call("echo "+"0-"+str(self.env.max_core)+"> " + "/sys/fs/cgroup/cpuset/" +
						str(self.env.app_name)+"/cpuset.cpus", shell=True)
		subprocess.call("echo "+"0 > "+"/sys/fs/cgroup/cpuset/" +
						str(self.env.app_name)+"/cpuset.mems", shell=True)
		for tid in app_tids_list:
			subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuset/" +
							str(self.env.app_name)+"/tasks", shell=True)

		cmd = "cgcreate -g cpuacct:" + str(self.env.app_name)
		print(cmd)
		subprocess.call(cmd, shell=True)
		for tid in app_tids_list:
			subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuacct/" +
							str(self.env.app_name)+"/tasks", shell=True)

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
			freq = 3500000
			cpufreq.set_frequencies(freq, core)

		#file desciptor set
		fd_alloc_T = os.open("/sys/fs/cgroup/cpuset/"+str(self.env.app_name)+"/cpuset.cpus", os.O_WRONLY)
		self.l_fd_alloc_T.append(fd_alloc_T)

		for core in range(self.env.max_core):
			fd_alloc_P = os.open("/sys/class/net/" + str(self.env.net_name) + "/queues/tx-" + str(core) + "/xps_cpus", os.O_WRONLY)
			fd_alloc_freq = os.open("/sys/devices/system/cpu/cpu"+str(core)+"/cpufreq/scaling_setspeed", os.O_WRONLY)
			self.l_fd_alloc_P.append(fd_alloc_P)
			self.l_fd_alloc_freq.append(fd_alloc_freq)

	def close_fd(self):
		os.close(self.l_fd_alloc_T[0])

		for core in range(self.env.max_core):
			os.close(self.l_fd_alloc_P[core])
			os.close(self.l_fd_alloc_freq[core])
