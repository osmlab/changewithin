''' Support functions for changewithin.py script.
'''
import time, json, requests, os, sys
from lxml import etree
from sets import Set
from ModestMaps.Geo import MercatorProjection, Location, Coordinate
from tempfile import mkstemp

dir_path = os.path.dirname(os.path.abspath(__file__))

def getstate():
    r = requests.get('http://planet.openstreetmap.org/replication/day/state.txt')
    return r.text.split('\n')[1].split('=')[1]

def getosc():
    state = getstate()

    # zero-pad state so it can be safely split.
    state = '000000000' + state
    path = '%s/%s/%s' % (state[-9:-6], state[-6:-3], state[-3:])
    
    # prepare a local file to store changes
    handle, filename = mkstemp(prefix='change-', suffix='.osc.gz')
    os.close(handle)

    stateurl = 'http://planet.openstreetmap.org/replication/day/%s.osc.gz' % path
    sys.stderr.write('downloading %s...\n' % stateurl)
    status = os.system('wget --quiet %s -O %s' % (stateurl, filename))
    
    if status:
        status = os.system('curl --silent %s -o %s' % (stateurl, filename))
    
    if status:
        raise Exception('Failure from both wget and curl')
    
    sys.stderr.write('extracting %s...\n' % filename)
    os.system('gunzip -f %s' % filename)

    # knock off the ".gz" suffix and return
    return filename[:-3]

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

def coordAverage(c1, c2): return (float(c1) + float(c2)) / 2

def getExtent(s):
    extent = {}
    m = MercatorProjection(0)

    points = [[float(s['max_lat']), float(s['min_lon'])], [float(s['min_lat']), float(s['max_lon'])]]
    
    if (points[0][0] - points[1][0] == 0) or (points[1][1] - points[0][1] == 0):
        extent['lat'] = points[0][0]
        extent['lon'] = points[1][1]
        extent['zoom'] = 18
    else:
        i = float('inf')
         
        w = 800
        h = 600
         
        tl = [min(map(lambda x: x[0], points)), min(map(lambda x: x[1], points))]
        br = [max(map(lambda x: x[0], points)), max(map(lambda x: x[1], points))]
         
        c1 = m.locationCoordinate(Location(tl[0], tl[1]))
        c2 = m.locationCoordinate(Location(br[0], br[1]))
         
        while (abs(c1.column - c2.column) * 256.0) < w and (abs(c1.row - c2.row) * 256.0) < h:
            c1 = c1.zoomBy(1)
            c2 = c2.zoomBy(1)
         
        center = m.coordinateLocation(Coordinate(
            (c1.row + c2.row) / 2,
            (c1.column + c2.column) / 2,
            c1.zoom))
        
        extent['lat'] = center.lat
        extent['lon'] = center.lon
        if c1.zoom > 18:
            extent['zoom'] = 18
        else:
            extent['zoom'] = c1.zoom
        
    return extent

def hasbuildingtag(n):
    return n.find(".//tag[@k='building']") is not None
    
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
    changeset['addr_chg_nd'] = list(changeset['addr_chg_nd'])
    changeset['addr_chg_way'] = list(changeset['addr_chg_way'])
    url = 'http://api.openstreetmap.org/api/0.6/changeset/%s' % changeset['id']
    r = requests.get(url)
    if not r.text: return changeset
    t = etree.fromstring(r.text.encode('utf-8'))
    changeset['details'] = dict(t.find('.//changeset').attrib)
    comment = t.find(".//tag[@k='comment']")
    created_by = t.find(".//tag[@k='created_by']")
    if comment is not None: changeset['comment'] = comment.get('v')
    if created_by is not None: changeset['created_by'] = created_by.get('v')
    extent = getExtent(changeset['details'])
    changeset['map_img'] = 'http://api.tiles.mapbox.com/v3/lxbarth.map-lxoorpwz/%s,%s,%s/300x225.png' % (extent['lon'], extent['lat'], extent['zoom'])
    changeset['map_link'] = 'http://www.openstreetmap.org/?lat=%s&lon=%s&zoom=%s&layers=M' % (extent['lat'], extent['lon'], extent['zoom'])
    return changeset

def addchangeset(el, cid, changesets):
    if not changesets.get(cid, False):
        changesets[cid] = {
            'id': cid,
            'user': el.get('user'),
            'uid': el.get('uid'),
            'wids': set(),
            'nids': set(),
            'addr_chg_way': set(),
            'addr_chg_nd': set()
        }

#
# Templates for generated emails.
#

html_tmpl = '''
<div style='font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;color:#333;max-width:600px;'>
<p style='float:right;'>{{date}}</p>
<h1 style='margin-bottom:10px;'>Summary</h1>
{{#stats}}
<ul style='font-size:15px;line-height:17px;list-style:none;margin-left:0;padding-left:0;'>
<li>Total changesets: <strong>{{total}}</strong></li>
<li>Total address changes: <strong>{{addresses}}</strong></li>
<li>Total building footprint changes: <strong>{{buildings}}</strong></li>
</ul>
{{#limit_exceed}}
<p style='font-size:13px;font-style:italic;'>{{limit_exceed}}</p>
{{/limit_exceed}}
{{/stats}}
{{#changesets}}
<h2 style='border-bottom:1px solid #ddd;padding-top:15px;padding-bottom:8px;'>Changeset <a href='http://openstreetmap.org/browse/changeset/{{id}}' style='text-decoration:none;color:#3879D9;'>#{{id}}</a></h2>
<p style='font-size:14px;line-height:17px;margin-bottom:20px;'>
<a href='http://openstreetmap.org/user/{{#details}}{{user}}{{/details}}' style='text-decoration:none;color:#3879D9;font-weight:bold;'>{{#details}}{{user}}{{/details}}</a>: {{comment}}
</p>
<p style='font-size:14px;line-height:17px;margin-bottom:0;'>
Changed buildings: {{#wids}}<a href='http://openstreetmap.org/browse/way/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/wids}}
</p>
<p style='font-size:14px;line-height:17px;margin-top:5px;margin-bottom:20px;'>
Changed addresses: {{#addr_chg_nd}}<a href='http://openstreetmap.org/browse/node/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/addr_chg_nd}}{{#addr_chg_way}}<a href='http://openstreetmap.org/browse/way/{{.}}/history' style='text-decoration:none;color:#3879D9;'>#{{.}}</a> {{/addr_chg_way}}
</p>
<a href='{{map_link}}'><img src='{{map_img}}' style='border:1px solid #ddd;' /></a>
{{/changesets}}
</div>
'''

text_tmpl = '''
### Summary ###
{{date}}

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
Changed addresses: {{addr_chg_nd}} {{addr_chg_way}}
{{/changesets}}
'''