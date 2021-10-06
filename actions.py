import subprocess
from cpufreq import cpuFreq


class Action:
	def __init__(self, env):
		self.fd_alloc_T = None
		self.l_fd_alloc_P = list()
		self.l_fd_alloc_freq = list()
		self.env = env
		self.init_action()

	def alloc_T(self, target_core):
		f = self.fd_alloc_T
		if target_core == 1:
			f.write("0")
		else:
			f.write("0-"+str(target_core-1))

		return

	def alloc_P(self, target_core):
		#rss
		ethtool_str = "ethtool -X " + str(self.env.net_name) + " equal " + str(target_core)
		subprocess.call(ethtool_str,shell=True)
		for core in range(self.env.max_core):
			f = self.l_fd_alloc_P[core]
			if core < target_core:
				f.write("ff")
			else:
	 			f.write("00")

		return

	def change_freq_to(self, freq, core):
		f = self.l_fd_alloc_freq[core]
		f.write(str(freq))

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
		self.fd_alloc_T = open("/sys/fs/cgroup/cpuset/"+str(self.env.app_name)+"/cpuset.cpus", "w")
		for core in range(self.env.max_core):
			fd_alloc_P = open("/sys/class/net/" + str(self.env.net_name) + "/queues/tx-" + str(core) + "/xps_cpus", "w")
			fd_alloc_freq = open("/sys/devices/system/cpu/cpu"+str(core)+"/cpufreq/scaling_setspeed", "w")

			self.l_fd_alloc_P.append(fd_alloc_P)
			self.l_fd_alloc_freq.append(fd_alloc_freq)
