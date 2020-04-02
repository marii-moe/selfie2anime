# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/UGATIT-networks.ipynb (unless otherwise specified).

__all__ = ['MixedPrecision_LayerNorm', 'ResnetBlock', 'Spliter', 'ResnetGenerator', 'ResnetAdaILNBlock', 'adaILN',
           'ILN', 'Discriminator', 'RhoClipper']

# Cell
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.parameter import Parameter
from torch.utils.checkpoint import checkpoint,checkpoint_sequential

# Cell
class MixedPrecision_LayerNorm(nn.LayerNorm):
    def __init__(self, *args,**kwargs):
        super().__init__(*args,**kwargs)
    def forward(self, input):
        dtype=input.dtype
        out = super().forward(input.float())
        return out.to(dtype)

# Cell
class ResnetBlock(nn.Module):
    def __init__(self, dim, use_bias):
        super(ResnetBlock, self).__init__()
        conv_block = []
        conv_block += [nn.ReflectionPad2d(1),
                       nn.Conv2d(dim, dim, kernel_size=3, stride=1, padding=0, bias=use_bias),
                       nn.InstanceNorm2d(dim),
                       nn.ReLU(True)]

        conv_block += [nn.ReflectionPad2d(1),
                       nn.Conv2d(dim, dim, kernel_size=3, stride=1, padding=0, bias=use_bias),
                       nn.InstanceNorm2d(dim)]

        self.conv_block = nn.Sequential(*conv_block)

    def forward(self, x):
        x = x + self.conv_block(x)
        return x


# Cell
class Spliter(nn.Module):
    def __init__(self,layer,inp,out,splits=2,bias=False):
        super().__init__()
        self.splits=nn.ModuleList([layer(inp,out,bias=bias) for i in range(splits)])
    def forward(self,x):
        return torch.cat(tuple([checkpoint(split,x) if self.training else split(x) for split in self.splits]),1)

