#!/usr/bin/env python3
"""Negative controls for the lexical guard used by the repository cleanup."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from maintenance.layout import code_tokens, comment_issues


class RepositoryChecks(unittest.TestCase):
    def test_nested_comments_and_layout_preserve_code(self):
        before='val a = 1; io.out := a + 2'
        after='// Stage input\nval a = 1; /* outer /* inner */ comment */\nio.out := a + 2'
        self.assertEqual(code_tokens(before),code_tokens(after))

    def test_comment_markers_in_literals_are_functional(self):
        self.assertNotEqual(code_tokens('assert(x,"// old")'),code_tokens('assert(x,"// new")'))
        self.assertNotEqual(code_tokens('val s = """/* old */"""'),code_tokens('val s = """/* new */"""'))
        self.assertEqual(code_tokens('val c = \'/\' // comment'),code_tokens('val c = \'/\''))

    def test_operator_and_identifier_changes_are_rejected(self):
        self.assertNotEqual(code_tokens('x := a + b'),code_tokens('x := a - b'))
        self.assertNotEqual(code_tokens('val a = 1'),code_tokens('vala = 1'))
        self.assertEqual(code_tokens('x:=/* contract */a'),code_tokens('x:=a'))

    def test_declaration_and_long_block_are_detected(self):
        self.assertTrue(comment_issues('class Missing extends Module {}')[1])
        self.assertFalse(comment_issues('/** Contract. */\nclass Present extends Module {}')[1])
        self.assertTrue(comment_issues('\n'.join(f'val a{i} = {i}' for i in range(41)))[1])

    def test_declarations_in_comments_and_literals_are_ignored(self):
        source = '''/*
class NotCode
/* object NestedComment */
*/
/** Entry contract. */
object Actual {
  val text = """
trait NotCodeEither
"""
  val name = "class StillNotCode"
}
'''
        self.assertEqual(comment_issues(source)[1], [])
        # A real declaration after the literal still needs its own contract.
        self.assertEqual(comment_issues(source + 'class Missing {}')[1],
                         ['Missing at line 12 needs declaration ScalaDoc'])

    def test_indented_and_modified_top_level_declarations_are_detected(self):
        for header in ('  class Missing {}', '\tfinal class Missing {}',
                       '  private[vpu] case object Missing {}',
                       '  sealed trait Missing {}'):
            with self.subTest(header=header):
                self.assertEqual(len(comment_issues(header)[1]), 1)
                self.assertEqual(comment_issues('/** Contract. */\n' + header)[1], [])

    def test_annotations_belong_to_documented_header(self):
        header = '''@deprecated("old", "1")
@tools.Contract[Type](factory({ class Local {}; "class Fake" }))(1)
private[vpu] final class Present {}
'''
        self.assertEqual(comment_issues('/** Contract. */\n' + header)[1], [])
        self.assertEqual(comment_issues(header)[1],
                         ['Present at line 3 needs declaration ScalaDoc'])
        # A comment within an annotation is not the class's public contract.
        self.assertTrue(comment_issues('@Flag(/** Argument. */ 1) class Missing {}')[1])

    def test_only_adjacent_real_scaladoc_documents_a_declaration(self):
        for prefix in ('/* Ordinary block. */', 'val text = "/** Fake. */"',
                       '/** Earlier declaration. */\nval intervening = 1'):
            with self.subTest(prefix=prefix):
                self.assertTrue(comment_issues(prefix + '\nclass Missing {}')[1])
        source = '/** Outer contract. */\nobject Outer { class Local {} }'
        self.assertEqual(comment_issues(source)[1], [])


if __name__ == '__main__': unittest.main()
