# main.py (Version: 0.1.2 - Feb 10, 2025)
# Updates:
# - Scheduled times display only time of day (HH:MM AM/PM).
# - Data fetched every 60 seconds.
# - Improved filtering to avoid skipping valid arrivals.

from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional

app = FastAPI()

# Cached data for TriMet arrivals
cached_data = {}

async def fetch_data():
    """Fetch data from the TriMet API with a dynamic time range based on current time."""
    global cached_data
    current_hour = datetime.now().hour

    # Set time range dynamically: 300 minutes from 12 AM to 5 AM, 45 minutes otherwise
    if 0 <= current_hour < 5:
        minutes = 300  # Midnight to 5 AM
    else:
        minutes = 45  # 5 AM to Midnight

    print(f"Fetching data with time range: {minutes} minutes")  # Log the time range for debugging

    url = f"https://developer.trimet.org/ws/V2/arrivals?locIDs=4609,13948,13955,12957,13297,1416&minutes={minutes}&appid=OBFUSCATED_API"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            cached_data = response.json()
            print("Data fetched successfully.")
        else:
            print(f"Failed to fetch data: {response.status_code}")

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

@app.on_event("startup")
async def startup_event():
    """Initial data fetch on startup and schedule periodic updates every 60 seconds."""
    await fetch_data()  # Initial fetch
    asyncio.create_task(periodic_fetch())  # Schedule periodic updates

async def periodic_fetch():
    """Fetch data periodically every 60 seconds."""
    while True:
        await fetch_data()
        await asyncio.sleep(60)  # Wait for 60 seconds before fetching again
