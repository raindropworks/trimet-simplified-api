# trimet-simplified-api
docker container to simplify TriMet's API for use in local environments
 
This started out as a personal use project, that I thought others might have use for. The original use case was to take the massive amount of data that Trimet's API puts out, and parse it into a limited amount of data (currently arrival times for specific stops) and output it as JSON data that can be used by Home Assistant sensors to show arrivals for specific stops 
 
Prerequisites:

1) Docker (bit of a duh, here)
2) A developer key for TriMet's API (https://developer.trimet.org/)

This container will query the TriMet API once per minute for information about the stops that are requested in the docker configuration, and then parse the arrival times into a more human readable format that is published to a small internal web server. (for example, stop 7586 on line 44, the PCC Sylvania bus from SW 5th and Alder, would be available at http://localhost/stop/7586/route/44)
