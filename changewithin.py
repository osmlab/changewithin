import time, json, requests, os, sys
from lxml import etree
from datetime import datetime
from sys import argv
from sets import Set
import pystache

def extractosc(): os.system('gunzip -f change.osc.gz')
def readosc(): return etree.parse('change.osc')

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
    
def getaddresstags(tags):
    addr_tags = []
    for t in tags:
        key = t.get('k')
        if key.split(':')[0] == 'addr':
            addr_tags.append(t.attrib)
    return addr_tags
    
def hasaddresschange(gid, addr, version, elem):
    url = 'http://api.openstreetmap.org/api/0.6/%s/%s/history' % (elem, gid)
    r = requests.get(url)
    if not r.text: return False
    e = etree.fromstring(r.text.encode('utf-8'))
    previous_elem = e.find(".//%s[@version='%s']" % (elem, (version - 1)))
    previous_addr = getaddresstags(previous_elem.findall(".//tag[@k]"))
    if len(addr) != len(previous_addr):
        return True
    else:
        for a in addr:
            if a not in previous_addr: return True
    return False

def loadChangeset(changeset):
    changeset['wids'] = list(changeset['wids'])
    changeset['nids'] = list(changeset['nids'])
    changeset['addr_chg'] = list(changeset['addr_chg'])
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
    changeset['map_img'] = 'http://api.tiles.mapbox.com/v3/examples.map-uci7ul8p/%s,%s,15/300x225.png' % (center_lon, center_lat)
    changeset['map_link'] = 'http://www.openstreetmap.org/?lat=%s&lon=%s&zoom=15&layers=M' % (center_lat, center_lon)
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
stats['addresses'] = 0

def addchangeset(el, cid):
    if not changesets.get(cid, False):
        changesets[cid] = {
            'id': cid,
            'user': el.get('user'),
            'uid': el.get('uid'),
            'wids': Set(),
            'nids': Set(),
            'addr_chg': Set()
        }

sys.stderr.write('finding points\n')

for n in tree.iterfind('.//node'):
    lon = float(n.get('lon', 0))
    lat = float(n.get('lat', 0))
    if point_in_box(lon, lat, nybox) and pip(lon, lat):
        cid = n.get('changeset')
        nid = n.get('id', -1)
        nids.add(nid)
        ntags = n.findall(".//tag[@k]")
        addr_tags = getaddresstags(ntags)
        version = int(n.get('version'))
        if version != 1:
            if hasaddresschange(nid, addr_tags, version, 'node'):
                addchangeset(n, cid)
                changesets[cid]['addr_chg'].add(nid)
                stats['addresses'] += 1
        elif len(addr_tags):
            addchangeset(n, cid)
            changesets[cid]['addr_chg'].add(nid)
            stats['addresses'] += 1

sys.stderr.write('finding changesets\n')

for w in tree.iterfind('.//way'):
    relevant = False
    cid = w.get('changeset')
    wid = w.get('id', -1)
    if hasbuildingtag(w):
        for nd in w.iterfind('./nd'):
            if nd.get('ref', -2) in nids:
                relevant = True
                addchangeset(w, cid)
                nid = nd.get('ref', -2)
                changesets[cid]['nids'].add(nid)
                changesets[cid]['wids'].add(wid)
    if relevant:
        stats['buildings'] += 1
        wtags = w.findall(".//tag[@k]")
        version = int(w.get('version'))
        addr_tags = getaddresstags(wtags)
        if version != 1:
            if hasaddresschange(wid, addr_tags, version, 'way'):
                changesets[cid]['addr_chg'].add(wid)
                stats['addresses'] += 1
        elif len(addr_tags):
            changesets[cid]['addr_chg'].add(wid)
            stats['addresses'] += 1

changesets = map(loadChangeset, changesets.values())

stats['total'] = len(changesets)

if len(changesets) > 1000:
    changesets = changesets[:999]
    stats['limit_exceed'] = 'Note: For performance reasons only the first 1000 changesets are displayed.'

tmpl = """
<div style='font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;color:#333;max-width:600px;'>
<h1>Summary</h1>
{{#stats}}
<ul style='font-size:14px;line-height:17px;list-style:none;margin-left:0;padding-left:0;'>
<li>Total changesets: {{total}}</li>
<li>Total address changes: {{addresses}}</li>
<li>Total building footprint changes: {{buildings}}</li>
{{#limit_exceed}}
<p style='font-size:13px;font-style:italic;'>{{limit_exceed}}</p>
{{/limit_exceed}}
</ul>
{{/stats}}
{{#changesets}}
<h2 style='border-top:1px solid #ccc;padding-top:15px;'>Changeset <a href='http://openstreetmap.org/browse/changeset/{{id}}' style='text-decoration:none;color:#3879D9;'>#{{id}}</a></h2>
<p style='font-size:14px;line-height:17px;'>
<a href='http://openstreetmap.org/user/{{#details}}{{user}}{{/details}}' style='text-decoration:none;color:#3879D9;font-weight:bold;'>{{#details}}{{user}}{{/details}}</a>: {{comment}}
</p>
<p style='font-size:14px;line-height:17px;'>
Changed buildings: {{#wids}}<a href='http://openstreetmap.org/browse/way/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/wids}}
</p>
<p style='font-size:14px;line-height:17px;'>
Changed addresses: {{#addr_chg}}<a href='http://openstreetmap.org/browse/way/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/addr_chg}}
</p>
</ul>
<a href='{{map_link}}'><img src='{{map_img}}' style='border:1px solid #ccc;' /></a>
{{/changesets}}
</div>
"""

text_tmpl = """
### Summary ###

{{#stats}}
Total changesets: {{total}}
Total building footprint changes: {{buildings}}
Total address changes: {{addresses}}
{{#limit_exceed}}

{{limit_exceed}}

{{/limit_exceed}}
{{/stats}}

{{#changesets}}
--- Changeset #{{id}} ---
URL: http://openstreetmap.org/browse/changeset/{{id}}
User: http://openstreetmap.org/user/{{#details}}{{user}}{{/details}}
Comment: {{comment}}

Changed buildings: {{wids}}
Changed addresses: {{addr_chg}}
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

now = datetime.now()

resp = requests.post(('https://api.mailgun.net/v2/changewithin.mailgun.org/messages'),
    auth = ('api', 'key-7y2k6qu8-qq1w78o1ow1ms116pkn31j7'),
    data = {
            'from': 'Change Within <changewithin@changewithin.mailgun.org>',
            'to': json.load(open('users.json')),
            'subject': 'OSM building and address changes %s' % now.strftime("%B %d %Y"),
            'text': text_version,
            "html": html_version,
    })

f_out = open('osm_change_report_%s.html' % now.strftime("%m-%d-%y"), 'w')
f_out.write(html_version.encode('utf-8'))
f_out.close()

# print html_version

# print resp, resp.text