# Cell
class ResnetGenerator(nn.Module):
    def __init__(self, input_nc, output_nc, ngf=64, n_blocks=6, img_size=256, light=False):
        assert(n_blocks >= 0)
        super(ResnetGenerator, self).__init__()
        self.input_nc = input_nc
        self.output_nc = output_nc
        self.ngf = ngf
        self.n_blocks = n_blocks
        self.img_size = img_size
        self.light = light

        DownBlock = []
        DownBlock += [nn.ReflectionPad2d(3),
                      nn.Conv2d(input_nc, ngf, kernel_size=7, stride=1, padding=0, bias=False),
                      nn.InstanceNorm2d(ngf),
                      nn.ReLU(True)]

        # Down-Sampling
        n_downsampling = 2
        for i in range(n_downsampling):
            mult = 2**i
            DownBlock += [nn.ReflectionPad2d(1),
                          nn.Conv2d(ngf * mult, ngf * mult * 2, kernel_size=3, stride=2, padding=0, bias=False),
                          nn.InstanceNorm2d(ngf * mult * 2),
                          nn.ReLU(True)]

        # Down-Sampling Bottleneck
        mult = 2**n_downsampling
        for i in range(n_blocks):
            DownBlock += [ResnetBlock(ngf * mult, use_bias=False)]

        # Class Activation Map
        self.gap_fc = nn.Linear(ngf * mult, 2, bias=False)
        self.gmp_fc = nn.Linear(ngf * mult, 2, bias=False)
        self.conv1x1 = nn.Conv2d(ngf * mult * 2, ngf * mult, kernel_size=1, stride=1, bias=True)
        self.relu = nn.ReLU(True)

        # Gamma, Beta block
        if self.light:
            FC = [nn.Linear(ngf * mult, ngf * mult, bias=False),
                  nn.ReLU(True),
                  nn.Linear(ngf * mult, ngf * mult, bias=False),
                  nn.ReLU(True)]
        else:
            #img_size //3 // mult *img_size // mult //3 * ngf * mult
            FC0 =Spliter(
                        nn.Linear,
                        img_size // mult * img_size // mult * ngf * mult, ngf * mult//32, bias=False,
                        splits=32
                )

            FC = [nn.ReLU(True),
                  MixedPrecision_LayerNorm(ngf * mult),
                  nn.Linear(ngf * mult, ngf * mult, bias=False),
                  nn.ReLU(True),
                  MixedPrecision_LayerNorm(ngf * mult),
                 ]
        self.gamma = nn.Linear(ngf * mult, ngf * mult, bias=False)
        self.beta = nn.Linear(ngf * mult, ngf * mult, bias=False)

        # Up-Sampling Bottleneck
        for i in range(n_blocks):
            setattr(self, 'UpBlock1_' + str(i+1), ResnetAdaILNBlock(ngf * mult, use_bias=False))

        # Up-Sampling
        UpBlock2 = []
        for i in range(n_downsampling):
            mult = 2**(n_downsampling - i)
            UpBlock2 += [nn.Upsample(scale_factor=2, mode='nearest'),
                         nn.ReflectionPad2d(1),
                         nn.Conv2d(ngf * mult, int(ngf * mult / 2), kernel_size=3, stride=1, padding=0, bias=False),
                         ILN(int(ngf * mult / 2)),
                         nn.ReLU(True)]

        UpBlock2 += [ nn.ReflectionPad2d(3),
                     nn.Conv2d(ngf, output_nc, kernel_size=7, stride=1, padding=0, bias=False)]

        self.DownBlock0 = nn.Sequential(*(DownBlock[:2]))
        self.DownBlock = nn.Sequential(*(DownBlock[2:]))
        self.FC0=FC0
        self.FC = nn.Sequential(*FC)
        self.UpBlock2 = nn.Sequential(*UpBlock2)
        #self.out_scale = torch.tensor(2., requires_grad=False)
        #self.out_shift = torch.tensor(1., requires_grad=False)

        self.big_IN=nn.InstanceNorm2d(ngf * mult)
    def _calculate_global_pooling(self, x):
        gap = torch.nn.functional.adaptive_avg_pool2d(x, 1)
        cam_logit = self.gap_fc(gap.view(x.shape[0], -1)) if not self.training else checkpoint(self.gap_fc,gap.view(x.shape[0], -1))
        gap = list(self.gap_fc.parameters())[0]
        gap = gap[1] - gap[0]
        gap = x * gap[None].unsqueeze(2).unsqueeze(3)

        gmp = torch.nn.functional.adaptive_max_pool2d(x, 1)
        cam_logit = torch.cat([cam_logit,self.gmp_fc(gmp.view(x.shape[0], -1))], 1) if not self.training else torch.cat([cam_logit,checkpoint(self.gmp_fc,gmp.view(x.shape[0], -1))], 1)
        gmp = list(self.gmp_fc.parameters())[0]
        gmp = gmp[1] - gmp[0]
        gmp = x * gmp[None].unsqueeze(2).unsqueeze(3)

        return torch.cat([gap, gmp], 1), cam_logit

    def _calculate_scale_shift(self,x):
        if self.light:
            x_ = torch.nn.functional.adaptive_avg_pool2d(x, 1)
            x_ = x_.view(x_.shape[0], -1)
            x_ = checkpoint(self.FC0,x_) if (self.training) else self.FC0(x_)
            x_ = self.FC(x_)
        else:
            x_ = x.view(x.shape[0], -1)
            x_ = self.FC0(x_)
            x_ = self.FC(x_)
        return self.gamma(x_), self.beta(x_)

    def forward(self, input):
        x = self.DownBlock0(input)
        for layer in self.DownBlock:
            x=layer(x) if isinstance(layer,nn.ReLU) or not self.training else checkpoint(layer,x)
        #x = checkpoint_sequential(self.DownBlock, 8, x) if (self.training) else self.DownBlock(x)
        x,cam_logit = self._calculate_global_pooling(x)
        x = self.relu(checkpoint(self.conv1x1,x) if self.training else self.conv1x1(x))

        heatmap = torch.sum(x, dim=1, keepdim=True)
        x = self.big_IN(x)

        gamma, beta = self._calculate_scale_shift(x)


        for i in range(self.n_blocks):
            x = getattr(self, 'UpBlock1_' + str(i+1))(x, gamma, beta) if i%2==0 or not self.training else checkpoint(getattr(self, 'UpBlock1_' + str(i+1)),x, gamma, beta)
        #x = self.UpBlock2(x) #(+self.out_shift)/self.out_scale
        for layer in self.UpBlock2:
            x = layer(x) if isinstance(layer,nn.ReLU) or not self.training else checkpoint(layer,x)

        return x, cam_logit, heatmap


