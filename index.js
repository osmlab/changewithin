var pip = require('point-in-polygon'),
    request = require('request'),
    fs = require('fs'),
    cheerio = require('cheerio'),
    linger = require('linger');
    zlib = require('zlib'),
    http = require('http'),
    fs = require('fs');

module.exports = {
    update: update
};

function dayState(cb) {
    request('http://planet.openstreetmap.org/replication/day/state.txt', function(err, r, body) {
        if (err) throw err;
        cb(body.split('\n')[1].split('=')[1]);
    });
}

function dayReplication(state, cb) {
    var request = http.get({
        host: 'planet.openstreetmap.org',
        path: '/replication/day/000/000/' + state + '.osc.gz',
        port: 80,
        headers: { 'accept-encoding': 'gzip,deflate' } });
    request.on('response', function(response) {
        var output = fs.createWriteStream('state.osc');
        response.pipe(zlib.createGunzip()).pipe(output);
        response.on('end', function() {
            cb();
        });
    });
}

function update(boundary, cb) {
    var ring = boundary.features[0].geometry.coordinates[0];
    linger('getting state');
    dayState(function(state) {
        linger();
        linger('getting replication');
        dayReplication(state, function() {
            linger();
            cb();
        });
    });
}
