"""Read-only reference comparison. No storefront, catalog, order or payment writes.
Evidence is encrypted by the workflow before leaving the runner.
"""
import concurrent.futures, hashlib, json, re, time, traceback
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

OUT=Path('qa-evidence'); OUT.mkdir(exist_ok=True)
REF='https://on-cloudtilt.fr'; DRAFT='https://empireluxe.fr'; THEME='205091570007'
HEADERS={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36','Accept-Language':'fr-FR,fr;q=0.9'}
REPORT={'started':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'draft_theme_id':THEME,'read_only':True,'routes':[],'visual':[],'interaction':[]}

def write(name,data):
    dest=OUT/name;dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,ensure_ascii=False,indent=2) if not isinstance(data,str) else data,encoding='utf-8')

def get(url):
    r=requests.get(url,headers=HEADERS,timeout=30)
    return r

def draft_url(view='',extra=''):
    return DRAFT+'/?preview_theme_id='+THEME+('&view='+view if view else '')+('&'+extra if extra else '')

def norm(s):
    s=re.sub(r'\s+',' ',s).strip()
    s=s.replace('bonjour@on-cloudtilt.fr','[CONTACT]').replace('bonjour@exemple.fr','[CONTACT]').replace('empireluxe.10@gmail.com','[CONTACT]')
    return s

def imgkey(src):
    s=urlsplit(urljoin(REF,src)).path
    return re.sub(r'_\d+x\d*(?=\.)','',s)

def extract(html):
    soup=BeautifulSoup(html,'html.parser');main=soup.select_one('#MainContent') or soup.select_one('main') or soup
    def tx(sel):return [norm(e.get_text(' ',strip=True)) for e in main.select(sel)]
    reviews=[{'text':norm(c.select_one('.nolya-review-card__text').get_text()) if c.select_one('.nolya-review-card__text') else '', 'name':norm(c.select_one('.nolya-review-card__name').get_text()) if c.select_one('.nolya-review-card__name') else '', 'image':imgkey(c.select_one('img').get('src','')) if c.select_one('img') else ''} for c in main.select('.nolya-review-card')]
    cards=[{'name':norm(c.select_one('.grid-product__title').get_text()) if c.select_one('.grid-product__title') else '', 'price':norm(c.select_one('.grid-product__price').get_text()) if c.select_one('.grid-product__price') else ''} for c in main.select('.grid-product') if c.select_one('.grid-product__title')]
    return {'title':tx('.product-single__title'),'price':tx('[data-product-price]')[:1],'headings':tx('h1,h2,h3'),'reviews':reviews,'ratings':tx('.nolya-rating__count'),'cards':cards,'sizes':[e.get('value') for e in main.select('input[data-variant-input]')],'liquid_errors':re.findall(r'Liquid (?:error|syntax error)[^<\n]{0,220}',html),'main_bytes':len(str(main)),'html_bytes':len(html),'theme_id':(re.search(r'Shopify\.theme\s*=\s*\{[^;]*?"id"\s*:\s*(\d+)',html) or [None,None])[1]}

manifest=get(DRAFT+'/cdn/shop/t/4/assets/empire-reference-manifest.json').json()
write('manifest.json',manifest)
pages=manifest.get('pages',[])
write('routes.json',get(DRAFT+'/cdn/shop/t/4/assets/empire-routes.json').json())
write('catalogue.json',get(DRAFT+'/cdn/shop/t/4/assets/empire-demo-catalogue.json').json())
route_map={p['path']:p['view'] for p in pages}

def check_pair(p):
    view=p['view'];path=p['path'];result={'path':path,'view':view}
    try:
        a=get(REF+path);b=get(draft_url(view))
        write('html/reference-'+view+'.html',a.text);write('html/draft-'+view+'.html',b.text)
        aa=extract(a.text);bb=extract(b.text)
        fields=['title','price','ratings','reviews','cards','sizes']
        result.update({'reference_status':a.status_code,'draft_status':b.status_code,'reference':aa,'draft':bb,'mismatch':[k for k in fields if aa[k]!=bb[k]],'incomplete':aa['main_bytes']<400 or bb['main_bytes']<400})
    except Exception as e:result['error']=str(e)[:300]
    return result

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for result in pool.map(check_pair,pages):
        REPORT['routes'].append(result)
