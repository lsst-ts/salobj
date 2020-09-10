# This file is part of ts_salobj.
#
# Developed for the LSST Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = [
    "IdlMetadata",
    "TopicMetadata",
    "FieldMetadata",
    "parse_idl",
    "parse_nonsal_idl",
]

import re


class IdlMetadata:
    """Information about SAL topics in an IDL file.

    Parameters
    ----------
    name : `str`
        SAL component name, e.g. "ATPtg".
    idl_path : `pathlib.Path`
        Path to IDL file.
    sal_version : `str` or `None`
        Version of ts_sal used to generate the IDL file,
        or `None` if not found.
    xml_version : `str`
        Version of ts_xml used to generate the IDL file,
        or `None` if not found.
    topic_info : `dict` [`str`: `TopicMetadata`]
        Dict of SAL topic name: topic metadata.
    """

    def __init__(self, name, idl_path, sal_version, xml_version, topic_info):
        self.name = name
        self.idl_path = idl_path
        self.sal_version = sal_version
        self.xml_version = xml_version
        self.topic_info = topic_info

    def __repr__(self):
        return (
            f"IdlMetadata(idl_path={self.idl_path}, "
            f"sal_version={repr(self.sal_version)}, "
            f"xml_version={repr(self.xml_version)})"
        )


class TopicMetadata:
    """Metadata about a topic.

    Parameters
    ----------
    sal_name : `str`
        SAL topic name, e.g. `logevent_summaryState`.
    version_hash : `str`
        Version has code.
    description : `str` or `None`
        Topic description, or `None` if unknown.

    Attributes
    ----------
    field_info : `dict` [`str`, `FieldMetadata`]
        Dict of field name: field metadata.
    """

    def __init__(self, sal_name, version_hash, description):
        self.sal_name = sal_name
        self.version_hash = version_hash
        self.description = description
        self.field_info = dict()

    def __repr__(self):
        return f"TopicMetadata(sal_name={repr(self.sal_name)}, description={self.description})"


class FieldMetadata:
    """Information about a field.

    Parameters
    ----------
    name : `str`
        Field name.
    description : `str` or `None`
        Description; `None` if not specified.
    units : `str` or `None`
        Units; `None` if not specified.
    type_name : `str`
        Data type name from the IDL file, e.g.
        "string<8>", "float", "double".
        This may not match the Python data type of the field.
        For instance dds maps most integer types to `int`,
        and both "float" and "double" to `double`.
    array_length : `int`
        Number of elements if an array; None if not an array.
    str_length : `int`
        Maximum allowed string length; None if unspecified (no limit)
        or not a string.
    """

    def __init__(self, name, description, units, type_name, array_length, str_length):
        self.name = name
        self.description = description
        self.units = units
        self.type_name = type_name
        self.array_length = array_length
        self.str_length = str_length

    def __repr__(self):
        return (
            f"FieldMetadata(name={repr(self.name)}, "
            f"description={repr(self.description)}, "
            f"units={repr(self.units)}, "
            f"type_name={repr(self.type_name)},"
            f"array_length={self.array_length}"
            f"str_length={self.str_length})"
        )

    def __str__(self):
        return f"description={repr(self.description)}, units={repr(self.units)}"


