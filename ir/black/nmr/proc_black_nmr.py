"""Read Bruker processed spectra (pdata/1/1r), calibrate on CDCl3, list peaks/integrals."""
import sys, re, os, json
import numpy as np
from scipy.signal import find_peaks
def par(f):
    d={}
    for line in open(f,encoding='latin-1'):
        m=re.match(r'##\$(\w+)= *(.*)',line)
        if m: d[m.group(1)]=m.group(2).strip()
    return d
def load(exp):
    p=par(os.path.join(exp,'pdata/1/procs'))
    si=int(p['SI']); off=float(p['OFFSET']); sw=float(p['SW_p']); sf=float(p['SF']); nc=int(p['NC_proc'])
    dt='<i4' if p.get('BYTORDP','0')=='0' else '>i4'
    y=np.fromfile(os.path.join(exp,'pdata/1/1r'),dtype=dt).astype(float)*2.0**nc
    x=off-np.arange(si)*(sw/sf)/si
    return x,y
def calib(x,y,ref,win):
    m=(x>ref-win)&(x<ref+win); return x[m][np.argmax(y[m])]
if __name__=="__main__":
    root=sys.argv[1]; out=sys.argv[2]
    res={}
    # 1H
    x,y=load(os.path.join(root,'NVM-tk-BD/1'))
    c=calib(x,y,7.26,0.15); x=x+(7.26-c); print("1H shift applied",round(7.26-c,3))
    np.save(os.path.join(out,'H1_ppm.npy'),x); np.save(os.path.join(out,'H1_int.npy'),y)
    noise=np.std(y[(x>9)&(x<11)]); p,_=find_peaks(y,height=20*noise,distance=5)
    print("1H peaks:",[(round(x[i],3),round(y[i]/y.max(),4)) for i in p if -0.5<x[i]<9])
    def integ(a,b): m=(x>=a)&(x<=b); return float(np.trapezoid(y[m][::-1],x[m][::-1]))
    regs={"arom 7.65-7.80":(7.62,7.80),"arom 7.45-7.60":(7.44,7.60),"OCH2 4.20-4.40":(4.20,4.42),"CH2 1.65-1.80":(1.62,1.80),"CH2 1.35-1.52":(1.33,1.52),"CH3 0.90-1.02":(0.88,1.03),
          "4.0-4.2":(4.0,4.2),"3.5-4.0":(3.5,4.0),"2.0-3.5":(2.0,3.5),"1.20-1.33":(1.20,1.33),"0.80-0.88":(0.80,0.88),"5.0-7.2":(5.0,7.2),"8.0-9.0":(8.0,9.0)}
    I={k:integ(*v) for k,v in regs.items()}; ref=I["OCH2 4.20-4.40"]/4
    print("1H integrals (OCH2=4H):",{k:round(v/ref,3) for k,v in I.items()})
    res['H']={k:round(v/ref,3) for k,v in I.items()}
    # 13C
    x,y=load(os.path.join(root,'NVM-tk-BD/2'))
    c=calib(x,y,77.16,1.5)
    m=(x>75)&(x<79); xs=x[m]; ys=y[m]; pk,_=find_peaks(ys,height=ys.max()*0.3); trip=sorted(xs[pk])
    print("CDCl3 lines",[round(v,3) for v in trip])
    centre=np.median(trip) if len(trip)==3 else c
    x=x+(77.16-centre); print("13C shift applied",round(77.16-centre,3))
    np.save(os.path.join(out,'C13_ppm.npy'),x); np.save(os.path.join(out,'C13_int.npy'),y)
    noise=np.std(y[(x>190)&(x<220)]); p,_=find_peaks(y,height=6*noise,distance=3)
    pk=[(round(x[i],2),round(y[i]/noise,1)) for i in p if 0<x[i]<200]
    print("13C peaks (ppm, S/N):",pk); res['C']=pk
    json.dump(res,open(os.path.join(out,'nmr_black_summary.json'),'w'),ensure_ascii=False,indent=1)
