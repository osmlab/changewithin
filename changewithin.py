import time, json, requests, os, sys
from lxml import etree
from datetime import datetime
from sys import argv
from sets import Set
import pystache

def extractosc(): os.system('gunzip -f change.osc.gz')
def readosc(): return etree.parse('hourtest.osc')

def getstate():
    r = requests.get('http://planet.openstreetmap.org/replication/day/state.txt')
    return r.text.split('\n')[1].split('=')[1]

def getosc(state):
    stateurl = 'http://planet.openstreetmap.org/replication/day/000/000/%s.osc.gz' % state
    sys.stderr.write('downloading %s...\n' % stateurl)
    os.system('wget --quiet %s -O change.osc.gz' % stateurl)

def get_bbox(poly):
    box = [200, 200, -200, -200]
    for p in poly:
        if p[0] < box[0]: box[0] = p[0]
        if p[0] > box[2]: box[2] = p[0]
        if p[1] < box[1]: box[1] = p[1]
        if p[1] > box[3]: box[3] = p[1]
    return box

def point_in_box(x, y, box):
    return x > box[0] and x < box[2] and y > box[1] and y < box[3]

def point_in_poly(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in xrange(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def pip(lon, lat): return point_in_poly(lon, lat, nypoly)

def coordAverage(c1, c2): return (float(c1) + float(c2)) / 2

def hasbuildingtag(n):
    return n.find(".//tag[@k='building']") is not None or n.find(".//tag[@k='amenity']") is not None

def loadChangeset(changeset):
    changeset['wids'] = list(changeset['wids'])
    changeset['nids'] = list(changeset['nids'])
    url = 'http://api.openstreetmap.org/api/0.6/changeset/%s' % changeset['id']
    r = requests.get(url)
    if not r.text: return changeset
    t = etree.fromstring(r.text.encode('utf-8'))
    changeset['details'] = dict(t.find('.//changeset').attrib)
    comment = t.find(".//tag[@k='comment']")
    created_by = t.find(".//tag[@k='created_by']")
    if comment is not None: changeset['comment'] = comment.get('v')
    if created_by is not None: changeset['created_by'] = created_by.get('v')
    center_lat = coordAverage(changeset['details']['min_lat'], changeset['details']['max_lat'])
    center_lon = coordAverage(changeset['details']['min_lon'], changeset['details']['max_lon'])
    changeset['map_img'] = 'http://api.tiles.mapbox.com/v3/matt.map-38s82292/%s,%s,16/300x300.png' % (center_lon, center_lat)
    return changeset

ny = json.load(open('nyc.geojson'))
nypoly = ny['features'][0]['geometry']['coordinates'][0]
nybox = get_bbox(nypoly)
sys.stderr.write('getting state\n')
state = getstate()
getosc(state)
sys.stderr.write('extracting\n')
extractosc()

sys.stderr.write('reading file\n')
tree = readosc()

nids = Set()
changesets = {}
stats = {}
stats['buildings'] = 0

sys.stderr.write('finding points\n')

for n in tree.iterfind('.//node'):
    lon = float(n.get('lon', 0))
    lat = float(n.get('lat', 0))
    if point_in_box(lon, lat, nybox) and pip(lon, lat):
        nids.add(n.get('id', -1))

sys.stderr.write('finding changesets\n')

for w in tree.iterfind('.//way'):
    building = False
    cid = w.get('changeset')
    wid = w.get('id', -1)
    for nd in w.iterfind('./nd'):
        if nd.get('ref', -2) in nids and hasbuildingtag(w):
            building = True
            if not changesets.get(cid, False):
                changesets[cid] = {
                    'id': cid,
                    'user': w.get('user'),
                    'uid': w.get('uid'),
                    'wids': Set(),
                    'nids': Set()
                }
            nid = nd.get('ref', -2)
            changesets[cid]['nids'].add(nid)
            changesets[cid]['wids'].add(wid)
    if building:
        stats['buildings'] += 1

changesets = map(loadChangeset, changesets.values())

stats['total'] = len(changesets)

tmpl = """
<h1>Summary</h1>
{{#stats}}
Total changesets: {{total}}<br>
Total building footprint changes: {{buildings}}
{{/stats}}
{{#changesets}}
<h2>Changeset #<a href='http://openstreetmap.org/browse/changeset/{{id}}'>{{id}}</a></h2>
<p>
<a href='http://openstreetmap.org/user/{{#details}}{{user}}{{/details}}'>{{#details}}{{user}}{{/details}}</a>: {{comment}}
</p>
Changed buildings: {{#wids}}<a href='http://openstreetmap.org/browse/way/{{.}}'>#{{.}}</a>{{/wids}}
<img src='{{map_img}}' />
{{/changesets}}
"""

text_tmpl = """
## OSM Change Report
{{#changesets}}

<h2>Changeset http://openstreetmap.org/browse/changeset/{{id}}
<p>
user http://openstreetmap.org/user/{{#details}}{{user}}{{/details}} {{#details}}{{user}}{{/details}} used {{created_by}}
</p>

### Ways
{{#wids}}
* http://openstreetmap.org/browse/way/{{.}}
{{/wids}}

### Nodes
<ul>
{{#nids}}
* http://openstreetmap.org/browse/node/{{.}}
{{/nids}}
</ul>
{{/changesets}}
"""

html_version = pystache.render(tmpl, {
    'changesets': changesets,
    'stats': stats
})

text_version = pystache.render(text_tmpl, {
    'changesets': changesets,
    'stats': stats
})

resp = requests.post(('https://api.mailgun.net/v2/changewithin.mailgun.org/messages'),
    auth = ('api', 'key-7y2k6qu8-qq1w78o1ow1ms116pkn31j7'),
    data = {
            'from': 'Change Within <changewithin@changewithin.mailgun.org>',
            'to': json.load(open('users.json')),
            'subject': 'Daily OSM Report',
            'text': text_version,
            "html": html_version,
    })

print html_version

# print resp, resp.text
