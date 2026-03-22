;; 1. Standard Test Classes
((class_declaration
  name: (identifier) @namespace.name)
  (#match? @namespace.name "Tests?$")) @rule.java_class

;; 2. JUnit (4 & 5) and TestNG Methods
((method_declaration
  (modifiers
    [
      (marker_annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
      (annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
    ]))
  (#match? @attr.name "^(Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate|CartesianTest)$")) @rule.junit_testng_test

;; 3. Spring Boot Integration Test Classes
((class_declaration
  (modifiers
    [
      (marker_annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
      (annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
    ]))
  (#match? @attr.name "^(SpringBootTest|WebMvcTest|WebFluxTest|DataJpaTest|DataMongoTest|RestClientTest|JsonTest)$")) @rule.spring_boot_test

;; 4. Cucumber / BDD Step Definitions
((method_declaration
  (modifiers
    [
      (marker_annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
      (annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
    ]))
  (#match? @attr.name "^(Given|When|Then|And|But)$")) @rule.cucumber_step

;; 5. Test Suites & Runners
((class_declaration
  (modifiers
    [
      (marker_annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
      (annotation name: [(identifier) @attr.name (scoped_identifier name: (identifier) @attr.name)])
    ]))
  (#match? @attr.name "^(RunWith|CucumberOptions|Suite)$")) @rule.java_test_suite