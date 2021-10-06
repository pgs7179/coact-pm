import actions
import time
import math
from cpufreq import cpuFreq


class CoactPM:
    def __init__(self, env):
        self.env = env
        #memcached
        #self.threshold = 0.45
        #nginx
        self.threshold = 0.25
        self.down_step = 4
        self.margin = 0.10
        self.freq_margin = 0.00

        self.l_long_app_usage = list()
        self.l_short_app_usage = list()
        self.l_var_usage = list()
        self.l_pred_app_usage = [0] * self.env.max_core
        self.period = env.period
        self.core_alloc_step = 4
        self.is_alloc = False
        self.base_freq=2400000
        self.dec_counter = 0


    def run(self):
        #get usage
        itr = 1
        cpufreq = cpuFreq()
        core_T, core_P = self.env.max_core, self.env.max_core

        self.env.update_time()
        while True:
            self.env.update_app_usage_per_core()

            print("#############itr: ", itr,"##################")
            #### core alloc 
            if itr % self.core_alloc_step == 0:
                self.l_long_app_usage = self.env.get_app_usage_per_core_with_basefreq(step=self.core_alloc_step - 1,base_freq=self.base_freq)
                #self.l_var_usage = self.env.get_var_app_usage_per_core(l_app_usage=self.l_app_usage)
                print("long_usage: ", self.l_long_app_usage[:self.env.max_core]) 
                print("var_usage: ", self.l_var_usage[:self.env.max_core]) 

                core_T, core_P = self.manage_core_T()
                core_T, core_P = self.manage_core_P(core_T, core_P)

                self.alloc_core(core_T, core_P)
                #print("core T: ", self.env.core_T, " core P: ", self.env.core_P)
            else:
                self.l_short_app_usage = self.env.get_app_usage_per_core()
                self.manage_freq()
                print("short_usage: ", self.l_short_app_usage[:self.env.max_core]) 
                print("freq: ",self.env.l_core_freq)

            time.sleep(self.period)

            #update time
            self.env.update_time()
            itr += 1


    def alloc_core(self, core_T, core_P):
        if core_T > self.env.max_core:
            core_T = self.env.max_core

        if core_P > self.env.max_core:
            core_P = self.env.max_core

        if self.env.core_T != core_T:
            self.env.core_T = core_T
            actions.alloc_T(core_T, self.env.app_name)

        if self.env.core_P != core_P:
            self.env.core_P = core_P
            actions.alloc_P(core_P, self.env.net_name)

    def manage_core_T(self):
        ########core_T control##########
        '''
        app_overusage = 0
        for app_usage in self.l_long_app_usage:
            #threshold violation
            if app_usage > self.threshold:
                app_overusage += app_usage - self.threshold
                
        target_core = self.env.core_T + math.ceil(app_overusage / self.threshold) 
        core_T, core_P = target_core, target_core 
        '''

        total_app_usage = 0
        for app_usage in self.l_long_app_usage:
            #threshold violation
            total_app_usage += app_usage
                
        target_core = math.ceil(total_app_usage / self.threshold * (1 + self.margin))
        if target_core == 0:
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
        '''

        l_app_usage_TP = self.l_long_app_usage[:self.env.core_P]
        usage_TP = sum(l_app_usage_TP) / self.env.core_P
        if (1 + self.margin) * usage_TP < self.threshold and core_P != 1:
            core_P -= 1

        '''
               
        return core_T, core_P

    def manage_freq(self):
        ##########freq control############
        for core in range(self.env.max_core):
            next_freq = self.env.l_freq[0]
            next_freq_index = 0

            if self.is_alloc == False:
                core_usage = (1 + self.freq_margin) * self.l_short_app_usage[core]

                # slack base manage
                if core_usage == 0:
                    slack_ratio = 0
                else:
                    slack_ratio = (core_usage / self.threshold) 
                cur_freq = self.env.l_core_freq[core]
                req_freq = cur_freq * slack_ratio 

                reversed_l_freq = self.env.l_freq[::-1]
                for freq in reversed_l_freq:
                    if freq > req_freq: 
                        next_freq = freq
                        self.env.l_core_freq[core] = next_freq
                        break

                #print("core: ", core, "req_freq: ", req_freq , "next_freq: ", next_freq)
                '''
                if core_usage < self.threshold:
                    next_freq_index = self.env.l_core_freq_index[core] + self.freq_step
                    if next_freq_index >= len(self.env.l_freq):
                        next_freq_index = len(self.env.l_freq) - 1
                    next_freq = self.env.l_freq[next_freq_index]

                '''

            self.env.l_core_freq[core] = next_freq
            self.env.l_core_freq_index[core] = next_freq_index

            actions.change_freq_to(next_freq, core)
    

        