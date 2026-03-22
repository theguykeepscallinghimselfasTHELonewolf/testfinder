import os
import re
import json
from pathlib import Path

# Stage 1: Deterministic Safe Paths (Folders and Files we don't need an AST/LLM to verify)
SAFE_INFRA_DIRS = {
    'node_modules', 'venv', '.venv', '__pycache__', '.git', 
    'build', 'dist', 'target', 'bin', 'obj', 'out', '.idea', '.vscode'
}

SAFE_CONFIG_FILES = {
    '.gitignore', 'uv.lock', 'package-lock.json', 'yarn.lock', 
    'poetry.lock', 'pom.xml', 'build.gradle', 'dockerfile', 'docker-compose.yml',
    'coverity.yaml', 'tox.ini', 'pytest.ini'
}

def validate_regex_exclusions(project_root: str, regex_string: str, analyzer) -> dict:
    """
    Finds all files matched by the regex and categorizes them into safe vs suspicious.
    """
    root_path = Path(project_root).resolve()
    
    try:
        # Coverity regexes are usually PCRE. Python's re handles this well enough for validation.
        exclusion_pattern = re.compile(regex_string)
    except re.error as e:
        print(f"❌ Invalid Regex Provided: {e}")
        return {}

    report = {
        "valid_infrastructure": [],
        "valid_tests_ast": [],
        "suspicious_files": []
    }

    print(f"\n🔬 Scanning repository against regex: {regex_string}")

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Normalize path separators for regex matching (Coverity uses forward slashes)
        current_dir = Path(dirpath)
        
        for filename in filenames:
            file_path = current_dir / filename
            # Convert to relative path using forward slashes
            rel_path = str(file_path.relative_to(root_path)).replace("\\", "/")
            
            # Did this file get excluded by the developer's regex?
            if exclusion_pattern.search(rel_path):
                
                # --- STAGE 1: Heuristic Filter (Infra & Configs) ---
                path_parts = set(file_path.parts)
                if path_parts.intersection(SAFE_INFRA_DIRS) or filename.lower() in SAFE_CONFIG_FILES:
                    report["valid_infrastructure"].append(rel_path)
                    continue
                
                # --- STAGE 2: AST Filter (Is it actually a test?) ---
                # We reuse the exact same engine we built for detection!
                ast_result = analyzer.analyze_file(str(file_path), str(root_path))
                
                if ast_result and ast_result.get("hit_count", 0) > 0:
                    # The AST proved it is a test file
                    report["valid_tests_ast"].append({
                        "file": rel_path,
                        "frameworks": ast_result.get("frameworks", []),
                        "hits": ast_result.get("hit_count")
                    })
                    continue
                
                # --- STAGE 3: The Delta (Suspicious) ---
                # If it's not standard infra, and AST didn't find test functions... why is it excluded?
                report["suspicious_files"].append(rel_path)

    return report

def print_validation_report(report: dict, export_json: bool = True):
    """Outputs the validation results for the CI/CD pipeline."""
    if not report:
        return

    infra_count = len(report["valid_infrastructure"])
    test_count = len(report["valid_tests_ast"])
    suspicious_count = len(report["suspicious_files"])

    print("\n🛡️  Regex Validation Report")
    print("=" * 60)
    print(f"✅ Valid Infrastructure/Config Files : {infra_count}")
    print(f"✅ Valid Test Files (Verified by AST): {test_count}")
    print(f"⚠️  Suspicious Files (Requires Review): {suspicious_count}")
    print("=" * 60)

    if suspicious_count > 0:
        print("\n🚨 SUSPICIOUS FILES DETECTED:")
        print("These files matched the exclusion regex but contain no detectable test")
        print("frameworks and are not standard infrastructure. They may be source code.")
        print("-" * 60)
        for f in report["suspicious_files"]:
            print(f"  [X] {f}")
        print("-" * 60)
    else:
        print("\n✅ All excluded files have been mathematically or heuristically verified as safe.")

    # Dump the JSON payload specifically for your upcoming GitHub Action LLM step
    if export_json:
        out_file = "validation_payload.json"
        with open(out_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n📦 Pipeline payload written to: {out_file}")
        if suspicious_count > 0:
            print("   -> Pass the `suspicious_files` array to your LLM API for final verification.")