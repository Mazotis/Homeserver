var express = require('express');
var port = 8081;
var basepath = "";
var ssl = false;
var lang = "en";
var keyfile, certfile;
var http, options, helmet;
const { spawn } = require('child_process');
const fs = require("fs");

process.argv.forEach(function (val, index, array) {
    if (index == 2) {
        console.log("Started webserver on port " + val);
        port = val;
    }
    if (index == 3) {
        console.log("Set language to: " + val);
        lang = val
    }
    if (index == 4) {
        console.log("Encrypted connection with SSL support: " + val);
        ssl = (val == 'true');
    }
    if (ssl && index == 5) {
        console.log("Loading key file: " + val);
        keyfile = val;
    }
    if (ssl && index == 6) {
        console.log("Loading cert file: " + val);
        certfile = val;
    }
});

const ejs = require('ejs');
const xmlParser = require('fast-xml-parser');
const app = express();

app.use(express.static('public'));
app.use(express.urlencoded({extended: false}));
app.use(express.json());
app.set('view engine', 'ejs');

// SSL support
if (ssl) {
    options = {
        key: fs.readFileSync(keyfile),
        cert: fs.readFileSync(certfile) 
    };

    http = require("https").createServer(options, app);
    helmet = require("helmet");
} else {
    http = require("http").createServer(app);
}

// LOCALES SUPPORT
const GetText = require("node-gettext")
const {po} = require("gettext-parser")
const path = require("path")
const translationsDir = '../locales'
const locales = ['en', 'fr']

const gt = new GetText()

locales.forEach((locale) => {
    const fileName = `base.po`
    let translationsFilePath = path.join(translationsDir, locale, "/LC_MESSAGES/", fileName)
    console.log("Loaded locale file " + translationsFilePath)
    let translationsContent = fs.readFileSync(translationsFilePath)

    let parsedTranslations = po.parse(translationsContent)
    gt.addTranslations(locale, "messages", parsedTranslations)
})
gt.setLocale(lang)
gt.on('error', error => console.log('oh nose', error))

// SOCKETIO
const io = require('socket.io')(http);
let hs_socket

io.on('connection', (socket) => {
    socket.on('set_hs_socket', (msg) => {
        hs_socket = socket
    });
    socket.on('update_state', (msg) => {
        io.emit('push_state', msg);
    });
});

console.log("Got basepath: " + __dirname);
if (ssl) {
    app.use(
        helmet({
            contentSecurityPolicy: false,
        })
    );
}

http.listen(port);

// *** GET Routes ***
app.get('/', function (req, res) {
    res.render('index', {gt: gt});
});

app.get('/js/app.ejs', function (req, res) {
    res.set('Content-Type', 'application/javascript')
    res.render('app', {gt: gt});
});

app.get('/preseteditor', function (req, res) {
    res.render('modules/preseteditor', {gt: gt});
});

app.get('/presetselect', function (req, res) {
    res.render('modules/presetselect', {gt: gt});
});

app.get('/groupselect', function (req, res) {
    res.render('modules/groupselect', {gt: gt});
});

// *** POST Routes ***
app.post('/query', function (req, res) {
    let request_body = JSON.parse(JSON.stringify(req.body))
    hs_socket.emit('query', request_body, function(data) {
        res.set('Content-Type', request_body.return_type);
        res.send(JSON.stringify(data))
    });
/*
    const process = spawn("python3",[__dirname + '/../home.py', '--query-server', JSON.stringify(req.body)]);
    process.stdout.on('data', function(data) {
        res.set('Content-Type', 'application/json');
        res.send(data)
    });
*/
});

app.post('/getmodule', function (req, res) {
    let request_body = JSON.parse(JSON.stringify(req.body))
    res.set('Content-Type', 'text/html');
    res.send(res.render('modules/' + request_body.module_page, {gt: gt}))
});

app.post('/configxml', function (req, res) {
    const options = {
        ignoreAttributes: false,
        parseAttributeValue: true,
        ignoreNameSpace: false,
        attributeNamePrefix : "attr_",
        tagValueProcessor : function(val, tagName) {
            if (tagName == "tl") {
                return gt.gettext(val)
            }
            return val
        }
    };
    const xml = xmlParser.parse(fs.readFileSync('views/configurables.xml', 'utf8'), options);
    res.send(xml);
});
