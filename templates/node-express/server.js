const express = require('express'); const app = express(); app.get('/', (_, res) => res.send('Node Express Template')); app.listen(3000, '0.0.0.0');
