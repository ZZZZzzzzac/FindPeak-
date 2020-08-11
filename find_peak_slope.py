import numpy as np
import matplotlib.pyplot as plt 
import pandas as pd
from rd import Reader
from zacLib import nextpow2,mySmooth
import matplotlib

def rd_reader(file,nframe=1,pos=0):
    read = Reader(file)
    fs = read.header.dump()['sampling']['sample_rate']
    framesize = read.header.frame_size
    return read.read(1,pos,nframe*framesize).reshape(nframe,framesize),fs

def fft(signal,nfft):    
    t1 = np.fft.fft(signal,nfft)
    t2 = t1.sum(axis=0)
    t3 = np.abs(t2)
    t4 = np.log10(t3)[:nfft//2]
    return t4

def dev(x,n=1):
    # this function calculate derivative/slope x' of x, 
    # current algorithm use `(sum of right n point) - (sum of left n point)`
    # i.e. : x'[i] = x[i+1:i+n+1].sum() -  x[i-n:n].sum()
    # this algorithm is equivalent to smooth with n point flat kernel then get smoothed[i+n]-smoothed[i-n]
    # when n is too small, it may miss some low slope signal
    # when n is too large, narrow band signal may be flatten
    # TODO: find a more accurate and noise insensitive way to calculate slope
    y = np.zeros(x.size,dtype=x.dtype)
    cx = np.cumsum(x)
    dcx = cx[n:]-cx[:-n] # cx[n:]-cx[:-n] is equivalent to mySmooth(x,n,0)
    y[n+1:-n] = dcx[n+1:] - dcx[:-n-1]
    y[n] = dcx[n] - cx[n-1]
    return y

def get_edge(x,th,thp):
    # Iterate along x once, so it is O(n). It's actually a state machine
    # state "Nethier", -th+thp < x[i] < th-thp <= this `thp` to prevent noise in x from creating fake peak
    # state "Rising", x[i] > th
    # state "Falling", x[i] < -th
    # state transfer: 
    # "N"->"N", "N"->"R" and "N"->"F": pass
    # "R"->"R": update maxPeak; "F"->"F": update minPeak
    # "R"->"N", last rising edge ends, append maxPeak location then reset maxPeak
    # "F"->"N", last falling edge ends, append minPeak location then reset minPeak
    # when append maxPeak, `len(ploc)-len(vloc)==1` means two rising edge in a row, choose last one
    # when append minPeak, `len(ploc)=len(vloc)` means two falling edge in a row, keep first one
    ploc=[]
    vloc=[]
    maxPeak = 0
    minPeak = 0
    pl = 0
    vl = 0
    current = 'neither'
    for i,d in enumerate(x):
        if d>th:
            # print("R",i,d,maxPeak,pl)
            current = 'rising'
            if d>maxPeak:
                maxPeak = d
                pl = i
        elif d<-th:
            # print("F",i,d,minPeak,vl)
            current = 'falling'
            if d<minPeak:
                minPeak = d
                vl = i
        elif d<th-thp and d>-th+thp: # prevent noise in x from creating fake peak
            if current == 'rising':
                if len(ploc)-len(vloc)==1: # two rising edge
                    # print("{:}=>{:}".format(ploc[-1],pl))
                    ploc[-1] = pl # choose last one
                else:
                    # print("append pl ",pl)
                    ploc.append(pl)
                maxPeak = 0
            elif current == 'falling':
                if len(ploc)-len(vloc)==1: # not two falling edge
                    # print("append vl ",vl)
                    vloc.append(vl) # keep first one
                minPeak = 0
            current = 'neither'
    if len(ploc)-len(vloc)==1:ploc.pop()
    return np.array(ploc),np.array(vloc)

def sample2frequency(sm,new_peak,new_pits):
    npeak = len(new_peak)
    avg_frq = (new_peak+new_pits)//2
    max_frq = np.zeros(npeak,dtype=int)
    dev_band = new_pits-new_peak
    half_left = np.zeros(npeak,dtype=int)
    half_right = np.zeros(npeak,dtype=int)
    def get_nearest_minimum(x,i,direction='left'):
        if direction == 'left':
            while i>1:
                if x[i-1]>x[i] and x[i]<x[i+1]:
                    break
                i-=1
            return i
        elif direction == 'right':
            while i<x.size-1:
                if x[i-1]>x[i] and x[i]<x[i+1]:
                    break
                i+=1
            return i
        else:
            return None
    for i,(up,down) in enumerate(zip(new_peak,new_pits)):   
        max_frq[i] = up + sm[up:down].argmax()
        maxi = sm[max_frq[i]]
        # TODO: half_left/right not very accurate, nearest minimum is not best method to find height reference
        left_min = get_nearest_minimum(sm,up,'left') 
        right_min = get_nearest_minimum(sm,down,'right')
        mini = max(sm[left_min],sm[right_min])
        height = (maxi+mini)/2
        left_idx = up
        while sm[left_idx]<height:
            left_idx+=1
        right_idx = down
        while sm[right_idx]<height:
            right_idx-=1
        half_left[i] = left_idx
        half_right[i] = right_idx
    return avg_frq,max_frq,dev_band,half_left,half_right,half_right-half_left

def plot_all(sp,sm,dsp,slope_th,
             new_peak,new_pits,avg_frq,max_frq,dev_band,half_left,half_right,f=1):    
    matplotlib.use("Qt5Agg")
    f_axis = np.arange(sm.size)*f
    plt.figure()
    ax1 = plt.subplot(211)
    # plt.plot(sp,'.',markersize=1,label='Raw') # if sp.size>1e6, plot sp as scatter will be very slow
    plt.plot(f_axis,sm,label='Smoothed')
    plt.plot(new_peak*f,sm[new_peak],'r^',label='rising')
    plt.plot(new_pits*f,sm[new_pits],'gv',label='falling')
    plt.plot(half_left*f,sm[half_left],'b>',label='half_left')
    plt.plot(half_right*f,sm[half_right],'b<',label='half_right')
    plt.plot(avg_frq*f,sm[avg_frq],'d',label='avg_peak')
    plt.plot(max_frq*f,sm[max_frq],'s',label='max_peak')
    plt.legend(loc='right')
    plt.subplot(212,sharex=ax1)
    plt.plot(f_axis,dsp)
    plt.plot(f_axis,np.ones(sm.size)*slope_th,'--')
    plt.plot(f_axis,np.ones(sm.size)*-slope_th,'--')
    plt.plot(new_peak*f,dsp[new_peak],'r^',markersize=4)
    plt.plot(new_pits*f,dsp[new_pits],'gv',markersize=4)
    plt.show()

def find_peak_slope(sp,width,slope_th):    
    # padding zeros due to dev() cannot calculate derivative at both end
    # sp = np.concatenate([np.ones(width)*sp[0],sp,np.ones(width)*sp[-1]])
    sm = mySmooth(sp,width,n=1) # n control shape of smooth kernel (lager n, kernel is more like gaussian(bell) shape)
    dsp = dev(sp,width) # calculate derivative/slope
    new_peak,new_pits = get_edge(dsp,slope_th,slope_th/10)   
    print(new_peak,new_pits)
    avg_frq,max_frq,dev_band,half_left,half_right,half_band = sample2frequency(sm,new_peak,new_pits)
    return sm,dsp,new_peak,new_pits,avg_frq,max_frq,dev_band,half_left,half_right,half_band

def find_peak_slope_from_rd(file,width,slope_th,nframe=10,pos=10):
    signal,fs = rd_reader('siga.rd',nframe=10,pos=10) # Import data
    framesize = signal.shape[1]
    nfft = nextpow2(framesize,n=0) 
    sp = fft(signal,nfft) # get spectrum (fft)
    # Main function find_peak_slope
    sm,dsp,new_peak,new_pits,avg_frq,max_frq,\
        dev_band,half_left,half_right,half_band = find_peak_slope(sp,width,slope_th)

    # result representation
    # f = 1/nfft*2*fs/1e6 # using frequency as x-axis
    f = 1 # using sample points as x-axis
    plot_all(sp,sm,dsp,slope_th,new_peak,new_pits,avg_frq,max_frq,dev_band,half_left,half_right,f)
    df = pd.DataFrame({ 'avg_frq':avg_frq*f,'max_frq':max_frq*f,
                        'slope band':dev_band*f,
                        'half_band':half_band*f})
    return df

