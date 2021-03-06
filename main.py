#import numpy as np
#import matplotlib.pyplot as plt
import sys
#from time import sleep, strftime

sys.path.append("/home/caslab/coact-pm")

from env.env import Environment
from policy.coactpm import CoactPM
from actions import Action

if __name__=="__main__":
	# environment for getting states and peforming actions
	env = Environment()
	actions = Action(env)
	agent = CoactPM(env,actions)
	try: 
		agent.run()
	except KeyboardInterrupt:
		actions.close_fd()
		actions.kill_be()
		sys.exit(0)


