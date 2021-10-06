import actions
import time
from multiprocessing import Process, Queue
import socket
from bcc import BPF
from time import sleep, strftime
import sys,os
import struct

class Environment():
	def __init__(self):

		#cpu engy msr addr
		self.msr_addr = "1553"

		#config
		self.window_size = 21
		self.period = 0.1  # s
		self.server_ip = "10.150.21.207"
		self.server_port = 9999
		self.app_name = "memcached"
		#self.app_name = "nginx"
		self.net_name = "enp59s0f0"

		#time
		self.l_time = [0]

		#power
		self.max_power = 1000 * 1000
		self.min_power = 6 * 100 * 1000

		#latency
		self.slo = 1.5

		#cores
		self.max_core = 8
		self.core_T = self.max_core
		self.core_P = self.max_core

		#freq
		self.l_freq = [3500000, 3300000, 3200000, 3000000, 2900000, \
						2700000, 2600000, 2400000, 2300000, 2100000, \
						2000000, 1800000, 1700000, 1500000, 1400000, 1200000] 
		#self.l_freq = [3500000, 2900000, 2300000, 1700000, 1200000] 

		self.l_core_freq = [self.l_freq[0]] * self.max_core
		self.l_core_freq_index = [0] * self.max_core

		#stat list
		# start latency collection daemon periodically
		self.latency_queue = Queue(maxsize=self.window_size)
		self.latency_collector = Process(target=self.__latency_collect_daemon,
										args=(self.latency_queue,))
		self.latency_collector.deamon = True
		self.latency_collector.start()

		self.l_engy = list()
		self.l_accu_app_usage = list()
		self.ll_accu_app_usage = list()
		self.l_accu_pkt_usage = list()

		actions.init_action(self.app_name, self.net_name)

	def __latency_collect_daemon(self,latency_queue):
		server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)        
		server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		print("ip: " + str(self.server_ip) + " port: " + str(self.server_port))
		server_socket.bind((self.server_ip, self.server_port))
		server_socket.listen()
		client_socket, addr = server_socket.accept()
		print('Connected by', addr)

		while True:
			#get latency
			data = client_socket.recv(1024)
			data = str(data.decode())
			data = data.split(':')
			data = ' '.join(data).split()

			#put latency to queue
			for latency in data:
				latency_queue.put(float(latency))

		client_socket.close()
		server_socket.close()
		sys.exit(0)
		
	def get_latency(self):
		avg_latency = 0.0
		accu_latency = 0.0
		count = 0
		while self.latency_queue.qsize():
			accu_latency += self.latency_queue.get()
			count += 1

		if count > 0: 
			avg_latency = accu_latency / count

		print("p99: ", avg_latency)
		return avg_latency
	
	def get_power(self):
		norm_power = 0
		diff_time = 0
		diff_engy = 0

		while True:
			cur_engy = self.__read_msr(self.msr_addr)
			if len(self.l_engy) == 0 or cur_engy != self.l_engy[-1]:
				break
		
		self.l_engy.append(cur_engy)

		if len(self.l_engy) > self.window_size:
			self.l_engy.pop(0)	

		if len(self.l_engy)  >  1:
			diff_engy = self.l_engy[-1] - self.l_engy[-2] 
			diff_time = self.l_time[-1] - self.l_time[-2]
			if diff_time != 0:
				power = diff_engy / diff_time  
				norm_power = (power - self.min_power) \
					/ (self.max_power - self.min_power)
		
		print("power: ", norm_power)
		return norm_power

	"""
	def __get_app_usage(self):
		app_usage = 0
		accu_app_usage = 0

		#get accumulated app usage from cgroup
		f = open("/sys/fs/cgroup/cpuacct/" +
					self.app_name+"/cpuacct.usage")
		for line in f.readlines():
			accu_app_usage = float(line)
		f.close()
		self.l_accu_app_usage.append(accu_app_usage)

		if len(self.l_accu_app_usage) > self.window_size:
			self.l_accu_app_usage.pop(0)	
		
		if len(self.l_accu_app_usage) < 2:
			return 0

		diff_app_usage = self.l_accu_app_usage[-1] - self.l_accu_app_usage[-2] #ns
		diff_time = self.l_time[-1] - self.l_time[-2]
		cur_app_usage = diff_app_usage / diff_time / 1000 / 1000 / 1000 

		return cur_app_usage
	"""

	def update_app_usage_per_core(self,step=1):
		l_app_usage = list()
		l_accu_app_usage = list()

		#get accumulated app usage from cgroup
		f = open("/sys/fs/cgroup/cpuacct/" +
					self.app_name+"/cpuacct.usage_percpu")
		for line in f.readlines():
			l_temp = line.split(" ")
			for app_usage in l_temp[:-1]:
				l_accu_app_usage.append(int(app_usage))
		f.close()

		self.ll_accu_app_usage.append(l_accu_app_usage)

		if len(self.ll_accu_app_usage) > self.window_size:
			self.ll_accu_app_usage.pop(0)	
	
	def get_var_app_usage_per_core(self, l_app_usage):
		l_var_app_usage = list()
		avg_usage = float(sum(l_app_usage)) / self.core_T
		for core in range(self.max_core):
			if avg_usage == 0:
				var_app_usage = 0
			else:
				var_app_usage = float(l_app_usage[core]) / avg_usage

			l_var_app_usage.append(var_app_usage)
		
		return l_var_app_usage

	def get_app_usage_per_core(self, step=1):
		l_app_usage = list()
		l_accu_app_usage = list()

		if len(self.ll_accu_app_usage) < 2:
			return [0] * self.max_core

		diff_time = self.l_time[-1] - self.l_time[-(1+step)]
		for cpu in range(self.max_core):
			diff_app_usage = self.ll_accu_app_usage[-1][cpu] - \
				self.ll_accu_app_usage[-(1+step)][cpu]  # ns
			cur_app_usage = round(diff_app_usage /
			                      diff_time / 1000 / 1000 / 1000, 4)
			l_app_usage.append(cur_app_usage)

		return l_app_usage


	def get_app_usage_per_core_with_basefreq(self,step=1,base_freq=3600000):
		l_app_usage = list()
		l_accu_app_usage = list()

		if len(self.ll_accu_app_usage) < 2:
			return [0] * self.max_core

		diff_time = self.l_time[-1] - self.l_time[-(1+step)]
		for cpu in range(self.max_core):
			diff_app_usage = self.ll_accu_app_usage[-1][cpu] - self.ll_accu_app_usage[-(1+step)][cpu] #ns
			freq_times = self.l_core_freq[cpu] / base_freq
			cur_app_usage = round(freq_times * diff_app_usage / diff_time / 1000 / 1000 / 1000, 4) 
			l_app_usage.append(cur_app_usage)

		return l_app_usage
	

	def __read_msr(self, msr, cpu = 0):
		f = os.open('/dev/cpu/%d/msr' % (cpu,), os.O_RDONLY)
		os.lseek(f, int(msr), os.SEEK_SET)
		val = struct.unpack('Q', os.read(f, 8))[0]
		os.close(f)
		return val

	def update_time(self):
		if len(self.l_time) > self.window_size:
			self.l_time.pop(0)

		self.l_time.append(time.time()) #secs
		return

	