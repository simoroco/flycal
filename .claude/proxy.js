const http = require('http');

const TARGET_HOST = 'localhost';
const TARGET_PORT = 4444;
const LISTEN_PORT = 8080;

const server = http.createServer((clientReq, clientRes) => {
  const headers = { ...clientReq.headers };
  delete headers.host; // Let Node set the correct Host header
  const options = {
    hostname: TARGET_HOST,
    port: TARGET_PORT,
    path: clientReq.url,
    method: clientReq.method,
    headers
  };

  const proxyReq = http.request(options, (proxyRes) => {
    clientRes.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(clientRes, { end: true });
  });

  proxyReq.on('error', (err) => {
    console.error('Proxy error:', err.message);
    if (!clientRes.headersSent) {
      clientRes.writeHead(502, { 'Content-Type': 'text/plain' });
    }
    clientRes.end('Proxy error: ' + err.message);
  });

  clientReq.pipe(proxyReq, { end: true });
});

server.listen(LISTEN_PORT, () => {
  console.log(`Proxy running on http://localhost:${LISTEN_PORT} -> ${TARGET_HOST}:${TARGET_PORT}`);
});
