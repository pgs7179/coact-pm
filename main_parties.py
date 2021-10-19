#import numpy as np
#import matplotlib.pyplot as plt
import sys
#from time import sleep, strftime

sys.path.append("/home/caslab/coact-pm")

from env.env import Environment
from policy.parties import Parties
from actions import Action

if __name__=="__main__":
	# environment for getting states and peforming actions
	env = Environment()
	actions = Action(env)
	agent = Parties(env,actions)
	try: 
		agent.run()
	except KeyboardInterrupt:
		actions.close_fd()
		sys.exit(0)


