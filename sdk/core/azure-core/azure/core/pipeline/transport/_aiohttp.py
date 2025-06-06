# --------------------------------------------------------------------------
#
# Copyright (c) Microsoft Corporation. All rights reserved.
#
# The MIT License (MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the ""Software""), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
# --------------------------------------------------------------------------
from __future__ import annotations
import sys
from typing import (
    Any,
    Optional,
    AsyncIterator as AsyncIteratorType,
    TYPE_CHECKING,
    overload,
    cast,
    Union,
    Type,
    MutableMapping,
)
from types import TracebackType
from collections.abc import AsyncIterator

import logging
import asyncio  # pylint: disable=do-not-import-asyncio
import codecs
import aiohttp
import aiohttp.client_exceptions
from multidict import CIMultiDict

from azure.core.configuration import ConnectionConfiguration
from azure.core.exceptions import (
    ServiceRequestError,
    ServiceRequestTimeoutError,
    ServiceResponseError,
    ServiceResponseTimeoutError,
    IncompleteReadError,
)
from azure.core.pipeline import AsyncPipeline

from ._base import HttpRequest
from ._base_async import AsyncHttpTransport, AsyncHttpResponse, _ResponseStopIteration
from ...utils._pipeline_transport_rest_shared import (
    _aiohttp_body_helper,
    get_file_items,
)
from .._tools import is_rest as _is_rest
from .._tools_async import (
    handle_no_stream_rest_response as _handle_no_stream_rest_response,
)

if TYPE_CHECKING:
    from ...rest import (
        HttpRequest as RestHttpRequest,
        AsyncHttpResponse as RestAsyncHttpResponse,
    )
    from ...rest._aiohttp import RestAioHttpTransportResponse

# Matching requests, because why not?
CONTENT_CHUNK_SIZE = 10 * 1024
_LOGGER = logging.getLogger(__name__)

try:
    # ConnectionTimeoutError was only introduced in aiohttp 3.10 so we want to keep this
    # backwards compatible. If client is using aiohttp <3.10, the behaviour will safely
    # fall back to treating a TimeoutError as a ServiceResponseError (that wont be retried).
    from aiohttp.client_exceptions import ConnectionTimeoutError
except ImportError:

    class ConnectionTimeoutError(Exception): ...  # type: ignore[no-redef]


