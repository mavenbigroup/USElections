import urllib.request, re
UA={"User-Agent":"Mozilla/5.0 (compatible; midterm-night-board/1.0)"}
def get(u,t=20):
    with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t) as r: return r.read().decode("utf-8","replace")
seen=set()
for page in ["https://onpointpolitics.us/results/2026","https://onpointpolitics.us/results/monitor","https://onpointpolitics.us/maps/early-vote","https://civicapi.org/","https://civicapi.org/api-documentation"]:
    try:
        h=get(page)
    except Exception as e:
        print("PROBE page fail",page,e); continue
    for m in set(re.findall(r'civicapi\.org/[A-Za-z0-9_\-/{}\.\?=&$`+:]*',h)): print("PROBE inline",page,m)
    srcs=re.findall(r'<script[^>]+src="([^"]+)"',h)
    for s in srcs:
        u=s if s.startswith("http") else re.match(r'https://[^/]+',page).group(0)+s
        if u in seen: continue
        seen.add(u)
        try: js=get(u)
        except Exception as e: continue
        for m in set(re.findall(r'(?:civicapi\.org)?/api/v[0-9]/[A-Za-z0-9_\-/{}\.\?=&$`+:]{2,80}',js)): print("PROBE js",u.split('/')[-1][:40],m)
        for m in set(re.findall(r'civicapi\.org[^"\'`\s]{0,80}',js)): print("PROBE jsurl",u.split('/')[-1][:40],m)
