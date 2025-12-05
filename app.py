const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const multer = require('multer');
const fs = require('fs-extra');
const path = require('path');
const bodyParser = require('body-parser');
const login = require("ws3-fca");

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// AppState और Uploads डायरेक्टरी बनाओ
fs.ensureDirSync('./uploads');
fs.ensureDirSync('./appstates');
fs.ensureDirSync('./temp');

// Multer setup for file uploads
const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        if (file.fieldname === 'appstateFile') {
            cb(null, './appstates/');
        } else if (file.fieldname === 'msgFile') {
            cb(null, './uploads/');
        }
    },
    filename: function (req, file, cb) {
        const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
        cb(null, uniqueSuffix + path.extname(file.originalname));
    }
});

const upload = multer({ storage: storage });

// Middleware
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static(__dirname));

// Active sessions store
const activeSessions = new Map();

// Facebook Login Function
async function loginWithAppState(appStateStr) {
    return new Promise((resolve, reject) => {
        try {
            let appState;
            if (typeof appStateStr === 'string') {
                appState = JSON.parse(appStateStr);
            } else {
                appState = appStateStr;
            }
            
            login({ appState: appState }, (err, api) => {
                if (err) {
                    console.error('Login error:', err);
                    return reject(err);
                }
                console.log('Login successful for user:', api.getCurrentUserID());
                resolve(api);
            });
        } catch (error) {
            reject(error);
        }
    });
}

// Send Message Function
async function sendFacebookMessage(api, threadID, message) {
    return new Promise((resolve, reject) => {
        api.sendMessage(message, threadID, (err, info) => {
            if (err) {
                console.error('Send message error:', err);
                return reject(err);
            }
            console.log('Message sent successfully to:', threadID);
            resolve(info);
        });
    });
}

// Delay Function
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Routes
app.post('/upload-appstate', upload.single('appstateFile'), (req, res) => {
    try {
        if (!req.file) {
            return res.json({ success: false, message: 'कोई फाइल अपलोड नहीं हुई' });
        }
        
        const fileContent = fs.readFileSync(req.file.path, 'utf8');
        const appStates = fileContent.split('\n')
            .filter(line => line.trim() !== '')
            .map(line => {
                try {
                    return JSON.parse(line.trim());
                } catch {
                    return line.trim();
                }
            });
        
        res.json({ 
            success: true, 
            message: `${appStates.length} AppStates अपलोड हुए`,
            count: appStates.length,
            filename: req.file.filename
        });
    } catch (error) {
        console.error('Upload error:', error);
        res.json({ success: false, message: 'फाइल प्रोसेस करने में error' });
    }
});

app.post('/upload-message', upload.single('msgFile'), (req, res) => {
    try {
        if (!req.file) {
            return res.json({ success: false, message: 'कोई फाइल अपलोड नहीं हुई' });
        }
        
        const fileContent = fs.readFileSync(req.file.path, 'utf8');
        const messages = fileContent.split('\n').filter(line => line.trim() !== '');
        
        res.json({ 
            success: true, 
            message: `${messages.length} मैसेज अपलोड हुए`,
            count: messages.length,
            filename: req.file.filename,
            messages: messages
        });
    } catch (error) {
        console.error('Upload error:', error);
        res.json({ success: false, message: 'फाइल प्रोसेस करने में error' });
    }
});

