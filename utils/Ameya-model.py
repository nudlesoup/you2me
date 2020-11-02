# Copyright (c) Facebook, Inc. and its affiliates. All rights reserved.

import torch
import torch.nn as nn
import torchvision.models as models
from torch.nn.utils.rnn import pack_padded_sequence
from IPython import embed



class EncoderCNN(nn.Module):
    def __init__(self, embed_size):
        super(EncoderCNN, self).__init__()
        resnet = models.resnet152(pretrained=True)
        modules = list(resnet.children())[:-1]
        self.resnet = nn.Sequential(*modules)
        self.linear = nn.Linear(resnet.fc.in_features, embed_size)
        self.bn = nn.BatchNorm1d(embed_size, momentum=0.01)

    def forward(self, images):
        images = images.transpose(0, 1)
        feat_block = []
        for batch in images:
            with torch.no_grad():
                features = self.resnet(batch)
            features = features.reshape(features.size(0), -1)
            features = self.bn(self.linear(features))
            feat_block.append(features)
        feat_block = torch.stack(feat_block, dim=1)
        return feat_block


class DecoderRNN(nn.Module):
    def __init__(self, embed_size, hidden_size, vocab_size, num_layers,
                 num_homog=15, homog_size=9, pose2_size=75):
        super(DecoderRNN, self).__init__()
        self.embed = nn.Embedding(vocab_size, embed_size)
        self.lstm = nn.LSTM((embed_size * 2) + (homog_size * num_homog) + pose2_size, hidden_size, num_layers,
                            batch_first=True)
        
        self.linear = nn.Linear(hidden_size, (vocab_size))
        
        self.embed_size = embed_size

    def forward(self, features, homography, poses2, lengths,states=None):
        """ decode image feature vectors and generate pose sequences """

        first = True
        prev_pose = torch.zeros([features.shape[0], 1, self.embed_size]).cuda().float()
        #embed()

        for i in range(features.shape[1]):
            # inputVec = torch.cat((inputVecs[i, :].unsqueeze(0), self.embed), dim=1)
            # concat the embedding with (im features, homographies)
            embeddings = torch.cat((prev_pose, features[:,i,:].unsqueeze(1)), 2)
            embeddings = torch.cat((embeddings, homography[:,i,:].unsqueeze(1).cuda()), 2)
            embeddings = torch.cat((embeddings, poses2[:,i,:].unsqueeze(1).cuda()), 2)
            #packed = pack_padded_sequence(embeddings, lengths, batch_first=True)
            hiddens, _ = self.lstm(embeddings,states)
            y_pred = self.linear(hiddens.squeeze(1))
            # lstm_out, self.hidden = self.lstm(inputVec.unsqueeze(0))
            # y_pred = self.linear(lstm_out)[0]
            _, predicted = y_pred.max(1)
            prev_pose = self.embed(predicted)
            prev_pose = prev_pose.unsqueeze(1)
            if first:
                outputs = y_pred
                first = False
            else:
                outputs = torch.cat((outputs, y_pred))

        return outputs

    def sample(self, features, homography, openpose, states=None):
        sampled_ids = []
        embeddings = torch.zeros([1, 1, self.embed_size]).cuda().float()
        features = features.squeeze(0)
        # embed()

        for i in range(features.shape[0]):
            curr_feat = features[i].unsqueeze(0).unsqueeze(1)
            curr_h = homography[i].unsqueeze(0).unsqueeze(1)
            curr_op = openpose[i].unsqueeze(0).unsqueeze(1)
            tensor = torch.cat((embeddings, curr_feat), 2)
            tensor = torch.cat((tensor, curr_h.cuda()), 2)
            tensor = torch.cat((tensor, curr_op.cuda()), 2)
            hiddens, states = self.lstm(tensor, states)
            outputs = self.linear(hiddens.squeeze(1))
            # predicted=torch.argmax(outputs, 1)
            _, predicted = outputs.max(1)
            sampled_ids.append(predicted)
            embeddings = self.embed(predicted)
            embeddings = embeddings.unsqueeze(1)

        sampled_ids = torch.stack(sampled_ids, 1)
        return sampled_ids
