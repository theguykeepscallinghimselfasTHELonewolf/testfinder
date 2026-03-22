import argparse
import json
import sys
from pathlib import Path
from path_finder import detect_project_root
from analyzer import TestAnalyzer
from utils.validator import validate_regex_exclusions, print_validation_report

# ... (Replace the hardcoded function) ...
def print_supported_languages(analyzer: TestAnalyzer):
    """Prints a dynamic table based on currently installed SCM queries."""
    capabilities = analyzer.get_supported_capabilities()
    
    print("\n🌐 TestFinder Supported Languages & Frameworks")
    print("=" * 105)
    
    if not capabilities:
        print("⚠️  No query files (.scm) found in the queries directory.")
        print("=" * 105 + "\n")
        return

    # Calculate dynamic column widths
    max_lang = max([len(c["language"]) for c in capabilities] + [10])
    max_ext = max([len(c["extensions"]) for c in capabilities] + [15])
    
    row_format = f"| {{:<{max_lang}}} | {{:<{max_ext}}} | {{:<}}"
    
    print(row_format.format("Language", "Extensions", "Frameworks Detected"))
    print("-" * 105)
    
    for cap in capabilities:
        print(row_format.format(cap["language"], cap["extensions"], cap["frameworks"]))
        
    print("=" * 105 + "\n")



def main():
    parser = argparse.ArgumentParser(description="TestFinder: Detect test files intelligently.")
    parser.add_argument("target_path", nargs='?', default=None, help="Directory or file to scan for tests")
    parser.add_argument("--queries", default="queries", help="Path to the queries directory")
    parser.add_argument("--format", choices=['json', 'text'], default='text', help="Output format")
    parser.add_argument("--source", help="Code snippet to analyze")
    parser.add_argument("--language", help="Language of the code snippet")
    parser.add_argument("--supported", action="store_true", help="List supported languages and testing frameworks")
    parser.add_argument("--validate", type=str, help="Validate an existing Coverity regex against the target path")
    args = parser.parse_args()
    analyzer = TestAnalyzer(queries_dir=args.queries)
    if args.supported:
        print_supported_languages(analyzer)
        sys.exit(0)


    # Modified check to allow running just --supported without a target_path
    if not args.target_path and not args.source:
        parser.error("Either target_path or --source must be provided. Use --help for usage.")

    if args.source and not args.language:
        parser.error("--language is required when using --source.")

    project_root = None
    if args.target_path:
        target_path = Path(args.target_path).resolve()

        if not target_path.exists():
            print(f"Error: Path {target_path} does not exist.")
            sys.exit(1)
        project_root = detect_project_root(str(target_path))
        if not project_root:
            project_root = str(target_path) if target_path.is_dir() else str(target_path.parent)
    else:
        project_root = str(Path.cwd())
    
    
    if args.validate:
        if not args.target_path:
            parser.error("--validate requires a target_path to scan against.")
        
        report = validate_regex_exclusions(project_root, args.validate, analyzer)
        print_validation_report(report)
        
        # CI/CD Standard: Exit with code 1 if suspicious files are found so the pipeline halts
        if len(report.get("suspicious_files", [])) > 0:
            sys.exit(1)
        sys.exit(0)
   



    # Intercept the --supported flag dynamically
    if args.supported:
        print_supported_languages(analyzer)
        sys.exit(0)



    findings = []
    if args.source:
        result = analyzer.analyze_source(args.source, args.language)
        if result:
            findings.append(result)
    elif args.target_path:
        target_path = Path(args.target_path).resolve()
        if target_path.is_file():
            result = analyzer.analyze_file(str(target_path), project_root)
            if result:
                findings.append(result)
        else:
            findings = analyzer.scan_directory(str(target_path), project_root)

    if args.format == 'json':
        print(json.dumps(findings, indent=2))
    else:
        if not findings:
            print(f"\n🔍 TestFinder Analysis (Root: {project_root})")
            print("-" * 50)
            print("No tests found.")
            print("-" * 50)
            return

        # 1. Aggregate Summary Data
        all_langs = set()
        all_frameworks = set()
        for f in findings:
            all_langs.add(f.get('language', 'unknown').capitalize())
            all_frameworks.update(f.get('frameworks', []))
        
        # Print Header
        print(f"\n🔍 TestFinder Analysis (Root: {project_root})")
        print("=" * 110)
        print(f"📊 SUMMARY REPORT")
        print(f"   Languages Detected : {', '.join(sorted(all_langs)) if all_langs else 'None'}")
        print(f"   Frameworks Found   : {', '.join(sorted(all_frameworks)) if all_frameworks else 'None'}")
        print(f"   Total Test Files   : {len(findings)}")
        print("=" * 110)

        # 2. Calculate dynamic column widths for the table
        max_file = max([len(f.get('file', '(source)')) for f in findings] + [4])
        max_lang = max([len(f.get('language', '')) for f in findings] + [8])
        max_hits = max([len(str(f.get('hit_count', 0))) for f in findings] + [4])
        max_fw = max([len(", ".join(f.get('frameworks', []))) for f in findings] + [10])
        
        # Row formatter using f-string padding
        row_format = f"| {{:<{max_file}}} | {{:<{max_lang}}} | {{:>{max_hits}}} | {{:<{max_fw}}} | {{:<}}"
        
        # Print Table Headers
        header = row_format.format("File", "Language", "Hits", "Frameworks", "Triggers")
        print(header)
        print("-" * len(header))
        
        # Print Rows
        for f in findings:
            file_val = f.get('file', '(source)')
            lang_val = f.get('language', '').capitalize()
            hits_val = str(f.get('hit_count', 0))
            fw_val = ", ".join(f.get('frameworks', []))
            trig_val = " + ".join(f.get('reasons', []))
            
            print(row_format.format(file_val, lang_val, hits_val, fw_val, trig_val))
        
        print("=" * 110 + "\n")
# --- Trigger the TUI & Regex Workflow ---
        if findings:
            proceed = input("Do you want to review these files and build an exclusion list? (y/N): ")
            if proceed.strip().lower() == 'y':
                from utils.tui_selector import ExclusionTUI, generate_csv_report
                from utils.yaml_generator import generate_all_yamls  # <-- UPDATED IMPORT
                
                # Run the interactive TUI
                app = ExclusionTUI(findings, project_root)
                tui_result = app.run()
                
                if tui_result:
                    # 1. Generate the CSV and JSON reports
                    generate_csv_report(tui_result)
                    
                    # 2. Generate Coverity YAMLs based on monorepo structure
                    final_paths = tui_result.get("selected_for_exclusion", [])
                    # NEW: Grab the false positives from the TUI
                    false_positives = list(tui_result.get("false_positives", {}).keys()) 
                    
                    if final_paths:
                        generate_all_yamls(final_paths, false_positives) # NEW: Pass them in!
                    else:
                        print("\n⚠️ No files were selected for exclusion. Skipping YAML generation.")
                else:
                    print("\nAborted exclusion list builder.")

if __name__ == "__main__":
    main()