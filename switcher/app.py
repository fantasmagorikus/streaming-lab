import os, asyncio
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, Response, HTTPException
from prometheus_client import Gauge, Counter, generate_latest, CONTENT_TYPE_LATEST

P=os.getenv("PRIMARY_BASE_URL","http://origin-primary/hls").rstrip("/")
B=os.getenv("BACKUP_BASE_URL" ,"http://origin-backup/hls").rstrip("/")
PL=os.getenv("PLAYLIST_PATH","index.m3u8")
INT=int(os.getenv("CHECK_INTERVAL_SECONDS","5"))
TH =float(os.getenv("SEGMENT_AGE_THRESHOLD_SECONDS","20"))
N  =int(os.getenv("REQUIRED_WINDOWS","3"))

app=FastAPI(title="switcher")
active="primary"
bad_win=0   # janelas ruins do primário (para cair p/ backup)
good_win=0  # janelas boas do primário (para voltar do backup)

gA=Gauge("switcher_active_origin","1 primary, 0 backup"); gA.set(1)
gS=Gauge("segment_age_seconds","age",["origin"])
c5=Counter("origin_http_5xx_total","5xx",["origin"])
cF=Counter("failovers_total","failovers")
cR=Counter("switchbacks_total","switchbacks_to_primary")

def now(): return datetime.now(timezone.utc)
def pdt_age(txt:str)->float:
    last=None
    for line in txt.splitlines():
        if line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            try: last=datetime.fromisoformat(line.split(":",1)[1].strip().replace("Z","+00:00"))
            except: pass
    if not last: raise ValueError("no PDT")
    return (now()-last).total_seconds()

async def loop():
    global active, bad_win, good_win
    async with httpx.AsyncClient() as c:
        while True:
            try:
                pr=await c.get(f"{P}/{PL}",timeout=5)
                br=await c.get(f"{B}/{PL}",timeout=5)
                if 500<=pr.status_code<600: c5.labels("primary").inc()
                if 500<=br.status_code<600: c5.labels("backup").inc()
                pr.raise_for_status(); br.raise_for_status()

                pa=pdt_age(pr.text); ba=pdt_age(br.text)
                gS.labels("primary").set(pa); gS.labels("backup").set(ba)

                if active=="primary":
                    bad_win = bad_win+1 if pa>TH else 0
                    if bad_win>=N:
                        active="backup"; gA.set(0); cF.inc(); bad_win=0; good_win=0
                else:  # active == "backup"
                    good_win = good_win+1 if pa<=TH else 0
                    if good_win>=N:
                        active="primary"; gA.set(1); cR.inc(); good_win=0; bad_win=0

            except Exception:
                pass
            await asyncio.sleep(INT)

@app.on_event("startup")
async def _s(): asyncio.create_task(loop())

def base(): return P if active=="primary" else B

@app.get("/hls/{path:path}")
async def hls(path:str):
    async with httpx.AsyncClient() as c: r=await c.get(f"{base()}/{path}",timeout=10)
    if r.status_code>=400: raise HTTPException(r.status_code)
    return Response(r.content, headers={"Content-Type": r.headers.get("content-type","application/octet-stream")})

@app.get("/metrics")
def m(): return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/healthz")
def h(): return {"active_origin": active}
