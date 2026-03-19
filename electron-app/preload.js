const { contextBridge, ipcRenderer } = require('electron');

const API_BASE_URL = 'http://127.0.0.1:8091';

contextBridge.exposeInMainWorld('api', {
  post: (endpoint, data) => {
    return fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    }).then(response => {
      if (!response.ok) {
        return response.json().then(err => { throw new Error(err.detail || 'Network response was not ok'); });
      }
      return response.json();
    });
  },
  get: (endpoint) => {
    const url = new URL(`${API_BASE_URL}${endpoint}`);
    url.searchParams.append('_', new Date().getTime());
    return fetch(url).then(response => {
      if (!response.ok) {
        return response.json().then(err => { throw new Error(err.detail || 'Network response was not ok'); });
      }
      return response.json();
    });
  },
  delete: (endpoint) => {
    return fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'DELETE',
    }).then(response => {
      if (!response.ok) {
        return response.json().then(err => { throw new Error(err.detail || 'Network response was not ok'); });
      }
      return response.json();
    });
  },
  showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),
  showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),
  saveFile: (args) => ipcRenderer.send('save-file', args),
  readFile: (filePath) => ipcRenderer.invoke('read-file', filePath),
  readDir: (dirPath) => ipcRenderer.invoke('read-dir', dirPath),
  openExternal: (filePath) => ipcRenderer.send('open-external', filePath),
  getFilePathUrl: (filePath) => ipcRenderer.invoke('get-file-path-url', filePath),
  getContent: (content) => ipcRenderer.invoke('get-content', content),
});
