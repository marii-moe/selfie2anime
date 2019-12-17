#AUTOGENERATED! DO NOT EDIT! File to edit: dev/UGATIT_Original.ipynb (unless otherwise specified).

__all__ = ['fakemodule', 'path', 'path']

#Cell
from functools import partial
import numpy as np
from pathlib import Path
path=Path("/home/fast/.fastai/data/selfie2anime")
"""
Uncomment this to completely fake data
path=Path("/home/fast/fastai_dev/anime/")

if((path/'ugatit').exists()):
    x=np.load(str(path/'ugatit.npy'))
else:
    x=np.random.normal(0,1,[2,2,3,128,128])
    np.save(str(path/'ugatit'),x)
"""
class fakemodule(object):
    def get_worker_info():
        return 0
"""    def ImageFolder(path,transforms):
        return path
    class DataLoader():
        def __init__(self,dataset, batch_size=2, shuffle=True):
            self.dataset=dataset
            if(dataset=='dataset/trainA' or dataset=='dataset/testA'):
                self.x=x[0]
            else:
                self.x=x[1]
        def __iter__(self):
            return self
        def __next__(self):
            return self.next()
        def next(self):
            return (torch.FloatTensor(self.x),0) #unused label
    def _DatasetKind():
        return 0
"""

import sys

sys.modules["cv2"] = fakemodule
#Uncomment this as well to completely fake input
#sys.modules["torch.utils.data.dataloader"] = fakemodule
#sys.modules["dataset"] = fakemodule

from fast.torch_basics import *

from UGATIT import UGATIT
from networks import *