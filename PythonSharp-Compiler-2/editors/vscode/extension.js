const vscode = require('vscode');
const child_process = require('child_process');
const path = require('path');
const fs = require('fs');

/**
 * Lightweight JSON-RPC 2.0 Client over stdio for PythonSharp Language Server (`psc lsp`).
 * Requires zero external npm dependencies.
 */
class PythonSharpLanguageClient {
  constructor(context, outputChannel) {
    this.context = context;
    this.outputChannel = outputChannel;
    this.process = null;
    this.nextId = 1;
    this.pendingRequests = new Map();
    this.buffer = Buffer.alloc(0);
    this.diagnosticCollection = vscode.languages.createDiagnosticCollection('pythonsharp');
    this.context.subscriptions.push(this.diagnosticCollection);
    this.isInitialized = false;
  }

  log(msg) {
    if (this.outputChannel) {
      this.outputChannel.appendLine(`[PythonSharp LSP] ${msg}`);
    }
  }

  findServerCommand() {
    const config = vscode.workspace.getConfiguration('pythonsharp');
    const customPath = config.get('serverPath');
    if (customPath && customPath.trim().length > 0) {
      return { command: customPath.trim(), args: ['lsp'] };
    }

    // Check workspace virtualenvs first
    const workspaceFolders = vscode.workspace.workspaceFolders || [];
    for (const folder of workspaceFolders) {
      const venvCandidates = [
        path.join(folder.uri.fsPath, '.venv', 'bin', 'psc'),
        path.join(folder.uri.fsPath, 'venv', 'bin', 'psc'),
        path.join(folder.uri.fsPath, '.env', 'bin', 'psc'),
      ];
      for (const cand of venvCandidates) {
        if (fs.existsSync(cand)) {
          return { command: cand, args: ['lsp'] };
        }
      }
    }

    // Default to 'psc' in PATH, with fallback to 'python3 -m psc.cli lsp'
    return { command: 'psc', args: ['lsp'], fallback: { command: 'python3', args: ['-m', 'psc.cli', 'lsp'] } };
  }

  start() {
    this.stop();

    const serverCmd = this.findServerCommand();
    this.log(`Starting server process: ${serverCmd.command} ${serverCmd.args.join(' ')}`);

    const spawnProcess = (cmd, args) => {
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
      return child_process.spawn(cmd, args, {
        cwd: workspaceRoot,
        env: { ...process.env, PYTHONUNBUFFERED: '1' }
      });
    };

    try {
      this.process = spawnProcess(serverCmd.command, serverCmd.args);
    } catch (err) {
      if (serverCmd.fallback) {
        this.log(`Spawning ${serverCmd.command} failed: ${err.message}. Trying fallback: ${serverCmd.fallback.command}`);
        this.process = spawnProcess(serverCmd.fallback.command, serverCmd.fallback.args);
      } else {
        vscode.window.showErrorMessage(`Failed to start PythonSharp LSP: ${err.message}`);
        return;
      }
    }

    this.process.on('error', (err) => {
      this.log(`Server process error: ${err.message}`);
      if (!this.isInitialized && serverCmd.fallback) {
        this.log(`Attempting fallback to ${serverCmd.fallback.command}...`);
        try {
          this.process = spawnProcess(serverCmd.fallback.command, serverCmd.fallback.args);
          this.setupStreams();
          this.initialize();
          return;
        } catch (e) {
          this.log(`Fallback also failed: ${e.message}`);
        }
      }
      vscode.window.showErrorMessage(`PythonSharp LSP error: ${err.message}`);
    });

    this.process.on('exit', (code, signal) => {
      this.log(`Server process exited with code ${code}, signal ${signal}`);
      this.isInitialized = false;
      this.rejectAllPending('Server exited');
    });

    this.setupStreams();
    this.initialize();
  }

  setupStreams() {
    this.buffer = Buffer.alloc(0);

    this.process.stdout.on('data', (chunk) => {
      this.buffer = Buffer.concat([this.buffer, chunk]);
      this.processIncomingBuffer();
    });

    this.process.stderr.on('data', (chunk) => {
      this.log(`[STDERR] ${chunk.toString('utf8').trim()}`);
    });
  }

  processIncomingBuffer() {
    while (true) {
      const headerEndIndex = this.buffer.indexOf('\r\n\r\n');
      if (headerEndIndex === -1) {
        break;
      }

      const headerString = this.buffer.slice(0, headerEndIndex).toString('ascii');
      let contentLength = -1;
      const lines = headerString.split('\r\n');
      for (const line of lines) {
        const parts = line.split(':');
        if (parts.length >= 2 && parts[0].trim().toLowerCase() === 'content-length') {
          contentLength = parseInt(parts[1].trim(), 10);
          break;
        }
      }

      if (contentLength === -1) {
        this.log(`Malformed header, dropping buffer`);
        this.buffer = Buffer.alloc(0);
        break;
      }

      const totalMessageLength = headerEndIndex + 4 + contentLength;
      if (this.buffer.length < totalMessageLength) {
        // Need more data
        break;
      }

      const bodySlice = this.buffer.slice(headerEndIndex + 4, totalMessageLength);
      this.buffer = this.buffer.slice(totalMessageLength);

      try {
        const payload = JSON.parse(bodySlice.toString('utf8'));
        this.handleMessage(payload);
      } catch (err) {
        this.log(`Failed to parse JSON body: ${err.message}`);
      }
    }
  }

