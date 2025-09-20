const express = require('express');
const cors = require('cors');
const https = require('https');

const app = express();
const PORT = 3001;

// Enable CORS for all routes
app.use(cors());
app.use(express.json());

// PI Web API configuration
const PI_CONFIG = {
    host: '192.168.74.128',
    port: 443,
    username: 'win-lqin09i7rg4\\administrator',
    password: 'Brungy509@'
};

// Create basic auth header
const auth = Buffer.from(`${PI_CONFIG.username}:${PI_CONFIG.password}`).toString('base64');

// Helper function to make HTTPS requests to PI Web API
function makePIRequest(path) {
    return new Promise((resolve, reject) => {
        const options = {
            hostname: PI_CONFIG.host,
            port: PI_CONFIG.port,
            path: path,
            method: 'GET',
            headers: {
                'Authorization': `Basic ${auth}`,
                'Content-Type': 'application/json'
            },
            rejectUnauthorized: false // Accept self-signed certificates
        };

        const req = https.request(options, (res) => {
            let data = '';

            res.on('data', (chunk) => {
                data += chunk;
            });

            res.on('end', () => {
                try {
                    const jsonData = JSON.parse(data);
                    resolve(jsonData);
                } catch (error) {
                    reject(new Error(`JSON Parse Error: ${error.message}`));
                }
            });
        });

        req.on('error', (error) => {
            reject(error);
        });

        req.end();
    });
}

// Proxy route for PI Web API attributes
app.get('/api/pi/attributes', async (req, res) => {
    try {
        console.log('Fetching PI attributes...');
        const path = '/piwebapi/elements/F1EmQmqOHC3i_kyP3ytLaQ6cSACt0PThFj8BGgrwAMKdv39AV0lOLUxRSu4wOUk3Ukc0XERBVEFCQVNFMVXA5BY2AXONGT-awo-apnzE/attributes';
        const data = await makePIRequest(path);
        console.log('PI attributes fetched successfully');
        res.json(data);
    } catch (error) {
        console.error('Error fetching PI attributes:', error.message);
        res.status(500).json({ error: error.message });
    }
});

// Proxy route for PI Web API attribute values
app.get('/api/pi/value/:webId', async (req, res) => {
    try {
        const webId = req.params.webId;
        console.log(`Fetching value for WebId: ${webId}`);
        const path = `/piwebapi/streams/${webId}/value`;
        const data = await makePIRequest(path);
        console.log('PI value fetched successfully');
        res.json(data);
    } catch (error) {
        console.error('Error fetching PI value:', error.message);
        res.status(500).json({ error: error.message });
    }
});

// Health check endpoint
app.get('/api/health', (req, res) => {
    res.json({ status: 'OK', message: 'PI Web API Proxy Server is running' });
});

app.listen(PORT, () => {
    console.log(`PI Web API Proxy Server running on http://localhost:${PORT}`);
    console.log(`Health check: http://localhost:${PORT}/api/health`);
    console.log(`PI Attributes: http://localhost:${PORT}/api/pi/attributes`);
});