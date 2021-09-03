# PyTorch
import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.optim as optim

# Lib
import numpy as np
import random
from copy import deepcopy
import matplotlib.pyplot as plt
from IPython import display
import os


# Files
from ddpg.noise import OrnsteinUhlenbeckActionNoise as OUNoise
from ddpg.replaybuffer import Buffer
from ddpg.actorcritic import Actor, Critic

torch.autograd.set_detect_anomaly(True)

PLOT_FIG = True

# Hyperparameters
ACTOR_LR = 0.0001
CRITIC_LR = 0.001
MINIBATCH_SIZE = 64
NUM_EPISODES = 9000
NUM_TIMESTEPS = 300
MU = 0
SIGMA = 0.2
CHECKPOINT_DIR = './checkpoints/manipulator/'
BUFFER_SIZE = 100000
DISCOUNT = 0.9
TAU = 0.001
WARMUP = 70
EPSILON = 1.0
EPSILON_DECAY = 1e-6

NUM_ACTIONS = 16
NUM_STATES = 4

#ID = 'default'

def obs2state(state_list):
    #l1 = [val.tolist() for val in list(observation.values())]
    #l2 = []
    #for sublist in l1:
    #    try:
    #        l2.extend(sublist)
    #    except:
    #        l2.append(sublist)
    return torch.FloatTensor(state_list).view(1, -1)



