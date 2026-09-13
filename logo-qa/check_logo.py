"""Read-only logo QA. Candidate styles are injected ONLY inside the QA browser.
No Shopify writes, purchases, subscriptions or customer submissions.
"""
import json, io, os, re, hashlib, zipfile
from pathlib import Path
import requests
from PIL import Image
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
OUT=Path('logo-evidence');OUT.mkdir(exist_ok=True)
DRAFT='https://empireluxe.fr/?preview_theme_id=205091570007'
LOGO='https://cdn.shopify.com/s/files/1/1030/5273/8903/files/empireluxe-logo-or3.png?v=1783992853'
CSS='''/* Empire Luxe: preserve the original transparent artwork and its true ratio. */
#SiteHeader .header-item--logo{flex:0 0 auto!important;min-width:0;width:auto!important}
#SiteHeader .site-header__logo{width:116px;margin:0;line-height:0}
#SiteHeader .site-header__logo .site-header__logo-link{width:100%!important;height:auto!important;padding:0!important;aspect-ratio:650 / 274;position:relative;background:transparent!important;box-shadow:none!important;border:0}
#SiteHeader .site-header__logo .logo--has-inverted{display:block!important}
#SiteHeader .site-header__logo .logo--inverted{display:none!important}
#SiteHeader .site-header__logo img{position:static!important;width:100%!important;height:auto!important;max-height:none!important;object-fit:contain;filter:none!important;-webkit-filter:none!important;mix-blend-mode:normal;opacity:1!important;transform:none!important;background:transparent!important;box-shadow:none!important}
#HeaderWrapper.is-light #SiteHeader{background:transparent!important;box-shadow:none!important}
#HeaderWrapper.is-light:before,#HeaderWrapper.is-light:after{background:none!important;box-shadow:none!important;content:none!important}
@media(min-width:769px){#SiteHeader .site-header__logo{width:172px}}
'''
(OUT/'candidate.css').write_text(CSS)
PUBLIC=b'''-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAv8GlR1Hf5erJpNRsRINi
ftPFrPiKL8QpbIkzI024qbyKrLbeBINk1Es7oNcFkNFgxryCj5jZMbxWrOTLBQ/n
qB6tJSJdym0nYnlj3zatvwVSZh3AY6qmUumjmXaf1orD75UgsXZjLEbp0RW2uQ/A
Uw+KLuP1P/ppjIiP35N7dXSRqRm1PiYQdX4UWQhVtGsAUumI39Nsi2LAiqEz82o4
pRFPxekcy8wezIWbcPWF7seotk4WrpyWpEnsKYQWKy1TRYdmI4mlJp9EQnQZYfs9
8QiCp2P6yc/wOVkUzrJHDRW3DAhSJGRLYQPZkRthkXqMAZnqadLcAE79u3Na4/c0
0wIDAQAB
-----END PUBLIC KEY-----'''
HIDE='''#shopify-pc__banner,#shopify-pc__prefs,#shopify-preview-bar-iframe,#OnlineStorePreviewBarIframe,#preview-bar-iframe,.shopify-preview-bar,.shopify-pc__banner__dialog,[id^="NewsletterPopup-"]{display:none!important}html,body{scroll-behavior:auto!important}.modal-open{overflow:auto!important}'''
JS="""() => ({theme:window.Shopify?.theme,viewport:[innerWidth,innerHeight],overflow:document.documentElement.scrollWidth>innerWidth,items:[...document.querySelectorAll('#HeaderWrapper,#SiteHeader,#SiteHeader .header-layout,#SiteHeader .site-header__logo,#SiteHeader .site-header__logo-link,#SiteHeader .site-header__logo img,#SiteHeader .site-nav__icons')].map(e=>{let r=e.getBoundingClientRect(),s=getComputedStyle(e);return {tag:e.tagName,id:e.id,cls:e.className,rect:{x:r.x,y:r.y,w:r.width,h:r.height},display:s.display,filter:s.filter,background:s.background,padding:s.padding,position:s.position,src:e.currentSrc,naturalWidth:e.naturalWidth,naturalHeight:e.naturalHeight}})})"""
report=[]
try:
    r=requests.get(LOGO,timeout=20);r.raise_for_status();(OUT/'actual-logo.png').write_bytes(r.content)
    im=Image.open(io.BytesIO(r.content)).convert('RGBA');(OUT/'logo-pixels.json').write_text(json.dumps({'size':im.size,'alpha_extrema':im.getchannel('A').getextrema(),'sha256':hashlib.sha256(r.content).hexdigest()}))
    with sync_playwright() as p:
        b=p.chromium.launch()
        for width in [390,1440]:
            for side,url in [('reference','https://on-cloudtilt.fr/'),('draft',DRAFT),('product',DRAFT+'&view=p-91194e8eefcb')]:
                ctx=b.new_context(viewport={'width':width,'height':920},device_scale_factor=1,locale='fr-FR');page=ctx.new_page();page.set_default_timeout(8000)
                record={'width':width,'side':side}
                try:
                    response=page.goto(url,wait_until='domcontentloaded',timeout=30000);page.wait_for_timeout(1300)
                    page.add_style_tag(content=HIDE);page.evaluate("document.documentElement.classList.remove('modal-open');document.body.classList.remove('modal-open')")
                    page.evaluate("() => Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,2000))])")
                    page.wait_for_timeout(450);record['before']=page.evaluate(JS)
                    (OUT/f'{side}-{width}.html').write_text(page.content())
                    page.screenshot(path=str(OUT/f'{side}-{width}-before.png'))
                    if side!='reference':
                        if str(record['before'].get('theme',{}).get('id'))!='205091570007':raise RuntimeError('Wrong preview theme')
                        page.add_style_tag(content=CSS);page.wait_for_timeout(250);record['candidate']=page.evaluate(JS)
                        page.screenshot(path=str(OUT/f'{side}-{width}-candidate.png'))
                        page.locator('#SiteHeader').screenshot(path=str(OUT/f'{side}-{width}-header-candidate.png'))
                    if width==390:
                        for i,el in enumerate(page.locator('link[rel=stylesheet]').all()):
                            href=el.get_attribute('href')
                            if not href:continue
                            from urllib.parse import urljoin
                            address=urljoin(url,href)
                            try:
                                rr=requests.get(address,timeout=12)
                                if rr.status_code==200:(OUT/f'{side}-stylesheet-{i}.css').write_text(rr.text)
                            except Exception:pass
                except Exception as e:record['error']=str(e)
                finally:report.append(record);ctx.close()
        b.close()
finally:
    (OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    public=serialization.load_pem_public_key(PUBLIC);buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for f in OUT.rglob('*'):
            if f.is_file():z.write(f,str(f.relative_to(OUT)))
    key=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
    ek=public.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    Path('logo-qa-encrypted.bin').write_bytes(b'EQA1'+ek+nonce+AESGCM(key).encrypt(nonce,buf.getvalue(),b'empire-qa'))
    print('Logo comparison captured; evidence encrypted; no store changes.')
