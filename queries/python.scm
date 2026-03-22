;; --- ORIGINAL LOGIC (Function Definitions) ---
((function_definition
  name: (identifier) @test.name)
  (#match? @test.name "^test_")) @rule.name_match

(decorated_definition
  ((function_definition
    name: (identifier) @test.name)
    (#match? @test.name "^test_"))) @rule.decorated_test



;; --- FIXED: STEALTH TEST LOGIC (Inheritance) ---
;; Safely matches `class A(TestCase):` OR `class A(unittest.TestCase):`
((class_definition
  name: (identifier) @test.class
  superclasses: (argument_list
    [
      (identifier) @parent
      (attribute attribute: (identifier) @parent)
    ]))
  (#match? @parent "TestCase")) @rule.inheritance

;; --- FIXED: STEALTH TEST LOGIC (Generic Decorators) ---
;; Safely digs into the (decorator) node to find the name, even if it's a function call like @pytest.mark(...)
((decorated_definition
  (decorator
    [
      (identifier) @dec_name
      (attribute attribute: (identifier) @dec_name)
      (call function: (identifier) @dec_name)
      (call function: (attribute attribute: (identifier) @dec_name))
    ]))
  (#match? @dec_name "(pytest|fixture|test)")) @rule.test_decorator