write('route-report.json',REPORT['routes'])
print('Route comparison complete:',len(REPORT['routes']),'pairs',flush=True)

HIDE='''#shopify-pc__banner,#shopify-pc__prefs,#shopify-preview-bar-iframe,#OnlineStorePreviewBarIframe,#preview-bar-iframe,.shopify-preview-bar,.shopify-pc__banner__dialog,[id^="NewsletterPopup-"]{display:none!important}html,body{scroll-behavior:auto!important}.modal-open{overflow:auto!important}'''
SELECTORS='main h1,main h2,main h3,main .nolya-rating,main .nolya-reviews,main video,main [class*="ai-modern-banner__image"],main [class*="ai-collection-scroll__name"],main [class*="ai-newsletter-signup__content"],main [class*="hpf-footer-"][class$="__top"]'
MASKS='.site-header__logo, [class^="hpf-footer-"][class$="__logo"],a[href^="mailto:"],video,.announcement-bar,.ai-footer__bottom-au1a5vkxuv1bity9ydaigenblock54926a36grbv3'

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    def assets(response):
        try:
            url=response.url;ctype=response.headers.get('content-type','')
            if response.status==200 and ('css' in ctype or 'javascript' in ctype) and ('on-cloudtilt.fr' in url or 'empireluxe.fr' in url):
                suffix='.css' if 'css' in ctype else '.js'; name='assets/'+hashlib.sha1(url.encode()).hexdigest()+suffix
                write(name,response.text());asset_map[url]=name
        except:pass
    asset_map={}
    samples=[('home',''),('shoes','/collections/chaussures'),('clothes','/collections/vetement'),('accessories','/collections/accessoires'),('watches','/collections/ap-x-swatch'),('product','/products/cloudtilt-remix-sunstone-ivory-femme'),('saucony-product','/products/saucony-progrid-omni-9-premium-grey'),('watch-product','/products/swatch-x-audemars-piguet-bioceramic-royal-pop-huit-blanc-ssx03w100n'),('clothes-product','/products/club-t')]
    for width in [390,1440]:
        contexts=[browser.new_context(viewport={'width':width,'height':900},device_scale_factor=1,locale='fr-FR',timezone_id='Europe/Paris') for _ in range(2)]
        for ctx in contexts:ctx.set_default_timeout(7000)
        for label,path in samples:
            if path and path not in route_map:continue
            pair=[]
            for side,ctx in zip(['reference','draft'],contexts):
                page=ctx.new_page();errors=[]
                page.on('pageerror',lambda err, dest=errors:dest.append(str(err)[:350]))
                page.on('response',assets)
                url=REF+(path or '/') if side=='reference' else draft_url(route_map.get(path,''),'qa_capture=20260913')
                base=f'{label}-{width}-{side}'
                try:
                    resp=page.goto(url,wait_until='domcontentloaded',timeout=35000)
                    page.wait_for_timeout(1600)
                    page.add_style_tag(content=HIDE)
                    page.evaluate("document.documentElement.classList.remove('modal-open');document.body.classList.remove('modal-open')")
                    try:page.evaluate("() => Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,4000))])")
                    except:pass
                    height=page.evaluate('document.documentElement.scrollHeight')
                    for y in range(0,min(height,24000),650):
                        page.evaluate('(y)=>window.scrollTo(0,y)',y);page.wait_for_timeout(80)
                    page.wait_for_timeout(900)
                    page.evaluate('''() => {document.querySelectorAll('video').forEach(v=>{v.pause();try{v.currentTime=0.1}catch{}});document.getAnimations().forEach(a=>{try{let t=a.effect.getTiming();if(t.iterations!==Infinity)a.finish();else a.pause()}catch{}});window.scrollTo(0,0)}''')
                    page.wait_for_timeout(300)
                    metrics=page.evaluate('''(selectors)=>({theme:window.Shopify?.theme,viewport:{w:innerWidth,h:innerHeight},scrollWidth:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,brokenImages:Array.from(document.images).filter(i=>getComputedStyle(i).display!=='none'&&i.getBoundingClientRect().width>0&&i.complete&&i.naturalWidth===0&&i.currentSrc).map(i=>({src:i.currentSrc,alt:i.alt})),anchors:Array.from(document.querySelectorAll(selectors)).map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {tag:e.tagName,id:e.id,cls:String(e.className),text:(e.tagName==='VIDEO'?'':e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,120),x:r.x,y:r.y,w:r.width,h:r.height,font:s.font,fontFamily:s.fontFamily,color:s.color}})})''',SELECTORS)
                    write(base+'.json',{'url':url,'http':resp.status if resp else None,'metrics':metrics,'errors':errors})
                    write('rendered/'+base+'.html',page.content())
                    page.screenshot(path=str(OUT/(base+'.png')),full_page=True,animations='disabled',timeout=25000)
                    page.screenshot(path=str(OUT/(base+'-masked.png')),full_page=True,animations='disabled',mask=[page.locator(MASKS)],mask_color='#777777',timeout=25000)
                    pair.append({'side':side,'width':width,'label':label,'http':resp.status if resp else None,'metrics':metrics,'errors':errors,'screenshot':base+'.png'})
                    if side=='draft' and str(metrics.get('theme',{}).get('id'))!=THEME:raise AssertionError('Wrong draft theme')
                    if label=='home':
                        nav=page.locator('.js-drawer-open-nav:visible').first
                        if nav.count():
                            try:
                                nav.click();page.wait_for_timeout(350)
                                REPORT['interaction'].append({'width':width,'side':side,'test':'menu opens','pass':page.locator('#NavDrawer').evaluate("e=>e.classList.contains('drawer--is-open')")})
                                page.screenshot(path=str(OUT/(base+'-menu.png')),animations='disabled')
                                close=page.locator('#NavDrawer .js-drawer-close:visible').first
                                if close.count():close.click()
                                else:page.keyboard.press('Escape')
                            except Exception as e:REPORT['interaction'].append({'width':width,'side':side,'test':'menu','error':str(e)[:180]})
                    if label=='product' and side=='draft':
                        if page.locator('form[data-empire-preview-product]').count():
                            try:
                                size=page.locator('input[data-variant-input][value="42"]');size.check(force=True)
                                page.locator('form[data-empire-preview-product] button[name="add"]').click()
                                page.wait_for_timeout(500)
                                cart=page.locator('#CartDrawer')
                                REPORT['interaction'].append({'width':width,'side':side,'test':'demo size 42 to isolated cart','cartText':cart.inner_text(),'storedCart':page.evaluate("sessionStorage.getItem('empire-reference-preview-cart-v1')")})
                                page.screenshot(path=str(OUT/(base+'-cart.png')),animations='disabled')
                            except Exception as e:REPORT['interaction'].append({'width':width,'side':side,'test':'demo cart','error':str(e)[:180]})
                except Exception as e:
                    pair.append({'side':side,'width':width,'label':label,'error':str(e)[:350]})
                finally:page.close()
            comparison={'label':label,'width':width,'pages':pair}
            try:
                ia=Image.open(OUT/f'{label}-{width}-reference-masked.png').convert('RGB');ib=Image.open(OUT/f'{label}-{width}-draft-masked.png').convert('RGB')
                comparison['image_sizes']=[ia.size,ib.size]
                if ia.size==ib.size:
                    d=ImageChops.difference(ia,ib);hist=d.convert('L').histogram();comparison['changed_pixel_ratio_above_24']=sum(hist[25:])/(ia.width*ia.height)
                    d.save(OUT/f'{label}-{width}-difference.png')
            except Exception as e:comparison['comparison_error']=str(e)[:150]
            REPORT['visual'].append(comparison)
            write('report.json',REPORT)
            print('Rendered comparison:',label,width,flush=True)
        for c in contexts:c.close()
    browser.close()
write('asset-map.json',asset_map)
REPORT['finished']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
write('report.json',REPORT)
print('Browser verification completed. Detailed evidence encrypted, no store writes.',flush=True)