app.post('/start-sending', async (req, res) => {
    try {
        const { 
            threadId, 
            prefix, 
            delay: delayTime, 
            loop, 
            appStates: manualAppStates,
            appStateFile,
            messages: manualMessages,
            messageFile
        } = req.body;
        
        if (!threadId || threadId.trim() === '') {
            return res.json({ success: false, message: 'Group ID डालो' });
        }
        
        if (!prefix || prefix.trim() === '') {
            return res.json({ success: false, message: 'Message Prefix डालो' });
        }
        
        const delaySeconds = parseInt(delayTime) || 20;
        const loopEnabled = loop === 'true';
        
        let appStates = [];
        let messages = [];
        
        // Load AppStates
        if (appStateFile && appStateFile !== 'undefined') {
            try {
                const filePath = path.join('./appstates', appStateFile);
                if (fs.existsSync(filePath)) {
                    const fileContent = fs.readFileSync(filePath, 'utf8');
                    appStates = fileContent.split('\n')
                        .filter(line => line.trim() !== '')
                        .map(line => {
                            try {
                                return JSON.parse(line.trim());
                            } catch {
                                return line.trim();
                            }
                        });
                }
            } catch (error) {
                console.error('Error loading appstate file:', error);
            }
        }
        
        if (manualAppStates && manualAppStates.length > 0) {
            if (typeof manualAppStates === 'string') {
                appStates = manualAppStates.split('\n')
                    .filter(line => line.trim() !== '')
                    .map(line => {
                        try {
                            return JSON.parse(line.trim());
                        } catch {
                            return line.trim();
                        }
                    });
            } else if (Array.isArray(manualAppStates)) {
                appStates = manualAppStates;
            }
        }
        
        // Load Messages
        if (messageFile && messageFile !== 'undefined') {
            try {
                const filePath = path.join('./uploads', messageFile);
                if (fs.existsSync(filePath)) {
                    const fileContent = fs.readFileSync(filePath, 'utf8');
                    messages = fileContent.split('\n').filter(line => line.trim() !== '');
                }
            } catch (error) {
                console.error('Error loading message file:', error);
            }
        }
        
        if (manualMessages && manualMessages.length > 0) {
            if (typeof manualMessages === 'string') {
                messages = manualMessages.split('\n').filter(line => line.trim() !== '');
            } else if (Array.isArray(manualMessages)) {
                messages = manualMessages;
            }
        }
        
        if (appStates.length === 0) {
            return res.json({ success: false, message: 'कम से कम एक AppState डालो' });
        }
        
        if (messages.length === 0) {
            return res.json({ success: false, message: 'कम से कम एक मैसेज डालो' });
        }
        
        const sessionId = 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        const session = {
            threadId: threadId.trim(),
            prefix: prefix.trim(),
            delay: delaySeconds,
            loop: loopEnabled,
            appStates: appStates,
            messages: messages,
            status: 'running',
            sentCount: 0,
            failedCount: 0,
            totalMessages: appStates.length * messages.length,
            currentAppStateIndex: 0,
            currentMessageIndex: 0
        };
        
        activeSessions.set(sessionId, session);
        
        // Start sending messages
        sendMessages(sessionId);
        
        res.json({ 
            success: true, 
            sessionId: sessionId,
            message: 'मैसेज भेजना शुरू हुआ',
            stats: {
                appStates: appStates.length,
                messages: messages.length,
                total: session.totalMessages
            }
        });
        
    } catch (error) {
        console.error('Start sending error:', error);
        res.json({ success: false, message: 'Error: ' + error.message });
    }
});