class DDPG:
    def __init__(self, env):
        self.env = env
        self.stateDim = NUM_STATES
        self.actionDim = NUM_ACTIONS
        self.actor = Actor(self.stateDim, self.actionDim)
        self.critic = Critic(self.stateDim, self.actionDim)
        self.targetActor = deepcopy(Actor(self.stateDim, self.actionDim))
        self.targetCritic = deepcopy(Critic(self.stateDim, self.actionDim))
        self.actorOptim = optim.Adam(self.actor.parameters(), lr=ACTOR_LR)
        self.criticOptim = optim.Adam(self.critic.parameters(), lr=CRITIC_LR)
        self.criticLoss = nn.MSELoss()
        self.noise = OUNoise(mu=np.zeros(self.actionDim), sigma=SIGMA)
        self.replayBuffer = Buffer(BUFFER_SIZE)
        self.batchSize = MINIBATCH_SIZE
        self.checkpoint_dir = CHECKPOINT_DIR
        self.discount = DISCOUNT
        self.warmup = WARMUP
        self.epsilon = EPSILON
        self.epsilon_decay = EPSILON_DECAY
        self.rewardgraph = []
        self.start = 0
        self.end = NUM_EPISODES

    # Inputs: Batch of next states, rewards and terminal flags of size self.batchSize
    # Target Q-value <- reward and bootstraped Q-value of next state via the target actor and target critic
    # Output: Batch of Q-value targets
    def getQTarget(self, nextStateBatch, rewardBatch, terminalBatch):       
        targetBatch = torch.FloatTensor(rewardBatch)
        nonFinalMask = torch.ByteTensor(tuple(map(lambda s: s != True, terminalBatch)))
        nextStateBatch = torch.cat(nextStateBatch)
        nextActionBatch = self.targetActor(nextStateBatch)
        nextActionBatch.volatile = True
        qNext = self.targetCritic(nextStateBatch, nextActionBatch)  
        
        nonFinalMask = self.discount * nonFinalMask.type(torch.FloatTensor)
        targetBatch += nonFinalMask * qNext.squeeze().data
        
        return Variable(targetBatch, volatile=False)

    # weighted average update of the target network and original network
    # Inputs: target actor(critic) and original actor(critic)
    def updateTargets(self, target, original):
        for targetParam, orgParam in zip(target.parameters(), original.parameters()):
            targetParam.data.copy_((1 - TAU)*targetParam.data + TAU*orgParam.data)

    # Inputs: Current state of the episode
    # Output: the action which maximizes the Q-value of the current state-action pair
    def getMaxAction(self, curState):
        noise = self.epsilon * Variable(torch.FloatTensor(self.noise()), volatile=True)
        action = self.actor(curState).detach()
        actionNoise = action + noise
        
        # get the max
        #action_list = actionNoise.tolist()[0]
        #max_action = max(action_list)
        #max_index = action_list.index(max_action)

        return actionNoise

    # training of the original and target actor-critic networks
    def train(self):
        if not os.path.exists(self.checkpoint_dir):
            os.makedirs(self.checkpoint_dir)
            
        print('Training started...')
        
        action_step = 1
        #available_actions = [0, action_step, -action_step]
        all_rewards = []
        avg_rewards = []
        # for each episode 
        for episode in range(self.start, self.end):
            state = self.env.reset()
            
            ep_reward = 0
            
            for step in range(NUM_TIMESTEPS):
            # while not time_step.last():
                # print each time step only at the last EPISODE
                print("step: ", step)
                if episode == NUM_EPISODES-1:
                    print("EP:", episode, " | Step:", step)
                    print("Update - Current p99:", self.env.get_latency())
                    print("Update - Current Power:", self.env.get_power()) 
                    print("Update - Current App Usage:", state['app_usage']) 
                    print("Update - Current Pkt Usage:", state['pkt_usage']) 

                core_T = state['core_T']
                core_P = state['core_P']
                app_usage = state['app_usage']
                pkt_usage = state['pkt_usage']


                # get maximizing action
                currStateTensor = Variable(obs2state([
                    core_T, core_P, app_usage, pkt_usage
                ]),volatile=True)
                print(state)
                self.actor.eval()     
                action = self.getMaxAction(currStateTensor)
                currStateTensor.volatile = False
                action.volatile = False

                print(action)

                
                self.actor.train()
                
                # step episode
                state, reward, done = self.env.step(action)

                print('Reward: {}'.format(reward))

                core_T = state['core_T']
                core_P = state['core_P']
                app_usage = state['app_usage']
                pkt_usage = state['pkt_usage']

                
                nextState = Variable(obs2state([
                    core_T, core_P, app_usage, pkt_usage
                ]),volatile=True)
                ep_reward += reward
                
                # Update replay bufer
                self.replayBuffer.append((currStateTensor, action, nextState, reward, done))
                
                # Training loop
                if len(self.replayBuffer) >= self.warmup:
                    curStateBatch, actionBatch, nextStateBatch, \
                    rewardBatch, terminalBatch = self.replayBuffer.sample_batch(self.batchSize)
                    curStateBatch = torch.cat(curStateBatch)
                    actionBatch = torch.cat(actionBatch)
                    
                    qPredBatch = self.critic(curStateBatch, actionBatch)
                    qTargetBatch = self.getQTarget(nextStateBatch, rewardBatch, terminalBatch).unsqueeze(1)
                    
                    # Critic update
                    self.criticOptim.zero_grad()
                    criticLoss = self.criticLoss(qPredBatch, qTargetBatch)
                    print('Critic Loss: {}'.format(criticLoss))
                    criticLoss.backward(retain_graph=True)
                    self.criticOptim.step()
            
                    # Actor update
                    self.actorOptim.zero_grad()
                    actorLoss = -torch.mean(self.critic(curStateBatch, self.actor(curStateBatch)))
                    print('Actor Loss: {}'.format(actorLoss))
                    actorLoss.backward(retain_graph=True)
                    self.actorOptim.step()
                    
                    # Update Targets                        
                    self.updateTargets(self.targetActor, self.actor)
                    self.updateTargets(self.targetCritic, self.critic)
                    self.epsilon -= self.epsilon_decay
            print("EP -", episode, "| Total Reward -", ep_reward)
   
            # save to checkpoints
            if episode % 20 == 0:
                self.save_checkpoint(episode)
            self.rewardgraph.append(ep_reward)

            if PLOT_FIG:
                if episode % 1 ==0 and episode != 0:
                    plt.plot(self.rewardgraph, color='darkorange')  # total rewards in an iteration or episode
                    # plt.plot(avg_rewards, color='b')  # (moving avg) rewards
                    plt.xlabel('Episodes')
                    plt.savefig('ep'+str(episode)+'.png')
        if PLOT_FIG:
            plt.plot(self.rewardgraph, color='darkorange')  # total rewards in an iteration or episode
            # plt.plot(avg_rewards, color='b')  # (moving avg) rewards
            plt.xlabel('Episodes')
            plt.savefig('final.png')

    def save_checkpoint(self, episode_num):
        checkpointName = self.checkpoint_dir + 'ep{}.pth.tar'.format(episode_num)
        checkpoint = {
            'episode': episode_num,
            'actor': self.actor.state_dict(),
            'critic': self.critic.state_dict(),
            'targetActor': self.targetActor.state_dict(),
            'targetCritic': self.targetCritic.state_dict(),
            'actorOpt': self.actorOptim.state_dict(),
            'criticOpt': self.criticOptim.state_dict(),
            'replayBuffer': self.replayBuffer,
            'rewardgraph': self.rewardgraph,
            'epsilon': self.epsilon
            
        } 
        torch.save(checkpoint, checkpointName)
    
    def loadCheckpoint(self, checkpointName):
        if os.path.isfile(checkpointName):
            print("Loading checkpoint...")
            checkpoint = torch.load(checkpointName)
            self.start = checkpoint['episode'] + 1
            self.actor.load_state_dict(checkpoint['actor'])
            self.critic.load_state_dict(checkpoint['critic'])
            self.targetActor.load_state_dict(checkpoint['targetActor'])
            self.targetCritic.load_state_dict(checkpoint['targetCritic'])
            self.actorOptim.load_state_dict(checkpoint['actorOpt'])
            self.criticOptim.load_state_dict(checkpoint['criticOpt'])
            self.replayBuffer = checkpoint['replayBuffer']
            self.rewardgraph = checkpoint['rewardgraph']
            self.epsilon = checkpoint['epsilon']
            print('Checkpoint loaded')
        else:
            raise OSError('Checkpoint not found')
