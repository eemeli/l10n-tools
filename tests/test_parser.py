# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import shutil
import tempfile
import textwrap
import unittest
from os.path import join

from l10n_parser import OffsetComment, Parser


class TestParserContext(unittest.TestCase):
    def test_linecol(self):
        "Should return 1-based line and column numbers."
        ctx = Parser.Context(
            """first line
second line
third line
"""
        )
        self.assertEqual(ctx.linecol(0), (1, 1))
        self.assertEqual(ctx.linecol(1), (1, 2))
        self.assertEqual(ctx.linecol(len("first line")), (1, len("first line") + 1))
        self.assertEqual(ctx.linecol(len("first line") + 1), (2, 1))
        self.assertEqual(ctx.linecol(len(ctx.contents)), (4, 1))

    def test_empty_parser(self):
        p = Parser()
        self.assertTupleEqual(tuple(p), tuple())


class TestOffsetComment(unittest.TestCase):
    def test_offset(self):
        ctx = Parser.Context(
            textwrap.dedent(
                """\
            #foo
            #bar
            # baz
            """
            )
        )  # noqa
        offset_comment = OffsetComment(ctx, (0, len(ctx.contents)))
        self.assertEqual(
            offset_comment.val,
            textwrap.dedent(
                """\
                foo
                bar
                 baz
            """
            ),
        )


class TestUniversalNewlines(unittest.TestCase):
    def setUp(self):
        """Create a parser for this test."""
        self.parser = Parser()
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        "tear down this test"
        del self.parser
        shutil.rmtree(self.dir)

    def test_universal_newlines(self):
        f = join(self.dir, "file")
        with open(f, "wb") as fh:
            fh.write(b"one\ntwo\rthree\r\n")
        self.parser.readFile(f)
        self.assertEqual(self.parser.ctx.contents, "one\ntwo\nthree\n")
