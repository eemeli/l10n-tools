# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import annotations

import re

from .android import AndroidParser
from .base import (
    CAN_COPY,
    CAN_MERGE,
    CAN_NONE,
    CAN_SKIP,
    BadEntity,
    Comment,
    Entity,
    Entry,
    Junk,
    OffsetComment,
    Parser,
    Whitespace,
)
from .defines import DefinesInstruction, DefinesParser
from .dtd import DTDEntity, DTDParser
from .fluent import FluentComment, FluentEntity, FluentMessage, FluentParser, FluentTerm
from .ini import IniParser, IniSection
from .po import PoParser
from .properties import PropertiesEntity, PropertiesParser

__all__ = [
    "CAN_NONE",
    "CAN_COPY",
    "CAN_SKIP",
    "CAN_MERGE",
    "Junk",
    "Entry",
    "Entity",
    "Whitespace",
    "Comment",
    "OffsetComment",
    "BadEntity",
    "Parser",
    "AndroidParser",
    "DefinesParser",
    "DefinesInstruction",
    "DTDParser",
    "DTDEntity",
    "FluentParser",
    "FluentComment",
    "FluentEntity",
    "FluentMessage",
    "FluentTerm",
    "IniParser",
    "IniSection",
    "PoParser",
    "PropertiesParser",
    "PropertiesEntity",
]


__constructors = [
    ("strings.*\\.xml$", AndroidParser()),
    ("\\.dtd$", DTDParser()),
    ("\\.properties$", PropertiesParser()),
    ("\\.ini$", IniParser()),
    ("\\.inc$", DefinesParser()),
    ("\\.ftl$", FluentParser()),
    ("\\.pot?$", PoParser()),
]


def getParser(path: str) -> Parser:
    for item in __constructors:
        if re.search(item[0], path):
            return item[1]
    raise UserWarning("Cannot find Parser")


def hasParser(path: str) -> bool:
    try:
        return bool(getParser(path))
    except UserWarning:
        return False
