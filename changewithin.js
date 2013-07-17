var fs = require('fs'),
    changewithin = require('./'),
    linger = require('linger'),
    argv = require('optimist').argv;

if (argv._.length) {
    var boundary;
    try {
        boundary = JSON.parse(fs.readFileSync(argv._[0], 'utf8'));
    } catch(e) {
        return console.error('Failed to read boundary %s\n%s', argv._[0], e.toString());
    }
    changewithin.update(boundary, function() {
    });
} else {
    return console.error('usage: changewithin [boundary]');
}
