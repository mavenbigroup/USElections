#!/usr/bin/env python3
"""Background civicAPI results scraper. Writes results_auto.json incrementally so partial
results are usable even when civicAPI is slow. Run under `timeout` from the workflow loop."""
import json, re, time, pathlib, datetime, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "results_auto.json"
UA = {"User-Agent": "midterm-night-board/1.0 (+github pages)"}
BASE = "https://civicapi.org/api/v2/race/search?startDate=2026-11-03&endDate=2026-11-03"
AB = {"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"}
SKIP = ("shadow", "state senate", "state house", "lieutenant", "referendum", "proposition", "question", "judicial", "judge", "court", "mayor", "assembly", "delegate", "council", "secretary", "attorney", "treasurer", "auditor", "comptroller", "commissioner", "board", "superintendent", "legislat", "measure", "amendment")

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

def getj(url, t=45):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def classify(race):
    typ = str(race.get("type") or "").lower()
    ab = str(race.get("province") or "").upper()
    if ab not in AB or any(s in typ for s in SKIP):
        return None
    if "senate" in typ:
        return f"{ab}-SEN"
    if "governor" in typ:
        return f"{ab}-GOV"
    if "representative" in typ or "house" in typ or "congress" in typ:
        m = re.search(r"(\d{1,2})", str(race.get("district") or ""))
        return f"{ab}-{int(m.group(1)):02d}" if m else f"{ab}-AL"
    return None

def tally(race):
    d = r = o = 0; called = None
    for c in race.get("candidates") or []:
        try: v = int(c.get("votes") or 0)
        except Exception: v = 0
        p = str(c.get("party") or "").lower()
        if p.startswith("dem"):
            d += v; called = "D" if c.get("winner") else called
        elif p.startswith("rep"):
            r += v; called = "R" if c.get("winner") else called
        else:
            o += v; called = "I" if c.get("winner") else called
    try: pct = round(float(race.get("percent_reporting")), 1)
    except Exception: pct = None
    out = {"d": d, "r": r, "o": o, "pct": pct, "src": "civicapi", "raceId": race.get("id")}
    if called: out["called"] = called
    return out

state = {"started": now(), "races": {}, "types": {}, "fetched": 0, "total": None, "mode": None}

def absorb(lst):
    for race in lst or []:
        if not isinstance(race, dict): continue
        state["fetched"] += 1
        t = str(race.get("type")); state["types"][t] = state["types"].get(t, 0) + 1
        key = classify(race)
        if not key: continue
        tl = tally(race)
        prev = state["races"].get(key)
        if prev is None or tl["d"] + tl["r"] >= prev["d"] + prev["r"]:
            state["races"][key] = tl

def flush(final=False):
    state["updated"] = now(); state["final"] = final
    tmp = OUT.with_suffix(".tmp"); tmp.write_text(json.dumps(state)); tmp.replace(OUT)

def crawl(base, label):
    first = getj(f"{base}&offset=0")
    total = int(first.get("count") or 0); lim = int(first.get("limit") or 20) or 20
    absorb(first.get("races")); flush()
    offs = list(range(lim, min(total, 6000), lim))
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(getj, f"{base}&offset={o}"): o for o in offs}
        n = 0
        for fu in as_completed(futs):
            try: absorb(fu.result().get("races"))
            except Exception: pass
            n += 1
            if n % 10 == 0: flush()
    return total

t0 = time.time()
# 1) try type filters (small, fast if civicAPI honours them)
filtered_ok = False
for typ in ("Senate", "Governor", "Representative"):
    try:
        probe = getj(f"{BASE}&type={urllib.request.quote(typ)}&offset=0")
        types = {str(x.get("type")) for x in probe.get("races") or []}
        if probe.get("races") and all(typ.lower() in t.lower() for t in types):
            filtered_ok = True
            state["mode"] = "filtered"
            crawl(f"{BASE}&type={urllib.request.quote(typ)}", typ)
    except Exception as e:
        print("filter probe failed", typ, str(e)[:100])
# 2) fall back to crawling everything
if not filtered_ok:
    state["mode"] = "full"
    try:
        state["total"] = crawl(BASE, "all")
    except Exception as e:
        print("full crawl failed", str(e)[:120])
flush(final=True)
wv = sum(1 for v in state["races"].values() if v["d"] or v["r"] or v.get("called"))
print(f"civicAPI results: mode={state['mode']} fetched={state['fetched']} matched={len(state['races'])} with_votes={wv} in {time.time()-t0:.0f}s")