class AioHttpTransport(AsyncHttpTransport):
    """AioHttp HTTP sender implementation.

    Fully asynchronous implementation using the aiohttp library.

    :keyword session: The client session.
    :paramtype session: ~aiohttp.ClientSession
    :keyword bool session_owner: Session owner. Defaults True.
    :keyword bool use_env_settings: Uses proxy settings from environment. Defaults to True.

    .. admonition:: Example:

        .. literalinclude:: ../samples/test_example_async.py
            :start-after: [START aiohttp]
            :end-before: [END aiohttp]
            :language: python
            :dedent: 4
            :caption: Asynchronous transport with aiohttp.
    """

    def __init__(
        self,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        loop=None,
        session_owner: bool = True,
        **kwargs,
    ):
        if loop and sys.version_info >= (3, 10):
            raise ValueError("Starting with Python 3.10, asyncio doesn’t support loop as a parameter anymore")
        self._loop = loop
        self._session_owner = session_owner
        self.session = session
        if not self._session_owner and not self.session:
            raise ValueError("session_owner cannot be False if no session is provided")
        self.connection_config = ConnectionConfiguration(**kwargs)
        self._use_env_settings = kwargs.pop("use_env_settings", True)
        # See https://github.com/Azure/azure-sdk-for-python/issues/25640 to understand why we track this
        self._has_been_opened = False

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        await self.close()

    async def open(self):
        """Opens the connection."""
        if self._has_been_opened and not self.session:
            raise ValueError(
                "HTTP transport has already been closed. "
                "You may check if you're calling a function outside of the `async with` of your client creation, "
                "or if you called `await close()` on your client already."
            )
        if not self.session:
            if self._session_owner:
                jar = aiohttp.DummyCookieJar()
                clientsession_kwargs = {
                    "trust_env": self._use_env_settings,
                    "cookie_jar": jar,
                    "auto_decompress": False,
                }
                if self._loop is not None:
                    clientsession_kwargs["loop"] = self._loop
                self.session = aiohttp.ClientSession(**clientsession_kwargs)
            else:
                raise ValueError("session_owner cannot be False and no session is available")

        self._has_been_opened = True
        await self.session.__aenter__()

    async def close(self):
        """Closes the connection."""
        if self._session_owner and self.session:
            await self.session.close()
            self.session = None

    def _build_ssl_config(self, cert, verify):
        """Build the SSL configuration.

        :param tuple cert: Cert information
        :param bool verify: SSL verification or path to CA file or directory
        :rtype: bool or str or ssl.SSLContext
        :return: SSL Configuration
        """
        ssl_ctx = None

        if cert or verify not in (True, False):
            import ssl

            if verify not in (True, False):
                ssl_ctx = ssl.create_default_context(cafile=verify)
            else:
                ssl_ctx = ssl.create_default_context()
            if cert:
                ssl_ctx.load_cert_chain(*cert)
            return ssl_ctx
        return verify

    def _get_request_data(self, request):
        """Get the request data.

        :param request: The request object
        :type request: ~azure.core.pipeline.transport.HttpRequest or ~azure.core.rest.HttpRequest
        :rtype: bytes or ~aiohttp.FormData
        :return: The request data
        """
        if request.files:
            form_data = aiohttp.FormData(request.data or {})
            for form_file, data in get_file_items(request.files):
                content_type = data[2] if len(data) > 2 else None
                try:
                    form_data.add_field(form_file, data[1], filename=data[0], content_type=content_type)
                except IndexError as err:
                    raise ValueError("Invalid formdata formatting: {}".format(data)) from err
            return form_data
        return request.data

    @overload
    async def send(
        self,
        request: HttpRequest,
        *,
        stream: bool = False,
        proxies: Optional[MutableMapping[str, str]] = None,
        **config: Any,
    ) -> AsyncHttpResponse:
        """Send the request using this HTTP sender.

        Will pre-load the body into memory to be available with a sync method.
        Pass stream=True to avoid this behavior.

        :param request: The HttpRequest object
        :type request: ~azure.core.pipeline.transport.HttpRequest
        :return: The AsyncHttpResponse
        :rtype: ~azure.core.pipeline.transport.AsyncHttpResponse

        :keyword bool stream: Defaults to False.
        :keyword MutableMapping proxies: dict of proxy to used based on protocol. Proxy is a dict (protocol, url)
        """

    @overload
    async def send(
        self,
        request: RestHttpRequest,
        *,
        stream: bool = False,
        proxies: Optional[MutableMapping[str, str]] = None,
        **config: Any,
    ) -> RestAsyncHttpResponse:
        """Send the `azure.core.rest` request using this HTTP sender.

        Will pre-load the body into memory to be available with a sync method.
        Pass stream=True to avoid this behavior.

        :param request: The HttpRequest object
        :type request: ~azure.core.rest.HttpRequest
        :return: The AsyncHttpResponse
        :rtype: ~azure.core.rest.AsyncHttpResponse

        :keyword bool stream: Defaults to False.
        :keyword MutableMapping proxies: dict of proxy to used based on protocol. Proxy is a dict (protocol, url)
        """

    async def send(
        self,
        request: Union[HttpRequest, RestHttpRequest],
        *,
        stream: bool = False,
        proxies: Optional[MutableMapping[str, str]] = None,
        **config,
    ) -> Union[AsyncHttpResponse, RestAsyncHttpResponse]:
        """Send the request using this HTTP sender.

        Will pre-load the body into memory to be available with a sync method.
        Pass stream=True to avoid this behavior.

        :param request: The HttpRequest object
        :type request: ~azure.core.rest.HttpRequest
        :return: The AsyncHttpResponse
        :rtype: ~azure.core.rest.AsyncHttpResponse

        :keyword bool stream: Defaults to False.
        :keyword MutableMapping proxies: dict of proxy to used based on protocol. Proxy is a dict (protocol, url)
        """
        await self.open()
        try:
            auto_decompress = self.session.auto_decompress  # type: ignore
        except AttributeError:
            # auto_decompress is introduced in aiohttp 3.7. We need this to handle aiohttp 3.6-.
            auto_decompress = False

        proxy = config.pop("proxy", None)
        if proxies and not proxy:
            # aiohttp needs a single proxy, so iterating until we found the right protocol

            # Sort by longest string first, so "http" is not used for "https" ;-)
            for protocol in sorted(proxies.keys(), reverse=True):
                if request.url.startswith(protocol):
                    proxy = proxies[protocol]
                    break

        response: Optional[Union[AsyncHttpResponse, RestAsyncHttpResponse]] = None
        ssl = self._build_ssl_config(
            cert=config.pop("connection_cert", self.connection_config.cert),
            verify=config.pop("connection_verify", self.connection_config.verify),
        )
        # If ssl=True, we just use default ssl context from aiohttp
        if ssl is not True:
            config["ssl"] = ssl
        # If we know for sure there is not body, disable "auto content type"
        # Otherwise, aiohttp will send "application/octet-stream" even for empty POST request
        # and that break services like storage signature
        if not request.data and not request.files:
            config["skip_auto_headers"] = ["Content-Type"]
        try:
            stream_response = stream
            timeout = config.pop("connection_timeout", self.connection_config.timeout)
            read_timeout = config.pop("read_timeout", self.connection_config.read_timeout)
            socket_timeout = aiohttp.ClientTimeout(sock_connect=timeout, sock_read=read_timeout)
            result = await self.session.request(  # type: ignore
                request.method,
                request.url,
                headers=request.headers,
                data=self._get_request_data(request),
                timeout=socket_timeout,
                allow_redirects=False,
                proxy=proxy,
                **config,
            )
            if _is_rest(request):
                from azure.core.rest._aiohttp import RestAioHttpTransportResponse

                response = RestAioHttpTransportResponse(
                    request=request,
                    internal_response=result,
                    block_size=self.connection_config.data_block_size,
                    decompress=not auto_decompress,
                )
                if not stream_response:
                    await _handle_no_stream_rest_response(response)
            else:
                # Given the associated "if", this else is legacy implementation
                # but mypy do not know it, so using a cast
                request = cast(HttpRequest, request)
                response = AioHttpTransportResponse(
                    request,
                    result,
                    self.connection_config.data_block_size,
                    decompress=not auto_decompress,
                )
                if not stream_response:
                    await response.load_body()
        except AttributeError as err:
            if self.session is None:
                raise ValueError(
                    "No session available for request. "
                    "Please report this issue to https://github.com/Azure/azure-sdk-for-python/issues."
                ) from err
            raise
        except aiohttp.client_exceptions.ClientResponseError as err:
            raise ServiceResponseError(err, error=err) from err
        except ConnectionTimeoutError as err:
            raise ServiceRequestTimeoutError(err, error=err) from err
        except asyncio.TimeoutError as err:
            raise ServiceResponseTimeoutError(err, error=err) from err
        except aiohttp.client_exceptions.ClientError as err:
            raise ServiceRequestError(err, error=err) from err
        return response


