#import numpy as np
#import matplotlib.pyplot as plt
import sys
#from time import sleep, strftime

sys.path.append("/home/caslab/coact-pm")

from env.env import Environment
from policy.coactpm import CoactPM

if __name__=="__main__":
	# environment for getting states and peforming actions
	env = Environment()
	agent = CoactPM(env)
	agent.run()


