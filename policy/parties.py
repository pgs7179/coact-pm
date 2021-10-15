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
        
        self.period = 0.5 # 500 ms

        ###online profile###
        self.prev_latency = 10000000000
        self.curr_latency = 10000000000

        #self.debug = False
        self.debug = True


    def run(self):
        #get usage
        itr = 1
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
                self.upsize()
            elif slack > 0.2:
                self.downsize()

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
            if direction == UP:
                self.core = self.core + 1
                if self.core > self.env.max_core:
                    self.core = self.env.max_core
            else:
                self.core = self.core - 1
                if self.core < 0:
                    self.core = 0

        if action == FREQ:
            if direction == UP:
                self.freq = self.freq - 1
                if self.freq < 0:
                    self.freq = 0
            else:
                self.freq = self.freq + 1
                if self.core > self.freq_max_idx:
                    self.core = self.freq_max_idx
        self.actions.alloc_T(target_core=self.core)
        
        for core in range(self.env.max_core):
            if core < self.core:
                self.actions.change_freq_to(freq=self.env.l_freq[self.freq], core=core)
            else:
                self.actions.change_freq_to(freq=self.env.l_freq[self.freq_max_idx], core=core)


