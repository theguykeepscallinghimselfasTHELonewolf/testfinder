import os
from pathlib import Path
from typing import Union
from tree_sitter import Language, Parser, Query
from language_detector import detect_language_from_file

# Handle newer tree-sitter versions (v0.25+)
try:
    from tree_sitter import QueryCursor
except ImportError:
    QueryCursor = None

# Human-readable translations for our Tree-sitter rules
TAG_TRANSLATIONS = {
    # Python
    "rule.name_match": "Contains test function (test_*)",
    "rule.decorated_test": "Contains decorated test function",
    "rule.class_name": "Contains test suite class (Test*)",
    "rule.inheritance": "Inherits from testing framework (TestCase)",
    "rule.test_decorator": "Uses testing-specific decorator (@pytest / @fixture)",
    "rule.django_testcase": "Inherits from Django TestCase", # Just in case you kept the Django one!

    # JavaScript / TypeScript
    "rule.js_test_block": "Contains JS test block (describe/it/test)",
    
    # Go
    "rule.go_test_func": "Contains Go test function (Test*/Example*)",

    # C# (.NET)
    "rule.xunit_test": "xUnit framework detected ([Fact] / [Theory])",
    "rule.nunit_test": "NUnit framework detected ([Test] / [TestCase])",
    "rule.mstest_test": "MSTest framework detected ([TestMethod])",
    "rule.specflow_test": "SpecFlow BDD generated test detected",

    # Java (JVM)
    "rule.java_class": "Java Test Class (Naming Convention)",
    "rule.junit_testng_test": "Annotated test method (@Test, etc.)",
    "rule.spring_boot_test": "Spring Boot Integration Test (@SpringBootTest, etc.)",
    "rule.cucumber_step": "Cucumber BDD Step Definition (@Given, @When, etc.)",
    "rule.java_test_suite": "Java Test Suite/Runner (@RunWith, @CucumberOptions)",
}
FRAMEWORK_MAPPING = {
    # C#
    "rule.xunit_test": "xUnit",
    "rule.nunit_test": "NUnit",
    "rule.nunit_class": "NUnit",
    "rule.mstest_test": "MSTest",
    "rule.mstest_class": "MSTest",
    "rule.specflow_test": "SpecFlow",
    
    # Python
    "rule.name_match": "Pytest/Unittest",
    "rule.decorated_test": "Pytest",
    "rule.class_name": "Pytest/Unittest",
    "rule.inheritance": "Unittest/Django",
    "rule.test_decorator": "Pytest",
    
    # JavaScript / Go / Lua
    "rule.js_test_block": "Jest/Mocha",
    "rule.go_test_func": "Go Test",
    "rule.lua_test_block": "Busted",

    # Java (JVM)
    "rule.junit_testng_test": "JUnit/TestNG",
    "rule.spring_boot_test": "Spring Boot Test",
    "rule.cucumber_step": "Cucumber (BDD)",
    "rule.java_test_suite": "Test Runner/Suite"
}
LANGUAGE_META = {
    "python": {"name": "Python", "frameworks": ["Pytest", "Unittest", "Django"]},
    "go": {"name": "Go", "frameworks": ["Standard Go Test"]},
    "csharp": {"name": "C# (.NET)", "frameworks": ["xUnit", "NUnit", "MSTest", "SpecFlow"]},
    "java": {"name": "Java (JVM)", "frameworks": ["JUnit (4/5)", "TestNG", "Spring Boot", "Cucumber"]},
    
}

# Dynamically load language bindings as needed
def get_ts_language(lang_name: str) -> Union[Language, None]:
    if lang_name == "python":
        import tree_sitter_python as tspy
        return Language(tspy.language())
    elif lang_name == "csharp":
        import tree_sitter_c_sharp as csharp
        return Language(csharp.language())
    elif lang_name == "java":
        import tree_sitter_java as tsjava
        return Language(tsjava.language())


