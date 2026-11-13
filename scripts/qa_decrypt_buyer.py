import re
import requests

BASE = 'http://127.0.0.1:8000'


def csrf(html: str) -> str:
    m = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)', html)
    return m.group(1) if m else ''


s = requests.Session()
r = s.get(f'{BASE}/panel/login/')
s.post(
    f'{BASE}/panel/login/',
    data={'email': 'db@magtech.local', 'password': 'DbAdmin123!', 'csrfmiddlewaretoken': csrf(r.text)},
    headers={'Referer': f'{BASE}/panel/login/'},
)
users = s.get(f'{BASE}/panel/users/')
# find buyer with decrypt
for email in ('student@example.com', 'office@example.com', 'ilyaegorov575@gmail.com'):
    m = re.search(rf'{re.escape(email)}[\s\S]{{0,400}}/panel/users/(\d+)/decrypt/', users.text)
    if not m:
        # looser
        idx = users.text.find(email)
        chunk = users.text[idx : idx + 800] if idx >= 0 else ''
        m2 = re.search(r'/panel/users/(\d+)/decrypt/', chunk)
        uid = m2.group(1) if m2 else None
    else:
        uid = m.group(1)
    print('email', email, 'uid', uid)
    if not uid:
        continue
    d = s.get(f'{BASE}/panel/users/{uid}/decrypt/')
    r = s.post(
        f'{BASE}/panel/users/{uid}/decrypt/',
        data={'csrfmiddlewaretoken': csrf(d.text), 'confirm': '1', 'reason': 'QA buyer decrypt'},
        headers={'Referer': f'{BASE}/panel/users/{uid}/decrypt/'},
    )
    has_block = 'Расшифрованные значения' in r.text
    print(' revealed block', has_block)
    if has_block:
        block = re.search(r'Расшифрованные значения[\s\S]{0,600}', r.text)
        print(re.sub(r'<[^>]+>', ' ', block.group(0))[:400])
    break

# moderate first review
rev = s.get(f'{BASE}/panel/reviews/44/moderate/')
print('review moderate', rev.status_code, sorted(set(re.findall(r'name="([^"]+)"', rev.text))))
if rev.status_code == 200 and 'csrfmiddlewaretoken' in rev.text:
    fields = sorted(set(re.findall(r'name="([^"]+)"', rev.text)))
    data = {'csrfmiddlewaretoken': csrf(rev.text)}
    for n in fields:
        if n == 'csrfmiddlewaretoken':
            continue
        if 'status' in n or 'action' in n or 'decision' in n:
            # pick approve-like
            m = re.search(rf'name="{n}"[\s\S]*?</select>|<input[^>]+name="{n}"[^>]*>', rev.text)
            opts = re.findall(r'value="([^"]+)"', m.group(0)) if m else []
            data[n] = next((o for o in opts if o and o.lower() in ('approved', 'publish', 'ok', 'visible', '1')), opts[0] if opts else 'approved')
        elif n == 'confirm':
            data[n] = 'on'
        else:
            data[n] = ''
    r = s.post(f'{BASE}/panel/reviews/44/moderate/', data=data, headers={'Referer': f'{BASE}/panel/reviews/44/moderate/'}, allow_redirects=True)
    print('moderate post', r.status_code, r.url)

# audit filter
a = s.get(f'{BASE}/panel/audit/?action=pii_decrypt&q=db')
print('audit pii_decrypt', a.status_code, 'pii_decrypt' in a.text, a.text.count('pii_decrypt'))
