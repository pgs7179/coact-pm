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
		self.period = 0.05  # s
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

		self.__init_ebpf()
		actions.init_action(self.app_name, self.net_name)

	def get_state(self):
		#TODO
		app_usage = self.__get_app_usage()
		pkt_usage = self.__get_pkt_usage()

		state = {
			'core_T': self.core_T/self.max_core, 
			'core_P': self.core_P/self.max_core, 
			'app_usage': app_usage/self.core_T, 
			'pkt_usage': pkt_usage/self.core_P
		}
		return state
	
	def action(self,action):
		core_T_action = self.core_T
		core_P_action = self.core_P

		if action < 8:
			core_T_action = action + 1

		if action >= 8 and action < 16:
			core_P_action = action -8 + 1


		#if episode == NUM_EPISODES-1:
		print("Update - Actions to take:",
				core_T_action, core_P_action)

		#alloc cores for T
		actions.alloc_T(int(core_T_action),self.app_name)
		#Alloc cores for P
		actions.alloc_P(int(core_P_action),self.net_name)

		self.core_T = int(core_T_action)
		self.core_P = int(core_P_action)

		#sleep during the period
		time.sleep(self.period)
		self.update_time()

	def reset(self):
		state = self.get_state()
		return state
	
	def get_reward(self):
		reward = 0.0
		lat_reward = 0.0
		power_reward = 0.0 

		latency = self.get_latency()

		if latency > self.slo: 
			lat_reward = max(-latency / self.slo, -5)
		else:
			lat_reward = (self.slo - latency) / self.slo
		
		power_reward = ( 1 - self.get_power())
		reward = 0.5 * lat_reward + 0.5 * power_reward
		
		return reward


	def step(self,action):
		action_list = action.tolist()[0]
		max_action = max(action_list)
		max_index = action_list.index(max_action)
		self.action(max_index)
		state = self.get_state()
		reward = self.get_reward()
		done = False

		return state, reward, done


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

	def get_app_usage_per_core(self,step=1):
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

		if len(self.ll_accu_app_usage) < 2:
			return [0] * self.max_core

		diff_time = self.l_time[-1] - self.l_time[-(1+step)]
		for cpu in range(self.max_core):
			diff_app_usage = self.ll_accu_app_usage[-1][cpu] - self.ll_accu_app_usage[-(1+step)][cpu] #ns
			cur_app_usage = round(diff_app_usage / diff_time / 1000 / 1000 / 1000, 4) 
			l_app_usage.append(cur_app_usage)

		return l_app_usage

	def get_app_usage_per_core_with_maxfreq(self,step=1):
		l_app_usage = list()
		l_accu_app_usage = list()

		if len(self.ll_accu_app_usage) < 2:
			return [0] * self.max_core

		diff_time = self.l_time[-1] - self.l_time[-(1+step)]
		for cpu in range(self.max_core):
			diff_app_usage = self.ll_accu_app_usage[-1][cpu] - self.ll_accu_app_usage[-(1+step)][cpu] #ns
			freq_times = self.l_core_freq[cpu] / self.l_freq[0] 
			cur_app_usage = round(freq_times * diff_app_usage / diff_time / 1000 / 1000 / 1000, 4) 
			l_app_usage.append(cur_app_usage)

		return l_app_usage



	def __get_pkt_usage(self):
		pkt_usage = 0
		dist = self.dist
		for k, v in sorted(dist.items(), key=lambda dist: dist[1].value):
			pkt_usage = v.value / self.factor

		self.l_accu_pkt_usage.append(pkt_usage)

		if len(self.l_accu_pkt_usage) > self.window_size:
			self.l_accu_pkt_usage.pop(0)	
		
		if len(self.l_accu_pkt_usage) < 2:
			return 0

		diff_pkt_usage = self.l_accu_pkt_usage[-1] - self.l_accu_pkt_usage[-2] #ns
		diff_time = self.l_time[-1] - self.l_time[-2]
		cur_pkt_usage = diff_pkt_usage / diff_time / 1000 / 1000 / 1000 
		return cur_pkt_usage

	def __get_cpustat(self):

		return cpustat


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

	def __init_ebpf(self):
		############# for ebpf ################

		self.factor = 1
		label = "nsecs"

		# define BPF program
		bpf_text = """
		#include <uapi/linux/ptrace.h>

		typedef struct entry_key {
			u32 pid;
			u32 cpu;
		} entry_key_t;

		typedef struct irq_key {
			u32 vec;
			u64 slot;
		} irq_key_t;

		typedef struct account_val {
			u64 ts;
			u32 vec;
		} account_val_t;

		BPF_HASH(start, entry_key_t, account_val_t);
		BPF_HASH(iptr, u32);
		BPF_HISTOGRAM(dist, irq_key_t);

		TRACEPOINT_PROBE(irq, softirq_entry)
		{
			account_val_t val = {};
			entry_key_t key = {};

			key.pid = bpf_get_current_pid_tgid();
			key.cpu = bpf_get_smp_processor_id();
			val.ts = bpf_ktime_get_ns();
			val.vec = args->vec;

			if (val.vec != 3)
				return 0;

			start.update(&key, &val);

			return 0;
		}

		TRACEPOINT_PROBE(irq, softirq_exit)
		{
			u64 delta;
			u32 vec;
			account_val_t *valp;
			irq_key_t key = {0};
			entry_key_t entry_key = {};

			entry_key.pid = bpf_get_current_pid_tgid();
			entry_key.cpu = bpf_get_smp_processor_id();

			// fetch timestamp and calculate delta
			valp = start.lookup(&entry_key);
			if (valp == 0) {
				return 0;   // missed start
			}
			delta = bpf_ktime_get_ns() - valp->ts;
			vec = valp->vec;

			if (vec != 3)
				return 0;

			// store as sum or histogram
			STORE

			start.delete(&entry_key);
			return 0;
		}
		"""

		# code substitutions
		bpf_text = bpf_text.replace('STORE',
			'key.vec = valp->vec; ' +
			'dist.atomic_increment(key, delta);' 
			)

		# load BPF program
		b = BPF(text=bpf_text)

		# output
		self.dist = b.get_table("dist")