class AioHttpStreamDownloadGenerator(AsyncIterator):
    """Streams the response body data.

    :param pipeline: The pipeline object
    :type pipeline: ~azure.core.pipeline.AsyncPipeline
    :param response: The client response object.
    :type response: ~azure.core.rest.AsyncHttpResponse
    :keyword bool decompress: If True which is default, will attempt to decode the body based
        on the *content-encoding* header.
    """

    @overload
    def __init__(
        self,
        pipeline: AsyncPipeline[HttpRequest, AsyncHttpResponse],
        response: AioHttpTransportResponse,
        *,
        decompress: bool = True,
    ) -> None: ...

    @overload
    def __init__(
        self,
        pipeline: AsyncPipeline[RestHttpRequest, RestAsyncHttpResponse],
        response: RestAioHttpTransportResponse,
        *,
        decompress: bool = True,
    ) -> None: ...

    def __init__(
        self,
        pipeline: AsyncPipeline,
        response: Union[AioHttpTransportResponse, RestAioHttpTransportResponse],
        *,
        decompress: bool = True,
    ) -> None:
        self.pipeline = pipeline
        self.request = response.request
        self.response = response
        self.block_size = response.block_size
        self._decompress = decompress
        internal_response = response.internal_response
        self.content_length = int(internal_response.headers.get("Content-Length", 0))
        self._decompressor = None

    def __len__(self):
        return self.content_length

    async def __anext__(self):
        internal_response = self.response.internal_response
        try:
            chunk = await internal_response.content.read(self.block_size)
            if not chunk:
                raise _ResponseStopIteration()
            if not self._decompress:
                return chunk
            enc = internal_response.headers.get("Content-Encoding")
            if not enc:
                return chunk
            enc = enc.lower()
            if enc in ("gzip", "deflate"):
                if not self._decompressor:
                    import zlib

                    zlib_mode = (16 + zlib.MAX_WBITS) if enc == "gzip" else -zlib.MAX_WBITS
                    self._decompressor = zlib.decompressobj(wbits=zlib_mode)
                chunk = self._decompressor.decompress(chunk)
            return chunk
        except _ResponseStopIteration:
            internal_response.close()
            raise StopAsyncIteration()  # pylint: disable=raise-missing-from
        except aiohttp.client_exceptions.ClientPayloadError as err:
            # This is the case that server closes connection before we finish the reading. aiohttp library
            # raises ClientPayloadError.
            _LOGGER.warning("Incomplete download.")
            internal_response.close()
            raise IncompleteReadError(err, error=err) from err
        except aiohttp.client_exceptions.ClientResponseError as err:
            raise ServiceResponseError(err, error=err) from err
        except asyncio.TimeoutError as err:
            raise ServiceResponseError(err, error=err) from err
        except aiohttp.client_exceptions.ClientError as err:
            raise ServiceRequestError(err, error=err) from err
        except Exception as err:
            _LOGGER.warning("Unable to stream download.")
            internal_response.close()
            raise


