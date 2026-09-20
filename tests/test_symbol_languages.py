"""
Regression tests for symbol_search.py's per-language symbol extraction.

Written after auditing every language this module claims to support by
actually installing each tree_sitter_<lang> package and testing real code
samples - not by assumption. That audit found several real, previously
silent bugs (see individual test docstrings for which), all fixed
alongside adding six new languages (Kotlin, Swift, Scala, Lua, Bash,
Dart). These tests exist so none of that regresses.
"""

import os

import pytest

from symbol_search import SymbolIndexer, LANGUAGE_EXTENSIONS, LANGUAGE_MODULE_NAMES, get_tree_sitter_parser


ALL_LANGUAGES = sorted(set(LANGUAGE_EXTENSIONS.values()))

# (filename, source, expected symbol names that MUST be found)
LANGUAGE_SAMPLES = {
    "python": ("sample.py", "class Greeter:\n    def __init__(self, name):\n        self.name = name\n    def greet(self):\n        return self.name\n\ndef main():\n    pass\n",
               {"Greeter", "__init__", "greet", "main"}),
    "javascript": ("sample.js", "class Greeter {\n    constructor(name) { this.name = name; }\n    greet() { return this.name; }\n}\nfunction main() {}\n",
                   {"Greeter", "constructor", "greet", "main"}),
    "typescript": ("sample.ts", "interface Named { name: string; }\nclass Greeter implements Named {\n    constructor(public name: string) {}\n    greet(): string { return this.name; }\n}\nfunction main(): void {}\n",
                   {"Named", "Greeter", "constructor", "greet", "main"}),
    "tsx": ("sample.tsx", "class Greeter {\n    constructor(public name: string) {}\n    greet(): string { return this.name; }\n}\nfunction main(): void {}\n",
            {"Greeter", "constructor", "greet", "main"}),
    "rust": ("sample.rs", "struct Greeter { name: String }\nimpl Greeter {\n    fn greet(&self) -> String { self.name.clone() }\n}\nfn main() {}\n",
             {"Greeter", "greet", "main"}),
    "go": ("sample.go", "package main\ntype Greeter struct { Name string }\nfunc (g Greeter) Greet() string { return g.Name }\nfunc main() {}\n",
           {"Greet", "main"}),
    "cpp": ("sample.cpp", "class Greeter {\npublic:\n    Greeter(std::string name) : name(name) {}\n    std::string greet() { return name; }\nprivate:\n    std::string name;\n};\nint main() { return 0; }\n",
            {"Greeter", "greet", "main"}),
    "c": ("sample.c", "struct Greeter { char* name; };\nvoid greet(struct Greeter* g) {}\nint main() { return 0; }\n",
          {"Greeter", "greet", "main"}),
    "java": ("Sample.java", "class Greeter {\n    private String name;\n    public String greet() { return name; }\n}\n",
             {"Greeter", "greet"}),
    "c_sharp": ("sample.cs", "class Greeter {\n    public string Greet() => \"hi\";\n}\n",
                {"Greeter", "Greet"}),
    "php": ("sample.php", "<?php\nclass Greeter {\n    public function __construct(public string $name) {}\n    public function greet(): string { return $this->name; }\n}\nfunction main() {}\n",
            {"Greeter", "__construct", "greet", "main"}),
    "ruby": ("sample.rb", "class Greeter\n  def initialize(name)\n    @name = name\n  end\n  def greet\n    @name\n  end\nend\n",
             {"Greeter", "initialize", "greet"}),
    "kotlin": ("sample.kt", "class Greeter(val name: String) {\n    fun greet(): String {\n        return name\n    }\n}\n\nfun main() {\n}\n",
               {"Greeter", "greet", "main"}),
    "swift": ("sample.swift", "class Greeter {\n    let name: String\n    init(name: String) { self.name = name }\n    func greet() -> String { return name }\n}\nfunc main() {}\n",
              {"Greeter", "greet", "main"}),
    "scala": ("sample.scala", "class Greeter(name: String) {\n  def greet(): String = name\n}\nobject Main {\n  def main(args: Array[String]): Unit = {}\n}\n",
              {"Greeter", "greet", "main"}),
    "lua": ("sample.lua", "function greet(name)\n    return name\nend\n\nlocal function main()\nend\n",
            {"greet", "main"}),
    "bash": ("sample.sh", "greet() {\n    echo \"hi $1\"\n}\n\nmain() {\n    greet world\n}\n",
             {"greet", "main"}),
    "dart": ("sample.dart", "class Greeter {\n  final String name;\n  Greeter(this.name);\n\n  String greet() {\n    return name;\n  }\n}\n\nvoid main() {\n}\n",
             {"Greeter", "greet", "main"}),
}


