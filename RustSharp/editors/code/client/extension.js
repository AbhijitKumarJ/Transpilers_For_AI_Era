// RustSharp Language Client for VS Code (Zero External Dependencies)
const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
const fs = require('fs');

let serverProcess = null;
let requestId = 0;
const pendingRequests = new Map();
let incomingBuffer = '';
let diagnosticCollection = null;
let statusBarItem = null;
let outputChannel = null;

function log(msg) {
  if (outputChannel) {
    outputChannel.appendLine(`[${new Date().toISOString()}] ${msg}`);
  }
}

function findServerPath(workspaceFolders) {
  const config = vscode.workspace.getConfiguration('rustsharp');
  const customPath = config.get('serverPath');
  if (customPath && customPath !== 'rsharpc' && fs.existsSync(customPath)) {
    return customPath;
  }

  // Check workspace target folders
  if (workspaceFolders && workspaceFolders.length > 0) {
    for (const folder of workspaceFolders) {
      const releaseBin = path.join(folder.uri.fsPath, 'target', 'release', 'rsharpc');
      if (fs.existsSync(releaseBin)) {
        return releaseBin;
      }
      const debugBin = path.join(folder.uri.fsPath, 'target', 'debug', 'rsharpc');
      if (fs.existsSync(debugBin)) {
        return debugBin;
      }
    }
  }

  // Check ~/.cargo/bin/rsharpc
  const home = process.env.HOME || process.env.USERPROFILE || '';
  const cargoBin = path.join(home, '.cargo', 'bin', 'rsharpc');
  if (fs.existsSync(cargoBin)) {
    return cargoBin;
  }

  return 'rsharpc';
}

function sendRequest(method, params) {
  if (!serverProcess || serverProcess.killed) {
    return Promise.reject(new Error('RustSharp LSP server is not running'));
  }
  const id = String(++requestId);
  const msgObj = { jsonrpc: '2.0', id, method, params };
  const jsonStr = JSON.stringify(msgObj);
  const packet = `Content-Length: ${Buffer.byteLength(jsonStr, 'utf8')}\r\n\r\n${jsonStr}`;
  serverProcess.stdin.write(packet);

  return new Promise((resolve, reject) => {
    pendingRequests.set(id, { resolve, reject });
  });
}

function sendNotification(method, params) {
  if (!serverProcess || serverProcess.killed) return;
  const msgObj = { jsonrpc: '2.0', method, params };
  const jsonStr = JSON.stringify(msgObj);
  const packet = `Content-Length: ${Buffer.byteLength(jsonStr, 'utf8')}\r\n\r\n${jsonStr}`;
  serverProcess.stdin.write(packet);
}

function handleMessage(msg) {
  if (msg.id && pendingRequests.has(String(msg.id))) {
    const { resolve, reject } = pendingRequests.get(String(msg.id));
    pendingRequests.delete(String(msg.id));
    if (msg.error) {
      reject(new Error(msg.error.message || JSON.stringify(msg.error)));
    } else {
      resolve(msg.result);
    }
    return;
  }

  // Handle server-initiated notifications
  if (msg.method === 'textDocument/publishDiagnostics') {
    const { uri, diagnostics } = msg.params || {};
    if (diagnosticCollection && uri) {
      const targetUri = vscode.Uri.parse(uri);
      const vsDiags = (diagnostics || []).map(d => {
        const range = new vscode.Range(
          d.range.start.line,
          d.range.start.character,
          d.range.end.line,
          d.range.end.character
        );
        const severity = d.severity === 1 ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning;
        const diag = new vscode.Diagnostic(range, d.message, severity);
        diag.source = d.source || 'rsharpc';
        diag.code = d.code;
        return diag;
      });
      diagnosticCollection.set(targetUri, vsDiags);
    }
  }
}

function onStdoutData(chunk) {
  incomingBuffer += chunk.toString('utf8');
  while (true) {
    const headerEnd = incomingBuffer.indexOf('\r\n\r\n');
    if (headerEnd === -1) break;

    const header = incomingBuffer.substring(0, headerEnd);
    const match = header.match(/Content-Length:\s*(\d+)/i);
    if (!match) {
      incomingBuffer = incomingBuffer.substring(headerEnd + 4);
      continue;
    }

    const contentLength = parseInt(match[1], 10);
    const bodyStart = headerEnd + 4;
    const totalLength = bodyStart + contentLength;

    if (Buffer.byteLength(incomingBuffer, 'utf8') < totalLength) {
      break;
    }

    const bodyStr = incomingBuffer.substring(bodyStart, bodyStart + contentLength);
    incomingBuffer = incomingBuffer.substring(bodyStart + contentLength);

    try {
      const msg = JSON.parse(bodyStr);
      handleMessage(msg);
    } catch (e) {
      log(`JSON parse error: ${e.message}`);
    }
  }
}

