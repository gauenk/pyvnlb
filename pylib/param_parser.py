
import torch
import numpy as np
from einops import rearrange
from easydict import EasyDict as edict
from collections.abc import Iterable

import vnlb

# from .ptr_utils import py2swig
from .image_utils import est_sigma

def optional(pydict,key,default,dtype=None):
    # -- get elem --
    rtn = default
    if pydict is None: rtn = default
    elif key in pydict: rtn = pydict[key]

    # -- convert to swig --
    if isinstance(rtn,Iterable):        
        if isinstance(rtn,list):
            if dtype is None: dtype = np.float32
            rtn = np.array(rtn,dtype=dtype)
        return vnlb.swig_ptr(rtn)
    else:
        return rtn

def set_optional_params(args,pyargs):
    # -- set optional numeric vals --
    args.ps = optional(pyargs,'ps',3)
    args.k = optional(pyargs,'k',1)
    args.use_clean = optional(pyargs,'clean',None) != None
    args.use_flow = optional(pyargs,'flow',None) != None
    args.search_space = optional(pyargs,'search_space',[3,3],np.uint32)
    args.num_patches = optional(pyargs,'num_patches',[3,3],np.uint32)
    args.rank = optional(pyargs,'rank',[49,49],np.uint32)
    args.thresh = optional(pyargs,'thresh',[1e-1,1e-2])
    args.beta = optional(pyargs,'beta',[1e-1,1e-2])
    args.flat_areas = optional(pyargs,'flat_areas',[True,True],bool)
    args.couple_ch = optional(pyargs,'couple_ch',[True,True],bool)
    args.aggeBoost = optional(pyargs,'agge_boost',[True,True],bool)
    args.patch_step = optional(pyargs,'patch_step',[4,4],np.uint32)
    args.verbose = True
    args.print_params = 1
    
def np_zero_tensors(t,h,w,c):
    tensors = edict()
    tensors.flow = np.zeros((w,h,2,t),dtype=np.float32)
    tensors.oracle = np.zeros((w,h,2,t),dtype=np.float32)
    tensors.clean = np.zeros((w,h,c,t),dtype=np.float32)
    tensors.basic = np.zeros((w,h,c,t),dtype=np.float32)
    tensors.final = np.zeros((w,h,c,t),dtype=np.float32)
    return tensors

def set_tensors(args,pyargs,tensors):
    args.fflow = optional(pyargs,'flow',tensors.flow)
    args.oracle = optional(pyargs,'oracle',tensors.oracle)
    args.clean = optional(pyargs,'clean',tensors.clean)
    args.basic = optional(pyargs,'basic',tensors.basic)
    args.final = optional(pyargs,'final',tensors.final)

def init_args(noisy,sigma,pyargs):

    # -- extract info --
    verbose = optional(pyargs,'verbose',True)
    dtype = noisy.dtype
    t,h,w,c  = noisy.shape

    # -- format noisy image --
    noisy = rearrange(noisy,'t h w c -> w h c t')
    if dtype != np.float32 and verbose:
        print(f"Warning: converting noisy image from {dtype} to np.float32.")
        noisy = noisy.astype(np.float32)
    if not noisy.data.contiguous:
        noisy = np.ascontiguousarray(noisy)

    # -- get sigma --
    sigma = optional(pyargs,'sigma',None)
    if sigma is None:
        sigma = est_sigma(noisy)

    # -- params --
    args = vnlb.PyVnlbParams()

    # -- set required numeric values --
    args.noisy = vnlb.swig_ptr(noisy)
    args.w = w
    args.h = h
    args.c = c
    args.t = t
    args.sigma = vnlb.swig_ptr(np.array([sigma,sigma],dtype=np.float32))
    args.sigmaBasic = vnlb.swig_ptr(np.array([sigma,sigma],dtype=np.float32))
    
    # -- set optional params --
    set_optional_params(args,pyargs)

    return args