#import numpy as np
#import matplotlib.pyplot as plt
import sys
#from time import sleep, strftime

#sys.path.append("/home/caslab/coact-pm")
sys.path.append("/home/caslab/Downloads/coact-pm-default")

from env.env import Environment
from policy.clite import Clite
from actions import Action

#import time
#from skopt import gp_minimize
#from scipy.stats.mstats import gmean


if __name__=="__main__":
	# environment for getting states and peforming actions
	env = Environment()
	actions = Action(env)

	agent = Clite(env,actions)
	try: 
		agent.run()
	except KeyboardInterrupt:
		actions.close_fd()
		sys.exit(0)