class TestAnalyzer:
    def __init__(self, queries_dir: str = "queries"):
        self.queries_dir = Path(queries_dir)
        self.parsers: dict[str, Parser] = {}
        self.queries: dict[str, Query] = {}
        self.loaded_languages: dict[str, Language] = {}

    def _setup_language(self, lang_name: str) -> bool:
        """Loads the parser and query file for a detected language."""
        if lang_name in self.parsers:
            return True

        if lang_name not in self.loaded_languages:
            ts_lang = get_ts_language(lang_name)
            if not ts_lang:
                return False
            self.loaded_languages[lang_name] = ts_lang
        
        ts_lang = self.loaded_languages[lang_name]

        # Look for queries/<lang_name>.scm
        query_file = self.queries_dir / f"{lang_name}.scm"
        if not query_file.exists():
            return False

        # Initialize Parser and securely compile Query
        parser = Parser(ts_lang)
        self.parsers[lang_name] = parser
        
        try:
            self.queries[lang_name] = Query(ts_lang, query_file.read_text(encoding="utf-8"))
        except Exception as e:
            # THIS PREVENTS CLI CRASHES FROM BAD .SCM FILES
            print(f"[ERROR] Failed to compile SCM query for {lang_name}.scm: {e}")
            return False
            
        return True

    def analyze_file(self, file_path: str, project_root: str) -> Union[dict, None]:
        """Detects language, applies query, and returns test metadata if found."""
        lang_name = detect_language_from_file(file_path, project_root=project_root)
        
        if lang_name == "unknown" or not self._setup_language(lang_name):
            return None

        parser = self.parsers[lang_name]

        try:
            with open(file_path, "rb") as f:
                tree = parser.parse(f.read())
                result = self._analyze_tree(tree, lang_name)
                if result:
                    result["file"] = os.path.relpath(file_path, project_root)
                    return result
        except Exception as e:
            print(f"[ERROR] Failed parsing {file_path}: {e}")
        return None

    def get_supported_capabilities(self) -> list[dict]:
        """Dynamically inspects the queries directory to see what is actually supported."""
        from language_detector import detector
        capabilities = []
        
        # Only report languages that ACTUALLY have a .scm file installed!
        for query_file in self.queries_dir.glob("*.scm"):
            lang_key = query_file.stem
            meta = LANGUAGE_META.get(lang_key, {"name": lang_key.capitalize(), "frameworks": ["Custom AST Rules"]})
            
            # Dynamically pull extensions from your language_detector.py
            exts = [ext for ext, l in detector.EXTENSION_MAPPING.items() if l == lang_key]
            
            # Format extensions cleanly, handle Go special case
            if lang_key == "go":
                ext_str = "_test.go"
            elif exts:
                # Show up to 4 extensions so the table doesn't break, append "..." if more
                ext_str = ", ".join(exts[:4]) + ("..." if len(exts) > 4 else "")
            else:
                ext_str = "Auto-detected"

            capabilities.append({
                "language": meta["name"],
                "extensions": ext_str,
                "frameworks": ", ".join(meta["frameworks"])
            })
            
        # Sort alphabetically by language name
        return sorted(capabilities, key=lambda x: x["language"])

    def analyze_source(self, source_code: str, lang_name: str) -> Union[dict, None]:
        """Analyzes a string of source code."""
        if lang_name == "unknown" or not self._setup_language(lang_name):
            return None

        parser = self.parsers[lang_name]
        tree = parser.parse(bytes(source_code, "utf8"))
        return self._analyze_tree(tree, lang_name)

    def _analyze_tree(self, tree, lang_name: str) -> Union[dict, None]:
        """Analyzes a tree-sitter tree and returns translated test metadata."""
        query = self.queries[lang_name]
        
        if QueryCursor is not None and not hasattr(query, "captures"):
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)
        else:
            captures = query.captures(tree.root_node)

        if not captures:
            return None

        raw_tags = []
        hit_count = 0

        if isinstance(captures, dict):
            for tag, nodes in captures.items():
                raw_tags.append(tag)
                if tag.startswith("rule."):
                    hit_count += len(nodes)
        else:
            for node, tag in captures:
                raw_tags.append(tag)
                if tag.startswith("rule."):
                    hit_count += 1

        human_reasons = set()
        frameworks = set() # NEW: Track frameworks
        
        for tag in raw_tags:
            if tag.startswith("rule."):
                translation = TAG_TRANSLATIONS.get(tag, tag.replace("rule.", "").replace("_", " ").capitalize())
                human_reasons.add(translation)
                
                # NEW: Map the tag to a framework
                if tag in FRAMEWORK_MAPPING:
                    frameworks.add(FRAMEWORK_MAPPING[tag])

        if hit_count > 0:
            return {
                "language": lang_name,
                "hit_count": hit_count,
                "reasons": list(human_reasons),
                "frameworks": list(frameworks) # NEW: Return frameworks
            }
        return None

    def scan_directory(self, target_dir: str, project_root: str) -> list[dict]:
        """Walks the directory and analyzes all files."""
        results = []
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', 'venv', '__pycache__')]
            for file in files:
                full_path = os.path.join(root, file)
                analysis = self.analyze_file(full_path, project_root)
                if analysis:
                    results.append(analysis)
        return results