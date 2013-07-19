changewithin is a simple script that pulls [daily changes](http://planet.openstreetmap.org/)
from OpenStreetMap with `requests`, parses them with `lxml`, finds the ones that are inside
of a GeoJSON shape, sorts out the ones that are buildings, and emails a set of users
with [mailgun](http://www.mailgun.com/).

## Installation

Requires Python with lxml, requests, pystache

    mkvirtualenv --no-site-packages changewithin
    pip install -r requirements.txt

## Running

    python changewithin.py
