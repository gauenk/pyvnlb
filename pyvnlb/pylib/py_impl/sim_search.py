
import cv2
import numpy as np
from einops import rearrange
from numba import njit,jit,prange
from pyvnlb.pylib.tests import save_images

def runSimSearch(noisy,sigma,pidx,tensors,params,step=0):

    # -- extract info for explicit call --
    ps = params['sizePatch'][step]
    ps_t = params['sizePatchTime'][step]
    npatches = params['nSimilarPatches'][step]
    nwindow_xy = params['sizeSearchWindow'][step]
    nfwd = params['sizeSearchTimeFwd'][step]
    nbwd = params['sizeSearchTimeBwd'][step]
    nwindow_t = nfwd + nbwd + 1
    couple_ch = params['coupleChannels'][step]
    step1 = params['isFirstStep'][step]

    # -- extract tensors --
    fflow = tensors['fflow']
    bflow = tensors['bflow']
    # print("fflow.shape: ",fflow.shape)

    # -- color transform --
    noisy = apply_color_xform_cpp(noisy)

    # -- find the best patches using c++ logic --
    values,indices = exec_cpp_sim_search(pidx,noisy,fflow,bflow,sigma,ps,ps_t,
                                         npatches,nwindow_xy,nfwd,nbwd,couple_ch,step1)

    # -- group the values and indices --
    # print(indices,pidx)

    # -- patches to groups --
    groups = None#patches2groups(patches)

    return groups,values,indices

def apply_color_xform_cpp(burst):
    """
    rgb -> yuv [using cpp logic]
    """
    burst_yuv = []
    # burst = rearrange(burst,'t c h w -> t h w c')
    t,h,w,c = burst.shape
    for ti in range(t):

        # -- init --
        image = burst[ti]
        image_yuv = np.zeros_like(image)
        weights = [1./np.sqrt(3),1./np.sqrt(2),2./np.sqrt(3)*np.sqrt(2.)]

        # -- rgb -> yuv --
        image_yuv[0] = weights[0] * (image[0] + image[1] + image[2])
        image_yuv[1] = weights[1] * (image[0] - image[2])
        image_yuv[2] = weights[2] * (.25 * image[0] - 0.5 * image[1] + .25 * image[2])

        # -- append --
        burst_yuv.append(image_yuv)
    burst_yuv = np.stack(burst_yuv)

    return burst_yuv

def apply_color_xform(burst):
    """
    rgb -> yuv
    """
    burst_yuv = []
    burst = rearrange(burst,'t c h w -> t h w c')
    t,h,w,c = burst.shape
    for ti in range(t):
        image_yuv = cv2.cvtColor(burst[ti], cv2.COLOR_RGB2YUV)
        burst_yuv.append(image_yuv)
    burst_yuv = np.stack(burst_yuv)
    burst_yuv = rearrange(burst_yuv,'t h w c -> t c h w')
    return burst_yuv

def idx2coords(idx,width,height,color):

    # -- get shapes --
    whc = width*height*color
    wh = width*height

    # -- compute coords --
    t = (idx      ) // whc
    c = (idx % whc) // wh
    y = (idx % wh ) // width
    x = idx % width

    return t,c,y,x


def exec_cpp_sim_search(pidx,noisy,fflow,bflow,sigma,ps,ps_t,
                        npatches,nwindow_xy,nWt_f,nWt_b,couple_ch,step1):

    # -- init shapes --
    t,c,h,w = noisy.shape
    patches = np.zeros((npatches,ps_t,c,ps,ps))
    vals = np.ones((t-ps_t+1,nwindow_xy,nwindow_xy),dtype=np.float32)*np.inf
    indices = np.zeros((t-ps_t+1,nwindow_xy,nwindow_xy),dtype=np.int32)

    # -- search --
    # print("-"*30)
    numba_cpp_sim_search(pidx,vals,indices,noisy,fflow,bflow,sigma,
                         ps,ps_t,npatches,nwindow_xy,nWt_f,nWt_b,couple_ch,step1)

    # -- remove ref frame --
    # t_c = coords(pidx,w,h,c)[0]
    # ncat = np.concatenate
    # print(deltas[:t_c].shape)
    # deltas = ncat([deltas[:t_c],deltas[t_c+1:]],axis=0)
    # print("deltas.shape: ",deltas.shape)
    # save_images("sim_search.png",deltas[:,None])
    # print(deltas)
    # checks = [1095,37824]
    # for idx in checks:
    #     i_idx = np.where(indices == idx)
    #     print(i_idx)
    #     print("vals[%d]: %2.3f" % (idx,vals[i_idx]))

    # -- argmin --
    vals_f = vals.ravel()
    vindices = np.argsort(vals_f)[:npatches]
    vals = vals_f[vindices]
    indices = indices.ravel()[vindices]

    return vals,indices

