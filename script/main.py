# main.py (Version: 1.0.0 - Feb 12, 2025
# Updates:
# - Use environment variables for API key and stop IDs.
# - More robust health check (self-restarts if stale, also health check self-recovers if stale data is resolved)
# - Setting up for integration in public docker image.

import os
from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from datetime import datetime, timezone, timedelta

app = FastAPI()

# Load required environment variables
TRIMET_API_KEY = os.getenv("TRIMET_API_KEY")
STOP_IDS = os.getenv("STOP_IDS")

if not TRIMET_API_KEY or not STOP_IDS:
    raise ValueError("Missing required environment variables: TRIMET_API_KEY and/or STOP_IDS")

# Load optional configuration
FETCH_MINUTES = int(os.getenv("FETCH_MINUTES", 45))

# Cached data & last fetch time
cached_data = {}
last_successful_fetch = None

async def fetch_data():
    """Fetch TriMet data and update cache."""
    global cached_data, last_successful_fetch
    print(f"Fetching data for the next {FETCH_MINUTES} minutes.")

    url = f"https://developer.trimet.org/ws/V2/arrivals?locIDs={STOP_IDS}&minutes={FETCH_MINUTES}&appid={TRIMET_API_KEY}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            cached_data = response.json()
            last_successful_fetch = datetime.now(timezone.utc)
            print(f"[{last_successful_fetch}] Data fetched successfully.")
    except (httpx.ConnectTimeout, httpx.HTTPStatusError) as e:
        print(f"[{datetime.now()}] Fetch failed: {e}")
    except Exception as e:
        print(f"[{datetime.now()}] Unexpected error: {e}")

@app.get("/stop/{stop_id}/route/{route_id}")
async def get_next_arrivals(stop_id: int, route_id: int, count: int = 2):
    """Return the next arrivals for a specific stop and route."""
    if not cached_data:
        raise HTTPException(status_code=503, detail="No data available. Please try again later.")

    arrivals = cached_data.get("resultSet", {}).get("arrival", [])
    next_arrivals = [
        {
            "minutes_until_arrival": max((datetime.fromtimestamp(arrival.get("estimated") or arrival.get("scheduled"), tz=timezone.utc) - datetime.now(timezone.utc)).total_seconds() // 60, 0),
            "scheduled_time": datetime.fromtimestamp(arrival.get("scheduled"), tz=timezone.utc).strftime("%I:%M %p")
        }
        for arrival in arrivals
        if arrival.get("locid") == stop_id and arrival.get("signRoute") == route_id
    ][:count]

    if not next_arrivals:
        raise HTTPException(status_code=404, detail="No upcoming arrivals found.")

    return {"next_arrivals": next_arrivals}

@app.get("/health")
async def health():
    """Health check that returns stale status and allows self-recovery."""
    global last_successful_fetch
    if not last_successful_fetch:
        raise HTTPException(status_code=503, detail="No successful data fetch yet.")

    time_since_last_fetch = (datetime.now(timezone.utc) - last_successful_fetch).total_seconds()
    if time_since_last_fetch > 120:
        print(f"Health check failed: Data is stale for {int(time_since_last_fetch)} seconds. Attempting fetch.")
        await fetch_data()  # Try fetching immediately before failing health check
        time_since_last_fetch = (datetime.now(timezone.utc) - last_successful_fetch).total_seconds()

    if time_since_last_fetch > 120:
        raise HTTPException(status_code=503, detail=f"Data is stale. Last fetched {int(time_since_last_fetch)} seconds ago.")

    return {"status": "healthy", "last_fetch": last_successful_fetch.isoformat()}

@app.on_event("startup")
async def startup_event():
    """Initial fetch and periodic updates."""
    await fetch_data()
    asyncio.create_task(periodic_fetch())

async def periodic_fetch():
    """Continuously fetch data every 60 seconds."""
    while True:
        await fetch_data()
        await asyncio.sleep(60)

