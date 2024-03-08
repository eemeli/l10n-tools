# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections.abc import Callable
from re import fullmatch
from typing import Any

from fluent.syntax import ast as ftl
from fluent.syntax import serialize

from .. import message as msg
from .. import resource as res


def fluent_serialize(
    resource: res.Resource[msg.Message, res.M],
    serialize_metadata: Callable[[res.Metadata[res.M]], str | None] | None = None,
) -> str:
    """
    Serialize a resource as the contents of a Fluent FTL file.

    Section identifiers are not supported.
    Single-part message identifiers are treated as message values,
    while two-part message identifiers are considered message attributes.

    Function names are upper-cased, and annotations with the `message` function
    are mapped to message and term references.

    If the resource includes any metadata, a `serialize_metadata` callable must be provided
    to map each field into a comment value, or to discard it by returning an empty value.
    """
    ftl_ast = fluent_astify(resource, serialize_metadata)
    return serialize(ftl_ast)


def fluent_astify(
    resource: res.Resource[msg.Message, res.M],
    serialize_metadata: Callable[[res.Metadata[res.M]], str | None] | None = None,
) -> ftl.Resource:
    """
    Transform a resource into a corresponding Fluent AST structure.

    Section identifiers are not supported.
    Single-part message identifiers are treated as message values,
    while two-part message identifiers are considered message attributes.

    Function names are upper-cased, and annotations with the `message` function
    are mapped to message and term references.

    If the resource includes any metadata, a `serialize_metadata` callable must be provided
    to map each field into a comment value, or to discard it by returning an empty value.
    """

    def comment(
        node: (
            res.Resource[Any, Any]
            | res.Section[Any, Any]
            | res.Entry[Any, Any]
            | res.Comment
        )
    ) -> str:
        cs = node.comment.rstrip()
        if not isinstance(node, res.Comment) and node.meta:
            if not serialize_metadata:
                raise Exception("Metadata requires serialize_metadata parameter")
            for field in node.meta:
                meta_str = serialize_metadata(field)
                if meta_str:
                    ms = meta_str.strip("\n")
                    cs = f"{cs}\n{ms}" if cs else ms
        return cs

    body: list[ftl.EntryType] = []
    res_comment = comment(resource)
    if res_comment:
        body.append(ftl.ResourceComment(res_comment))
    for idx, section in enumerate(resource.sections):
        section_comment = comment(section)
        if idx != 0 or section_comment:
            body.append(ftl.GroupComment(section_comment))
        cur: ftl.Message | ftl.Term | None = None
        cur_id = ""
        for entry in section.entries:
            entry_comment = comment(entry)
            if isinstance(entry, res.Comment):
                body.append(ftl.Comment(entry_comment))
                cur = None
            elif len(entry.id) == 1:
                cur_id = entry.id[0]
                id = ftl.Identifier(cur_id)
                value = pattern(entry.value)
                cur = (
                    ftl.Term(id, value) if cur_id[0] == "-" else ftl.Message(id, value)
                )
                if entry_comment:
                    cur.comment = ftl.Comment(entry_comment)
                body.append(cur)
            elif len(entry.id) == 2:  # attribute
                if cur is None or entry.id[0] != cur_id:
                    cur_id = entry.id[0]
                    id = ftl.Identifier(cur_id)
                    if cur_id[0] == "-":
                        value = ftl.Pattern([ftl.Placeable(ftl.StringLiteral(""))])
                        cur = ftl.Term(id, value)
                    else:
                        cur = ftl.Message(id)
                    if entry_comment:
                        cur.comment = ftl.Comment(entry_comment)
                    body.append(cur)
                elif entry_comment:
                    attr_comment = f"{entry.id[1]}:\n{entry_comment}"
                    if cur.comment:
                        cur.comment.content = (
                            str(cur.comment.content) + "\n\n" + attr_comment
                        )
                    else:
                        cur.comment = ftl.Comment(attr_comment)
                cur.attributes.append(
                    ftl.Attribute(ftl.Identifier(entry.id[1]), pattern(entry.value))
                )
            else:
                raise Exception(f"Unsupported message id: {entry.id}")
    return ftl.Resource(body)