@njit
def numba_cpp_sim_search(pidx,vals,indices,noisy,fflow,bflow,sigma,
                         ps,ps_t,npatches,nWxy,nWt_f,nWt_b,couple_ch,step1):
    # -- init shapes --
    t,c,h,w = noisy.shape
    nframes,color,height,width = t,c,h,w
    chnls = 1 if step1 else color

    def coords2pix(hi,wi,ti):
        pix = ti * width * height * color
        pix += hi * width
        pix += wi
        return pix

    def coords(idx):

        # -- get shapes --
        whc = width*height*color
        wh = width*height

        # -- compute coords --
        t = (idx      ) // whc
        c = (idx % whc) // wh
        y = (idx % wh ) // width
        x = idx % width

        return t,c,y,x

    # -- "center" coords at index "pidx" --
    t_c,c_c,h_c,w_c = coords(pidx)
    # print(t_c,c_c,h_c,w_c)

    # int shift_t = std::min(0, (int)pt -  sWt_b)
    # + std::max(0, (int)pt +  sWt_f - (int)sz.frames + sPt);
    # ranget[0] = std::max(0, (int)pt - sWt_b - shift_t);
    # ranget[1] = std::min((int)sz.frames - sPt, (int)pt +  sWt_f - shift_t);

    # -- search --
    npatch = 0
    shift_t = min(0,t_c - nWt_b) + max(0,t_c + nWt_f - t + ps_t)
    t_start = max(t_c - nWt_b - shift_t,0)
    t_end = min(t - ps_t, t_c + nWt_f - shift_t)+1
    t_idx = 0

    # -- states --
    cw_vals = np.zeros(t_end-t_start+1,dtype=np.int32)
    ch_vals = np.zeros(t_end-t_start+1,dtype=np.int32)
    ct_vals = np.zeros(t_end-t_start+1,dtype=np.int32)

    # print("example: ",noisy[2,0,20,23],2,0,20,23)
    # print("example: ",noisy[2,0,23,20],2,0,23,20)
    # print("ps: %d" % ps)
    # print("t_c,c_c,h_c,w_c: (%d,%d,%d,%d)" % (t_c,c_c,h_c,w_c))

    # ---------------------
    # for (int qt = pt+1; qt <= ranget[1]; ++qt) srch_ranget.push_back(qt);
    # for (int qt = pt-1; qt >= ranget[0]; --qt) srch_ranget.push_back(qt);
    # ---------------------

    # print("ranget: (%d,%d,%d)" % (t_start,t_end,shift_t))
    # print(t_c)
    # print(np.arange(t_c+1,t_end))
    # print(np.arange(t_c-1,t_start-1,-1))
    trange = [t_c]
    trange_s = np.arange(t_c+1,t_end)
    trange_e = np.arange(t_start,t_c)[::-1]
    for t_i in range(trange_s.shape[0]):
        trange.append(trange_s[t_i])
    for t_i in range(trange_e.shape[0]):
        trange.append(trange_e[t_i])
    # trange = np.concatenate([np.array([t_c],np.int32),np.arange(t_c+1,t_end),],axis=0)
    # trange = np.roll(trange,shift_t)
    # print(trange)
    # exit()

    # -- start search --
    for t_i in trange:

        # -------------------------------------

	# int dt = qt - ranget[0]; // search region frame number
	# int dir = std::max(-1, std::min(1, qt - (int)pt)); // direction (forward or backwards from pt)

        # "previous"
	# int cx0 = cx[dt - dir];
	# int cy0 = cy[dt - dir];
	# int ct0 = ct[dt - dir];

        # "update values"
	# float cx_f = cx0 + (use_flow ? (dir > 0 ? fflow(cx0,cy0,ct0,0) : bflow(cx0,cy0,ct0,0)) : 0.f);
	# float cy_f = cy0 + (use_flow ? (dir > 0 ? fflow(cx0,cy0,ct0,1) : bflow(cx0,cy0,ct0,1)) : 0.f);

        # "current"
	# cx[dt] = std::max(0.f, std::min((float)sz.width  - 1, roundf(cx_f)));
	# cy[dt] = std::max(0.f, std::min((float)sz.height - 1, roundf(cy_f)));
	# ct[dt] = qt;

        # -------------------------------------

        # -- centering --
        t_idx = t_i - min(trange)
        direction = max(-1,min(1,t_i - t_c))
        # print("(t_i,t_idx,dir): (%d,%d,%d)" % (t_i,t_idx,direction))
        if direction != 0:
            cw0 = cw_vals[t_idx-direction]
            ch0 = ch_vals[t_idx-direction]
            ct0 = ct_vals[t_idx-direction]

            flow = fflow if direction > 0 else bflow

            # print(cw0,ch0,ct0)
            cw_f = cw0 + flow[ct0,0,ch0,cw0]
            ch_f = ch0 + flow[ct0,1,ch0,cw0]
            # print("(cw0,ch0,ct0): (%d,%d,%d)" % (cw0,ch0,ct0))
            # print("(cw_f,ch_f,dir): (%2.3f,%2.3f)" % (cw_f,ch_f))

            cw = max(0,min(w-1,round(cw_f)))
            ch = max(0,min(h-1,round(ch_f)))
            ct = t_idx

        else:
            cw = w_c
            ch = h_c
            ct = t_c

        # -- update --
        cw_vals[t_idx] = cw
        ch_vals[t_idx] = ch
        ct_vals[t_idx] = ct

        # -- grab patches --
        # fwd_l = fflow[ti,ci,hl,wl]
        # fwd_k = fflow[ti,ci,hk,wk]
        # bwd_l = bflow[ti,ci,hl,wl]
        # bwd_k = bflow[ti,ci,hk,wk]

        # ------------------------

	# int shift_x = std::min(0, cx[dt] - (sWx-1)/2);
	# int shift_y = std::min(0, cy[dt] - (sWy-1)/2);

	# shift_x += std::max(0, cx[dt] + (sWx-1)/2 - (int)sz.width  + sPx);
	# shift_y += std::max(0, cy[dt] + (sWy-1)/2 - (int)sz.height + sPx);

	# rangex[0] = std::max(0, cx[dt] - (sWx-1)/2 - shift_x);
	# rangey[0] = std::max(0, cy[dt] - (sWy-1)/2 - shift_y);

	# rangex[1] = std::min((int)sz.width  - sPx, cx[dt] + (sWx-1)/2 - shift_x);
	# rangey[1] = std::min((int)sz.height - sPx, cy[dt] + (sWy-1)/2 - shift_y);

        # ------------------------

        # -- shifts --
        shift_w = min(0,cw - (nWxy-1)//2) + max(0,cw + (nWxy-1)//2 - w  + ps)
        shift_h = min(0,ch - (nWxy-1)//2) + max(0,ch + (nWxy-1)//2 - h  + ps)
        # shift_h = max(0,ch + (nWxy-1)//2 - h  + ps)

        # -- spatial endpoints --
        h_start = max(0,ch - (nWxy-1)//2 - shift_h)
        h_end = min(h-ps,ch + (nWxy-1)//2 - shift_h)+1

        w_start = max(0,cw - (nWxy-1)//2 - shift_w)
        w_end = min(w-ps,cw + (nWxy-1)//2 - shift_w)+1

        # if t_idx == 2:
        #     w_start = 4
        #     w_end = 30+1
        # elif t_idx == 3:
        #     w_start = 0
        #     w_end = 26+1
        # -- for each in spatial windows --
        # h_start = 1
        # w_start = 0
        # h_end = 28
        # w_end = 27

	# int dt = qt - ranget[0]; // search region frame number
	# int dir = std::max(-1, std::min(1, qt - (int)pt)); // direction (forward or backwards from pt)


        # print("rangex[0,1]: (%d,%d,%d,%d)" % (w_start,w_end,shift_w,cw))
        # print("rangey[0,1]: (%d,%d,%d,%d)" % (h_start,h_end,shift_h,ch))
        h_range = np.arange(h_start,h_end)
        w_range = np.arange(w_start,w_end)
        for h_idx in prange(len(h_range)):
            h_i = h_range[h_idx]
            for w_idx in prange(len(w_range)):
                w_i = w_range[w_idx]
                # pix_idx = coords2pix(h_i,w_i,t_i)

                # -- compute patch deltas --
                delta = 0.
                for pt in range(ps_t):
                    for pi in range(ps):
                        for pj in range(ps):
                            for c_i in range(chnls):
                                pix_l = noisy[t_c+pt,c_i,h_c+pi,w_c+pj]/255.
                                pix_k = noisy[t_i+pt,c_i,h_i+pi,w_i+pj]/255.
                                delta += (pix_l - pix_k)**2.
                vals[t_idx,h_idx,w_idx] = delta/(ps*ps*ps_t*chnls)
                indices[t_idx,h_idx,w_idx] = coords2pix(h_i,w_i,t_i)
