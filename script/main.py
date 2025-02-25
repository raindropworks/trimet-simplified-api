# main.py (Version: 0.1.5a - Feb 25, 2025)
# Updates:
# integrating environment variables to remove sensitive information hardcoded in script

import os
from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

app = FastAPI()

# Load required environment variables
TRIMET_API_KEY = os.getenv("TRIMET_API_KEY")
STOP_IDS = os.getenv("STOP_IDS")

if not TRIMET_API_KEY or not STOP_IDS:
    raise ValueError("Missing required environment variables: TRIMET_API_KEY and/or STOP_IDS")

# Cached data for TriMet arrivals and last successful fetch time
cached_data = {}
last_successful_fetch = None  # Timestamp of the last successful data fetch

# Load optional configuration
FETCH_MINUTES = int(os.getenv("FETCH_MINUTES", 45))


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
    except httpx.ConnectTimeout:
        print(f"[{datetime.now()}] Connection timeout. Retrying in next interval...")
    except httpx.HTTPStatusError as e:
        print(f"[{datetime.now()}] HTTP error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        print(f"[{datetime.now()}] Unexpected error: {e}")


def convert_to_pacific(unix_time: int) -> str:
    """Convert Unix time (milliseconds) to a readable Pacific time string (only time of day)."""
    utc_time = datetime.fromtimestamp(unix_time / 1000, tz=timezone.utc)
    pacific_time = utc_time.astimezone(timezone(timedelta(hours=-8)))
    return pacific_time.strftime("%I:%M %p")


def calculate_minutes_until(unix_time: Optional[int]) -> Optional[int]:
    """Calculate minutes until arrival. Return None if unix_time is None."""
    if unix_time is None:
        return None
    arrival_time = datetime.fromtimestamp(unix_time / 1000, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    return max(int((arrival_time - now).total_seconds() // 60), 0)


@app.get("/stop/{stop_id}/route/{route_id}")
async def get_next_arrivals(stop_id: int, route_id: int, count: Optional[int] = 2):
    """Return the next arrivals for a specific stop and route."""
    if not cached_data:
        raise HTTPException(status_code=503, detail="No data available. Please try again later.")
    
    arrivals = cached_data.get("resultSet", {}).get("arrival", [])
    next_arrivals = [
        {
            "minutes_until_arrival": calculate_minutes_until(arrival.get("estimated") or arrival.get("scheduled")),
            "scheduled_time": convert_to_pacific(arrival.get("scheduled")),
        }
        for arrival in arrivals
        if arrival.get("locid") == stop_id and arrival.get("signRoute") == route_id
        and calculate_minutes_until(arrival.get("estimated") or arrival.get("scheduled")) is not None
    ]

    if len(next_arrivals) > count:
        next_arrivals = next_arrivals[:count]  # Limit to `count` arrivals

    if not next_arrivals:
        raise HTTPException(status_code=404, detail="No upcoming arrivals found for this stop and route.")
    
    return {"next_arrivals": next_arrivals}


@app.get("/health")
async def health():
    """Health check endpoint to ensure the data is up-to-date."""
    if not last_successful_fetch:
        raise HTTPException(status_code=503, detail="No successful data fetch yet.")
    
    time_since_last_fetch = (datetime.now(timezone.utc) - last_successful_fetch).total_seconds()
    if time_since_last_fetch > 120:  # Data is stale if older than 2 minutes
        raise HTTPException(status_code=503, detail=f"Data is stale. Last fetched {int(time_since_last_fetch)} seconds ago.")
    
    return {"status": "healthy", "last_fetch": last_successful_fetch.isoformat()}


@app.on_event("startup")
async def startup_event():
    """Initial data fetch on startup and schedule periodic updates every 60 seconds."""
    await fetch_data()
    asyncio.create_task(periodic_fetch())


async def periodic_fetch():
    """Fetch data periodically every 60 seconds."""
    while True:
        try:
            await fetch_data()
        except Exception as e:
            print(f"[{datetime.now()}] Error during periodic fetch: {e}")
        await asyncio.sleep(60)

