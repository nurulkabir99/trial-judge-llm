"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = require("vscode");
const axios_1 = require("axios");
const saveResult_1 = require("./saveResult");
function activate(context) {
    const backendUrl = vscode.workspace.getConfiguration().get("scaLLM.backendUrl");
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.text = "SLA: Idle";
    statusBar.color = undefined;
    statusBar.show();
    vscode.workspace.onDidSaveTextDocument(async (document) => {
        try {
            const filePath = document.fileName;
            const content = document.getText();
            const languageId = document.languageId;
            statusBar.text = "SLA: Analyzing…";
            //  POST to n8n webhook
            const response = await axios_1.default.post(backendUrl, {
                file_path: filePath,
                code: content,
                language: languageId
            });
            const result = response.data;
            (0, saveResult_1.saveResultToProject)(result, filePath, content, languageId);
            // Extract fields from Trial Judge output
            const verdict = result.verdict || "unknown";
            const licenseRisk = result.license_risk || "unknown";
            const basis = result.infringement_basis || "unknown";
            statusBar.text = `SLA: ${verdict} | ${licenseRisk}`;
            if (verdict === "violation") {
                statusBar.color = "#ff5555";
            }
            else if (verdict === "high_risk") {
                statusBar.color = "#ffaa00";
            }
            else {
                statusBar.color = undefined;
            }
            vscode.window.showInformationMessage(`[SCA-LLM]\nVerdict: ${verdict}\nRisk: ${licenseRisk}\nBasis: ${basis}`);
            // Also print detailed report in an output panel
            const panel = vscode.window.createOutputChannel("SLA Trial Judge Report");
            panel.clear();
            panel.appendLine("=== SLA Trial Judge Output ===");
            panel.appendLine(JSON.stringify(result, null, 2));
            panel.show();
        }
        catch (error) {
            statusBar.text = "SLA: Error";
            vscode.window.showErrorMessage(`SLA-LLM Error: ${error.message || error}`);
        }
    });
    context.subscriptions.push(statusBar);
}
function deactivate() { }
//# sourceMappingURL=extension.js.map