changewithin is a simple script that pulls [daily changes](http://planet.openstreetmap.org/)
from OpenStreetMap with `requests`, parses them with `lxml`, finds the ones that are inside
of a GeoJSON shape, sorts out the ones that are buildings, and emails a set of users
with [mailgun](http://www.mailgun.com/).

## Installation

Requires wget, use [homebrew](http://brew.sh/) for the simplest installation:

    brew install wget

Requires Python with lxml, requests, pystache

    mkvirtualenv --no-site-packages changewithin
    pip install -r requirements.txt

## Running

    python changewithin.py

## Automating

Assuming the above installation, edit your [cron table](https://en.wikipedia.org/wiki/Cron) (`crontab -e`) to run the script once a day at 7:00am.

    0 7 * * * ~/path/to/changewithin/bin/python ~/path/to/changewithin/changewithin.py

