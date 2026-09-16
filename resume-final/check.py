import json,time,io,os,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
O=Path('final-evidence');O.mkdir(exist_ok=True)
T='205091570007';D='https://empireluxe.fr';R='https://on-cloudtilt.fr'
report={'theme_id':T,'screens':[],'tests':[],'started':time.time()}
def record(label,ok,detail=None):report['tests'].append({'test':label,'pass':bool(ok),'detail':detail})
HIDE='[id^="NewsletterPopup-"],#shopify-pc__banner,#shopify-preview-bar-iframe,#OnlineStorePreviewBarIframe,#preview-bar-iframe{display:none!important}'
with sync_playwright() as pw:
 b=pw.chromium.launch()
 for width in [390,1440]:
  contexts={s:b.new_context(viewport={'width':width,'height':900},locale='fr-FR') for s in ['reference','draft']}
  pages={s:c.new_page() for s,c in contexts.items()}
  errors={s:[] for s in pages};failures={s:[] for s in pages}
  for s,page in pages.items():
   page.set_default_timeout(6000)
   page.on('pageerror',lambda e,s=s:errors[s].append(str(e)))
   page.on('requestfailed',lambda r,s=s:failures[s].append({'url':r.url,'error':r.failure}))
  cases=[('home','/',''),('shoes','/collections/chaussures','c-066616f09e93'),('clothes','/collections/vetement','c-4a3a353925cd'),('product','/products/cloudtilt-remix-sunstone-ivory-femme','p-91194e8eefcb'),('clothes-product','/products/club-t','p-bce5e7eb05bc'),('search','/search?q=Cloudtilt',None),('cart','/cart',None)]
  for label,path,view in cases:
   for side,page in pages.items():
    if side=='reference' and label=='cart':continue
    try:
     url=R+path if side=='reference' else D+('/?view='+view if view else '/' if view=='' else path)
     if side=='draft' and label=='home':url+='?preview_theme_id='+T
     response=page.goto(url,wait_until='domcontentloaded',timeout=25000);time.sleep(1.2)
     if response.status!=200:raise RuntimeError('HTTP '+str(response.status))
     page.add_style_tag(content=HIDE)
     page.evaluate("document.documentElement.classList.remove('modal-open');document.body.classList.remove('modal-open')")
     if side=='draft':record(f'{width} {label} correct draft',str(page.evaluate('window.Shopify?.theme?.id'))==T)
     h=page.evaluate('document.documentElement.scrollHeight')
     for y in range(0,min(h,9000),750):page.evaluate('(y)=>scrollTo(0,y)',y);time.sleep(.08)
     time.sleep(.8)
     page.evaluate("document.querySelectorAll('video').forEach(v=>{v.pause();try{v.currentTime=.1}catch{}});document.getAnimations().forEach(a=>{try{if(a.effect.getTiming().iterations!==Infinity)a.finish();else a.pause()}catch{}});scrollTo(0,0)")
     metrics=page.evaluate('''()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,bridge:window.EmpirePreview?.referenceBridgeVersion,errors:[],brokenImages:[...document.images].filter(i=>i.getBoundingClientRect().width&&i.complete&&!i.naturalWidth&&i.currentSrc).map(i=>i.currentSrc),reviews:document.querySelectorAll('.nolya-review-card').length,recent:[...document.querySelectorAll('[data-section-type="recently-viewed"]')].map(e=>({items:e.querySelectorAll('.grid-product').length,visible:!!e.getBoundingClientRect().height})),recommendations:[...document.querySelectorAll('[data-section-type="product-recommendations"]')].map(e=>({items:e.querySelectorAll('.grid-product').length,visible:!!e.getBoundingClientRect().height})),searchResults:document.getElementById('EmpireSearchOutput')?.dataset.empireResults,headings:[...document.querySelectorAll('main h1,main h2,main h3')].map(e=>e.innerText)})''')
     metrics['errors']=errors[side][:];metrics['requestFailures']=failures[side][:]
     report['screens'].append({'label':label,'width':width,'side':side,'metrics':metrics})
     name=f'{label}-{width}-{side}'
     (O/(name+'.html')).write_text(page.content())
     page.screenshot(path=str(O/(name+'.png')),full_page=True,animations='disabled',timeout=20000)
     if side=='draft':
      record(f'{width} {label} no overflow',metrics['scrollWidth']==width)
      record(f'{width} {label} no broken image',not metrics['brokenImages'])
      record(f'{width} {label} no JS error',not errors[side],errors[side][:])
      if label=='home':
       page.locator('.js-drawer-open-nav:visible').first.click();record(f'{width} menu opens',page.locator('#NavDrawer').evaluate("e=>e.classList.contains('drawer--is-open')"));page.locator('#NavDrawer .js-drawer-close').click()
      if label=='product':
       inp=page.locator('input[data-variant-input][value="42"]').first
       id=inp.get_attribute('id');page.locator('label[for="'+id+'"]').click()
       record(f'{width} size 42 selected',inp.is_checked())
       page.locator('form[data-empire-preview-product] button[name="add"]').click();time.sleep(.25)
       snap=page.evaluate('window.EmpirePreviewCart.snapshot()')
       record(f'{width} product to cart',snap['item_count']==1 and snap['items'][0]['variant']=='42' and snap['total_price']==11000,snap)
       page.screenshot(path=str(O/f'cart-drawer-{width}.png'))
      if label=='clothes-product':
       record(f'{width} recommendations restored',any(x['visible'] and x['items']>0 for x in metrics['recommendations']))
       record(f'{width} recently viewed restored',any(x['visible'] and x['items']>0 for x in metrics['recent']))
      if label=='search':record(f'{width} search results',int(metrics['searchResults'] or 0)>0,metrics['searchResults'])
      if label=='cart':
       form=page.locator('#EmpireCartPage');snap=page.evaluate('window.EmpirePreviewCart.snapshot()');record(f'{width} cart survives navigation',snap['item_count']==1,snap)
       form.locator('[data-empire-qty="1"]').first.click();snap=page.evaluate('window.EmpirePreviewCart.snapshot()');record(f'{width} quantity increment',snap['item_count']==2 and snap['total_price']==22000,snap)
       form.locator('[name="checkout"]').click();record(f'{width} safe demo checkout',form.locator('[data-empire-demo-note]').is_visible())
       form.locator('[data-empire-remove]').first.click();record(f'{width} remove item',page.evaluate('window.EmpirePreviewCart.snapshot().item_count')==0)
    except Exception as e:record(f'{width} {label} {side} execution',False,str(e)[:700])
    (O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    time.sleep(.8)
  for c in contexts.values():c.close()
 b.close()
report['finished']=time.time();(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
public=Path('resume-final/public.pem').read_bytes();key=serialization.load_pem_public_key(public);buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
 for f in O.rglob('*'):
  if f.is_file():z.write(f,str(f.relative_to(O)))
secret=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12);wrapped=key.encrypt(secret,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
Path('final-evidence.bin').write_bytes(b'EQA1'+wrapped+nonce+AESGCM(secret).encrypt(nonce,buf.getvalue(),b'empire-qa'))
print('Evidence saved. Test results retained in encrypted report.')
