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
        
        self.period = 0.5 # 500 ms

        ###online profile###
        self.prev_latency = 10000000000
        self.curr_latency = 0

        #self.debug = False
        self.debug = True


    def run(self):
        #get usage
        itr = 1
        cpufreq = cpuFreq()

        self.action = [random.randrange(0,2), random.randrange(0,2)]

        self.env.update_time()
        while True:

            if self.debug:
                print("#############itr: ", itr,"##################")



            time.sleep(self.period)
            #update time
            self.env.update_time()
            self.online_profile()

            slack = (self.env.slo - self.curr_latency) / self.env.slo
            if slack < 0.05:
                self.upsize()
            elif slack > 0.2:
                self.downsize()

            itr += 1


    def online_profile(self):
        return

    def downsize(self):
        return

    def upsize(self):
        return

