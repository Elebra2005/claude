import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import load
import numpy as np
from scipy.signal import find_peaks, savgol_filter
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.size":9,"axes.spines.top":False,"axes.spines.right":False,
    "axes.edgecolor":"#888","axes.labelcolor":"#333","xtick.color":"#555","ytick.color":"#555"})
HERE=os.path.dirname(os.path.abspath(__file__))
C_BLK="#2a78d6"; C_REF="#eb6834"
ZONES=[(3200,3600,"ν O–H","#9ec5f4"),
 (2800,3000,"ν C–H (CH₂, CH₃)","#cfcfcf"),
 (2540,2600,"ν S–H (тиокол)","#f6d36b"),
 (1700,1760,"ν C=O 1723","#f4a6a6"),
 (1595,1610,"аром. C=C 1600","#b9e4c9"),
 (1575,1590,"аром. 1580 (фталат)","#b9e4c9"),
 (1440,1470,"δ CH₂/CH₃ 1465","#d9d2f0"),
 (1405,1415,"S–CH₂ 1410 (тиокол)","#fbd3b0"),
 (1378,1392,"δ CH₃ 1385","#d9d2f0"),
 (1260,1300,"ν C(=O)–O 1285 (фталат)","#f4a6a6"),
 (1100,1135,"ν O–C–C 1120","#f4a6a6"),
 (1060,1080,"1072","#f4a6a6"),
 (1018,1030,"формаль 1024 (тиокол)","#cde2fb"),
 (935,965,"960/940 (н-бутил)","#d9d2f0"),
 (735,750,"o-замещ. бензол 742","#b9e4c9"),
 (560,650,"M–O неорг. (MnO₂?)","#e5e5e5")]
def absb(x,t):
    base=np.percentile(t[(x>2000)&(x<2600)],50); return -np.log10(np.clip(t/base,1e-3,None))
d=np.loadtxt(os.path.join(HERE,"buryak_shmurdyak_black.csv"),delimiter=';',skiprows=2,encoding='latin-1')
x,t=d[:,0],d[:,1]; m=x>=560; x,t=x[m],t[m]; A=absb(x,t)
p,_=find_peaks(savgol_filter(A,9,2),prominence=.004,distance=6)
peaks=[(int(x[i]),round(float(A[i]),3)) for i in p[::-1] if not (2000<x[i]<2200)]
json.dump(peaks,open(os.path.join(HERE,"peaks_black.json"),"w"))
def shade(ax,ytxt=1.005):
    tier=0
    for lo,hi,lab,c in ZONES:
        ax.axvspan(lo,hi,color=c,alpha=.45,lw=0,zorder=0)
        if hi>1800: y=ytxt
        else: y=ytxt+0.055*(tier%5); tier+=1
        xc=(lo+hi)/2
        if hi<=1800 and hi-lo<150:
            ax.plot([xc,xc],[1.0,y],color="#999",lw=.5,transform=ax.get_xaxis_transform(),clip_on=False)
        ax.text(xc,y,lab,ha="center",va="bottom",fontsize=6.8,color="#333",bbox=dict(fc="white",ec="none",pad=0.5),transform=ax.get_xaxis_transform())
# 1 spectrum
fig,ax=plt.subplots(figsize=(13,6.2)); shade(ax)
ax.plot(x,t,color=C_BLK,lw=1.4,zorder=3)
for i in p:
    if 2000<x[i]<2800: continue
    ax.annotate(f"{x[i]:.0f}",(x[i],t[i]),xytext=(0,-12),textcoords="offset points",ha="center",fontsize=7,rotation=90,va="top")
ax.set_xlim(4000,560); ax.set_ylim(20,102); ax.set_xlabel("Волновое число, см⁻¹"); ax.set_ylabel("Пропускание, %T")
ax.set_title("ИК-спектр (НПВО) — buryak_shmurdyak_black",loc="left",pad=120,fontsize=11)
ax.grid(axis="x",color="#eee",lw=.6); fig.tight_layout(); fig.savefig(os.path.join(HERE,"spectrum_black.png"),dpi=160); plt.close(fig)
# 2 overlay with thiokol 1t
x1,t1=load("1t"); mm=x1>=560; x1,t1=x1[mm],t1[mm]; A1=absb(x1,t1)
fig,ax=plt.subplots(figsize=(13,6.2)); shade(ax)
ax.plot(x1,A1,color=C_REF,lw=1.2,label="buryak_1t — чистый тиокол (эталон)",zorder=3)
ax.plot(x,A,color=C_BLK,lw=1.4,label="buryak_shmurdyak_black",zorder=4)
ax.set_xlim(4000,560); ax.set_xlabel("Волновое число, см⁻¹"); ax.set_ylabel("Оптическая плотность A")
ax.set_title("Сравнение с чистым тиоколом (buryak_1t)",loc="left",pad=120,fontsize=11); ax.legend(frameon=False,loc="upper left")
fig.tight_layout(); fig.savefig(os.path.join(HERE,"overlay_black_vs_1t.png"),dpi=160); plt.close(fig)
# 3 zooms
fig,axs=plt.subplots(2,2,figsize=(13,8))
for ax,(lo,hi,tt) in zip(axs.flat,[(1550,1800,"C=O 1723 и дублет ароматики 1600/1580 — признаки фталата"),
   (1000,1320,"Отпечаток: фталат (1285, 1120, 1072, 1040) против тиокола (1024, 1110)"),
   (560,1000,"960/940 (н-бутил), 742 (o-замещ. бензол), рост ниже 650 (M–O)"),
   (2500,2640,"S–H 2560 — у тиокола есть, у образца нет")]):
    for xx,aa,c,l in [(x1,A1,C_REF,"buryak_1t (тиокол)"),(x,A,C_BLK,"buryak_shmurdyak_black")]:
        k=(xx>=lo)&(xx<=hi); ax.plot(xx[k],aa[k],color=c,lw=1.4,label=l)
    for zlo,zhi,lab,c in ZONES:
        if zhi>lo and zlo<hi: ax.axvspan(max(zlo,lo),min(zhi,hi),color=c,alpha=.45,lw=0,zorder=0)
    ax.set_xlim(hi,lo); ax.set_title(tt,fontsize=8.5,loc="left"); ax.set_xlabel("см⁻¹"); ax.set_ylabel("A")
axs[0,0].legend(frameon=False,fontsize=8)
fig.suptitle("Увеличенные диагностические области",x=0.01,ha="left",fontsize=11)
fig.tight_layout(); fig.savefig(os.path.join(HERE,"zoom_black.png"),dpi=160); plt.close(fig)
print(peaks)
