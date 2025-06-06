# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import logging
import stat
from io import SEEK_END, SEEK_SET, UnsupportedOperation
from os import fstat
from typing import Dict, Optional

import isodate


_LOGGER = logging.getLogger(__name__)

_REQUEST_DELIMITER_PREFIX = "batch_"
_HTTP1_1_IDENTIFIER = "HTTP/1.1"
_HTTP_LINE_ENDING = "\r\n"


def serialize_iso(attr):
    """Serialize Datetime object into ISO-8601 formatted string.

    :param Datetime attr: Object to be serialized.
    :rtype: str
    :raises: ValueError if format invalid.
    """
    if not attr:
        return None
    if isinstance(attr, str):
        attr = isodate.parse_datetime(attr)
    try:
        utc = attr.utctimetuple()
        if utc.tm_year > 9999 or utc.tm_year < 1:
            raise OverflowError("Hit max or min date")

        date = f"{utc.tm_year:04}-{utc.tm_mon:02}-{utc.tm_mday:02}T{utc.tm_hour:02}:{utc.tm_min:02}:{utc.tm_sec:02}"
        return date + "Z"
    except (ValueError, OverflowError) as err:
        raise ValueError("Unable to serialize datetime object.") from err
    except AttributeError as err:
        raise TypeError("ISO-8601 object must be valid datetime object.") from err


def get_length(data):
    length = None
    # Check if object implements the __len__ method, covers most input cases such as bytearray.
    try:
        length = len(data)
    except:  # pylint: disable=bare-except
        pass

    if not length:
        # Check if the stream is a file-like stream object.
        # If so, calculate the size using the file descriptor.
        try:
            fileno = data.fileno()
        except (AttributeError, UnsupportedOperation):
            pass
        else:
            try:
                mode = fstat(fileno).st_mode
                if stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                    # st_size only meaningful if regular file or symlink, other types
                    # e.g. sockets may return misleading sizes like 0
                    return fstat(fileno).st_size
            except OSError:
                # Not a valid fileno, may be possible requests returned
                # a socket number?
                pass

        # If the stream is seekable and tell() is implemented, calculate the stream size.
        try:
            current_position = data.tell()
            data.seek(0, SEEK_END)
            length = data.tell() - current_position
            data.seek(current_position, SEEK_SET)
        except (AttributeError, OSError, UnsupportedOperation):
            pass

    return length


def read_length(data):
    try:
        if hasattr(data, "read"):
            read_data = b""
            for chunk in iter(lambda: data.read(4096), b""):
                read_data += chunk
            return len(read_data), read_data
        if hasattr(data, "__iter__"):
            read_data = b""
            for chunk in data:
                read_data += chunk
            return len(read_data), read_data
    except:  # pylint: disable=bare-except
        pass
    raise ValueError("Unable to calculate content length, please specify.")


def validate_and_format_range_headers(
    start_range,
    end_range,
    start_range_required=True,
    end_range_required=True,
    check_content_md5=False,
    align_to_page=False,
):
    # If end range is provided, start range must be provided
    if (start_range_required or end_range is not None) and start_range is None:
        raise ValueError("start_range value cannot be None.")
    if end_range_required and end_range is None:
        raise ValueError("end_range value cannot be None.")

    # Page ranges must be 512 aligned
    if align_to_page:
        if start_range is not None and start_range % 512 != 0:
            raise ValueError(
                f"Invalid page blob start_range: {start_range}. " "The size must be aligned to a 512-byte boundary."
            )
        if end_range is not None and end_range % 512 != 511:
            raise ValueError(
                f"Invalid page blob end_range: {end_range}. " "The size must be aligned to a 512-byte boundary."
            )

    # Format based on whether end_range is present
    range_header = None
    if end_range is not None:
        range_header = f"bytes={start_range}-{end_range}"
    elif start_range is not None:
        range_header = f"bytes={start_range}-"

    # Content MD5 can only be provided for a complete range less than 4MB in size
    range_validation = None
    if check_content_md5:
        if start_range is None or end_range is None:
            raise ValueError("Both start and end range required for MD5 content validation.")
        if end_range - start_range > 4 * 1024 * 1024:
            raise ValueError("Getting content MD5 for a range greater than 4MB is not supported.")
        range_validation = "true"

    return range_header, range_validation


