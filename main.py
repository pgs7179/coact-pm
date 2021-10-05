import torch
import os
import numpy as np
import matplotlib.pyplot as plt
import sys
import time
from time import sleep, strftime

sys.path.append(".")

from env.env import Environment
from policy.coactpm import CoactPM

if __name__=="__main__":
	# environment for getting states and peforming actions
	env = Environment()
	agent = CoactPM(env)
	agent.run()