  handleMessage(msg) {
    if (typeof msg.id !== 'undefined') {
      const pending = this.pendingRequests.get(msg.id);
      if (pending) {
        this.pendingRequests.delete(msg.id);
        if (msg.error) {
          pending.reject(new Error(msg.error.message || 'JSON-RPC error'));
        } else {
          pending.resolve(msg.result);
        }
      }
    } else if (msg.method) {
      this.handleNotification(msg.method, msg.params);
    }
  }

  handleNotification(method, params) {
    if (method === 'textDocument/publishDiagnostics') {
      const uri = vscode.Uri.parse(params.uri);
      const diagnostics = (params.diagnostics || []).map((d) => {
        const range = new vscode.Range(
          new vscode.Position(d.range.start.line, d.range.start.character),
          new vscode.Position(d.range.end.line, d.range.end.character)
        );
        const severity = d.severity === 1 ? vscode.DiagnosticSeverity.Error
          : d.severity === 2 ? vscode.DiagnosticSeverity.Warning
          : vscode.DiagnosticSeverity.Information;
        const diag = new vscode.Diagnostic(range, d.message, severity);
        diag.source = d.source || 'psc';
        diag.code = d.code;
        return diag;
      });
      this.diagnosticCollection.set(uri, diagnostics);
    }
  }

  sendRequest(method, params) {
    if (!this.process || this.process.killed) {
      return Promise.reject(new Error('LSP process is not running'));
    }

    const id = this.nextId++;
    const payload = {
      jsonrpc: '2.0',
      id: id,
      method: method,
      params: params
    };

    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.writePayload(payload);
    });
  }

  sendNotification(method, params) {
    if (!this.process || this.process.killed) {
      return;
    }
    const payload = {
      jsonrpc: '2.0',
      method: method,
      params: params
    };
    this.writePayload(payload);
  }

  writePayload(payload) {
    try {
      const body = Buffer.from(JSON.stringify(payload), 'utf8');
      const header = Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, 'ascii');
      this.process.stdin.write(Buffer.concat([header, body]));
    } catch (err) {
      this.log(`Error writing payload: ${err.message}`);
    }
  }

  initialize() {
    const rootUri = vscode.workspace.workspaceFolders?.[0]?.uri.toString() || null;
    this.sendRequest('initialize', {
      processId: process.pid,
      rootUri: rootUri,
      capabilities: {
        textDocument: {
          hover: { dynamicRegistration: true, contentFormat: ['markdown', 'plaintext'] },
          completion: { dynamicRegistration: true },
          definition: { dynamicRegistration: true },
          publishDiagnostics: { relatedInformation: true }
        }
      }
    }).then((result) => {
      this.isInitialized = true;
      this.log(`Server initialized: ${JSON.stringify(result?.serverInfo || {})}`);
      this.sendNotification('initialized', {});

      // Sync currently open documents
      for (const doc of vscode.workspace.textDocuments) {
        if (doc.languageId === 'pythonsharp') {
          this.didOpen(doc);
        }
      }
    }).catch((err) => {
      this.log(`Initialize failed: ${err.message}`);
    });
  }

  didOpen(doc) {
    this.sendNotification('textDocument/didOpen', {
      textDocument: {
        uri: doc.uri.toString(),
        languageId: 'pythonsharp',
        version: doc.version,
        text: doc.getText()
      }
    });
  }

  didChange(e) {
    this.sendNotification('textDocument/didChange', {
      textDocument: {
        uri: e.document.uri.toString(),
        version: e.document.version
      },
      contentChanges: [
        { text: e.document.getText() }
      ]
    });
  }

  didClose(doc) {
    this.sendNotification('textDocument/didClose', {
      textDocument: {
        uri: doc.uri.toString()
      }
    });
  }

  rejectAllPending(reason) {
    for (const [id, req] of this.pendingRequests.entries()) {
      req.reject(new Error(reason));
    }
    this.pendingRequests.clear();
  }

  stop() {
    if (this.process) {
      try {
        this.sendRequest('shutdown', {}).catch(() => {});
        this.sendNotification('exit', {});
        this.process.kill();
      } catch (e) {
        // ignore
      }
      this.process = null;
    }
    this.isInitialized = false;
    this.diagnosticCollection.clear();
    this.rejectAllPending('Server stopped');
  }
}

/**
 * Extension entry point
 */
