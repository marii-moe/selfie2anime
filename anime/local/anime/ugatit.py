#AUTOGENERATED! DO NOT EDIT! File to edit: dev/UGATIT.ipynb (unless otherwise specified).

__all__ = ['fakemodule', 'UGATIT', 'UgatitModel', 'UGATITLoss']

#Cell
from functools import partial
import numpy as np
from pathlib import Path
from fast.torch_basics import *
import sys
class fakemodule(object):
    def method(a):
        return a
sys.modules["cv2"] = fakemodule
from UGATIT import ResnetGenerator,Discriminator,RhoClipper

#Cell
class UGATIT(object) :
    def __init__(self):
        self.ch = 64
        self.lr=0.0001
        self.weight_decay=0.0001
        """ Weight """
        self.cycle_weight = 10
        self.identity_weight = 10
        self.cam_weight = 1000

        """ Generator """
        self.n_res = 4

        """ Discriminator """
        self.n_dis = 6

        self.img_size = 128
        self.img_ch = 3

    def build_model(self):

        """ Define Generator, Discriminator """
        genA2B = ResnetGenerator(input_nc=3, output_nc=3, ngf=self.ch, n_blocks=self.n_res, img_size=self.img_size, light=False)
        genB2A = ResnetGenerator(input_nc=3, output_nc=3, ngf=self.ch, n_blocks=self.n_res, img_size=self.img_size, light=False)
        disGA = Discriminator(input_nc=3, ndf=self.ch, n_layers=7)
        disGB = Discriminator(input_nc=3, ndf=self.ch, n_layers=7)
        disLA = Discriminator(input_nc=3, ndf=self.ch, n_layers=5)
        disLB = Discriminator(input_nc=3, ndf=self.ch, n_layers=5)
        genA2B.name='genA2B'
        genB2A.name='genB2A'
        disGA.name='disGA'
        disGB.name='disGB'
        disLA.name='disLA'
        disLB.name='disLB'
        self.models=(genA2B,genB2A,disGA,disGB,disLA,disLB)


        """ Define Loss """
        L1_loss = nn.L1Loss()
        MSE_loss = nn.MSELoss()
        BCE_loss = nn.BCEWithLogitsLoss()
        self.losses=(L1_loss,MSE_loss,BCE_loss)

        """ Trainer """
        G_optim = torch.optim.Adam(itertools.chain(genA2B.parameters(), genB2A.parameters()), lr=self.lr, betas=(0.5, 0.999), weight_decay=self.weight_decay)
        D_optim = torch.optim.Adam(itertools.chain(disGA.parameters(), disGB.parameters(), disLA.parameters(), disLB.parameters()), lr=self.lr, betas=(0.5, 0.999), weight_decay=self.weight_decay)
        G_optim.name='gen_optim'
        D_optim.name='disc_optim'
        self.optims=(G_optim,D_optim)

        """ Define Rho clipper to constraint the value of rho in AdaILN and ILN"""
        self.Rho_clipper = RhoClipper(0, 1)

#Cell
class UgatitModel(nn.Module):
    def __init__(self,models):
        super(UgatitModel, self).__init__()
        keys=['GA2B','GB2A','DA','DB','LA','LB']
        self.models=nn.ModuleDict(zip(keys,models))
        self.optimizing_gen=True
    def forward(self, *x, **kwargs):
        x_a,x_b=x[0] if len(x)==1 else x #hackery depending on pytorch trace flag, input can be different
        if self.training:
            if self.optimizing_gen:
                return self.models['GA2B'](x_a),self.models['GB2A'](x_b)
            else:
                return self.models['DA'](x_a),self.models['DB'](x_b),self.models['LA'](x_a),self.models['LB'](x_b)
        else:
            return self.models['GA2B'](x_a),self.models['GB2A'](x_b)