# Cell
class ResnetAdaILNBlock(nn.Module):
    def __init__(self, dim, use_bias):
        super(ResnetAdaILNBlock, self).__init__()
        self.pad1 = nn.ReflectionPad2d(1)
        self.conv1 = nn.Conv2d(dim, dim, kernel_size=3, stride=1, padding=0, bias=use_bias)
        self.norm1 = adaILN(dim)
        self.relu1 = nn.ReLU(True)

        self.pad2 = nn.ReflectionPad2d(1)
        self.conv2 = nn.Conv2d(dim, dim, kernel_size=3, stride=1, padding=0, bias=use_bias)
        self.norm2 = adaILN(dim)

    def forward(self, x, gamma, beta):
        out = self.pad1(x)
        out = self.conv1(out)
        out = self.norm1(out, gamma, beta)
        out = self.relu1(out)
        out = self.pad2(out)
        out = self.conv2(out)
        out = self.norm2(out, gamma, beta)

        return out + x


# Cell
class adaILN(nn.Module):
    def __init__(self, num_features, eps=1e-5):
        super(adaILN, self).__init__()
        self.eps = eps
        self.rho = Parameter(torch.Tensor(1, num_features, 1, 1))
        self.rho_sigmoid=nn.Sigmoid()
        self.rho.data.fill_(0.0)
        self.IN = nn.InstanceNorm2d(num_features,affine=False)
        #self.LN = nn.LayerNorm(num_features,elementwise_affine=False)

    def forward(self, input, gamma, beta):
        out = self.IN(input)
        out = self.rho_sigmoid(self.rho).expand(input.shape[0], -1, -1, -1) * out
        out_ln = F.layer_norm(
            input, input.shape[1:], None,None, self.eps)
        #rho=self.rho_sigmoid(self.rho.expand(input.shape[0], -1, -1, -1))
        out_ln = (1-self.rho_sigmoid(self.rho).expand(input.shape[0], -1, -1, -1)) * out_ln
        out = out + out_ln
        out = out * gamma.unsqueeze(2).unsqueeze(3)
        out = out + beta.unsqueeze(2).unsqueeze(3)

        return out.to(input.dtype)


# Cell
class ILN(nn.Module):
    def __init__(self, num_features, eps=1e-5):
        super(ILN, self).__init__()
        self.eps = eps
        self.rho = Parameter(torch.Tensor(1, num_features, 1, 1))
        self.rho_sigmoid=nn.Sigmoid()
        self.gamma = Parameter(torch.Tensor(1, num_features, 1, 1))
        self.beta = Parameter(torch.Tensor(1, num_features, 1, 1))
        self.rho.data.fill_(0.0)
        self.gamma.data.fill_(1.0)
        self.beta.data.fill_(0.0)
        self.IN = nn.InstanceNorm2d(num_features,affine=False)

    def _iln(self,input):
        out = self.IN(input)
        out = self.rho_sigmoid(self.rho.expand(input.shape[0], -1, -1, -1)) * out
        out_ln = F.layer_norm(
            input, input.shape[1:], None,None, self.eps)
        out_ln = (1-self.rho_sigmoid(self.rho).expand(input.shape[0], -1, -1, -1)) * out_ln
        return out + out_ln

    def forward(self, x):
        dtype=x.dtype
        x = self._iln(x)
        x = x * self.gamma.expand(x.shape[0], -1, -1, -1)
        x = x + self.beta.expand(x.shape[0], -1, -1, -1)

        return x.to(dtype)


