import actions
import time
import math
from cpufreq import cpuFreq

from env.regression import Linear_Regression
#import numpy as np


class CoactPM:
    def __init__(self, env, actions):
        self.env = env
        self.actions = actions
        #memcached
        #self.threshold = 0.45
        #nginx
        self.threshold = 0.15
        self.down_step = 0
        self.margin = 0.00
        self.freq_margin = 0.00

        self.l_long_app_usage = list()
        self.l_short_app_usage = list()
        self.l_var_usage = list()
        self.l_pred_app_usage = [0] * self.env.max_core

        self.period = env.period
        self.core_alloc_step = 4
        self.is_alloc = False
        #self.base_freq=self.env.l_freq[-1]
        self.base_freq=self.env.l_freq[7]
        self.dec_counter = 0

        ###online profile###
        self.profile_size = 20
        self.l_profile = [0.0] * self.profile_size
        self.ll_accu_latency = [[0.0]] * self.profile_size

        #self.debug = False
        self.debug = True

        self.mode = "lc-only"
        #self.mode = "co-loc"

        self.opt = True
        #self.opt = False
        if self.env.lc_name == "memcached":
            #R2 = 0.7178174431617681
            self.core_coef = 0.05017675
            self.freq_coef = 0.0913457 / (10 ** 6) 
            self.intercept = 0.01835323

        if self.env.lc_name == "nginx":
            #R2 = 0.7605843515938565
            self.core_coef = 0.05424087
            self.freq_coef = 0.11612534 / (10 ** 6) 
            self.intercept = -0.11151826
        
        if self.env.lc_name == "xapian":
            #R2 = 0.6699626573006099 
            self.core_coef = 0.07149764
            self.freq_coef = 0.14374043 / (10 ** 6) 
            self.intercept = 0.05195069
        
        if self.env.lc_name == "mysql":
            #R2 = 0.7930371570703644
            self.core_coef = 0.06430502 
            self.freq_coef = 0.13744261 / (10 ** 6) 
            self.intercept = -0.19378322
        



        if self.mode == "co-loc":
            self.actions.init_be()
            self.base_freq=self.env.l_freq[0]
        

        self.lr = Linear_Regression()

    def run(self):
        #get usage
        itr = 1
        cpufreq = cpuFreq()
        core_T, core_P = self.env.max_core, self.env.max_core

        self.env.update_time()
        while True:
            self.env.update_app_usage_per_core()
            self.env.update_rx_pkts()

            if self.debug:
                print("#############itr: ", itr,"##################")
            #### core alloc 
            if itr % self.core_alloc_step == 0:
                self.l_long_app_usage = self.env.get_app_usage_per_core(step=self.core_alloc_step - 1)
                self.l_long_app_usage = self.convert_usage(l_app_usage=self.l_long_app_usage)
                #self.l_var_usage = self.env.get_var_app_usage_per_core(l_app_usage=self.l_app_usage)
                if self.debug:
                    print("long_usage: ", self.l_long_app_usage[:self.env.max_core]) 
                    print("be core: ", self.env.be_core)
                core_T, core_P = self.manage_core_T()
                #core_T, core_P = self.manage_core_P(core_T, core_P)

                self.alloc_core(core_T, core_P)
                if core_T > self.env.max_core:
                    core_T = self.env.max_core
                    for core in range(core_T):
                        self.actions.change_freq_to(freq=self.env.l_freq[0], core=core)

                if core_T != self.env.core_T:
                    for core in range(core_T):
                        self.actions.change_freq_to(freq=self.base_freq, core=core)
                
                if self.mode == "co-loc":
                    self.actions.alloc_be(self.env.max_core - core_T)


                if self.debug:
                    print("core T: ", self.env.core_T, " core P: ", self.env.core_P)
            else:
                self.l_short_app_usage = self.env.get_app_usage_per_core()
                self.manage_freq()
                if self.debug:
                    print("short_usage: ", self.l_short_app_usage[:self.env.max_core]) 
                    print("freq: ",self.env.l_core_freq)

            time.sleep(self.period)
            #update time
            self.env.update_time()
            self.online_profile()
            itr += 1


    def alloc_core(self, core_T, core_P):
        if core_T > self.env.max_core:
            core_T = self.env.max_core

        if core_P > self.env.max_core:
            core_P = self.env.max_core

        if self.env.core_T != core_T:
            self.env.core_T = core_T
            self.actions.alloc_T(target_core=core_T)

        if self.env.core_P != core_P:
            self.env.core_P = core_P
            self.actions.alloc_P(target_core=core_P)

    def manage_core_T(self):
        ########core_T control##########
        total_app_usage = 0
        target_core = 0

        for app_usage in self.l_long_app_usage:
            #threshold violation
            total_app_usage += app_usage
        
        if self.opt == False:        
            target_core = math.ceil((1 + self.margin) * total_app_usage / self.threshold )
        else:
            max_usage = max(self.l_long_app_usage)
            max_core_index = self.l_long_app_usage.index(max_usage)
            cur_freq = self.env.l_core_freq[max_core_index]
            slack_ratio = max_usage / self.threshold
            req_core = (1/self.core_coef) \
                        * (slack_ratio*(self.freq_coef*cur_freq \
                            + self.core_coef*self.env.core_T
                            + self.intercept)\
                        - self.freq_coef*self.base_freq - self.intercept)
            target_core = math.ceil(req_core)

        if target_core < 1:
            target_core = 1

        #dec
        if self.env.core_T > target_core:
            if self.dec_counter > 0:
                self.dec_counter -= 1
                core_T,core_P = self.env.core_T,self.env.core_P
            else:
                core_T,core_P = target_core,target_core
        else:
            self.dec_counter = self.down_step
            core_T, core_P = target_core, target_core 
        
        return core_T, core_P

    def manage_core_P(self, core_T, core_P):
                        
        ###########core_P control##########
        l_app_usage_TP = self.l_long_app_usage[:self.env.core_P]
        l_app_usage_T = self.l_long_app_usage[self.env.core_P:self.env.core_T]
        """
        total_usage_TP = sum(l_app_usage_TP) 
        total_usage_T = sum(l_app_usage_T) 

        usage_TP = sum(l_app_usage_TP) / self.env.core_P
        usage_T = usage_TP
        if self.env.core_P != self.env.core_T:
            usage_T = sum(l_app_usage_T) / (self.env.core_T - self.env.core_P)
        usage_P = usage_TP - usage_T
        total_usage_P = usage_P * self.env.core_P

        #unknown usage_P
        if usage_T == usage_TP:
            if (1 + self.margin) * usage_TP < self.threshold and core_P != 1:
                core_P -= 1
        #known usage_P            
        else:
            slack = self.threshold - (1 + self.margin) * usage_T
            if slack > 0 and total_usage_P > 0:
                core_P = int(total_usage_P / slack) + 1
                if core_P > core_T:
                    core_P = core_T

            else:
                core_P = core_T
        """

        l_app_usage_TP = self.l_long_app_usage[:self.env.core_P]
        usage_TP = sum(l_app_usage_TP) / self.env.core_P

        if self.opt == False:        
            if (1 + self.margin) * usage_TP < self.threshold and core_P != 1:
                core_P -= 1
        else:
            #TODO
            core_P = core_P



        return core_T, core_P

    def manage_freq(self):
        ##########freq control############
        req_freq = 0
        for core in range(self.env.max_core):
            next_freq = self.env.l_freq[0]
            next_freq_index = 0
            slack_ratio = 0

            if self.is_alloc == False:
                core_usage = (1 + self.freq_margin) * self.l_short_app_usage[core]

                # slack base manage
                if core_usage == 0:
                    slack_ratio = 0
                else:
                    slack_ratio = (core_usage / self.threshold) 
                cur_freq = self.env.l_core_freq[core]
                
                if self.opt == False:
                    req_freq = cur_freq * slack_ratio * self.freq_coef
                else:
                    req_freq = (1/self.freq_coef) \
                                * (slack_ratio*(self.freq_coef*self.base_freq \
                                    + self.core_coef*self.env.core_T
                                    + self.intercept)\
                                - self.core_coef*self.env.core_T - self.intercept)


                reversed_l_freq = self.env.l_freq[::-1]
                for freq in reversed_l_freq:
                    if freq > req_freq: 
                        next_freq = freq
                        self.env.l_core_freq[core] = next_freq
                        break

                '''
                if core_usage < self.threshold:
                    next_freq_index = self.env.l_core_freq_index[core] + self.freq_step
                    if next_freq_index >= len(self.env.l_freq):
                        next_freq_index = len(self.env.l_freq) - 1
                    next_freq = self.env.l_freq[next_freq_index]

                '''

            self.env.l_core_freq[core] = next_freq
            self.env.l_core_freq_index[core] = next_freq_index

            self.actions.change_freq_to(freq=next_freq,core=core)

    def geo_mean(self,l_input):
        result = math.exp(math.fsum(math.log(x) for x in l_input) / len(l_input)) 
        return result

    def online_profile(self):
        cur_latency = self.env.get_latency()
        max_usage = max(self.env.get_app_usage_per_core())
        max_index = self.env.get_app_usage_per_core().index(max_usage)
        load_index = int((max_usage * 100 + 1)/ self.profile_size) 
        rps = self.env.get_rps() 

        
        if load_index > self.profile_size:
            load_index = self.profile_size
        
        if cur_latency == 0:
            return


        #print("max_usage: ", max_usage)
        #print("load index: ", load_index)
        l_accu_latency = self.ll_accu_latency[load_index] 
        l_accu_latency.append(cur_latency)
        if len(l_accu_latency) > self.env.window_size:
            l_accu_latency.pop(0)

        self.l_profile[load_index] = sum(l_accu_latency) / len(l_accu_latency)
        #self.l_profile[load_index] = self.geo_mean(l_input=l_accu_latency)
        
        target_index=0
        for i in range(self.profile_size):
            if self.l_profile[i] < self.env.slo:
                target_index += 1
            else:
                break
        
        self.threshold = float(target_index + 1) / self.profile_size 
        if self.debug:
            print("cur threshold: ", self.threshold)
            #print(self.l_profile)

        #linear regression
        if max_usage == 0 or rps < 100:
            return

        data =  [self.env.core_T, self.env.core_P, self.env.l_core_freq[max_index]/ (10 ** 6) , rps, 1/max_usage, 0]
        self.lr.append_data(data)
 

    def convert_usage(self,l_app_usage):
        l_converted_app_usage = list()
        print("l_app_usage: ",l_app_usage)
        for cpu in range(self.env.max_core):
            usage = 0
            if self.opt == False:
                usage = l_app_usage[cpu] * self.env.l_core_freq[cpu] / self.base_freq
            else:
                usage = l_app_usage[cpu] \
                 * (self.freq_coef*self.env.l_core_freq[cpu] + self.core_coef*self.env.core_T + self.intercept) \
                     / (self.freq_coef*self.base_freq + self.core_coef*self.env.core_T + self.intercept) 
            l_converted_app_usage.append(usage)
        
        return l_converted_app_usage