#Cell
class UGATITLoss():
    def __init__(self, models,cycle_weight = 10,identity_weight = 10,cam_weight = 1000,adv_weight=1):
        store_attr(self, "cycle_weight,identity_weight,cam_weight,adv_weight")
        self.model_GA2B,self.model_GB2A,self.model_DA,self.model_DB,self.model_LA,self.model_LB=models
        self.MSE_loss=nn.MSELoss()
        self.L1_loss=nn.L1Loss()
        self.BCE_loss=nn.BCEWithLogitsLoss()
        self.loss_funcs=[self.MSE_loss,self.L1_loss,self.BCE_loss]
        self.losses=(self.GeneratorLoss(self),self.DiscriminatorLoss(self))

    #xb should be pred, need to figure out what to do here
    def __call__(self,xb,yb):
        return self.generator_loss(xb,yb)

    #fakeB - output of a generator that goes from A2B "B"
    #realA - real image of type "A"
    #genB2A - generator for going back to A(as in cycle)
    def recon_loss(self,fakeB,realA,genB2A):
        return self.L1_loss(genB2A(fakeB)[0],realA)

    def cam_loss(self,fake_A2B_cam_logit,fake_B2B_cam_logit):
        return self.BCE_loss(fake_A2B_cam_logit, torch.ones_like(fake_A2B_cam_logit)) \
            + self.BCE_loss(fake_B2B_cam_logit, torch.zeros_like(fake_B2B_cam_logit))

    def ad_loss(self,probs,target_value=1):
        prob, cam_prob, _ = probs
        ad_loss = self.MSE_loss(prob, torch.full_like(prob,fill_value=target_value))
        ad_cam_loss = self.MSE_loss(cam_prob, torch.full_like(cam_prob,fill_value=target_value))
        return  ad_loss + ad_cam_loss
    class GeneratorLoss(nn.Module):
        def __init__(self,ugatit):
            super(UGATITLoss.GeneratorLoss, self).__init__()
            self.ugatit=ugatit
            self.losses=nn.ModuleList(self.ugatit.loss_funcs)
        def decodes(self,preds):
            return ((TensorImage(preds[0][0]),TensorImage(preds[1][0])),)
        def __call__(self,pred,yb):
            real_A,real_B=yb
            u=self.ugatit
            fake_A2B, fake_A2B_cam_logit, _ = pred[0]
            fake_B2A, fake_B2A_cam_logit, _ = pred[1]

            fake_A2A, fake_A2A_cam_logit, _ = u.model_GB2A(real_A)
            fake_B2B, fake_B2B_cam_logit, _ = u.model_GA2B(real_B)

            ad_loss_A = u.ad_loss(u.model_DA(fake_B2A)) + u.ad_loss(u.model_LA(fake_B2A))
            ad_loss_B = u.ad_loss(u.model_DB(fake_A2B)) + u.ad_loss(u.model_LB(fake_A2B))
            loss = ad_loss_A + ad_loss_B

            recon_loss_A = u.recon_loss(fake_A2B,real_A,u.model_GB2A)
            recon_loss_B = u.recon_loss(fake_B2A,real_B,u.model_GA2B)
            loss += u.cycle_weight * (recon_loss_A + recon_loss_B)

            identity_loss_A = u.L1_loss(fake_A2A, real_A)
            identity_loss_B = u.L1_loss(fake_B2B, real_B)
            loss += u.identity_weight * (identity_loss_A + identity_loss_B)

            cam_loss_A = u.cam_loss(fake_B2A_cam_logit,fake_A2A_cam_logit)
            cam_loss_B = u.cam_loss(fake_A2B_cam_logit,fake_B2B_cam_logit)
            return loss + u.cam_weight * (cam_loss_A + cam_loss_B)
    class DiscriminatorLoss(nn.Module):
        def __init__(self,ugatit):
            super(UGATITLoss.DiscriminatorLoss, self).__init__()
            self.ugatit=ugatit
            self.mse=self.ugatit.MSE_loss

        def __call__(self,pred,yb):
            real_A,real_B=yb
            u=self.ugatit
            fake_A2B, _, _ = u.model_GA2B(real_A)
            fake_B2A, _, _ = u.model_GB2A(real_B)

            #Need to replace with adversarial loss, three variable ones/zeros_like, img, discriminator
            loss = u.ad_loss(pred[0])
            loss += u.ad_loss(pred[1])
            loss += u.ad_loss(pred[2])
            loss += u.ad_loss(pred[3])
            loss += u.ad_loss(u.model_DA(fake_B2A),target_value=0)
            loss += u.ad_loss(u.model_LA(fake_B2A),target_value=0)
            loss += u.ad_loss(u.model_DB(fake_A2B),target_value=0)
            loss += u.ad_loss(u.model_LB(fake_A2B),target_value=0)

            return u.adv_weight * loss