async function sendMessages(sessionId) {
    const session = activeSessions.get(sessionId);
    if (!session || session.status !== 'running') return;
    
    console.log(`Starting session ${sessionId} with ${session.appStates.length} AppStates`);
    
    let continueLoop = true;
    
    while (continueLoop && session.status === 'running') {
        for (let i = 0; i < session.appStates.length && session.status === 'running'; i++) {
            session.currentAppStateIndex = i;
            let api = null;
            
            try {
                console.log(`Logging in with AppState ${i + 1}/${session.appStates.length}`);
                api = await loginWithAppState(session.appStates[i]);
                
                for (let j = 0; j < session.messages.length && session.status === 'running'; j++) {
                    session.currentMessageIndex = j;
                    const fullMessage = `${session.prefix}\n${session.messages[j]}`;
                    
                    try {
                        console.log(`Sending message ${j + 1}/${session.messages.length} to ${session.threadId}`);
                        await sendFacebookMessage(api, session.threadId, fullMessage);
                        session.sentCount++;
                        console.log(`✓ Message sent successfully (${session.sentCount}/${session.totalMessages})`);
                        
                        // Send update via WebSocket
                        sendUpdate(sessionId, {
                            type: 'message_sent',
                            appState: i + 1,
                            message: j + 1,
                            totalSent: session.sentCount,
                            totalFailed: session.failedCount
                        });
                        
                    } catch (msgError) {
                        session.failedCount++;
                        console.error(`✗ Failed to send message:`, msgError.message);
                        
                        sendUpdate(sessionId, {
                            type: 'message_failed',
                            appState: i + 1,
                            message: j + 1,
                            error: msgError.message,
                            totalSent: session.sentCount,
                            totalFailed: session.failedCount
                        });
                    }
                    
                    // Delay between messages
                    if (session.status === 'running') {
                        await delay(session.delay * 1000);
                    }
                }
                
                if (api) {
                    try {
                        api.logout();
                        console.log(`Logged out from AppState ${i + 1}`);
                    } catch (logoutError) {
                        console.error('Logout error:', logoutError);
                    }
                }
                
            } catch (loginError) {
                session.failedCount += session.messages.length;
                console.error(`✗ Login failed for AppState ${i + 1}:`, loginError.message);
                
                sendUpdate(sessionId, {
                    type: 'login_failed',
                    appState: i + 1,
                    error: loginError.message,
                    totalSent: session.sentCount,
                    totalFailed: session.failedCount
                });
            }
        }
        
        // Check if should loop
        if (session.loop && session.status === 'running') {
            console.log('Looping back to start...');
            session.currentAppStateIndex = 0;
            session.currentMessageIndex = 0;
            continueLoop = true;
        } else {
            continueLoop = false;
        }
    }
    
    if (session.status === 'running') {
        session.status = 'completed';
        console.log(`Session ${sessionId} completed`);
        
        sendUpdate(sessionId, {
            type: 'completed',
            totalSent: session.sentCount,
            totalFailed: session.failedCount,
            successRate: ((session.sentCount / session.totalMessages) * 100).toFixed(2) + '%'
        });
    }
}

function sendUpdate(sessionId, data) {
    wss.clients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                sessionId: sessionId,
                ...data
            }));
        }
    });
}

app.get('/session-status/:sessionId', (req, res) => {
    const sessionId = req.params.sessionId;
    const session = activeSessions.get(sessionId);
    
    if (!session) {
        return res.json({ success: false, message: 'Session not found' });
    }
    
    res.json({
        success: true,
        status: session.status,
        sentCount: session.sentCount,
        failedCount: session.failedCount,
        totalMessages: session.totalMessages,
        progress: session.totalMessages > 0 ? 
            Math.round((session.sentCount / session.totalMessages) * 100) : 0,
        currentAppState: session.currentAppStateIndex + 1,
        currentMessage: session.currentMessageIndex + 1
    });
});

app.post('/stop-session/:sessionId', (req, res) => {
    const sessionId = req.params.sessionId;
    const session = activeSessions.get(sessionId);
    
    if (!session) {
        return res.json({ success: false, message: 'Session not found' });
    }
    
    session.status = 'stopped';
    activeSessions.set(sessionId, session);
    
    res.json({ 
        success: true, 
        message: 'Session stopped',
        sentCount: session.sentCount,
        failedCount: session.failedCount
    });
});

// WebSocket
wss.on('connection', (ws) => {
    console.log('New WebSocket connection');
    
    ws.on('message', (message) => {
        console.log('WebSocket message:', message);
    });
    
    ws.on('close', () => {
        console.log('WebSocket disconnected');
    });
});

