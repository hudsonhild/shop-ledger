import sys
from PIL import Image, ImageChops
a=Image.open(sys.argv[1]).convert('RGB'); b=Image.open(sys.argv[2]).convert('RGB'); W,H=a.size
d=ImageChops.difference(a,b).convert('L'); m=d.point(lambda v:255 if v>24 else 0)
def frac(box):
    h=m.crop(box).histogram(); return h[255]/sum(h)*100
print('overall %.2f%%'%frac((0,0,W,H)))
for k,box in {'topbar':(0,0,1440,56),'nav':(0,56,240,900),'content_top':(240,56,1440,668),'cards':(240,668,1440,900)}.items(): print('  %-12s %.2f%%'%(k,frac(box)))
bands=[(y,frac((0,y,W,min(H,y+20)))) for y in range(56,H,20)]
print('worst 20px bands below the top bar:',sorted([(round(f,1),y) for y,f in bands],reverse=True)[:10])
sbs=Image.new('RGB',(W*2+20,H),(255,0,255)); sbs.paste(a,(0,0)); sbs.paste(b,(W+20,0)); sbs.save(sys.argv[3]+'/side-by-side.png')
heat=b.copy(); red=Image.new('RGB',(W,H),(255,0,0)); heat=Image.composite(red,heat,m); heat.save(sys.argv[3]+'/diff-heat.png')