class AioHttpTransportResponse(AsyncHttpResponse):
    """Methods for accessing response body data.

    :param request: The HttpRequest object
    :type request: ~azure.core.pipeline.transport.HttpRequest
    :param aiohttp_response: Returned from ClientSession.request().
    :type aiohttp_response: aiohttp.ClientResponse object
    :param block_size: block size of data sent over connection.
    :type block_size: int
    :keyword bool decompress: If True which is default, will attempt to decode the body based
            on the *content-encoding* header.
    """

    def __init__(
        self,
        request: HttpRequest,
        aiohttp_response: aiohttp.ClientResponse,
        block_size: Optional[int] = None,
        *,
        decompress: bool = True,
    ) -> None:
        super(AioHttpTransportResponse, self).__init__(request, aiohttp_response, block_size=block_size)
        # https://aiohttp.readthedocs.io/en/stable/client_reference.html#aiohttp.ClientResponse
        self.status_code = aiohttp_response.status
        self.headers = CIMultiDict(aiohttp_response.headers)
        self.reason = aiohttp_response.reason
        self.content_type = aiohttp_response.headers.get("content-type")
        self._content = None
        self._decompressed_content = False
        self._decompress = decompress

    def body(self) -> bytes:
        """Return the whole body as bytes in memory.

        :rtype: bytes
        :return: The whole response body.
        """
        return _aiohttp_body_helper(self)

    def text(self, encoding: Optional[str] = None) -> str:
        """Return the whole body as a string.

        If encoding is not provided, rely on aiohttp auto-detection.

        :param str encoding: The encoding to apply.
        :rtype: str
        :return: The whole response body as a string.
        """
        # super().text detects charset based on self._content() which is compressed
        # implement the decoding explicitly here
        body = self.body()

        ctype = self.headers.get(aiohttp.hdrs.CONTENT_TYPE, "").lower()
        mimetype = aiohttp.helpers.parse_mimetype(ctype)

        if not encoding:
            # extract encoding from mimetype, if caller does not specify
            encoding = mimetype.parameters.get("charset")
        if encoding:
            try:
                codecs.lookup(encoding)
            except LookupError:
                encoding = None
        if not encoding:
            if mimetype.type == "application" and mimetype.subtype in ["json", "rdap"]:
                # RFC 7159 states that the default encoding is UTF-8.
                # RFC 7483 defines application/rdap+json
                encoding = "utf-8"
            elif body is None:
                raise RuntimeError("Cannot guess the encoding of a not yet read body")
            else:
                try:
                    import cchardet as chardet
                except ImportError:  # pragma: no cover
                    try:
                        import chardet  # type: ignore
                    except ImportError:  # pragma: no cover
                        import charset_normalizer as chardet  # type: ignore[no-redef]
                # While "detect" can return a dict of float, in this context this won't happen
                # The cast is for pyright to be happy
                encoding = cast(Optional[str], chardet.detect(body)["encoding"])
        if encoding == "utf-8" or encoding is None:
            encoding = "utf-8-sig"

        return body.decode(encoding)

    async def load_body(self) -> None:
        """Load in memory the body, so it could be accessible from sync methods."""
        try:
            self._content = await self.internal_response.read()
        except aiohttp.client_exceptions.ClientPayloadError as err:
            # This is the case that server closes connection before we finish the reading. aiohttp library
            # raises ClientPayloadError.
            raise IncompleteReadError(err, error=err) from err
        except aiohttp.client_exceptions.ClientResponseError as err:
            raise ServiceResponseError(err, error=err) from err
        except asyncio.TimeoutError as err:
            raise ServiceResponseError(err, error=err) from err
        except aiohttp.client_exceptions.ClientError as err:
            raise ServiceRequestError(err, error=err) from err

    def stream_download(
        self,
        pipeline: AsyncPipeline[HttpRequest, AsyncHttpResponse],
        *,
        decompress: bool = True,
        **kwargs,
    ) -> AsyncIteratorType[bytes]:
        """Generator for streaming response body data.

        :param pipeline: The pipeline object
        :type pipeline: azure.core.pipeline.AsyncPipeline
        :keyword bool decompress: If True which is default, will attempt to decode the body based
            on the *content-encoding* header.
        :rtype: AsyncIterator[bytes]
        :return: An iterator of bytes chunks.
        """
        return AioHttpStreamDownloadGenerator(pipeline, self, decompress=decompress, **kwargs)

    def __getstate__(self):
        # Be sure body is loaded in memory, otherwise not pickable and let it throw
        self.body()

        state = self.__dict__.copy()
        # Remove the unpicklable entries.
        state["internal_response"] = None  # aiohttp response are not pickable (see headers comments)
        state["headers"] = CIMultiDict(self.headers)  # MultiDictProxy is not pickable
        return state
