import numpy as np 
import matplotlib.pyplot as plt 
import pandas as pd
from sklearn import linear_model  
  
class Linear_Regression:
    def __init__(self):
        self.X = list() 
        self.Y = list() 
        self.coef = np.array([1, 1, 1, 1])
        self.learning_rate = 0.01
        self.itr = 0

        self.keys = ['thread_num','queue_num','freq','rps','rev_max_usage','norm_rps']
        self.df = pd.DataFrame(columns=self.keys)
        self.lr = linear_model.SGDRegressor(max_iter=10000)
        self.score = 0
        self.coef = [1,1]
        self.intercept = 0
        self.rps_gap=50
    
    def append_data(self,data):
        self.df.loc[len(self.df)] = data
        print("len: ",len(self.df))

        if len(self.df) % 100 == 99:
            self.train()
    
    def train(self):
        self.df['norm_rps'] = (self.df['rps'] - self.df['rps'].min()) / (self.df['rps'].max() - self.df['rps'].min())  
        self.df['norm_rps'] = self.df['norm_rps'] * self.rps_gap
        self.df['norm_rps'] = self.df['norm_rps'].apply(np.ceil)
        df1 = self.df.set_index(['norm_rps','thread_num','queue_num','freq'])
        df1 = df1.sort_values(by=['thread_num','queue_num','freq'], ascending=False)

        df2 = (df1.groupby(level=['norm_rps'])) 
        df2 = df2.transform('first')  
        result_df = df1['rev_max_usage'] / df2['rev_max_usage']   
        result_df = result_df.reset_index()      

        X = result_df[["thread_num","freq"]].values.tolist()  
        y = result_df['rev_max_usage'].tolist()  
        self.lr.fit(X, y) 

        self.score = self.lr.score(X,y)
        self.coef = self.lr.coef_
        self.intercept = self.lr.intercept_

        print("*************************************************************")
        print("score: ",self.score)
        print("coef: ",self.coef)
        print("intercept: ",self.intercept)
        print(result_df)
        print("*************************************************************")
    
    def get_score(self):
        return self.score
      
 