function startLanguageServer(context) {
  const folders = vscode.workspace.workspaceFolders;
  const serverPath = findServerPath(folders);
  const cwd = folders && folders.length > 0 ? folders[0].uri.fsPath : process.cwd();

  log(`Starting RustSharp LSP from: ${serverPath} (cwd: ${cwd})`);

  try {
    serverProcess = cp.spawn(serverPath, ['lsp'], {
      cwd,
      env: process.env,
      stdio: ['pipe', 'pipe', 'pipe']
    });

    serverProcess.stdout.on('data', onStdoutData);
    serverProcess.stderr.on('data', data => {
      log(`[Server stderr] ${data.toString()}`);
    });

    serverProcess.on('exit', (code, signal) => {
      log(`RustSharp LSP exited with code ${code}, signal ${signal}`);
      if (statusBarItem) {
        statusBarItem.text = '$(error) RustSharp LSP (Stopped)';
      }
    });

    serverProcess.on('error', err => {
      log(`Failed to spawn RustSharp LSP: ${err.message}`);
      vscode.window.showErrorMessage(`Failed to start RustSharp LSP: ${err.message}. Ensure 'rsharpc' is built in target/release/rsharpc.`);
      if (statusBarItem) {
        statusBarItem.text = '$(error) RustSharp LSP (Error)';
      }
    });

    // Send initialize request
    const rootUri = folders && folders.length > 0 ? folders[0].uri.toString() : null;
    sendRequest('initialize', {
      rootUri,
      capabilities: {
        textDocument: {
          hover: { dynamicRegistration: false },
          definition: { dynamicRegistration: false },
          completion: { dynamicRegistration: false },
          documentSymbol: { dynamicRegistration: false }
        },
        workspace: {
          symbol: { dynamicRegistration: false }
        }
      }
    }).then(result => {
      log(`RustSharp LSP initialized successfully: ${JSON.stringify(result)}`);
      sendNotification('initialized', {});
      if (statusBarItem) {
        statusBarItem.text = '$(zap) RustSharp LSP';
        statusBarItem.tooltip = 'RustSharp Language Server active (zero-cost C# to Rust)';
        statusBarItem.show();
      }

      // Sync currently open documents
      vscode.workspace.textDocuments.forEach(doc => {
        if (doc.languageId === 'rustsharp') {
          sendNotification('textDocument/didOpen', {
            uri: doc.uri.toString(),
            languageId: 'rustsharp',
            version: doc.version,
            text: doc.getText()
          });
        }
      });
    }).catch(err => {
      log(`Initialize failed: ${err.message}`);
    });
  } catch (err) {
    log(`Exception launching server: ${err.message}`);
  }
}

function stopLanguageServer() {
  if (serverProcess && !serverProcess.killed) {
    try {
      sendRequest('shutdown', {}).then(() => {
        sendNotification('exit', {});
        serverProcess.kill();
      }).catch(() => {
        serverProcess.kill();
      });
    } catch (_) {
      serverProcess.kill();
    }
  }
  pendingRequests.clear();
  incomingBuffer = '';
}