function activate(context) {
  const outputChannel = vscode.window.createOutputChannel('PythonSharp LSP');
  context.subscriptions.push(outputChannel);
  outputChannel.appendLine('PythonSharp extension activated.');

  const client = new PythonSharpLanguageClient(context, outputChannel);
  client.start();

  // Document synchronization events
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.languageId === 'pythonsharp') {
        client.didOpen(doc);
      }
    }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.languageId === 'pythonsharp') {
        client.didChange(e);
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      if (doc.languageId === 'pythonsharp') {
        client.didClose(doc);
      }
    })
  );

  // Register Hover Provider
  context.subscriptions.push(
    vscode.languages.registerHoverProvider('pythonsharp', {
      async provideHover(document, position, token) {
        try {
          const res = await client.sendRequest('textDocument/hover', {
            textDocument: { uri: document.uri.toString() },
            position: { line: position.line, character: position.character }
          });
          if (res && res.contents) {
            const md = new vscode.MarkdownString(res.contents.value || res.contents);
            md.isTrusted = true;
            return new vscode.Hover(md);
          }
        } catch (e) {
          // ignore hover error
        }
        return null;
      }
    })
  );

  // Register Definition Provider
  context.subscriptions.push(
    vscode.languages.registerDefinitionProvider('pythonsharp', {
      async provideDefinition(document, position, token) {
        try {
          const res = await client.sendRequest('textDocument/definition', {
            textDocument: { uri: document.uri.toString() },
            position: { line: position.line, character: position.character }
          });
          if (res && res.uri && res.range) {
            const targetUri = vscode.Uri.parse(res.uri);
            const targetRange = new vscode.Range(
              new vscode.Position(res.range.start.line, res.range.start.character),
              new vscode.Position(res.range.end.line, res.range.end.character)
            );
            return new vscode.Location(targetUri, targetRange);
          }
        } catch (e) {
          // ignore definition error
        }
        return null;
      }
    })
  );

  // Register Type Definition Provider
  context.subscriptions.push(
    vscode.languages.registerTypeDefinitionProvider('pythonsharp', {
      async provideTypeDefinition(document, position, token) {
        try {
          const res = await client.sendRequest('textDocument/typeDefinition', {
            textDocument: { uri: document.uri.toString() },
            position: { line: position.line, character: position.character }
          });
          if (res && res.uri && res.range) {
            const targetUri = vscode.Uri.parse(res.uri);
            const targetRange = new vscode.Range(
              new vscode.Position(res.range.start.line, res.range.start.character),
              new vscode.Position(res.range.end.line, res.range.end.character)
            );
            return new vscode.Location(targetUri, targetRange);
          }
        } catch (e) {
          // ignore type definition error
        }
        return null;
      }
    })
  );

  // Register Completion Provider
  context.subscriptions.push(
    vscode.languages.registerCompletionItemProvider('pythonsharp', {
      async provideCompletionItems(document, position, token, context) {
        try {
          const res = await client.sendRequest('textDocument/completion', {
            textDocument: { uri: document.uri.toString() },
            position: { line: position.line, character: position.character }
          });
          if (res && res.items) {
            return res.items.map((item) => {
              const ci = new vscode.CompletionItem(item.label);
              ci.kind = item.kind !== undefined ? item.kind : vscode.CompletionItemKind.Keyword;
              ci.detail = item.detail;
              return ci;
            });
          }
        } catch (e) {
          // ignore completion error
        }
        return null;
      }
    }, '.', ' ')
  );

  // Status Bar Item
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.text = '$(zap) PythonSharp';
  statusBar.tooltip = 'PythonSharp Language Server (Active)';
  statusBar.command = 'pythonsharp.showMenu';
  statusBar.show();
  context.subscriptions.push(statusBar);

  // Commands
  context.subscriptions.push(
    vscode.commands.registerCommand('pythonsharp.restartServer', () => {
      client.start();
      vscode.window.showInformationMessage('PythonSharp Language Server restarted.');
    }),
    vscode.commands.registerCommand('pythonsharp.build', () => {
      const term = vscode.window.createTerminal('PythonSharp Build');
      term.show();
      term.sendText('psc build');
    }),
    vscode.commands.registerCommand('pythonsharp.check', () => {
      const activeDoc = vscode.window.activeTextEditor?.document;
      const target = activeDoc ? activeDoc.uri.fsPath : '.';
      const term = vscode.window.createTerminal('PythonSharp Check');
      term.show();
      term.sendText(`psc check "${target}"`);
    }),
    vscode.commands.registerCommand('pythonsharp.showMenu', async () => {
      const choice = await vscode.window.showQuickPick([
        { label: '$(sync) Restart Language Server', action: 'restart' },
        { label: '$(symbol-keyword) Check Project Diagnostics', action: 'check' },
        { label: '$(play) Build Project (psc build)', action: 'build' },
      ], { placeHolder: 'PythonSharp Actions' });

      if (choice) {
        if (choice.action === 'restart') vscode.commands.executeCommand('pythonsharp.restartServer');
        if (choice.action === 'check') vscode.commands.executeCommand('pythonsharp.check');
        if (choice.action === 'build') vscode.commands.executeCommand('pythonsharp.build');
      }
    })
  );

  context.subscriptions.push({
    dispose: () => client.stop()
  });
}

function deactivate() {}

module.exports = {
  activate,
  deactivate
};

