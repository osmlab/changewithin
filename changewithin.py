import time, json, requests, os, sys
from ConfigParser import ConfigParser
from lxml import etree
from datetime import datetime
from sets import Set
import pystache

from lib import (
    extractosc, get_bbox, getstate, getosc, point_in_box, point_in_poly,
    hasbuildingtag, getaddresstags, hasaddresschange, loadChangeset
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

elif not config.has_option('email', 'recipients'):
    #
    # Missing recipients fall back to original users.json contents.
    #
    recipients = json.load(open(os.path.join(dir_path, 'users.json')))
    config.set('email', 'recipients', ' '.join(recipients))

#
# Get started with the area of interest (AOI).
#

aoi = json.load(open(os.path.join(dir_path, config.get('area', 'geojson'))))
aoi_poly = aoi['features'][0]['geometry']['coordinates'][0]
aoi_box = get_bbox(aoi_poly)
sys.stderr.write('getting state\n')
state = getstate()
getosc(state)
sys.stderr.write('extracting\n')
extractosc()

sys.stderr.write('reading file\n')

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
            'addr_chg_way': Set(),
            'addr_chg_nd': Set()
        }

sys.stderr.write('finding points\n')

# Find nodes that fall within specified area
context = iter(etree.iterparse('change.osc', events=('start', 'end')))
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
                        addchangeset(n, cid)
                        changesets[cid]['nids'].add(nid)
                        changesets[cid]['addr_chg_nd'].add(nid)
                        stats['addresses'] += 1
                elif len(addr_tags):
                    addchangeset(n, cid)
                    changesets[cid]['nids'].add(nid)
                    changesets[cid]['addr_chg_nd'].add(nid)
                    stats['addresses'] += 1
    n.clear()
    root.clear()

sys.stderr.write('finding changesets\n')

# Find ways that contain nodes that were previously determined to fall within specified area
context = iter(etree.iterparse('change.osc', events=('start', 'end')))
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
                        addchangeset(w, cid)
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

tmpl = """
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
"""

text_tmpl = """
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
"""

html_version = pystache.render(tmpl, {
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

# print html_version

# print resp, resp.text
