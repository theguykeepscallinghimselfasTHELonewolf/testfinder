import json, os
import re
from pathlib import Path
from collections import defaultdict

# Extensions that Coverity intercepts via build commands
COMPILED_EXTS = {'.java', '.cs', '.go', '.cpp', '.c', '.cc', '.cxx', '.h', '.hpp'}

def load_exclusions(json_path: str = "testfinder_exclusions.json"):
    """Loads both the excluded paths and the false positives from the JSON report."""
    if not Path(json_path).exists():
        print(f"❌ Error: Could not find {json_path}. Run the TUI selector first.")
        return [], []
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    paths = data.get("auto_detected_excluded", [])
    paths.extend([item["path"] for item in data.get("manually_excluded", [])])
    
    false_positives = [item["path"] for item in data.get("flagged_false_positives", [])]
    
    return sorted(paths), sorted(false_positives)

def categorize_by_project_and_type(paths: list[str], fps: list[str]) -> dict:
    """
    Identifies true project boundaries and categorizes files into Compiled vs Interpreted,
    keeping track of false positives for each category.
    """
    projects = defaultdict(lambda: {"compiled": [], "interpreted": [], "compiled_fps": [], "interpreted_fps": []})
    
    all_files = paths + fps
    if not all_files:
        return projects

    # Check if all files are sitting inside a single "wrapper" folder (e.g., TEST_REPOS)
    first_parts = set(Path(p).parts[0] for p in all_files if len(Path(p).parts) > 1)
    is_wrapper_folder = len(first_parts) == 1

    def route_file(p, is_fp=False):
        path_obj = Path(p)
        parts = path_obj.parts
        
        if is_wrapper_folder and len(parts) > 2:
            common_root = list(first_parts)[0]
            project_name = f"{common_root}/{parts[1]}"
            rel_path = str(Path(*parts[2:]))
        elif len(parts) > 1:
            project_name = parts[0]
            rel_path = str(Path(*parts[1:]))
        else:
            project_name = "root"
            rel_path = p
            
        suffix = path_obj.suffix.lower()
        
        # Route depending on if it's an exclusion or a false positive
        if not is_fp:
            if suffix in COMPILED_EXTS:
                projects[project_name]["compiled"].append(rel_path)
            else:
                projects[project_name]["interpreted"].append(rel_path)
        else:
            if suffix in COMPILED_EXTS:
                projects[project_name]["compiled_fps"].append(rel_path)
            else:
                projects[project_name]["interpreted_fps"].append(rel_path)

    for p in paths:
        route_file(p, is_fp=False)
    for p in fps:
        route_file(p, is_fp=True)
            
    return projects

def optimize_to_regex(paths: list[str], fps: list[str]) -> str:
    """
    Mathematical grouping to compress file paths.
    Uses PCRE Negative Lookaheads to protect False Positives from being swallowed by wildcards.
    """
    if not paths:
        return ""

    dir_groups = defaultdict(list)
    for p in paths:
        parent = str(Path(p).parent)
        if parent == ".":
            dir_groups[p].append(p)
        else:
            dir_groups[parent].append(p)

    fp_groups = defaultdict(list)
    for p in fps:
        parent = str(Path(p).parent)
        fp_groups[parent].append(Path(p).name)

    optimized_patterns = []
    
    for parent, items in dir_groups.items():
        fps_in_dir = fp_groups.get(parent, [])

        if len(items) > 2 or parent in items:
            safe_parent = re.escape(parent).replace(r"\\", "/")
            
            if fps_in_dir:
                # THE FIX: Construct negative lookahead for false positives!
                # e.g., (?!test_selenium\.py$|other_fp\.py$)
                safe_fps = [re.escape(fp) for fp in fps_in_dir]
                fp_lookahead = "(?!" + "|".join(safe_fps) + "$)"
                optimized_patterns.append(f"{safe_parent}/{fp_lookahead}[^/]+")
            else:
                optimized_patterns.append(f"{safe_parent}/[^/]+")
        else:
            for item in items:
                safe_item = re.escape(item).replace(r"\\", "/")
                optimized_patterns.append(safe_item)

    combined_regex = "|".join(optimized_patterns)
    return f"^(?:{combined_regex})$"


