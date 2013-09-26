''' Support functions for changewithin.py script.
'''
import time, json, requests, os, sys
from lxml import etree
from sets import Set
from ModestMaps.Geo import MercatorProjection, Location, Coordinate

dir_path = os.path.dirname(os.path.abspath(__file__))

def extractosc(): os.system('gunzip -f change.osc.gz')

def getstate():
    r = requests.get('http://planet.openstreetmap.org/replication/day/state.txt')
    return r.text.split('\n')[1].split('=')[1]

def getosc(state):
    # zero-pad state so it can be safely split.
    state = '000000000' + state
    path = '%s/%s/%s' % (state[-9:-6], state[-6:-3], state[-3:])

    stateurl = 'http://planet.openstreetmap.org/replication/day/%s.osc.gz' % path
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
    changeset['map_link'] = 'http://www.openstreetmap.org/?lat=%s&lon=%s&zoom=%s&layers=M' % (extent['lon'], extent['lat'], extent['zoom'])
    return changeset