# Cell
class Discriminator(nn.Module):
    def __init__(self, input_nc, ndf=64, n_layers=5):
        super(Discriminator, self).__init__()
        model = [nn.ReflectionPad2d(1),
                 nn.utils.spectral_norm(
                 nn.Conv2d(input_nc, ndf, kernel_size=4, stride=2, padding=0, bias=True)),
                 nn.LeakyReLU(0.2, True)]

        for i in range(1, n_layers - 2):
            mult = 2 ** (i - 1)
            model += [nn.ReflectionPad2d(1),
                      nn.utils.spectral_norm(
                      nn.Conv2d(ndf * mult, ndf * mult * 2, kernel_size=4, stride=2, padding=0, bias=True)),
                      nn.LeakyReLU(0.2, True)]

        mult = 2 ** (n_layers - 2 - 1)
        model += [nn.ReflectionPad2d(1),
                  nn.utils.spectral_norm(
                  nn.Conv2d(ndf * mult, ndf * mult * 2, kernel_size=4, stride=1, padding=0, bias=True)),
                  nn.LeakyReLU(0.2, True)]

        # Class Activation Map
        mult = 2 ** (n_layers - 2)
        self.gap_fc = nn.utils.spectral_norm(nn.Linear(ndf * mult, 1, bias=False))
        self.gmp_fc = nn.utils.spectral_norm(nn.Linear(ndf * mult, 1, bias=False))
        self.conv1x1 = nn.Conv2d(ndf * mult * 2, ndf * mult, kernel_size=1, stride=1, bias=True)
        self.leaky_relu = nn.LeakyReLU(0.2, True)

        self.pad = nn.ReflectionPad2d(1)
        self.conv = nn.utils.spectral_norm(
            nn.Conv2d(ndf * mult, 1, kernel_size=4, stride=1, padding=0, bias=False))

        self.model = nn.Sequential(*model)

    def forward(self, input):
        x = self.model[0](input)
        for layer in self.model[1:]:
            x=layer(x) if isinstance(layer,nn.LeakyReLU) or self.training else checkpoint(layer,x)
        #x = checkpoint_sequential(self.model[1:],10,x)

        gap = torch.nn.functional.adaptive_avg_pool2d(x, 1)
        gap_logit = self.gap_fc(gap.view(x.shape[0], -1)) if not self.training else checkpoint(self.gap_fc,gap.view(x.shape[0], -1))
        gap_weight = list(self.gap_fc.parameters())[0]
        gap = x * gap_weight.unsqueeze(2).unsqueeze(3)

        gmp = torch.nn.functional.adaptive_max_pool2d(x, 1)
        gmp_logit = self.gmp_fc(gmp.view(x.shape[0], -1)) if not self.training else checkpoint(self.gmp_fc,gmp.view(x.shape[0], -1))
        gmp_weight = list(self.gmp_fc.parameters())[0]
        gmp = x * gmp_weight.unsqueeze(2).unsqueeze(3)

        cam_logit = torch.cat([gap_logit, gmp_logit], 1)
        x = torch.cat([gap, gmp], 1)
        x = self.leaky_relu(self.conv1x1(x))

        heatmap = torch.sum(x, dim=1, keepdim=True)

        x = self.pad(x)
        out = self.conv(x)

        return out, cam_logit, heatmap


# Cell
class RhoClipper(object):

    def __init__(self, min, max, on=False):
        self.clip_min = min
        self.clip_max = max
        self.on=on
        assert min < max

    def __call__(self, module):

        if self.on and hasattr(module, 'rho'):
            w = module.rho.data
            w = w.clamp(self.clip_min, self.clip_max)
            module.rho.data = w
