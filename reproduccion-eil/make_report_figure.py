import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

SURF='#fcfcfb'; TXT='#0b0b0b'; TXT2='#52514e'; MUTED='#8a8984'; GRID='#e6e5e1'
S1='#2a78d6'; S2='#eb6834'; S3='#1baf7a'

SEEDS=[42,137,271,314,999,17,88,256,512,1024,7,23,99,404,808,11,55,333,777,2024]
R=[dict(np.load(f'seed_{s}.npy',allow_pickle=True).item()) for s in SEEDS]
d=np.array([r['d'] for r in R]); hs=np.array([r['hs'] for r in R]); ht=np.array([r['ht'] for r in R])
n=len(R); t=np.arange(1,d.shape[1]+1)

fig=plt.figure(figsize=(14,9.5),facecolor=SURF)
gs=fig.add_gridspec(2,2,hspace=.38,wspace=.24,left=.07,right=.97,top=.845,bottom=.09)

def sty(ax,title,sub=''):
    ax.set_facecolor(SURF)
    for s in ('top','right'): ax.spines[s].set_visible(False)
    for s in ('bottom','left'): ax.spines[s].set_color(GRID); ax.spines[s].set_linewidth(1)
    ax.tick_params(colors=TXT2,labelsize=9,length=0)
    ax.grid(True,color=GRID,lw=1,alpha=.9); ax.set_axisbelow(True)
    ax.set_title(title,color=TXT,fontsize=12,fontweight='bold',loc='left',pad=18 if sub else 8)
    if sub: ax.text(0,1.035,sub,transform=ax.transAxes,color=TXT2,fontsize=9.5,va='bottom')

fig.text(.07,.965,'Reproducción independiente — "Ergodicidad Informacional Local" en el Juego de la Vida',
         color=TXT,fontsize=15,fontweight='bold')
fig.text(.07,.935,f'Código del autor ejecutado sin modificar · N=200, K=300, T=1500, n={n} semillas · determinista (verificado)',
         color=TXT2,fontsize=10.5)

# ── A: |ΔH| trajectory ──────────────────────────────────────────────
axA=fig.add_subplot(gs[0,:])
sty(axA,'El "mínimo transitorio de EIL" es el primer paso en que H(tiempo) existe',
    'Media sobre 20 semillas, banda = IC95%. Eje x logarítmico para mostrar los primeros pasos.')
m=d.mean(0)*100; ci=1.96*d.std(0)/np.sqrt(n)*100
axA.fill_between(t,m-ci,m+ci,color=S1,alpha=.16,lw=0)
axA.plot(t,m,color=S1,lw=2,solid_capstyle='round')
axA.axhline(5,color=MUTED,lw=1.5,ls=(0,(4,3)))
axA.text(1550,5,' umbral EIL 5%',color=TXT2,fontsize=9,va='center')
axA.axvspan(1,3.5,color=MUTED,alpha=.12,lw=0)
axA.annotate('pasos 1–3: H(tiempo)=0\npor construcción → |ΔH|=100%',xy=(2,100),xytext=(1.25,62),
    color=TXT2,fontsize=9,ha='left',arrowprops=dict(arrowstyle='-',color=MUTED,lw=1))
axA.annotate(f'paso 4: la ventana se llena,\n|ΔH| cae a {d[:,3].mean()*100:.1f}% en UN paso',
    xy=(4,d[:,3].mean()*100),xytext=(7,26),color=S2,fontsize=9.5,fontweight='bold',
    arrowprops=dict(arrowstyle='->',color=S2,lw=1.6))
axA.annotate(f'final: {d[:,-50:].mean()*100:.1f}%',xy=(1400,d[:,-50:].mean()*100),
    xytext=(420,58),color=S1,fontsize=10,fontweight='bold',
    arrowprops=dict(arrowstyle='->',color=S1,lw=1.6))
axA.set_xscale('log'); axA.set_xlim(1,1500); axA.set_ylim(0,105)
axA.set_xlabel('Paso (escala log)',color=TXT2,fontsize=10)
axA.set_ylabel('|ΔH| relativo  (%)',color=TXT2,fontsize=10)

# ── B: H(space) vs H(time) ──────────────────────────────────────────
axB=fig.add_subplot(gs[1,0])
sty(axB,'H(espacio) y H(tiempo) se cruzan repetidamente',
    'El mínimo de |ΔH| es un cruce de curvas, no una meseta.')
axB.plot(t,hs.mean(0),color=S1,lw=2,label='H(espacio)',solid_capstyle='round')
axB.plot(t,ht.mean(0),color=S2,lw=2,label='H(tiempo)',solid_capstyle='round')
axB.text(760,hs.mean(0)[700]+.30,'H(espacio)',color=S1,fontsize=10,fontweight='bold')
axB.text(760,ht.mean(0)[700]-.48,'H(tiempo)',color=S2,fontsize=10,fontweight='bold')
axB.set_xscale('log'); axB.set_xlim(1,1500); axB.set_ylim(0,4.1)
axB.set_xlabel('Paso (escala log)',color=TXT2,fontsize=10)
axB.set_ylabel('H  (bits)',color=TXT2,fontsize=10)
axB.legend(frameon=False,fontsize=9.5,labelcolor=TXT2,loc='lower left')
axB.text(.97,.95,'signo de (Hs−Ht) cambia en 20/20 semillas\n(3–43 cruces cada una)',
    transform=axB.transAxes,ha='right',va='top',fontsize=9,color=TXT2)

# ── C: paper vs reproduction ────────────────────────────────────────
axC=fig.add_subplot(gs[1,1])
sty(axC,'Afirmaciones del paper vs. valores reproducidos',
    'E4–E6 reconstruidos a partir de la prosa: el script no contiene código para ellos.')
labs=['|ΔH| final\n(E1–E3)','E4 sondas\nfijas','E5 sondas\ndrift','E6 random\nwalk']
paper=[44.2,53.3,17.4,64.1]; repro=[46.5,32.8,30.1,11.6]
ok=[True,False,False,False]
y=np.arange(len(labs)); h=.36
for i in range(len(labs)):
    for val,off,col,lw in ((paper[i],h/2+.01,MUTED,0),(repro[i],-h/2-.01,S1 if ok[i] else S2,0)):
        axC.add_patch(FancyBboxPatch((0,y[i]+off-h/2),val,h,
            boxstyle='round,pad=0,rounding_size=1.1',fc=col,ec='none',mutation_aspect=.28))
    axC.text(paper[i]+1.5,y[i]+h/2+.01,f'{paper[i]:.1f}',va='center',fontsize=9,color=TXT2)
    axC.text(repro[i]+1.5,y[i]-h/2-.01,f'{repro[i]:.1f}',va='center',fontsize=9,
             color=S1 if ok[i] else S2,fontweight='bold')
axC.set_yticks(y); axC.set_yticklabels(labs,fontsize=9,color=TXT2)
axC.invert_yaxis(); axC.set_xlim(0,78); axC.grid(axis='y',color=SURF)
axC.set_xlabel('|ΔH| final  (%)',color=TXT2,fontsize=10)
axC.plot([],[],color=MUTED,lw=6,label='publicado'); axC.plot([],[],color=S1,lw=6,label='reproducido')
axC.legend(frameon=False,fontsize=9.5,labelcolor=TXT2,loc='upper right',ncol=1,bbox_to_anchor=(1.0,1.0))

fig.savefig('reproduction_report.png',dpi=150,facecolor=SURF,bbox_inches='tight')
print('saved reproduction_report.png')
