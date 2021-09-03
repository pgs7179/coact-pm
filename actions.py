import subprocess
from cpufreq import cpuFreq

def alloc_T(cores,app_name):
	if cores == 1:
		subprocess.call("echo "+"0"+ " > " + "/sys/fs/cgroup/cpuset/"+str(app_name)+"/cpuset.cpus",shell=True)
	else:
		subprocess.call("echo "+"0-"+str(cores - 1)+"> " + "/sys/fs/cgroup/cpuset/"+str(app_name)+"/cpuset.cpus",shell=True)

	return

def alloc_P(cores,net_name):
	ethtool_str="ethtool -X " + str(net_name) + " equal " + str(cores)
	subprocess.call(ethtool_str,shell=True)
	for i in range(8):
		if i < cores:
			ethtool_str="echo ff > /sys/class/net/" + str(net_name) \
				+ "/queues/tx-" + str(i) + "/xps_cpus"
		else:
			ethtool_str="echo 00 > /sys/class/net/" + str(net_name) \
				+ "/queues/tx-" + str(i) + "/xps_cpus"
		subprocess.call(ethtool_str,shell=True)

	return

def change_freq_to(freq,core):
	cpufreq = cpuFreq()
	cpufreq.set_frequencies(freq,core)
	
	return

def init_action(app_name,net_name):
	app_tids_list = list()
	if app_name == "memcached":
		grep_str="ps -eLF | grep " + app_name  + "|awk '{print $4}' | awk '{if (NR!=1) {print}}'"
	if app_name == "nginx":
		grep_str="ps -eLF | grep -e" + "\"" + app_name + ": worker"+ "\"" + " -e " + "polkitd " + "-e dbus"  + "|awk '{print $4}'"

	app_tids_str = subprocess.check_output (grep_str, shell=True)
	app_tids_str = app_tids_str.split()

	for tid in app_tids_str:
		try:
			app_tids_list.append(int(tid))
		except:
			break
	print("tid list: "+str(app_tids_list))


	#cgroup init
	cmd="cgcreate -g cpuset:"+ str(app_name)
	print(cmd)
	subprocess.call(cmd, shell=True)
	subprocess.call("echo "+"0-7"+"> " + "/sys/fs/cgroup/cpuset/" +
					str(app_name)+"/cpuset.cpus", shell=True)
	subprocess.call("echo "+"0 > "+"/sys/fs/cgroup/cpuset/" +
					str(app_name)+"/cpuset.mems", shell=True)
	for tid in app_tids_list:
		subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuset/" +
						str(app_name)+"/tasks", shell=True)

	cmd = "cgcreate -g cpuacct:" + str(app_name)
	print(cmd)
	subprocess.call(cmd, shell=True)
	for tid in app_tids_list:
		subprocess.call("echo " + str(tid) + " > /sys/fs/cgroup/cpuacct/" +
						str(app_name)+"/tasks", shell=True)

	ethtool_str = "ethtool -X " + str(net_name) + " equal " + "8"
	subprocess.call(ethtool_str, shell=True)
	for i in range(8):
		ethtool_str = "echo ff > /sys/class/net/" + str(net_name) \
			+ "/queues/tx-" + str(i) + "/xps_cpus"
		subprocess.call(ethtool_str, shell=True)


	cpufreq = cpuFreq()
	print(cpufreq.available_frequencies)
	cpufreq.set_governors("userspace")

	for core in range(8):
		freq = 3500000
		cpufreq.set_frequencies(freq, core)