def process_project_yaml(project: str, data: dict, base_dir: str, write_to_disk: bool):
    compiled_regex = optimize_to_regex(data["compiled"], data["compiled_fps"])
    interpreted_regex = optimize_to_regex(data["interpreted"], data["interpreted_fps"])
    
    # Determine the file path
    if project == "root":
        target_dir = Path(base_dir)
    else:
        target_dir = Path(base_dir) / project

    yaml_location = target_dir / "coverity.yaml"
    
    print(f"\n📦 Project: [ {project.upper()} ]")
    print("-" * 60)
    
    # Build the YAML string
    yaml_output = ["capture:"]
    if interpreted_regex: yaml_output.extend(["  files:", f"    exclude_regex: '{interpreted_regex}'"])
    if compiled_regex: yaml_output.extend(["  compiler_configuration:", "    cov_configure_args:", f"      - '--xml-option=skip_file:{compiled_regex}'"])
    
    yaml_string = "\n".join(yaml_output) + "\n"
    print(yaml_string)
    
    # Write to disk if requested
    if write_to_disk:
        os.makedirs(target_dir, exist_ok=True)
        # Check if file exists to warn about overwriting
        prefix = "⚠️ Overwrote existing" if yaml_location.exists() else "✅ Created new"
        
        with open(yaml_location, 'w', encoding='utf-8') as f:
            f.write(yaml_string)
            
        print(f"{prefix} file: {yaml_location}")
    else:
        print(f"📄 Suggested Path: {yaml_location}")

    print("-" * 60)

def generate_all_yamls(excluded_paths: list[str], false_positives: list[str], base_dir: str, write_to_disk: bool = False):
    print("\n🛡️  Coverity YAML Monorepo Generator")
    print("=" * 60)
    for project, data in categorize_by_project_and_type(excluded_paths, false_positives).items():
        if data["compiled"] or data["interpreted"]: 
            process_project_yaml(project, data, base_dir, write_to_disk)




def print_project_yaml(project: str, data: dict):
    """Outputs the scoped coverity.yaml configuration for a specific project."""
    compiled_regex = optimize_to_regex(data["compiled"], data["compiled_fps"])
    interpreted_regex = optimize_to_regex(data["interpreted"], data["interpreted_fps"])
    
    yaml_location = "coverity.yaml" if project == "root" else f"{project}/coverity.yaml"
    
    print(f"\n📦 Project: [ {project.upper()} ]")
    print(f"📄 Save this to: {yaml_location}")
    print("-" * 60)
    
    yaml_output = ["capture:"]
    
    if interpreted_regex:
        yaml_output.append("  files:")
        yaml_output.append(f'    exclude_regex: "{interpreted_regex}"')
        
    if compiled_regex:
        yaml_output.append("  compiler_configuration:")
        yaml_output.append("    cov_configure_args:")
        yaml_output.append(f'      - "--xml-option=skip_file:{compiled_regex}"')
        
    print("\n".join(yaml_output))
    print("-" * 60)

# def generate_all_yamls(excluded_paths: list[str], false_positives: list[str]):
#     print("\n🛡️  Coverity YAML Monorepo Generator")
#     print("=" * 60)
    
#     projects_data = categorize_by_project_and_type(excluded_paths, false_positives)
    
#     for project, data in projects_data.items():
#         if not data["compiled"] and not data["interpreted"]:
#             continue
#         print_project_yaml(project, data)

if __name__ == "__main__":
    import sys
    json_file = sys.argv[1] if len(sys.argv) > 1 else "testfinder_exclusions.json"
    
    excluded_paths, fps = load_exclusions(json_file)
    if excluded_paths:
        generate_all_yamls(excluded_paths, fps)