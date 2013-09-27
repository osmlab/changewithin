import time, json, requests, os, sys
from ConfigParser import ConfigParser
from lxml import etree
from datetime import datetime
from sets import Set
import pystache

from lib import (
    get_bbox, getstate, getosc, point_in_box, point_in_poly,
    hasbuildingtag, getaddresstags, hasaddresschange, loadChangeset,
    addchangeset, html_tmpl, text_tmpl
    )

dir_path = os.path.dirname(os.path.abspath(__file__))

#
# Configure for use. See config.ini for details.
#
config = ConfigParser()
config.read(os.path.join(dir_path, 'config.ini'))

#
# Environment variables override config file.
#
if 'AREA_GEOJSON' in os.environ:
    config.set('area', 'geojson', os.environ['AREA_GEOJSON'])

if 'MAILGUN_DOMAIN' in os.environ:
    config.set('mailgun', 'domain', os.environ['MAILGUN_DOMAIN'])

if 'MAILGUN_API_KEY' in os.environ:
    config.set('mailgun', 'api_key', os.environ['MAILGUN_API_KEY'])

if 'EMAIL_RECIPIENTS' in os.environ:
    config.set('email', 'recipients', os.environ['EMAIL_RECIPIENTS'])

#
# Get started with the area of interest (AOI).
#

aoi = json.load(open(os.path.join(dir_path, config.get('area', 'geojson'))))
aoi_poly = aoi['features'][0]['geometry']['coordinates'][0]
aoi_box = get_bbox(aoi_poly)
sys.stderr.write('getting state\n')
osc_file = getosc()

sys.stderr.write('reading file\n')

nids = Set()
changesets = {}
stats = {}
stats['buildings'] = 0
stats['addresses'] = 0

sys.stderr.write('finding points\n')

# Find nodes that fall within specified area
context = iter(etree.iterparse(osc_file, events=('start', 'end')))
event, root = context.next()
for event, n in context:
    if event == 'start':
        if n.tag == 'node':
            lon = float(n.get('lon', 0))
            lat = float(n.get('lat', 0))
            if point_in_box(lon, lat, aoi_box) and point_in_poly(lon, lat, aoi_poly):
                cid = n.get('changeset')
                nid = n.get('id', -1)
                nids.add(nid)
                ntags = n.findall(".//tag[@k]")
                addr_tags = getaddresstags(ntags)
                version = int(n.get('version'))
                
                # Capture address changes
                if version != 1:
                    if hasaddresschange(nid, addr_tags, version, 'node'):
                        addchangeset(n, cid, changesets)
                        changesets[cid]['nids'].add(nid)
                        changesets[cid]['addr_chg_nd'].add(nid)
                        stats['addresses'] += 1
                elif len(addr_tags):
                    addchangeset(n, cid, changesets)
                    changesets[cid]['nids'].add(nid)
                    changesets[cid]['addr_chg_nd'].add(nid)
                    stats['addresses'] += 1
    n.clear()
    root.clear()

sys.stderr.write('finding changesets\n')

# Find ways that contain nodes that were previously determined to fall within specified area
context = iter(etree.iterparse(osc_file, events=('start', 'end')))
event, root = context.next()
for event, w in context:
    if event == 'start':
        if w.tag == 'way':
            relevant = False
            cid = w.get('changeset')
            wid = w.get('id', -1)
            
            # Only if the way has 'building' tag
            if hasbuildingtag(w):
                for nd in w.iterfind('./nd'):
                    if nd.get('ref', -2) in nids:
                        relevant = True
                        addchangeset(w, cid, changesets)
                        nid = nd.get('ref', -2)
                        changesets[cid]['nids'].add(nid)
                        changesets[cid]['wids'].add(wid)
            if relevant:
                stats['buildings'] += 1
                wtags = w.findall(".//tag[@k]")
                version = int(w.get('version'))
                addr_tags = getaddresstags(wtags)
                
                # Capture address changes
                if version != 1:
                    if hasaddresschange(wid, addr_tags, version, 'way'):
                        changesets[cid]['addr_chg_way'].add(wid)
                        stats['addresses'] += 1
                elif len(addr_tags):
                    changesets[cid]['addr_chg_way'].add(wid)
                    stats['addresses'] += 1
    w.clear()
    root.clear()

changesets = map(loadChangeset, changesets.values())

stats['total'] = len(changesets)

if len(changesets) > 1000:
    changesets = changesets[:999]
    stats['limit_exceed'] = 'Note: For performance reasons only the first 1000 changesets are displayed.'
    
now = datetime.now()

html_version = pystache.render(html_tmpl, {
    'changesets': changesets,
    'stats': stats,
    'date': now.strftime("%B %d, %Y")
})

text_version = pystache.render(text_tmpl, {
    'changesets': changesets,
    'stats': stats,
    'date': now.strftime("%B %d, %Y")
})

resp = requests.post(('https://api.mailgun.net/v2/%s/messages' % config.get('mailgun', 'domain')),
    auth = ('api', config.get('mailgun', 'api_key')),
    data = {
            'from': 'Change Within <changewithin@%s>' % config.get('mailgun', 'domain'),
            'to': config.get('email', 'recipients').split(),
            'subject': 'OSM building and address changes %s' % now.strftime("%B %d, %Y"),
            'text': text_version,
            "html": html_version,
    })

f_out = open('osm_change_report_%s.html' % now.strftime("%m-%d-%y"), 'w')
f_out.write(html_version.encode('utf-8'))
f_out.close()

os.unlink(osc_file)

# print html_version

# print resp, resp.text
