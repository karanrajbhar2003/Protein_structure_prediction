const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, spawnSync } = require('child_process');

let pythonProcess = null;

/* -------------------- PYTHON FINDER -------------------- */
function findPython() {
    const candidates = [
        "E:/Conda/envs/protein-env/python.exe",
        "python",
        "python3"
    ];

    for (const candidate of candidates) {
        try {
            const result = spawnSync(candidate, ['--version']);
            if (result.status === 0) {
                console.log(`Found Python: ${candidate}`);
                return candidate;
            }
        } catch (_) {}
    }
    return null;
}

/* -------------------- PYTHON PROCESS -------------------- */
function createPythonProcess() {
    if (pythonProcess) return; // prevent duplicate spawn

    const script = path.join(__dirname, 'api_server.py');
    const pythonExecutable = findPython();

    if (!pythonExecutable) {
        console.error("Python executable not found");
        return;
    }

    pythonProcess = spawn(pythonExecutable, [script]);

    pythonProcess.stdout.on('data', data =>
        console.log(`Python stdout: ${data}`)
    );

    pythonProcess.stderr.on('data', data =>
        console.error(`Python stderr: ${data}`)
    );

    pythonProcess.on('close', code => {
        console.log(`Python exited with code ${code}`);
        pythonProcess = null;
    });
}

/* -------------------- WINDOW -------------------- */
function createWindow() {
    const win = new BrowserWindow({
        width: 1200,
        height: 800,
        icon: path.join(__dirname, 'logo.png'),
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        }
    });

    win.loadFile('index.html');
    win.webContents.openDevTools();
}

/* -------------------- IPC HANDLERS -------------------- */
ipcMain.on('open-external', (_, filePath) => {
    shell.openPath(path.normalize(filePath));
});

ipcMain.handle('get-file-path-url', (_, filePath) => {
    return `file://${path.normalize(filePath)}`;
});

ipcMain.handle('get-content', (_, content) => {
    const filePath = path.join(__dirname, 'content', `${content}.html`);
    if (content === 'about') {
        const aboutFilePath = path.join(__dirname, 'about.html');
        try {
            return fs.readFileSync(aboutFilePath, 'utf-8');
        } catch {
            return '<p>About content not found.</p>';
        }
    }
    try {
        return fs.readFileSync(filePath, 'utf-8');
    } catch {
        return '<p>Content not found.</p>';
    }
});

ipcMain.handle('read-file', async (_, filePath) => {
    const ext = path.extname(filePath).toLowerCase();
    if (['.png', '.jpg', '.jpeg', '.svg'].includes(ext)) {
        const data = await fs.promises.readFile(filePath, 'base64');
        return `data:image/${ext.slice(1)};base64,${data}`;
    }
    return fs.promises.readFile(filePath, 'utf-8');
});

ipcMain.handle('read-dir', (_, dirPath) => {
    return fs.promises.readdir(dirPath);
});

ipcMain.handle('show-open-dialog', async (event, options) => {
    const { filePaths } = await dialog.showOpenDialog(options);
    if (filePaths && filePaths.length > 0) {
        return filePaths[0];
    }
    return null;
});

ipcMain.handle('show-save-dialog', async (_, options) => {
    const { filePath } = await dialog.showSaveDialog(options);
    return filePath;
});

ipcMain.on('save-file', (_, { filePath, buffer }) => {
    let dataToWrite = buffer;
    if (Array.isArray(buffer)) {
        dataToWrite = Buffer.from(buffer);
    } else if (buffer && buffer.type === 'Buffer' && Array.isArray(buffer.data)) {
        dataToWrite = Buffer.from(buffer.data);
    }
    fs.writeFileSync(filePath, dataToWrite);
});

/* -------------------- APP LIFECYCLE -------------------- */
app.whenReady().then(() => {
    createPythonProcess();
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('will-quit', () => {
    if (pythonProcess) pythonProcess.kill();
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