def add_metadata_headers(metadata: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {}
    if metadata:
        for key, value in metadata.items():
            headers[f"x-ms-meta-{key.strip()}"] = value.strip() if value else value
    return headers


def serialize_batch_body(requests, batch_id):
    """
    --<delimiter>
    <subrequest>
    --<delimiter>
    <subrequest>    (repeated as needed)
    --<delimiter>--

    Serializes the requests in this batch to a single HTTP mixed/multipart body.

    :param List[~azure.core.pipeline.transport.HttpRequest] requests:
        a list of sub-request for the batch request
    :param str batch_id:
        to be embedded in batch sub-request delimiter
    :return: The body bytes for this batch.
    :rtype: bytes
    """

    if requests is None or len(requests) == 0:
        raise ValueError("Please provide sub-request(s) for this batch request")

    delimiter_bytes = (_get_batch_request_delimiter(batch_id, True, False) + _HTTP_LINE_ENDING).encode("utf-8")
    newline_bytes = _HTTP_LINE_ENDING.encode("utf-8")
    batch_body = []

    content_index = 0
    for request in requests:
        request.headers.update({"Content-ID": str(content_index), "Content-Length": str(0)})
        batch_body.append(delimiter_bytes)
        batch_body.append(_make_body_from_sub_request(request))
        batch_body.append(newline_bytes)
        content_index += 1

    batch_body.append(_get_batch_request_delimiter(batch_id, True, True).encode("utf-8"))
    # final line of body MUST have \r\n at the end, or it will not be properly read by the service
    batch_body.append(newline_bytes)

    return b"".join(batch_body)


def _get_batch_request_delimiter(batch_id, is_prepend_dashes=False, is_append_dashes=False):
    """
    Gets the delimiter used for this batch request's mixed/multipart HTTP format.

    :param str batch_id:
        Randomly generated id
    :param bool is_prepend_dashes:
        Whether to include the starting dashes. Used in the body, but non on defining the delimiter.
    :param bool is_append_dashes:
        Whether to include the ending dashes. Used in the body on the closing delimiter only.
    :return: The delimiter, WITHOUT a trailing newline.
    :rtype: str
    """

    prepend_dashes = "--" if is_prepend_dashes else ""
    append_dashes = "--" if is_append_dashes else ""

    return prepend_dashes + _REQUEST_DELIMITER_PREFIX + batch_id + append_dashes


def _make_body_from_sub_request(sub_request):
    """
    Content-Type: application/http
    Content-ID: <sequential int ID>
    Content-Transfer-Encoding: <value> (if present)

    <verb> <path><query> HTTP/<version>
    <header key>: <header value> (repeated as necessary)
    Content-Length: <value>
    (newline if content length > 0)
    <body> (if content length > 0)

    Serializes an http request.

    :param ~azure.core.pipeline.transport.HttpRequest sub_request:
       Request to serialize.
    :return: The serialized sub-request in bytes
    :rtype: bytes
    """

    # put the sub-request's headers into a list for efficient str concatenation
    sub_request_body = []

    # get headers for ease of manipulation; remove headers as they are used
    headers = sub_request.headers

    # append opening headers
    sub_request_body.append("Content-Type: application/http")
    sub_request_body.append(_HTTP_LINE_ENDING)

    sub_request_body.append("Content-ID: ")
    sub_request_body.append(headers.pop("Content-ID", ""))
    sub_request_body.append(_HTTP_LINE_ENDING)

    sub_request_body.append("Content-Transfer-Encoding: binary")
    sub_request_body.append(_HTTP_LINE_ENDING)

    # append blank line
    sub_request_body.append(_HTTP_LINE_ENDING)

    # append HTTP verb and path and query and HTTP version
    sub_request_body.append(sub_request.method)
    sub_request_body.append(" ")
    sub_request_body.append(sub_request.url)
    sub_request_body.append(" ")
    sub_request_body.append(_HTTP1_1_IDENTIFIER)
    sub_request_body.append(_HTTP_LINE_ENDING)

    # append remaining headers (this will set the Content-Length, as it was set on `sub-request`)
    for header_name, header_value in headers.items():
        if header_value is not None:
            sub_request_body.append(header_name)
            sub_request_body.append(": ")
            sub_request_body.append(header_value)
            sub_request_body.append(_HTTP_LINE_ENDING)

    # append blank line
    sub_request_body.append(_HTTP_LINE_ENDING)

    return "".join(sub_request_body).encode()