// Serve HTML
app.get('/', (req, res) => {
    const html = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Facebook Multi Messenger - 100% Working</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: Arial; }
            body { background: linear-gradient(135deg, #0f2027, #203a43, #2c5364); color: #1e88e5; min-height: 100vh; overflow-x: hidden; position: relative; }
            
            /* Rain Background */
            .rain { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: -1; }
            .rain::before { content: ''; position: absolute; width: 100%; height: 100%; background: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><circle cx="10" cy="10" r="1" fill="%2300b0ff" opacity="0.6"/><circle cx="30" cy="20" r="1" fill="%2300b0ff" opacity="0.6"/><circle cx="50" cy="15" r="1" fill="%2300b0ff" opacity="0.6"/><circle cx="70" cy="25" r="1" fill="%2300b0ff" opacity="0.6"/><circle cx="90" cy="10" r="1" fill="%2300b0ff" opacity="0.6"/></svg>') repeat; animation: rain 1s linear infinite; }
            @keyframes rain { 0% { transform: translateY(-100px); } 100% { transform: translateY(100vh); } }
            
            .container { max-width: 1200px; margin: 0 auto; padding: 20px; position: relative; z-index: 1; }
            
            header { text-align: center; margin-bottom: 30px; padding: 20px; background: rgba(13, 71, 161, 0.2); border-radius: 15px; border: 2px solid rgba(30, 136, 229, 0.5); box-shadow: 0 0 30px rgba(30, 136, 229, 0.3); }
            h1 { font-size: 2.8rem; margin-bottom: 10px; background: linear-gradient(45deg, #ff0000, #ff8000, #ffff00, #00ff00, #00ffff, #0000ff, #8000ff); -webkit-background-clip: text; background-clip: text; color: transparent; text-shadow: 0 0 20px rgba(255, 255, 255, 0.5); animation: glow 2s infinite alternate; }
            @keyframes glow { from { text-shadow: 0 0 10px rgba(255, 255, 255, 0.5); } to { text-shadow: 0 0 20px rgba(255, 255, 255, 0.8), 0 0 30px rgba(0, 255, 255, 0.6); } }
            
            .subtitle { font-size: 1.2rem; color: #00ffff; margin-bottom: 20px; }
            .warning { color: #ff4444; background: rgba(255, 68, 68, 0.1); padding: 10px; border-radius: 5px; margin: 10px 0; border: 1px solid #ff4444; }
            .success { color: #44ff44; background: rgba(68, 255, 68, 0.1); padding: 10px; border-radius: 5px; margin: 10px 0; border: 1px solid #44ff44; }
            
            .card { background: rgba(0, 0, 0, 0.4); border-radius: 10px; padding: 20px; margin-bottom: 20px; border: 1px solid rgba(30, 136, 229, 0.5); backdrop-filter: blur(5px); }
            
            .tabs { display: flex; margin-bottom: 20px; border-bottom: 2px solid #1e88e5; }
            .tab-btn { padding: 12px 25px; background: rgba(30, 136, 229, 0.2); border: none; color: #00ffff; font-size: 16px; cursor: pointer; border-radius: 5px 5px 0 0; margin-right: 5px; transition: all 0.3s; }
            .tab-btn.active { background: #1e88e5; color: white; box-shadow: 0 0 15px #1e88e5; }
            
            .tab-content { display: none; animation: fadeIn 0.5s; }
            .tab-content.active { display: block; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
            
            label { display: block; margin: 10px 0 5px; color: #00b0ff; font-weight: bold; }
            
            input, textarea, select { width: 100%; padding: 12px; margin: 5px 0 15px; border: 2px solid #ff0000; border-radius: 5px; background: rgba(0, 0, 0, 0.5); color: white; font-size: 16px; transition: all 0.3s; }
            input:focus, textarea:focus, select:focus { outline: none; border-color: #00ff00; box-shadow: 0 0 15px #00ff00; animation: inputGlow 1.5s infinite alternate; }
            @keyframes inputGlow { from { box-shadow: 0 0 10px #00ff00; } to { box-shadow: 0 0 20px #00ff00, 0 0 30px #00ff00; } }
            
            textarea { min-height: 100px; resize: vertical; }
            
            .file-upload { border: 3px dashed #ff0000; border-radius: 10px; padding: 30px; text-align: center; cursor: pointer; transition: all 0.3s; margin: 10px 0; }
            .file-upload:hover { border-color: #00ff00; background: rgba(0, 255, 0, 0.1); }
            .file-upload i { font-size: 50px; color: #ff0000; margin-bottom: 15px; }
            
            .counter { text-align: right; color: #00ffff; font-size: 14px; margin-top: -10px; }
            
            .status-box { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }
            .status-item { background: rgba(0, 0, 0, 0.5); padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #1e88e5; }
            .status-label { color: #00ffff; font-size: 14px; }
            .status-value { color:
