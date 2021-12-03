import actions
import time
import math
#from cpufreq import cpuFreq
#import numpy as np
import random
from skopt import gp_minimize
from scipy.stats.mstats import gmean


class Clite:
    def __init__(self, env, actions):
        self.env = env
        self.actions = actions

        self.core = 0 # the number of cores
        
        #self.period = 0.1 # 100 ms
        self.period = 0.05 # 50 ms

        ###online profile###
        self.prev_latency = 10000000000
        self.curr_latency = 10000000000

        #self.debug = False
        self.debug = True

        self.actions.init_be()

    def online_profile(self):
        time.sleep(self.period)
        #update time
        self.env.update_time()

        self.prev_latency = self.curr_latency
        self.curr_latency = self.env.get_latency()
        return

    def periodic_controller(self, input_config):
        #print("##########################################config" + str(input_config[0]))
        curr_config = input_config[0]

        # change core allocation by configuration of Bayesian Optimization
        self.actions.alloc_T(target_core=curr_config)
        self.actions.alloc_be(self.env.max_core - curr_config)

        self.online_profile()

        if self.env.slo <= self.curr_latency:
            return -1.0 * (0.5 * (self.env.slo/self.curr_latency))
        else:
            # return 0.5 + 0.5*geo.mean of normalized IPS of BE applications
            return -1.0 * (0.5 + 0.5*self.actions.measure_IPS(curr_config))

    def run(self):
        itr = 1
        #get usage
        self.core = self.env.max_core
        
        self.env.update_time()
        
        input_list = [(1, self.env.max_core)]
        time.sleep(10) # delayed execution of Bayesian Optimization for initalization of BE app.
        res = gp_minimize(self.periodic_controller, input_list, n_calls=20, acq_func='EI', random_state=123) # run Bayesian Optimization
        print(res.x) # optimal configuration by Bayesian Optimization
        self.periodic_controller(res.x) # set optimal configuration