def pattern(message: msg.Message) -> ftl.Pattern:
    decl = [d for d in message.declarations if isinstance(d, msg.Declaration)]
    if len(decl) != len(message.declarations):
        raise ValueError("Unsupported statements are not supported")
    if isinstance(message, msg.PatternMessage):
        return flat_pattern(decl, message.pattern)

    # It gets a bit complicated for SelectMessage. We'll be modifying this list,
    # building select expressions for each selector starting from the last one
    # until this list has only one entry `[[], pattern]`.
    #
    # We rely on the variants being in order, so that a variant with N keys
    # will be next to all other variants for which the first N-1 keys are equal.
    variants = [
        (list(keys), flat_pattern(decl, value))
        for keys, value in message.variants.items()
    ]

    other = fallback_name(message.variants)
    keys0 = variants[0][0]
    while keys0:
        selector = expression(decl, message.selectors[len(keys0) - 1])
        base_keys = []
        sel_exp = None
        i = 0
        while i < len(variants):
            keys, pattern = variants[i]
            key = keys.pop()  # Ultimately modifies keys0
            ftl_variant = ftl.Variant(
                variant_key(key, other), pattern, isinstance(key, msg.CatchallKey)
            )
            if sel_exp and keys == base_keys:
                sel_exp.variants.append(ftl_variant)
                variants.pop(i)
            else:
                base_keys = keys
                sel_exp = ftl.SelectExpression(selector.clone(), [ftl_variant])
                variants[i] = (keys, ftl.Pattern([ftl.Placeable(sel_exp)]))
                i += 1
    if len(variants) != 1:
        raise ValueError(f"Error resolving select message variants (n={len(variants)})")
    return variants[0][1]


def fallback_name(variants: msg.Variants) -> str:
    """
    Try `other`, `other1`, `other2`, ... until a free one is found.
    """
    i = 0
    key = root = "other"
    while any(
        key == (k.value if isinstance(k, msg.CatchallKey) else k)
        for keys in variants
        for k in keys
    ):
        i += 1
        key = f"{root}{i}"
    return key


def variant_key(
    key: str | msg.CatchallKey, other: str
) -> ftl.NumberLiteral | ftl.Identifier:
    kv = key.value or other if isinstance(key, msg.CatchallKey) else key
    try:
        float(kv)
        return ftl.NumberLiteral(kv)
    except Exception:
        if fullmatch(r"[a-zA-Z][\w-]*", kv):
            return ftl.Identifier(kv)
        raise ValueError(f"Unsupported variant key: {kv}")


def flat_pattern(decl: list[msg.Declaration], pattern: msg.Pattern) -> ftl.Pattern:
    elements: list[ftl.TextElement | ftl.Placeable] = []
    for el in pattern:
        if isinstance(el, str):
            elements.append(ftl.TextElement(el))
        elif isinstance(el, msg.Expression):
            elements.append(ftl.Placeable(expression(decl, el)))
        else:
            raise ValueError(f"Conversion to Fluent not supported: {el}")
    return ftl.Pattern(elements)


def expression(
    decl: list[msg.Declaration], expr: msg.Expression
) -> ftl.InlineExpression:
    arg = value(decl, expr.arg) if expr.arg is not None else None
    if isinstance(expr.annotation, msg.FunctionAnnotation):
        return function_ref(decl, arg, expr.annotation)
    elif expr.annotation:
        raise ValueError("Unsupported annotations are not supported")
    if arg:
        return arg
    raise ValueError("Invalid empty expression")


def function_ref(
    decl: list[msg.Declaration],
    arg: ftl.InlineExpression | None,
    annotation: msg.FunctionAnnotation,
) -> ftl.InlineExpression:
    named: list[ftl.NamedArgument] = []
    for name, val in annotation.options.items():
        ftl_val = value(decl, val)
        if isinstance(ftl_val, ftl.Literal):
            named.append(ftl.NamedArgument(ftl.Identifier(name), ftl_val))
        else:
            raise ValueError(f"Fluent option value not literal for {name}: {ftl_val}")

    if annotation.name == "string":
        if not arg:
            raise ValueError("Argument required for :string")
        if named:
            raise ValueError("Options on :string are not supported")
        return arg
    if annotation.name == "number" and isinstance(arg, ftl.NumberLiteral) and not named:
        return arg
    if annotation.name == "message":
        if not isinstance(arg, ftl.Literal):
            raise ValueError(
                "Message and term references must have a literal message identifier"
            )
        match = fullmatch(r"(-?[a-zA-Z][\w-]*)(?:\.([a-zA-Z][\w-]*))?", arg.value)
        if not match:
            raise ValueError(f"Invalid message or term identifier: {arg.value}")
        msg_id = match[1]
        msg_attr = match[2]
        attr = ftl.Identifier(msg_attr) if msg_attr else None
        if msg_id[0] == "-":
            args = ftl.CallArguments(named=named) if named else None
            return ftl.TermReference(ftl.Identifier(msg_id[1:]), attr, args)
        elif named:
            raise ValueError("Options on message references are not supported")
        else:
            return ftl.MessageReference(ftl.Identifier(msg_id), attr)

    args = ftl.CallArguments([arg] if arg else None, named)
    return ftl.FunctionReference(ftl.Identifier(annotation.name.upper()), args)


def value(
    decl: list[msg.Declaration], val: str | msg.VariableRef
) -> ftl.InlineExpression:
    if isinstance(val, str):
        try:
            float(val)
            return ftl.NumberLiteral(val)
        except Exception:
            return ftl.StringLiteral(val)
    else:
        local = next((d for d in decl if d.name == val.name), None)
        return (
            expression(decl, local.value)
            if local
            else ftl.VariableReference(ftl.Identifier(val.name))
        )
