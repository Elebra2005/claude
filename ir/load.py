import numpy as np, glob, os
from scipy.signal import find_peaks, savgol_filter
UP="/root/.claude/uploads/fc5e71b2-a817-5fe5-94d5-3f81e7042ced/"
NAMES={"1p":"9ec164e8-buryak_1p.csv","1t":"a4e1aced-buryak_1t.csv","2t":"d3295c78-buryak_2t.csv","2x":"ee35fb25-buryak_2x.csv"}
def load(k):
    d=np.loadtxt(UP+NAMES[k],delimiter=';',skiprows=2,encoding='latin-1')
    return d[:,0],d[:,1]
