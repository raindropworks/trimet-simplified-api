# trimet-simplified-api
docker container to simplify TriMet's API for use in local environments
 
This started out as a personal use project, that I thought others might have use for. The original use case was to take the massive amount of data that Trimet's API puts out, and parse it into a limited amount of data (currently arrival times for specific stops) and output it as JSON data that can be used by Home Assistant sensors to show arrivals for specific stops 
 
Prerequisites:

1) Docker (bit of a duh, here)
2) A developer key for TriMet's API (<https://developer.trimet.org/>)

This container will query the TriMet API once per minute for information about the stops that are requested in the docker configuration, and then parse the arrival times into a more human readable format that is published to a small internal web server. (for example, stop 7586 on line 44, the PCC Sylvania bus from SW 5th and Alder, would be available at `http://localhost/stop/7586/route/44`)

Docker installation:

```yaml
services:
  trimet-api:
    image: rdhi1734/trimet-simplified-api
    container_name: trimet-api
    ports:
      - "65000:8000" # highly recommend not using the default port
    environment:
      - TRIMET_API_KEY=${TRIMET_API} #Required
      - STOP_IDS=${STOPS} #Required. Format as '7586,1385,12980'
      - FETCH_MINUTES=45 #Optional, defaults to 45 minutes
      - TZ=America/Los_Angeles
    restart: always
    healthcheck: #Optional, add in if you want health checking
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 1m
      timeout: 10s
      retries: 3
      start_period: 30s
```

Integration into services like Home Assistant will require a variety of RESTful sensors, templates and HTML cards in Lovelace. I'll have a separate update for that later.