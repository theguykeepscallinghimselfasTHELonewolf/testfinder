;; ============================================================================
;; C# / .NET Test Framework Detection
;; Mapped directly from neotest-dotnet configurations
;; ============================================================================

;; 1. xUnit
(method_declaration
  (attribute_list
    (attribute
      name: [
        (identifier) @attr.name
        (qualified_name) @attr.name
      ]
      (#match? @attr.name "^(Fact|Theory)$")))) @rule.xunit_test

;; 2. NUnit
(method_declaration
  (attribute_list
    (attribute
      name: [
        (identifier) @attr.name
        (qualified_name) @attr.name
      ]
      (#match? @attr.name "^(Test|TestCase|TestCaseSource)$")))) @rule.nunit_test

;; 3. MSTest
(method_declaration
  (attribute_list
    (attribute
      name: [
        (identifier) @attr.name
        (qualified_name) @attr.name
      ]
      (#match? @attr.name "^(TestMethod|DataTestMethod)$")))) @rule.mstest_test

;; 4. SpecFlow (Generated BDD Tests)
(method_declaration
  (attribute_list
    (attribute
      name: [
        (identifier) @attr.name
        (qualified_name) @attr.name
      ]
      (#match? @attr.name "^(SkippableFactAttribute|Xunit\\.SkippableFactAttribute|TestMethodAttribute|TestAttribute|NUnit\\.Framework\\.TestAttribute)$")))) @rule.specflow_test