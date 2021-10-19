import actions
import time
import math
from cpufreq import cpuFreq
#import numpy as np
import random

# Actions
CORE = 0
FREQ = 1

# Direction
UP = 0
DOWN = 1


class Parties:
    def __init__(self, env, actions):
        self.env = env
        self.actions = actions

        self.action = [0, 0] # [action, direction]
        self.core = 0 # the number of cores
        self.freq = 0 # index of env.l_freq
        self.freq_max_idx = 0 # max index of env.l_freq
        
        self.period = 0.1 # 100 ms

        ###online profile###
        self.prev_latency = 10000000000
        self.curr_latency = 10000000000

        #self.debug = False
        self.debug = True



    def run(self):
        itr = 1
        #get usage
        cpufreq = cpuFreq()
        self.freq_max_idx = len(self.env.l_freq) - 1
        self.core = self.env.max_core

        self.action = [random.randrange(0,2), random.randrange(0,2)]

        self.env.update_time()
        while True:
            if self.debug:
                print("#############itr: ", itr,"##################")
            self.online_profile()

            slack = (self.env.slo - self.curr_latency) / self.env.slo
            if slack < 0.05:
                if self.debug:
                    print("UPSIZE!")
                self.upsize()
            elif slack > 0.2:
                if self.debug:
                    print("DOWNSIZE!")
                self.downsize()
            else:
                if self.debug:
                    print("Do Nothing!")
            itr += 1


    def online_profile(self):
        time.sleep(self.period)
        #update time
        self.env.update_time()

        self.prev_latency = self.curr_latency
        self.curr_latency = self.env.get_latency()
        return

    def downsize(self):
        if self.action[1] != DOWN:
            self.action = [random.randrange(0,2), DOWN]
        
        self.take_action(action=self.action[0], direction=self.action[1])

        self.online_profile()
        slack = (self.env.slo - self.curr_latency) / self.env.slo
        if slack < 0.05:
            self.take_action(action=self.action[0], direction=UP)
            self.action[0] = not self.action[0]

        return

    def upsize(self):
        if self.action[1] != UP:
            self.action = [random.randrange(0,2), UP]

        self.take_action(action=self.action[0], direction=self.action[1])

        self.online_profile()
        if self.curr_latency > self.prev_latency:
            self.action[0] = not self.action[0]
        return
    
    def take_action(self, action, direction):
        if action == CORE:
            if self.debug:
                print("action: CORE")
            if direction == UP:
                if self.debug:
                    print("direction: UP")
                self.core = self.core + 1
                if self.core > self.env.max_core:
                    self.core = self.env.max_core
                    self.action[0] = not self.action[0]
            else:
                if self.debug:
                    print("direction: DOWN")
                self.core = self.core - 1
                if self.core < 1:
                    self.core = 1
                    self.action[0] = not self.action[0]

        if action == FREQ:
            if self.debug:
                print("action: FREQ")
            if direction == UP:
                if self.debug:
                    print("direction: UP")
                self.freq = self.freq - 1
                if self.freq < 0:
                    self.freq = 0
                    self.action[0] = not self.action[0]
            else:
                if self.debug:
                    print("direction: DOWN")
                self.freq = self.freq + 1
                if self.freq > self.freq_max_idx:
                    self.freq = self.freq_max_idx
                    self.action[0] = not self.action[0]

        self.actions.alloc_T(target_core=self.core)


        
        for core in range(self.env.max_core):
            if core < self.core:
                if self.debug:
                    print("target core", core, self.env.l_freq[self.freq])
                self.actions.change_freq_to(freq=self.env.l_freq[self.freq], core=core)
            else:
                if self.debug:
                    print("else core", core, self.env.l_freq[self.freq_max_idx])
                self.actions.change_freq_to(freq=self.env.l_freq[self.freq_max_idx], core=core)