function activate(context) {
  outputChannel = vscode.window.createOutputChannel('RustSharp Language Server');
  diagnosticCollection = vscode.languages.createDiagnosticCollection('rustsharp');
  context.subscriptions.push(diagnosticCollection);
  context.subscriptions.push(outputChannel);

  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = 'rustsharp.restartServer';
  context.subscriptions.push(statusBarItem);

  // Register command to restart language server
  context.subscriptions.push(
    vscode.commands.registerCommand('rustsharp.restartServer', () => {
      vscode.window.showInformationMessage('Restarting RustSharp Language Server...');
      stopLanguageServer();
      startLanguageServer(context);
    })
  );

  function ensureDocumentOpen(doc) {
    if (!doc || !doc.uri) return;
    sendNotification('textDocument/didOpen', {
      uri: doc.uri.toString(),
      languageId: 'rustsharp',
      version: doc.version,
      text: doc.getText()
    });
  }

  // Register LSP Providers
  context.subscriptions.push(
    vscode.languages.registerHoverProvider('rustsharp', {
      provideHover(document, position) {
        ensureDocumentOpen(document);
        return sendRequest('textDocument/hover', {
          uri: document.uri.toString(),
          line: position.line,
          character: position.character
        }).then(result => {
          if (!result || !result.contents) return null;
          const md = new vscode.MarkdownString(result.contents.value);
          md.isTrusted = true;
          return new vscode.Hover(md);
        }).catch(() => null);
      }
    })
  );

  context.subscriptions.push(
    vscode.languages.registerDefinitionProvider('rustsharp', {
      provideDefinition(document, position) {
        ensureDocumentOpen(document);
        log(`Definition requested at ${document.uri.toString()}:${position.line}:${position.character}`);
        return sendRequest('textDocument/definition', {
          uri: document.uri.toString(),
          line: position.line,
          character: position.character
        }).then(result => {
          log(`Definition result: ${JSON.stringify(result)}`);
          if (!result) return null;
          function makeLocation(loc) {
            const uriStr = loc.uri;
            const targetUri = uriStr.startsWith('file://') ? vscode.Uri.parse(uriStr) : vscode.Uri.file(uriStr);
            const start = new vscode.Position(loc.range.start.line, loc.range.start.character);
            const end = new vscode.Position(loc.range.end.line, loc.range.end.character);
            return new vscode.Location(targetUri, new vscode.Range(start, end));
          }
          if (Array.isArray(result)) {
            return result.map(makeLocation);
          }
          return makeLocation(result);
        }).catch(err => {
          log(`Definition error: ${err.message}`);
          return null;
        });
      }
    })
  );

  context.subscriptions.push(
    vscode.languages.registerCompletionItemProvider('rustsharp', {
      provideCompletionItems(document, position) {
        return sendRequest('textDocument/completion', {
          uri: document.uri.toString(),
          line: position.line,
          character: position.character
        }).then(result => {
          if (!result || !result.items) return null;
          return result.items.map(item => {
            const ci = new vscode.CompletionItem(item.label, item.kind || vscode.CompletionItemKind.Method);
            ci.detail = item.detail;
            return ci;
          });
        }).catch(() => null);
      }
    }, '.', ':')
  );

  context.subscriptions.push(
    vscode.languages.registerDocumentSymbolProvider('rustsharp', {
      provideDocumentSymbols(document) {
        return sendRequest('textDocument/documentSymbol', {
          uri: document.uri.toString()
        }).then(result => {
          if (!result || !Array.isArray(result)) return [];
          function convert(s) {
            const range = new vscode.Range(s.range.start.line, s.range.start.character, s.range.end.line, s.range.end.character);
            const selRange = new vscode.Range(s.selectionRange.start.line, s.selectionRange.start.character, s.selectionRange.end.line, s.selectionRange.end.character);
            const sym = new vscode.DocumentSymbol(s.name, '', s.kind || vscode.SymbolKind.Class, range, selRange);
            if (s.children && Array.isArray(s.children)) {
              sym.children = s.children.map(convert);
            }
            return sym;
          }
          return result.map(convert);
        }).catch(() => []);
      }
    })
  );

  context.subscriptions.push(
    vscode.languages.registerWorkspaceSymbolProvider({
      provideWorkspaceSymbols(query) {
        return sendRequest('workspace/symbol', { query }).then(result => {
          if (!result || !Array.isArray(result)) return [];
          return result.map(s => new vscode.SymbolInformation(
            s.name,
            s.kind || vscode.SymbolKind.Class,
            '',
            new vscode.Location(
              vscode.Uri.parse(s.location.uri),
              new vscode.Range(s.location.range.start.line, s.location.range.start.character, s.location.range.end.line, s.location.range.end.character)
            )
          ));
        }).catch(() => []);
      }
    })
  );

  // Document Lifecycle Events
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument(doc => {
      if (doc.languageId === 'rustsharp') {
        sendNotification('textDocument/didOpen', {
          uri: doc.uri.toString(),
          languageId: 'rustsharp',
          version: doc.version,
          text: doc.getText()
        });
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument(evt => {
      if (evt.document.languageId === 'rustsharp') {
        sendNotification('textDocument/didChange', {
          uri: evt.document.uri.toString(),
          version: evt.document.version,
          text: evt.document.getText()
        });
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument(doc => {
      if (doc.languageId === 'rustsharp') {
        sendNotification('textDocument/didClose', {
          uri: doc.uri.toString()
        });
        if (diagnosticCollection) {
          diagnosticCollection.delete(doc.uri);
        }
      }
    })
  );

  // Start the server
  startLanguageServer(context);
}

function deactivate() {
  stopLanguageServer();
}

module.exports = {
  activate,
  deactivate
};
