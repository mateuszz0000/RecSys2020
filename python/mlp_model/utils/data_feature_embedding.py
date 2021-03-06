import torch
from torch.utils.data import DataLoader, Dataset
import random
import os
import pandas as pd
import numpy as np
import pickle
from utils.io import get_csr_matrix
import joblib

class TwitterDataset(Dataset):
    """Wrapper, convert <user, creator, rating> Tensor into Pytorch Dataset"""
    def __init__(self, token_tensor, feature_tensor, target_tensor, embrow_tensor, emb_file, emb_size): #, chunk):
        self.token_tensor = token_tensor
        self.feature_tensor = feature_tensor
        self.target_tensor = target_tensor
        self.embrow_tensor = embrow_tensor
        self.emb_file = emb_file
        self.emb_size = emb_size
        self.bytes_per_value = 32/8
        #self.chunk = chunk

    def __getitem__(self, index):

        # load embedding
        emb_row = self.embrow_tensor[index]
        embedding = np.memmap(self.emb_file, dtype='float32', mode='r',
         shape=(1, self.emb_size), offset=int(emb_row*self.emb_size*self.bytes_per_value))
        embedding = np.array(embedding).squeeze(0)

        return self.token_tensor[index], self.feature_tensor[index], self.target_tensor[index], embedding#, self.chunk[index]

    def __len__(self):
        return self.token_tensor.shape[0]

class LBDataset(Dataset):
    """Wrapper, convert <user, creator, tweet_lb, user_lb> Tensor into Pytorch Dataset"""
    def __init__(self, token_tensor, feature_tensor, tweet_lb, user_lb, embrow_tensor, emb_file, emb_size): #, chunk):
        self.token_tensor = token_tensor
        self.feature_tensor = feature_tensor
        self.user_lb = user_lb
        self.tweet_lb = tweet_lb
        self.embrow_tensor = embrow_tensor
        self.emb_file = emb_file
        self.emb_size = emb_size
        self.bytes_per_value = 32/8
        #self.chunk = chunk

    def __getitem__(self, index):
        # load embedding
        emb_row = self.embrow_tensor[index]
        embedding = np.memmap(self.emb_file, dtype='float32', mode='r',
         shape=(1, self.emb_size), offset=int(emb_row*self.emb_size*self.bytes_per_value))
        embedding = np.array(embedding).squeeze(0)

        return self.token_tensor[index], self.feature_tensor[index], self.tweet_lb[index], self.user_lb[index], embedding#, self.chunk[index]

    def __len__(self):
        return self.token_tensor.shape[0]


class Data:
    def __init__(self, args, dpath, tr_name, val_name,emb_size,is_lb=False):

        self.num_splits = args.num_splits
        self.emb_file = args.emb_file
        self.emb_size = emb_size

        self.train_files = ["{}/{}{}.sav".format(dpath, tr_name, i) for i in range(self.num_splits)]
        self.embedding_files = ["{}/{}{}.memmap".format(args.emb_folder, self.emb_file, i) for i in range(self.num_splits)]

        self.val_embedding_file = "{}/val_emb.memmap".format(args.emb_folder)
        self.submit_embedding_file = None
        
        if is_lb and "Valid" in val_name:
            self.submit_embedding_file = self.val_embedding_file
            print("\n\n\n ====================== WARNING ======================\nSetting submit embedding file to val embedding file because we're exporting csv files for Val set. If this isn't the case, this is the wrong behavior. Path {} \n ================================== \n\n\n".format(self.submit_embedding_file))
        elif is_lb and "Test" in val_name:
            self.submit_embedding_file = "{}/test_emb.memmap".format(args.emb_folder)
            print("\n\n\n ====================== WARNING ======================\nSetting submit embedding file to TEST EMBEDDING because we're exporting csv files for Test set. Path {} \n ============================================ \n\n\n".format(self.submit_embedding_file))
        elif is_lb:
            self.submit_embedding_file = "{}/submit_emb.memmap".format(args.emb_folder)
            print("\n ========================== WARNING ==========================\nSetting submit embedding file to submit (rather than test). Path {} \n".format(self.submit_embedding_file))

        self.splits_trained = 0
        self.split_indexes = list(range(self.num_splits))        

        with open(os.path.join(dpath, val_name), 'rb') as f:
            val_dict = joblib.load(f)
        
        self.val_labels = np.array(val_dict['labels']).astype(np.float)
        self.val_features = val_dict['features']
        self.val_tokens = val_dict['tokens']
        self.val_embrow = val_dict['tweet_row']
        #self.val_chunks = np.zeros(len(self.val_features),dtype=np.int64)

        if 'lb_user_ids' in val_dict.keys():
            self.val_lb_users = val_dict['lb_user_ids']
            self.val_lb_tweets = val_dict['tweet_ids']
            
        self.n_feature = self.val_features.shape[1] 
        self.n_token = self.val_tokens.shape[1]


    def initialize_split(self):

        if self.splits_trained % self.num_splits == 0:
            print("This is the start of {} splits, shuffling the split list ... ".format(self.num_splits))
            random.shuffle(self.split_indexes)


        split_ind = self.split_indexes[self.splits_trained % self.num_splits]
        self.current_train_file = self.train_files[split_ind]
        self.current_emb_file = self.embedding_files[split_ind]

        print("Initializing train split {} ... ".format(self.current_train_file))

        with open(self.current_train_file, 'rb') as f:
            tr_dict = joblib.load(f)
        
        self.tr_labels = np.array(tr_dict['labels']).astype(np.float)
        self.tr_features = tr_dict['features']
        self.tr_tokens = tr_dict['tokens']
        self.tr_embrow = tr_dict['tweet_row']
        #self.tr_chunks = tr_dict['chunks'].astype(np.int64)

        self.splits_trained += 1


    def instance_a_train_loader(self, batch_size):

        self.initialize_split()

        dataset = TwitterDataset(token_tensor=self.tr_tokens,
                                   feature_tensor=self.tr_features,
                                   target_tensor=self.tr_labels,
                                   embrow_tensor=self.tr_embrow,
                                   emb_file=self.current_emb_file,
                                   emb_size=self.emb_size)
                                   #chunk = self.tr_chunks)

        return DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=20, pin_memory=True)


    def instance_a_valid_loader(self, batch_size):
        dataset = TwitterDataset(token_tensor=self.val_tokens,
                                   feature_tensor=self.val_features,
                                   target_tensor=self.val_labels,
                                   embrow_tensor=self.val_embrow,
                                   emb_file=self.val_embedding_file,
                                   emb_size=self.emb_size)
                                   #chunk=self.val_chunks)

        return DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=False)
 

    def instance_a_lb_loader(self, batch_size):
        dataset =LBDataset(feature_tensor=self.val_features,
                                   token_tensor=self.val_tokens,
                                   tweet_lb=self.val_lb_tweets.tolist(),
                                   user_lb = self.val_lb_users.tolist(),
                                   embrow_tensor=self.val_embrow,
                                   emb_file=self.submit_embedding_file,
                                   emb_size=self.emb_size)
                                   #chunk=self.val_chunks)
        del self.val_tokens
        del self.val_features
        return DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers =20, pin_memory=True)
