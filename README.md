🛡️ TestFinder: SAST Exclusion Gatekeeper
📖 Overview
Static Application Security Testing (SAST) tools like Coverity are essential, but scanning test files, mocks, and fixtures wastes CI/CD compute time and generates false-positive vulnerability alerts.

However, allowing developers to blindly write exclusion regexes creates a massive security blind spot. Malicious actors or rushed developers could easily bypass security scans by placing production logic inside a tests/ folder or writing overly greedy wildcards.

TestFinder solves this by introducing a "Trust but Verify" architecture.

For Developers: It provides an interactive terminal UI (TUI) to automatically find test files, select exclusions, and   generate the perfect, secure regex for their coverity.yaml file.

For DevSecOps: It acts as an automated PR Gatekeeper. It reads modified SAST configurations and uses Abstract Syntax Trees (AST) to   prove that excluded files are actually test files. If production code is detected in the exclusion list, it escalates the file to an AI Security Agent (Copilot) for a final verdict before failing the build.

🏗️ Architecture: The 3-Stage Sieve
When a regex is validated, TestFinder processes matched files through three strict layers:

Stage 1: Heuristic Filter (O(1))
Instantly approves standard infrastructure directories (node_modules, .venv, target) and configuration files (.gitignore, uv.lock) that inherently do not require SAST scanning.

Stage 2: AST Parser (O(N))
Uses tree-sitter to parse the actual code of the excluded files. If the AST detects standard testing frameworks (e.g., Pytest, JUnit, xUnit, Go Tests), the file is   verified as safe and approved.

Stage 3: The AI Judge (Fallback)
If a file survives Stage 1 and 2, it is flagged as Suspicious. The CI/CD pipeline extracts this file and feeds it to a GitHub Copilot Agent. The LLM determines if it is a harmless fixture or an attempted security bypass.

💻 Developer Guide: CLI Usage
TestFinder makes it incredibly easy to build your SAST exclusion lists without ever writing regex manually.

1. Installation

Ensure you have Python 3.11+ and uv installed.

Bash
uv pip install tree-sitter tree-sitter-python tree-sitter-java tree-sitter-javascript tree-sitter-c-sharp tree-sitter-go PyYAML textual rich
2. Scan and Generate Exclusions (Interactive Mode)

Point the CLI at your repository. It will map the project, find all tests, and open an interactive UI.

Bash
uv run python src/main.py ./
Review: See exactly which files the AST engine flagged as tests.

Flag False Positives: Press t to explicitly force Coverity to scan a file that looks like a test but shouldn't be excluded.

Browse & Add: Manually exclude dummy vendor folders or mock data.

Auto-Generate: Upon exit, the tool will automatically write the perfectly scoped coverity.yaml file to your project root.

3. Check Supported Languages

See exactly which languages and testing frameworks the AST engine currently understands.

Bash
uv run python src/main.py --supported
🔐 DevSecOps Guide: Pipeline Integration
TestFinder is designed to run in GitHub Actions to validate PRs that modify SAST configurations.

CLI Validation Mode

You can manually test a regex against a repository to see what the gatekeeper will do:

Bash
uv run python src/main.py ./ --validate "^(?:tests/.*)$"
Outputs:

Exit 0: All files matched by the regex are   proven to be safe tests or infrastructure.

Exit 1: Suspicious files detected. A validation_payload.json is generated containing the exact files that bypassed the AST check.

The GitHub Actions Workflow

The automated gatekeeper triggers whenever a coverity.yaml file is modified in a Pull Request.

Regex Extraction: grep and sed extract the new regex from the YAML.

AST Validation: TestFinder runs the --validate command.

If Exit 0: Pipeline passes instantly (usually < 5 seconds).

LLM Escalation: If TestFinder exits with 1, the workflow reads validation_payload.json, truncates the suspicious source code, and queries the @github/copilot CLI.

The Verdict: Copilot comments directly on the PR. If it detects an attempted security bypass (e.g., "This contains production business logic"), the workflow fails, blocking the merge.