def parse_idl(name, idl_path):
    """Parse the SAL-generated IDL file.

    Parameters
    ----------
    name : str`
        SAL component name, e.g. "ATPtg".
    idl_path : `str`, `bytes`, or `pathlib.Path`
        Path to IDL file

    Returns
    -------
    metadata : `IdlMetadata`
        Parsed metadata.
    """
    # List of field types used in IDL, excluding "unsigned".
    type_names = (
        "string",
        "boolean",
        "float",
        "double",
        "octet",
        "short",
        "int",
        "long",
        "long long",
    )
    type_names_str = "|".join(type_names)

    sal_version_pattern = re.compile(
        r"//\sSAL_VERSION=(?P<sal_version>\S+) XML_VERSION=(?P<xml_version>\S+)"
    )
    topic_start_pattern = re.compile(
        r"\s*struct\s+(?P<sal_topic_name>.+)_(?P<version_hash>[a-zA-Z0-9]+) +{"
        r'\s*(?:// @Metadata=\((?:Description="(?P<description>.*)")?\))?'
    )
    topic_end_pattern = re.compile(r"\s};")
    field_pattern = re.compile(
        fr"\s*(?P<type_name>(?:unsigned )?(?:{type_names_str}))(?:<(?P<str_length>\d+)>)?"
        r"\s+(?P<field_name>[a-zA-Z][a-zA-Z0-9_-]*)(?:\[(?P<array_length>\d+)\])?;"
        r"\s*(?://\s*private)?"
        r'\s*(?:// @Metadata=\((?:Units="(?P<units>[^"]*)"),?'
        r'\s*(?:Description="(?P<description>.*)")?\))?'
    )

    # dict of sal_topic_name: `TopicMetadata`
    topic_info = dict()

    # Set topic_metadata to a `TopicMetadata` when parsing data for a topic
    # and None when not.
    topic_metadata = None
    isfirst = True
    sal_version = None
    xml_version = None
    with open(idl_path, "r") as f:
        for line in f:
            # The first line should contain version information
            # encoded as a comment.
            if isfirst:
                isfirst = False
                version_match = sal_version_pattern.match(line)
                if version_match:
                    sal_version = version_match.group("sal_version")
                    xml_version = version_match.group("xml_version")
                    continue

            if topic_metadata is None:
                # Look for the start of a new topic.
                topic_match = topic_start_pattern.match(line)
                if not topic_match:
                    continue

                sal_topic_name = topic_match.group("sal_topic_name")
                if sal_topic_name in topic_info:
                    raise RuntimeError(
                        f"Already parsed data for topic {sal_topic_name}"
                    )
                version_hash = topic_match.group("version_hash")
                topic_description = topic_match.group("description")
                topic_metadata = TopicMetadata(
                    sal_name=sal_topic_name,
                    version_hash=version_hash,
                    description=topic_description,
                )
                topic_info[sal_topic_name] = topic_metadata
            else:
                # Look for the next field or the end of this topic.
                field_match = field_pattern.match(line)
                if field_match:
                    field_name = field_match.group("field_name")
                    array_length = field_match.group("array_length")
                    if array_length is not None:
                        array_length = int(array_length)
                    str_length = field_match.group("str_length")
                    if str_length is not None:
                        str_length = int(str_length)
                    topic_metadata.field_info[field_name] = FieldMetadata(
                        name=field_name,
                        type_name=field_match.group("type_name"),
                        description=field_match.group("description"),
                        units=field_match.group("units"),
                        array_length=array_length,
                        str_length=str_length,
                    )
                elif topic_end_pattern.match(line):
                    topic_metadata = None

    # Note: the field types are too complicated to be described
    # by a FieldMetadata object, so leave that blank.

    return IdlMetadata(
        name=name,
        idl_path=idl_path,
        sal_version=sal_version,
        xml_version=xml_version,
        topic_info=topic_info,
    )


def parse_nonsal_idl(name, idl_path):
    """Parse a non-SAL idl file.

    This has only been tested on the OpenSplice DDS IDL file,
    but can be expanded to handle other non-SAL cases.

    Parameters
    ----------
    name : str`
        SAL component name, e.g. "ATPtg".
    idl_path : `str`, `bytes`, or `pathlib.Path`
        Path to IDL file

    Returns
    -------
    metadata : `IdlMetadata`
        Parsed metadata.
    """
    # List of field types used in IDL, excluding "unsigned".
    topic_start_pattern = re.compile(
        r"\s*#pragma\s+keylist\s+(?P<sal_topic_name>.+)\s+key"
    )

    # dict of sal_topic_name: `TopicMetadata`
    topic_info = dict()

    with open(idl_path, "r") as f:
        for line in f:
            # Look for the start of a new topic.
            topic_match = topic_start_pattern.match(line)
            if not topic_match:
                continue

            sal_topic_name = topic_match.group("sal_topic_name")
            if sal_topic_name in topic_info:
                raise RuntimeError(f"Already parsed data for topic {sal_topic_name}")
            topic_metadata = TopicMetadata(
                sal_name=sal_topic_name, version_hash="", description=None,
            )
            topic_info[sal_topic_name] = topic_metadata

    return IdlMetadata(
        name=name,
        idl_path=idl_path,
        sal_version=None,
        xml_version=None,
        topic_info=topic_info,
    )
