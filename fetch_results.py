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

def getj(url, t=25):
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
try:
    _prev = json.loads(OUT.read_text())
    state["races"] = _prev.get("races") or {}
except Exception:
    pass

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

def crawl(base, label, lim_hint=20):
    """Page until a short/empty page. civicAPI's `count` is the page size, not the total."""
    first = getj(f"{base}&offset=0")
    rows = first.get("races") or []
    lim = int(first.get("limit") or len(rows) or lim_hint) or lim_hint
    absorb(rows); flush()
    if len(rows) < lim:
        return len(rows)
    off = lim; got = len(rows)
    with ThreadPoolExecutor(max_workers=6) as ex:
        while off < 8000:
            batch = [off + i * lim for i in range(6)]
            res = list(ex.map(lambda o: (o, getj(f"{base}&offset={o}")), batch))
            short = False
            for o, pg in sorted(res):
                r = pg.get("races") or []
                absorb(r); got += len(r)
                if len(r) < lim:
                    short = True
            flush()
            if short:
                break
            off += 6 * lim
    return got


t0 = time.time()
# 1) type filters, probed in parallel (civicAPI is slow tonight)
filtered_ok = False
VARIANTS = {"senate": ["Senate", "US Senate", "U.S. Senate", "United States Senate"],
            "governor": ["Governor", "Gubernatorial"],
            "house": ["House", "US House", "U.S. House", "Representative", "US Representative", "U.S. Representative", "House of Representatives"]}
def probe(office, typ):
    try:
        pg = getj(f"{BASE}&type={urllib.request.quote(typ)}&offset=0", t=20)
    except Exception as e:
        return office, typ, None
    rows = pg.get("races") or []
    words = ("house", "representative", "congress") if office == "house" else (office,)
    good = bool(rows) and all(any(w in str(x.get("type") or "").lower() for w in words) for x in rows)
    if good:
        absorb(rows)
    return office, typ, good
chosen = {}
with ThreadPoolExecutor(max_workers=13) as ex:
    for office, typ, good in ex.map(lambda ot: probe(*ot), [(o, t) for o, ts in VARIANTS.items() for t in ts]):
        if good and office not in chosen:
            chosen[office] = typ
flush()
state["filters"] = chosen
print("filters:", chosen)
for office, typ in chosen.items():
    filtered_ok = True
    state["mode"] = "filtered"
    try:
        crawl(f"{BASE}&type={urllib.request.quote(typ)}", typ)
    except Exception as e:
        print("crawl failed", typ, str(e)[:100])
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
