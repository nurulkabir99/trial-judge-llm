"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.saveResultToProject = saveResultToProject;
const vscode = require("vscode");
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
function saveResultToProject(result, filePath, content, language) {
    // 1. Determine project root folder
    const workspaceFolders = vscode.workspace.workspaceFolders;
    let projectRoot = "";
    if (workspaceFolders && workspaceFolders.length > 0) {
        projectRoot = workspaceFolders[0].uri.fsPath;
    }
    else {
        projectRoot = __dirname;
    }
    // 2. Create dataset folder inside project
    const outputDir = path.join(projectRoot, "sca_llm_eval_data");
    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }
    // 3. Compute hash for deduplication
    const codeHash = crypto.createHash('sha256').update(content).digest('hex');
    // 4. Build structured record
    const record = {
        timestamp: new Date().toISOString(),
        file_path: filePath,
        language: language,
        code_hash: codeHash,
        snippet: content,
        snippet_length: content.length,
        // Trial LLM outputs
        trial_A: result.trial_A || null,
        trial_B: result.trial_B || null,
        // Judge LLM outputs
        verdict: result.verdict ?? null,
        infringement_basis: result.infringement_basis ?? null,
        license_risk: result.license_risk ?? null,
        reasoning: result.reasoning ?? null,
        // Multi-model info
        model_comparison: result.model_comparison || null,
        error_analysis: result.error_analysis || null,
        // Raw full JSON
        raw_output: result
    };
    // 5. Save as JSON file
    const outFile = path.join(outputDir, `record_${Date.now()}.json`);
    fs.writeFileSync(outFile, JSON.stringify(record, null, 2), "utf8");
    console.log(`Saved SCA record: ${outFile}`);
}
//# sourceMappingURL=saveResult.js.map