# main.py (Version: 0.1.5 - Feb 11, 2025)
# Updates:
# - Health check endpoint to ensure data freshness.
# - Ensures periodic fetch continues to run.
# - Logs more detailed errors for troubleshooting.

from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

app = FastAPI()

# Cached data for TriMet arrivals and last successful fetch time
cached_data = {}
last_successful_fetch = None  # Timestamp of the last successful data fetch


async def fetch_data():
    """Fetch data from the TriMet API with a dynamic time range based on the current time."""
    global cached_data, last_successful_fetch
    current_hour = datetime.now().hour
    minutes = 300 if 0 <= current_hour < 5 else 45  # 300 minutes from 12 AM to 5 AM, 45 minutes otherwise
    print(f"Fetching data with time range: {minutes} minutes")

    url = f"https://developer.trimet.org/ws/V2/arrivals?locIDs=4609,13948,13955,12957,13297,1416&minutes={minutes}&appid=OBFUSCATED_API"
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

