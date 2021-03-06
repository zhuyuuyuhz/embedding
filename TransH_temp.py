import load_data
import math
import numpy as np
import theano
import theano.tensor as T
import pdb
from datetime import *
import csv

data = load_data.Data('data/r1.train','data/r1.test')

class Train(object):
  """docstring for ClassName"""
  def __init__(self,user_d,item_d,relation_d,margin_in,rate_in,reg_param_in):
    self.n = user_d
    self.m = item_d
    self.k = relation_d
    self.margin = margin_in
    self.rate = rate_in
    self.reg_param = reg_param_in
    self.train_num = data.train_matrix.shape[0]
    self.test_num = data.test_matrix.shape[0]
    self.user_num = len(data.userid2seq)
    self.item_num = len(data.itemid2seq)
    self.relation_num = len(data.relation2seq)/2
    self.user_vec = np.random.uniform(-6/math.sqrt(self.n),6/math.sqrt(self.n),(self.user_num,self.n))
    self.item_vec = np.random.uniform(-6/math.sqrt(self.m),6/math.sqrt(self.m),(self.item_num,self.m))
    self.relation_vec = np.random.uniform(-6/math.sqrt(self.k),6/math.sqrt(self.k),(self.relation_num,self.k))
    self.relatioin_mapping_matrix = self.generate_mapping_matrix(self.n)
    self.graident_function = self.graident()
    self.loss = self.loss_init()

  def generate_mapping_matrix(self,n):
    m = np.random.rand(self.relation_num,n)
    for i in range(self.relation_num):
      m[i][:] /= np.linalg.norm(m[i][:])
    return m

  def loss_init(self):
    loss = 0
    for i in range(self.train_num):
      record = data.train_matrix[i,:]
      p_user = data.userid2seq[record[0]]
      p_item = data.itemid2seq[record[1]]
      p_relation = data.relation2seq[record[2]]
      n_user = p_user
      n_item = p_item
      n_relation = self.negative_sampling(p_relation)
      p_distance = self.cal_distance(p_user,p_item,p_relation)
      n_distance = self.cal_distance(n_user,n_item,n_relation)
      if p_distance+self.margin-n_distance>0:
        loss += p_distance+self.margin-n_distance
    loss /= self.train_num
    return loss

  def run(self,path):
    nepoch = 100
    predict_init,dis_init = self.predict()
    res_log = [[self.loss]+predict_init+dis_init]
    print('time:'+str(datetime.now())+' epoch:'+str(0)+' loss:'+str(self.loss)+' precision:'+str(predict_init))
    print('hit rating ratio(from 1 to 5):'+str(dis_init))
    for epoch in range(nepoch):
      self.loss = 0
      for i in range(self.train_num):
        record = data.train_matrix[i,:]
        p_user = data.userid2seq[record[0]]
        p_item = data.itemid2seq[record[1]]
        p_relation = data.relation2seq[record[2]]
        n_user = p_user
        n_item = p_item
        n_relation = self.negative_sampling(p_relation)
        p_distance = self.cal_distance(p_user,p_item,p_relation)
        n_distance = self.cal_distance(n_user,n_item,n_relation)
        if p_distance+self.margin-n_distance>0:
          self.loss += p_distance+self.margin-n_distance
          self.SGD(p_user,p_item,p_relation,n_user,n_item,n_relation)
      self.loss /= self.train_num
      precision,dis = self.predict()
      print('time:'+str(datetime.now())+' epoch:'+str(epoch+1)+' loss:'+str(self.loss)+' precision:'+str(precision))
      print('hit rating ratio(from 1 to 5):'+str(dis))
      res_log.append([self.loss]+precision+dis)
    with open(path,'w') as f:
      a = csv.writer(f,delimiter=',')
      a.writerows(res_log)

  def res_relations(self,user,item,top_n):
    sub_relation = {}
    for r in range(self.relation_num):
      sub = self.cal_distance(user,item,r)
      sub_relation[sub] = r
    sort_keys = [k for k in sub_relation.keys()]
    sort_keys.sort()
    rels = [sub_relation[r] for r in sort_keys[:top_n]]
    return rels

  def predict(self,n=1):
    precision = np.array([0]*n,dtype='double')
    hit_relations = [0]*5
    test_relations = [0]*5
    hit = 0
    for i in range(self.test_num):
      test_tuple = data.test_matrix[i,:]
      user = data.userid2seq[test_tuple[0]]
      item = data.itemid2seq[test_tuple[1]]
      relation = data.relation2seq[test_tuple[2]]
      test_relations[relation] += 1
      for top in range(n):
        rels = self.res_relations(user,item,top+1)
        if relation in rels:
          hit += 1
          hit_relations[relation] += 1
          precision[top] += 1
    precision /= self.test_num
    hit_relation_precision = [float(r[0])/r[1] for r in zip(hit_relations,test_relations)]
    # hit_relation_precision = [float(r)/hit for r in hit_relations]
    return precision.tolist(),hit_relation_precision

  def new_items(self,all,old):
    new = set()
    for i in all:
      if i not in old:
        new.add(i)
    return new

  def cal_preference(self,user,item,relation):
    user_vec = self.user_vec[user,:]
    item_vec = self.item_vec[item,:]
    relation_vec = self.relation_vec[relation,:]
    user_mat = self.user_mapping_tensor[relation,:,:]
    item_mat = self.item_mapping_tensor[relation,:,:]
    vec_norm = np.linalg.norm(user_vec.dot(user_mat)-item_vec.dot(item_mat))
    return vec_norm**2

  def top_item_recommend(self,top_n=5):
    precision = 0
    train_user_items = data.train_user_items()
    test_user_items = data.test_user_items()
    all_items = set([i for i in range(self.item_num)])
    test_user_count = 0
    for u in range(self.user_num):
      u_items = set(train_user_items[u])
      items = self.new_items(all_items,u_items)
      items_scores = []
      u_vec = self.user_vec[u,:][np.newaxis]
      for i in items:
        i_vec = self.item_vec[i,:][np.newaxis]
        closest_rating = self.res_relations(u,i,1)
        score = 1/(self.cal_preference(u,i,closest_rating)+1)
        items_scores.append((score,i))
      items_scores.sort(reverse=True)
      recommen_item = set([i[1] for i in items_scores[:top_n]])
      if u not in test_user_items: continue
      test_set = set(test_user_items[u])
      hit = len(test_set)-len(self.new_items(test_set,recommen_item))
      # pdb.set_trace()
      precision += float(hit)/top_n
      test_user_count += 1
    precision /= test_user_count
    return precision

  def negative_sampling(self,p_relation):
    if p_relation<0 or p_relation>4: print('relation is not in range')
    if p_relation == 4:
      n_relation = 0
    elif p_relation == 3:
      n_relation = 1
    elif p_relation == 2:
      n_relation = 0
    elif p_relation == 1:
      n_relation = 3
    else:
      n_relation = 4
    return n_relation

  def cal_distance(self,user,item,relation):
    user_vec = self.user_vec[user,:]
    item_vec = self.item_vec[item,:]
    relation_vec = self.relation_vec[relation,:]
    map_vec = self.relatioin_mapping_matrix[relation,:]
    user_rel = user_vec-(map_vec.T.dot(user_vec))*map_vec
    item_rel = item_vec-(map_vec.T.dot(item_vec))*map_vec
    vec_norm = np.linalg.norm(user_rel+relation_vec-item_rel)
    return vec_norm**2

  def graident(self):
    u = T.dvector('u')
    i = T.dvector('i')
    r = T.dvector('r')
    r1 = T.dvector('r1')
    rv = T.dvector('rv')
    rv1 = T.dvector('rv1')
    # construct theano expression graph
    u_r = u-T.transpose(rv).dot(u)*rv
    u_r1 = u-T.transpose(rv1).dot(u)*rv1
    i_r = i-T.transpose(rv).dot(i)*rv
    i_r1 = i-T.transpose(rv1).dot(i)*rv1
    distance_part = T.sum((u_r+r-i_r)**2)+self.margin-T.sum((u_r1+r1-i_r1)**2)+T.sum((T.transpose(rv).dot(r))**2)/T.sum(rv**2)+T.sum((T.transpose(rv1).dot(r1))**2)/T.sum(rv1**2)
    regularizatoin = self.reg_param*(T.sum(u**2)+T.sum(i**2)+T.sum(r**2)+T.sum(r1**2)+T.sum(rv**2)+T.sum(rv1**2))
    loss = distance_part+regularizatoin
    gu,gi,gr,gr1,grv,grv1 = T.grad(loss,[u,i,r,r1,rv,rv1])
    dloss = theano.function(inputs=[u,i,r,r1,rv,rv1],outputs=[gu,gi,gr,gr1,grv,grv1])
    return dloss

  def relation_part_g(self,relation,weight=1):
    drelation = 0
    for r in range(self.relation_num):
      if r == relation: continue
      r_vec = self.relation_vec[r,:]
      rel_vec = self.relation_vec[relation,:]
      x = 1
      sub = (rel_vec**2).sum()-(r_vec**2).sum()
      if r<relation:
        sub = -1*sub
        x = -1
      c = 1/(1+math.exp(-sub))
      dc = math.exp(-sub)/(1+math.exp(-sub))**2
      drelation += 2*weight*x/c*dc*(rel_vec**2).sum()
    return drelation

  def norm(self,v,m):
    v = v[np.newaxis]
    while True:
      vm = v.dot(m)
      n = (np.linalg.norm(vm))**2
      if n>1:
        temp = 2*vm
        m -= self.rate*v.T.dot(temp)
        # v -= self.rate*temp.dot(m.T)
      else:
        return m

  def SGD(self,p_user,p_item,p_relation,n_user,n_item,n_relation):
    dloss = self.graident_function
    p_user_vec = self.user_vec[p_user,:]
    p_item_vec = self.item_vec[p_item,:]
    p_relation_vec = self.relation_vec[p_relation,:]
    n_relation_vec = self.relation_vec[n_relation,:]
    p_rel_plane = self.relatioin_mapping_matrix[p_relation,:]
    n_rel_plane = self.relatioin_mapping_matrix[n_relation,:]
    
    dp_user,dp_item,dp_relation,dn_relation,dp_rel_plane,dn_rel_plane = dloss(p_user_vec,p_item_vec,p_relation_vec,n_relation_vec,p_rel_plane,n_rel_plane)
    dp_relation -= self.relation_part_g(p_relation)
    dn_relation -= self.relation_part_g(n_relation)
    self.user_vec[p_user,:] -= self.rate*dp_user
    self.item_vec[p_item,:] -= self.rate*dp_item
    self.relation_vec[p_relation,:] -= self.rate*dp_relation
    self.relation_vec[n_relation,:] -= self.rate*dn_relation
    self.relatioin_mapping_matrix[p_relation,:] -= self.rate*dp_rel_plane
    self.relatioin_mapping_matrix[n_relation,:] -= self.rate*dn_rel_plane
    ## normlization
    self.user_vec[p_user,:] /= np.linalg.norm(self.user_vec[p_user,:])
    self.item_vec[p_item,:] /= np.linalg.norm(self.item_vec[p_item,:])
    self.relation_vec[p_relation,:] /= np.linalg.norm(self.relation_vec[p_relation,:])
    self.relation_vec[n_relation,:] /= np.linalg.norm(self.relation_vec[n_relation,:])
    self.relatioin_mapping_matrix[p_relation,:] /= np.linalg.norm(self.relatioin_mapping_matrix[p_relation,:])
    self.relatioin_mapping_matrix[n_relation,:] /= np.linalg.norm(self.relatioin_mapping_matrix[n_relation,:])

    # if np.linalg.norm(self.user_vec[p_user,:])>1: self.user_vec[p_user,:] /= np.linalg.norm(self.user_vec[p_user,:])
    # if np.linalg.norm(self.item_vec[p_item,:])>1: self.item_vec[p_item,:] /= np.linalg.norm(self.item_vec[p_item,:])
    # if np.linalg.norm(self.relation_vec[p_relation,:])>1: self.relation_vec[p_relation,:] /= np.linalg.norm(self.relation_vec[p_relation,:])
    # if np.linalg.norm(self.relation_vec[n_relation,:])>1: self.relation_vec[n_relation,:] /= np.linalg.norm(self.relation_vec[n_relation,:])
    # self.user_mapping_tensor[p_relation,:,:] = self.norm(self.user_vec[p_user,:],self.user_mapping_tensor[p_relation,:,:])
    # self.user_mapping_tensor[n_relation,:,:] = self.norm(self.user_vec[p_user,:],self.user_mapping_tensor[n_relation,:,:])
    # self.item_mapping_tensor[p_relation,:,:] = self.norm(self.item_vec[p_item,:],self.item_mapping_tensor[p_relation,:,:])
    # self.item_mapping_tensor[n_relation,:,:] = self.norm(self.item_vec[p_item,:],self.item_mapping_tensor[n_relation,:,:])

if __name__ == "__main__":
  user_dem = [[20,20,20],[10,10,10],[30,30,30]]
  learning_rate = [0.01,0.005,0.001]
  for r in learning_rate:
    for d in user_dem:
      rr = Train(d[0],d[1],d[2],1,r,0.001)
      filename = str(d+[r])+'.csv'
      print(filename)
      rr.run('result/TransH/'+filename)