def test_every_extension_maps_to_an_installed_language():
    for ext, lang in LANGUAGE_EXTENSIONS.items():
        assert lang in LANGUAGE_MODULE_NAMES, f"{ext} maps to {lang!r}, which has no entry in LANGUAGE_MODULE_NAMES"


@pytest.mark.parametrize("lang", ALL_LANGUAGES)
def test_parser_loads_for_every_supported_language(lang):
    """Catches the exact class of bug found during the language-coverage
    audit: TypeScript and PHP were both listed as "supported" but their
    parsers silently failed to load (tree_sitter_typescript/tree_sitter_php
    don't expose a plain `.language()` the way most tree_sitter_<lang>
    packages do), meaning zero symbols were ever extracted from any .ts/
    .tsx/.php file with no error shown anywhere. A parser existing is a
    prerequisite for everything else in this file being meaningful."""
    parser = get_tree_sitter_parser(lang)
    assert parser is not None, f"get_tree_sitter_parser({lang!r}) returned None - the parser failed to load"


@pytest.mark.parametrize("lang,sample", LANGUAGE_SAMPLES.items())
def test_expected_symbols_are_extracted(lang, sample, temp_workspace):
    filename, source, expected_names = sample
    path = os.path.join(temp_workspace, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)

    indexer = SymbolIndexer()
    symbols = indexer.parse_file_symbols(path, temp_workspace)
    found_names = {s["name"] for s in symbols}

    missing = expected_names - found_names
    assert not missing, f"{lang}: expected symbols {missing} were not extracted (found: {found_names})"


@pytest.mark.parametrize("lang,sample", LANGUAGE_SAMPLES.items())
def test_no_duplicate_symbols(lang, sample, temp_workspace):
    """Regression test for a real bug found while adding struct_specifier/
    class_specifier support: C/C++ use the identical node type for both a
    real struct/class DEFINITION and a bare type REFERENCE elsewhere (e.g.
    a parameter typed `struct Foo*`), which without a body-presence check
    produced a duplicate "definition" for every place the type was merely
    referenced."""
    filename, source, _ = sample
    path = os.path.join(temp_workspace, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)

    indexer = SymbolIndexer()
    symbols = indexer.parse_file_symbols(path, temp_workspace)
    keys = [(s["name"], s["kind"], s["line"]) for s in symbols]
    assert len(keys) == len(set(keys)), f"{lang}: duplicate symbol entries found: {symbols}"


def test_c_struct_type_reference_is_not_a_duplicate_definition(temp_workspace):
    """The specific case that exposed the struct_specifier duplicate bug:
    a struct used as a parameter type must not itself be counted as a
    second definition of that struct."""
    path = os.path.join(temp_workspace, "sample.c")
    with open(path, "w", encoding="utf-8") as f:
        f.write("struct Greeter { char* name; };\nvoid greet(struct Greeter* g) {}\n")

    indexer = SymbolIndexer()
    symbols = indexer.parse_file_symbols(path, temp_workspace)
    greeter_defs = [s for s in symbols if s["name"] == "Greeter"]
    assert len(greeter_defs) == 1, f"expected exactly one Greeter definition, got {greeter_defs}"


def test_dart_constructor_is_classified_as_method_not_class(temp_workspace):
    """Regression test for a substring-collision bug: the kind
    classification checked `"struct" in node_type` before checking for
    "constructor", and "struct" is a literal substring of "constructor" -
    so every constructor_signature node was misclassified as kind="class"."""
    path = os.path.join(temp_workspace, "sample.dart")
    with open(path, "w", encoding="utf-8") as f:
        f.write("class Greeter {\n  final String name;\n  Greeter(this.name);\n}\n")

    indexer = SymbolIndexer()
    symbols = indexer.parse_file_symbols(path, temp_workspace)
    constructor = next(s for s in symbols if s["name"] == "Greeter" and s["kind"] != "class")
    assert constructor["kind"] == "method"


def test_c_function_name_found_via_nested_declarator(temp_workspace):
    """Regression test: C/C++ nest the actual function identifier inside a
    chain of "declarator" fields (function_definition -> declarator
    (function_declarator) -> declarator (identifier)) rather than exposing
    it as a direct child or a "name" field - a plain direct-children scan
    found nothing, silently extracting zero C/C++ functions."""
    path = os.path.join(temp_workspace, "sample.c")
    with open(path, "w", encoding="utf-8") as f:
        f.write("int main() { return 0; }\n")

    indexer = SymbolIndexer()
    symbols = indexer.parse_file_symbols(path, temp_workspace)
    assert any(s["name"] == "main" for s in symbols)
