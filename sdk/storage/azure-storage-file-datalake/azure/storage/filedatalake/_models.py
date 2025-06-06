# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
# pylint: disable=too-few-public-methods, too-many-instance-attributes, super-init-not-called, too-many-lines

from enum import Enum
from typing import (
    Any, Dict, List, Optional, Union,
    TYPE_CHECKING
)
from typing_extensions import Self

from azure.core import CaseInsensitiveEnumMeta
from azure.storage.blob import AccessPolicy as BlobAccessPolicy
from azure.storage.blob import AccountSasPermissions as BlobAccountSasPermissions
from azure.storage.blob import ArrowDialect as BlobArrowDialect
from azure.storage.blob import ContainerEncryptionScope as BlobContainerEncryptionScope
from azure.storage.blob import ContentSettings as BlobContentSettings
from azure.storage.blob import CustomerProvidedEncryptionKey as BlobCustomerProvidedEncryptionKey
from azure.storage.blob import DelimitedJsonDialect as BlobDelimitedJSON
from azure.storage.blob import DelimitedTextDialect as BlobDelimitedTextDialect
from azure.storage.blob import LeaseProperties as BlobLeaseProperties
from azure.storage.blob import ResourceTypes as BlobResourceTypes
from azure.storage.blob import UserDelegationKey as BlobUserDelegationKey
from azure.storage.blob._generated.models import (
    CorsRule as GenCorsRule,
    Logging as GenLogging,
    Metrics as GenMetrics,
    RetentionPolicy as GenRetentionPolicy,
    StaticWebsite as GenStaticWebsite
)
from azure.storage.blob._models import ContainerPropertiesPaged

from ._shared.models import DictMixin
from ._shared.parser import _filetime_to_datetime, _rfc_1123_to_datetime

if TYPE_CHECKING:
    from datetime import datetime


class RetentionPolicy(GenRetentionPolicy):
    """The retention policy which determines how long the associated data should persist.

    All required parameters must be populated in order to send to Azure.

    :param bool enabled:
        Indicates whether a retention policy is enabled for the storage service.
        The default value is False.
    :param Optional[int] days:
        Indicates the number of days that metrics or logging or soft-deleted data should be retained.
        All data older than this value will be deleted.
    """

    enabled: bool = False
    """Indicates whether a retention policy is enabled for the storage service."""
    days: Optional[int] = None
    """Indicates the number of days that metrics or logging or soft-deleted data should be retained.
        All data older than this value will be deleted."""

    def __init__(self, enabled: bool = False, days: Optional[int] = None) -> None:
        super(RetentionPolicy, self).__init__(enabled=enabled, days=days, allow_permanent_delete=None)
        if self.enabled and (self.days is None):
            raise ValueError("If policy is enabled, 'days' must be specified.")

    @classmethod
    def _from_generated(cls, generated):
        if not generated:
            return cls()
        return cls(
            enabled=generated.enabled,
            days=generated.days,
        )


class Metrics(GenMetrics):
    """A summary of request statistics grouped by API in hour or minute aggregates.

    All required parameters must be populated in order to send to Azure.

    :keyword str version:
        The version of Storage Analytics to configure. The default value is 1.0.
    :keyword bool enabled:
        Indicates whether metrics are enabled for the Datalake service.
        The default value is `False`.
    :keyword bool include_apis:
        Indicates whether metrics should generate summary statistics for called API operations.
    :keyword ~azure.storage.filedatalake.RetentionPolicy retention_policy:
        Determines how long the associated data should persist. If not specified the retention
        policy will be disabled by default.
    """

    version: str = '1.0'
    """The version of Storage Analytics to configure."""
    enabled: bool = False
    """Indicates whether metrics are enabled for the Datalake service."""
    include_apis: Optional[bool] = None
    """Indicates whether metrics should generate summary statistics for called API operations."""
    retention_policy: RetentionPolicy = RetentionPolicy()
    """Determines how long the associated data should persist."""

    def __init__(self, **kwargs: Any) -> None:
        self.version = kwargs.get('version', '1.0')
        self.enabled = kwargs.get('enabled', False)
        self.include_apis = kwargs.get('include_apis')
        self.retention_policy = kwargs.get('retention_policy') or RetentionPolicy()

    @classmethod
    def _from_generated(cls, generated):
        if not generated:
            return cls()
        return cls(
            version=generated.version,
            enabled=generated.enabled,
            include_apis=generated.include_apis,
            retention_policy=RetentionPolicy._from_generated(generated.retention_policy)  # pylint: disable=protected-access
        )


class CorsRule(GenCorsRule):
    """CORS is an HTTP feature that enables a web application running under one
    domain to access resources in another domain. Web browsers implement a
    security restriction known as same-origin policy that prevents a web page
    from calling APIs in a different domain; CORS provides a secure way to
    allow one domain (the origin domain) to call APIs in another domain.

    All required parameters must be populated in order to send to Azure.

    :param List[str] allowed_origins:
        A list of origin domains that will be allowed via CORS, or "*" to allow
        all domains. The list of must contain at least one entry. Limited to 64
        origin domains. Each allowed origin can have up to 256 characters.
    :param List[str] allowed_methods:
        A list of HTTP methods that are allowed to be executed by the origin.
        The list of must contain at least one entry. For Azure Storage,
        permitted methods are DELETE, GET, HEAD, MERGE, POST, OPTIONS or PUT.
    :keyword List[str] allowed_headers:
        Defaults to an empty list. A list of headers allowed to be part of
        the cross-origin request. Limited to 64 defined headers and 2 prefixed
        headers. Each header can be up to 256 characters.
    :keyword List[str] exposed_headers:
        Defaults to an empty list. A list of response headers to expose to CORS
        clients. Limited to 64 defined headers and two prefixed headers. Each
        header can be up to 256 characters.
    :keyword int max_age_in_seconds:
        The number of seconds that the client/browser should cache a
        preflight response.
    """

    allowed_origins: str
    """The comma-delimited string representation of the list of origin domains
        that will be allowed via CORS, or "*" to allow all domains."""
    allowed_methods: str
    """The comma-delimited string representation of the list of HTTP methods
        that are allowed to be executed by the origin."""
    allowed_headers: str
    """The comma-delimited string representation of the list of headers
        allowed to be a part of the cross-origin request."""
    exposed_headers: str
    """The comma-delimited string representation of the list of response
        headers to expose to CORS clients."""
    max_age_in_seconds: int
    """The number of seconds that the client/browser should cache a pre-flight response."""

    def __init__(self, allowed_origins: List[str], allowed_methods: List[str], **kwargs: Any) -> None:
        self.allowed_origins = ','.join(allowed_origins)
        self.allowed_methods = ','.join(allowed_methods)
        self.allowed_headers = ','.join(kwargs.get('allowed_headers', []))
        self.exposed_headers = ','.join(kwargs.get('exposed_headers', []))
        self.max_age_in_seconds = kwargs.get('max_age_in_seconds', 0)

    @staticmethod
    def _to_generated(rules: Optional[List["CorsRule"]]) -> Optional[List[GenCorsRule]]:
        if rules is None:
            return rules

        generated_cors_list = []
        for cors_rule in rules:
            generated_cors = GenCorsRule(
                allowed_origins=cors_rule.allowed_origins,
                allowed_methods=cors_rule.allowed_methods,
                allowed_headers=cors_rule.allowed_headers,
                exposed_headers=cors_rule.exposed_headers,
                max_age_in_seconds=cors_rule.max_age_in_seconds,
            )
            generated_cors_list.append(generated_cors)

        return generated_cors_list

    @classmethod
    def _from_generated(cls, generated):
        return cls(
            [generated.allowed_origins],
            [generated.allowed_methods],
            allowed_headers=[generated.allowed_headers],
            exposed_headers=[generated.exposed_headers],
            max_age_in_seconds=generated.max_age_in_seconds,
        )


class AccountSasPermissions(BlobAccountSasPermissions):
    """
    :class:`~ResourceTypes` class to be used with generate_account_sas
    function and for the AccessPolicies used with set_*_acl. There are two types of
    SAS which may be used to grant resource access. One is to grant access to a
    specific resource (resource-specific). Another is to grant access to the
    entire service for a specific account and allow certain operations based on
    perms found here.

    :param bool read:
        Valid for all signed resources types (Service, Container, and Object).
        Permits read permissions to the specified resource type.
    :param bool write:
        Valid for all signed resources types (Service, Container, and Object).
        Permits write permissions to the specified resource type.
    :param bool delete:
        Valid for Container and Object resource types, except for queue messages.
    :param bool list:
        Valid for Service and Container resource types only.
    :param bool create:
        Valid for the following Object resource types only: blobs and files.
        Users can create new blobs or files, but may not overwrite existing blobs or files.
    """

    def __init__(
        self, read: bool = False,
        write: bool = False,
        delete: bool = False,
        list: bool = False,  # pylint: disable=redefined-builtin
        create: bool = False
    ) -> None:
        super(AccountSasPermissions, self).__init__(
            read=read, create=create, write=write, list=list,
            delete=delete
        )


class FileSystemSasPermissions:
    """FileSystemSasPermissions class to be used with the
    :func:`~azure.storage.filedatalake.generate_file_system_sas` function.

    :param bool read:
        Read the content, properties, metadata etc.
    :param bool write:
        Create or write content, properties, metadata. Lease the file system.
    :param bool delete:
        Delete the file system.
    :param bool list:
        List paths in the file system.
    :keyword bool add:
        Append data to a file in the directory.
    :keyword bool create:
        Write a new file, snapshot a file, or copy a file to a new file.
    :keyword bool move:
        Move any file in the directory to a new location. Note the move operation can optionally be restricted to the
        child file or directory owner or the parent directory owner if the said parameter is included in the token
        and the sticky bit is set on the parent directory.
    :keyword bool execute:
        Get the status (system defined properties) and ACL of any file in the directory.
        If the caller is the owner, set access control on any file in the directory.
    :keyword bool manage_ownership:
        Allows the user to set owner, owning group, or act as the owner when renaming or deleting a file or directory
        within a folder that has the sticky bit set.
    :keyword bool manage_access_control:
         Allows the user to set permissions and POSIX ACLs on files and directories.
    """

    read: bool = False
    """Read the content, properties, metadata etc."""
    write: bool = False
    """Create or write content, properties, metadata. Lease the file system."""
    delete: bool = False
    """Delete the file system."""
    list: bool = False
    """List paths in the file system."""
    add: Optional[bool] = None
    """Append data to a file in the directory."""
    create: Optional[bool] = None
    """Write a new file, snapshot a file, or copy a file to a new file."""
    move: Optional[bool] = None
    """Move any file in the directory to a new location. Note the move operation can optionally be restricted to the
        child file or directory owner or the parent directory owner if the said parameter is included in the token
        and the sticky bit is set on the parent directory."""
    execute: Optional[bool] = None
    """Get the status (system defined properties) and ACL of any file in the directory.
        If the caller is the owner, set access control on any file in the directory."""
    manage_ownership: Optional[bool] = False
    """Allows the user to set owner, owning group, or act as the owner when renaming or deleting a file or directory
        within a folder that has the sticky bit set."""
    manage_access_control: Optional[bool] = False
    """Allows the user to set permissions and POSIX ACLs on files and directories."""

    def __init__(
        self, read: bool = False,
        write: bool = False,
        delete: bool = False,
        list: bool = False,  # pylint: disable=redefined-builtin
        **kwargs: Any
    ) -> None:
        self.read = read
        self.write = write
        self.delete = delete
        self.list = list
        self.add = kwargs.pop('add', None)
        self.create = kwargs.pop('create', None)
        self.move = kwargs.pop('move', None)
        self.execute = kwargs.pop('execute', None)
        self.manage_ownership = kwargs.pop('manage_ownership', None)
        self.manage_access_control = kwargs.pop('manage_access_control', None)
        self._str = (('r' if self.read else '') +
                     ('a' if self.add else '') +
                     ('c' if self.create else '') +
                     ('w' if self.write else '') +
                     ('d' if self.delete else '') +
                     ('l' if self.list else '') +
                     ('m' if self.move else '') +
                     ('e' if self.execute else '') +
                     ('o' if self.manage_ownership else '') +
                     ('p' if self.manage_access_control else ''))

    def __str__(self):
        return self._str

    @classmethod
    def from_string(cls, permission: str) -> Self:
        """Create a FileSystemSasPermissions from a string.

        To specify read, write, or delete permissions you need only to
        include the first letter of the word in the string. E.g. For read and
        write permissions, you would provide a string "rw".

        :param str permission: The string which dictates the read, add, create,
            write, or delete permissions.
        :return: A FileSystemSasPermissions object
        :rtype: ~azure.storage.filedatalake.FileSystemSasPermissions
        """
        p_read = 'r' in permission
        p_add = 'a' in permission
        p_create = 'c' in permission
        p_write = 'w' in permission
        p_delete = 'd' in permission
        p_list = 'l' in permission
        p_move = 'm' in permission
        p_execute = 'e' in permission
        p_manage_ownership = 'o' in permission
        p_manage_access_control = 'p' in permission

        parsed = cls(read=p_read, write=p_write, delete=p_delete,
                     list=p_list, add=p_add, create=p_create, move=p_move,
                     execute=p_execute, manage_ownership=p_manage_ownership,
                     manage_access_control=p_manage_access_control)
        return parsed


class DirectorySasPermissions:
    """DirectorySasPermissions class to be used with the
    :func:`~azure.storage.filedatalake.generate_directory_sas` function.

    :param bool read:
        Read the content, properties, metadata etc.
    :param bool create:
        Create a new directory.
    :param bool write:
        Create or write content, properties, metadata. Lease the directory.
    :param bool delete:
        Delete the directory.
    :keyword bool add:
        Append data to a file in the directory.
    :keyword bool list:
        List any files in the directory. Implies Execute.
    :keyword bool move:
        Move any file in the directory to a new location. Note the move operation can optionally be restricted to the
        child file or directory owner or the parent directory owner if the said parameter is included in the token
        and the sticky bit is set on the parent directory.
    :keyword bool execute:
        Get the status (system defined properties) and ACL of any file in the directory.
        If the caller is the owner, set access control on any file in the directory.
    :keyword bool manage_ownership:
        Allows the user to set owner, owning group, or act as the owner when renaming or deleting a file or directory
        within a folder that has the sticky bit set.
    :keyword bool manage_access_control:
         Allows the user to set permissions and POSIX ACLs on files and directories.
    """

    read: bool = False
    """Read the content, properties, metadata etc."""
    create: bool = False
    """Create a new directory."""
    write: bool = False
    """Create or write content, properties, metadata. Lease the directory."""
    delete: bool = False
    """Delete the directory."""
    add: Optional[bool] = False
    """Append data to a file in the directory."""
    list: Optional[bool] = False
    """List any files in the directory. Implies Execute."""
    move: Optional[bool] = False
    """Move any file in the directory to a new location. Note the move operation can optionally be restricted to the
        child file or directory owner or the parent directory owner if the said parameter is included in the token
        and the sticky bit is set on the parent directory."""
    execute: Optional[bool] = False
    """Get the status (system defined properties) and ACL of any file in the directory.
        If the caller is the owner, set access control on any file in the directory."""
    manage_ownership: Optional[bool] = False
    """Allows the user to set owner, owning group, or act as the owner when renaming or deleting a file or directory
        within a folder that has the sticky bit set."""
    manage_access_control: Optional[bool] = False
    """Allows the user to set permissions and POSIX ACLs on files and directories."""

    def __init__(
        self, read: bool = False,
        create: bool = False,
        write: bool = False,
        delete: bool = False,
        **kwargs: Any
    ) -> None:
        self.read = read
        self.create = create
        self.write = write
        self.delete = delete
        self.add = kwargs.pop('add', None)
        self.list = kwargs.pop('list', None)
        self.move = kwargs.pop('move', None)
        self.execute = kwargs.pop('execute', None)
        self.manage_ownership = kwargs.pop('manage_ownership', None)
        self.manage_access_control = kwargs.pop('manage_access_control', None)
        self._str = (('r' if self.read else '') +
                     ('a' if self.add else '') +
                     ('c' if self.create else '') +
                     ('w' if self.write else '') +
                     ('d' if self.delete else '') +
                     ('l' if self.list else '') +
                     ('m' if self.move else '') +
                     ('e' if self.execute else '') +
                     ('o' if self.manage_ownership else '') +
                     ('p' if self.manage_access_control else ''))

    def __str__(self):
        return self._str

    @classmethod
    def from_string(cls, permission: str) -> Self:
        """Create a DirectorySasPermissions from a string.

        To specify read, create, write, or delete permissions you need only to
        include the first letter of the word in the string. E.g. For read and
        write permissions, you would provide a string "rw".

        :param str permission: The string which dictates the read, add, create,
            write, or delete permissions.
        :return: A DirectorySasPermissions object
        :rtype: ~azure.storage.filedatalake.DirectorySasPermissions
        """
        p_read = 'r' in permission
        p_add = 'a' in permission
        p_create = 'c' in permission
        p_write = 'w' in permission
        p_delete = 'd' in permission
        p_list = 'l' in permission
        p_move = 'm' in permission
        p_execute = 'e' in permission
        p_manage_ownership = 'o' in permission
        p_manage_access_control = 'p' in permission

        parsed = cls(read=p_read, create=p_create, write=p_write, delete=p_delete, add=p_add,
                     list=p_list, move=p_move, execute=p_execute, manage_ownership=p_manage_ownership,
                     manage_access_control=p_manage_access_control)
        return parsed


class FileSasPermissions:
    """FileSasPermissions class to be used with the
    :func:`~azure.storage.filedatalake.generate_file_sas` function.

    :param bool read:
        Read the content, properties, metadata etc. Use the file as the source of a read operation.
    :param bool create:
        Write a new file.
    :param bool write:
        Create or write content, properties, metadata. Lease the file.
    :param bool delete:
        Delete the file.
    :keyword bool add:
        Append data to the file.
    :keyword bool move:
        Move any file in the directory to a new location. Note the move operation can optionally be restricted to the
        child file or directory owner or the parent directory owner if the said parameter is included in the token
        and the sticky bit is set on the parent directory.
    :keyword bool execute:
        Get the status (system defined properties) and ACL of any file in the directory.
        If the caller is the owner, set access control on any file in the directory.
    :keyword bool manage_ownership:
        Allows the user to set owner, owning group, or act as the owner when renaming or deleting a file or directory
        within a folder that has the sticky bit set.
    :keyword bool manage_access_control:
         Allows the user to set permissions and POSIX ACLs on files and directories.
    """

    read: bool = False
    """Read the content, properties, metadata etc. Use the file as the source of a read operation."""
    create: bool = False
    """Write a new file."""
    write: bool = False
    """Create or write content, properties, metadata. Lease the file."""
    delete: bool = False
    """Delete the file."""
    add: Optional[bool] = None
    """Append data to the file."""
    move: Optional[bool] = None
    """Move any file in the directory to a new location. Note the move operation can optionally be restricted to the
        child file or directory owner or the parent directory owner if the said parameter is included in the token
        and the sticky bit is set on the parent directory."""
    execute: Optional[bool] = None
    """Get the status (system defined properties) and ACL of any file in the directory.
        If the caller is the owner, set access control on any file in the directory."""
    manage_ownership: Optional[bool] = None
    """Allows the user to set owner, owning group, or act as the owner when renaming or deleting a file or directory
        within a folder that has the sticky bit set."""
    manage_access_control: Optional[bool] = None
    """Allows the user to set permissions and POSIX ACLs on files and directories."""

    def __init__(
        self, read: bool = False,
        create: bool = False,
        write: bool = False,
        delete: bool = False,
        **kwargs: Any
    ) -> None:
        self.read = read
        self.create = create
        self.write = write
        self.delete = delete
        self.add = kwargs.pop('add', None)
        self.move = kwargs.pop('move', None)
        self.execute = kwargs.pop('execute', None)
        self.manage_ownership = kwargs.pop('manage_ownership', None)
        self.manage_access_control = kwargs.pop('manage_access_control', None)
        self._str = (('r' if self.read else '') +
                     ('a' if self.add else '') +
                     ('c' if self.create else '') +
                     ('w' if self.write else '') +
                     ('d' if self.delete else '') +
                     ('m' if self.move else '') +
                     ('e' if self.execute else '') +
                     ('o' if self.manage_ownership else '') +
                     ('p' if self.manage_access_control else ''))

    def __str__(self):
        return self._str

    @classmethod
    def from_string(cls, permission: str) -> Self:
        """Create a FileSasPermissions from a string.

        To specify read, write, or delete permissions you need only to
        include the first letter of the word in the string. E.g. For read and
        write permissions, you would provide a string "rw".

        :param str permission: The string which dictates the read, add, create,
            write, or delete permissions.
        :return: A FileSasPermissions object
        :rtype: ~azure.storage.filedatalake.FileSasPermissions
        """
        p_read = 'r' in permission
        p_add = 'a' in permission
        p_create = 'c' in permission
        p_write = 'w' in permission
        p_delete = 'd' in permission
        p_move = 'm' in permission
        p_execute = 'e' in permission
        p_manage_ownership = 'o' in permission
        p_manage_access_control = 'p' in permission

        parsed = cls(read=p_read, create=p_create, write=p_write, delete=p_delete, add=p_add,
                     move=p_move, execute=p_execute, manage_ownership=p_manage_ownership,
                     manage_access_control=p_manage_access_control)
        return parsed


class AccessPolicy(BlobAccessPolicy):
    """Access Policy class used by the set and get access policy methods in each service.

    A stored access policy can specify the start time, expiry time, and
    permissions for the Shared Access Signatures with which it's associated.
    Depending on how you want to control access to your resource, you can
    specify all of these parameters within the stored access policy, and omit
    them from the URL for the Shared Access Signature. Doing so permits you to
    modify the associated signature's behavior at any time, as well as to revoke
    it. Or you can specify one or more of the access policy parameters within
    the stored access policy, and the others on the URL. Finally, you can
    specify all of the parameters on the URL. In this case, you can use the
    stored access policy to revoke the signature, but not to modify its behavior.

    Together the Shared Access Signature and the stored access policy must
    include all fields required to authenticate the signature. If any required
    fields are missing, the request will fail. Likewise, if a field is specified
    both in the Shared Access Signature URL and in the stored access policy, the
    request will fail with status code 400 (Bad Request).

    :param permission:
        The permissions associated with the shared access signature. The
        user is restricted to operations allowed by the permissions.
        Required unless an id is given referencing a stored access policy
        which contains this field. This field must be omitted if it has been
        specified in an associated stored access policy.
    :type permission: ~azure.storage.datalake.FileSystemSasPermissions or str
    :param expiry:
        The time at which the shared access signature becomes invalid.
        Required unless an id is given referencing a stored access policy
        which contains this field. This field must be omitted if it has
        been specified in an associated stored access policy. Azure will always
        convert values to UTC. If a date is passed in without timezone info, it
        is assumed to be UTC.
    :type expiry: ~datetime.datetime or str
    :keyword start:
        The time at which the shared access signature becomes valid. If
        omitted, start time for this call is assumed to be the time when the
        storage service receives the request. The provided datetime will always
        be interpreted as UTC.
    :paramtype start: ~datetime.datetime or str
    """

    def __init__(
        self, permission: Optional[Union[FileSystemSasPermissions, str]] = None,
        expiry: Optional[Union["datetime", str]] = None,
        **kwargs: Any
    ) -> None:
        super(AccessPolicy, self).__init__(
            permission=permission, expiry=expiry, start=kwargs.pop('start', None)  # type: ignore [arg-type]
        )


class LeaseProperties(BlobLeaseProperties):
    """DataLake Lease Properties."""


class EncryptionScopeOptions(BlobContainerEncryptionScope):
    """The default encryption scope configuration for a file system.

    This scope is used implicitly for all future writes within the file system,
    but can be overridden per blob operation.

    .. versionadded:: 12.9.0

    :param str default_encryption_scope:
        Specifies the default encryption scope to set on the file system and use for
        all future writes.
    :param bool prevent_encryption_scope_override:
        If true, prevents any request from specifying a different encryption scope than the scope
        set on the file system. Default value is false.
    """


class ContentSettings(BlobContentSettings):
    """The content settings of a file or directory.

    :keyword str content_type:
        The content type specified for the file or directory. If no content type was
        specified, the default content type is application/octet-stream.
    :keyword str content_encoding:
        If the content_encoding has previously been set for the file, that value is stored.
    :keyword str content_language:
        If the content_language has previously been set for the file, that value is stored.
    :keyword str content_disposition:
        content_disposition conveys additional information about how to process the response payload,
        and also can be  used to attach additional metadata. If content_disposition has previously
        been set for the file, that value is stored.
    :keyword str cache_control:
        If the cache_control has previously been set for the file, that value is stored.
    :keyword bytearray content_md5:
        If the content_md5 has been set for the file, this response header is stored so that the
        client can check for message content integrity.
    """

    def __init__(self, **kwargs: Any) -> None:
        super(ContentSettings, self).__init__(**kwargs)


class FileSystemProperties(DictMixin):
    """File System properties class.

    Returned ``FileSystemProperties`` instances expose these values through a
    dictionary interface, for example: ``file_system_props["last_modified"]``.
    Additionally, the file system name is available as ``file_system_props["name"]``.
    """

    name: str
    """Name of the filesystem."""
    last_modified: "datetime"
    """A datetime object representing the last time the file system was modified."""
    etag: str
    """The ETag contains a value that you can use to perform operations conditionally."""
    lease: LeaseProperties
    """Stores all the lease information for the file system."""
    public_access: Optional[str] = None
    """Specifies whether data in the file system may be accessed publicly and the level of access."""
    has_immutability_policy: bool
    """Represents whether the file system has an immutability policy."""
    has_legal_hold: bool
    """Represents whether the file system has a legal hold."""
    metadata: Dict[str, str]
    """A dict with name-value pairs to associate with the file system as metadata."""
    deleted: Optional[bool] = None
    """Whether this file system was deleted."""
    deleted_version: Optional[str] = None
    """The version of a deleted file system."""
    encryption_scope: EncryptionScopeOptions
    """The default encryption scope configuration for the file system."""

    def __init__(self, **kwargs: Any) -> None:
        self.name = None  # type: ignore [assignment]
        self.last_modified = None  # type: ignore [assignment]
        self.etag = None  # type: ignore [assignment]
        self.lease = None  # type: ignore [assignment]
        self.public_access = None
        self.has_immutability_policy = None  # type: ignore [assignment]
        self.has_legal_hold = None  # type: ignore [assignment]
        self.metadata = None  # type: ignore [assignment]
        self.deleted = None
        self.deleted_version = None
        default_encryption_scope = kwargs.get('x-ms-default-encryption-scope')
        if default_encryption_scope:
            self.encryption_scope = EncryptionScopeOptions(
                default_encryption_scope=default_encryption_scope,
                prevent_encryption_scope_override=kwargs.get('x-ms-deny-encryption-scope-override', False)
            )

    @classmethod
    def _from_generated(cls, generated):
        props = cls()
        props.name = generated.name
        props.last_modified = generated.properties.last_modified
        props.deleted = generated.deleted
        props.deleted_version = generated.version
        props.etag = generated.properties.etag
        props.lease = LeaseProperties._from_generated(generated)  # pylint: disable=protected-access
        props.public_access = PublicAccess._from_generated(  # pylint: disable=protected-access
            generated.properties.public_access)
        props.has_immutability_policy = generated.properties.has_immutability_policy
        props.has_legal_hold = generated.properties.has_legal_hold
        props.metadata = generated.metadata
        props.encryption_scope = EncryptionScopeOptions._from_generated(generated)  # pylint: disable=protected-access
        return props

    @classmethod
    def _convert_from_container_props(cls, container_properties):
        container_properties.__class__ = cls
        container_properties.public_access = PublicAccess._from_generated(  # pylint: disable=protected-access
            container_properties.public_access)
        container_properties.lease.__class__ = LeaseProperties
        return container_properties


class FileSystemPropertiesPaged(ContainerPropertiesPaged):
    """An Iterable of File System properties.

    :param command: Function to retrieve the next page of items.
    :type command: ~typing.Callable[]
    :param str prefix: Filters the results to return only file systems whose names
        begin with the specified prefix.
    :param int results_per_page: The maximum number of file system names to retrieve per call.
    :param str continuation_token: An opaque continuation token.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(FileSystemPropertiesPaged, self).__init__(*args, **kwargs)

    @staticmethod
    def _build_item(item):
        return FileSystemProperties._from_generated(item)  # pylint: disable=protected-access


class DirectoryProperties(DictMixin):
    """Directory properties class."""

    name: str
    """The name of the directory."""
    etag: str
    """The ETag contains a value that you can use to perform operations conditionally."""
    deleted: bool
    """Whether the currently directory is mark as deleted."""
    metadata: Dict[str, str]
    """Name-value pairs associated with the directory as metadata."""
    lease: LeaseProperties
    """Stores all the lease information for the directory."""
    last_modified: "datetime"
    """A datetime object representing the last time the directory was modified."""
    creation_time: "datetime"
    """A datetime object representing when the directory was created, in UTC."""
    deleted_time: Optional["datetime"] = None
    """A datetime object representing when the directory was deleted, in UTC."""
    remaining_retention_days: Optional[int] = None
    """The number of days that the directory will be retained before being permanently deleted by the service."""
    encryption_scope: Optional[str] = None
    """A predefined encryption scope used to encrypt the data on the service. An encryption
        scope can be created using the Management API and referenced here by name. If a default
        encryption scope has been defined at the file system, this value will override it if the
        file system level scope is configured to allow overrides. Otherwise an error will be raised."""
    owner: Optional[str] = None
    """The owner of the file or directory."""
    group: Optional[str] = None
    """The owning group of the file or directory."""
    permissions: Optional[str] = None
    """The permissions that are set for user, group, and other on the file or directory.
        Each individual permission is in [r,w,x,-]{3} format."""
    acl: Optional[str] = None
    """The POSIX ACL permissions of the file or directory."""

    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs.get('name')  # type: ignore [assignment]
        self.etag = kwargs.get('ETag')  # type: ignore [assignment]
        self.deleted = False
        self.metadata = kwargs.get('metadata')  # type: ignore [assignment]
        self.lease = LeaseProperties(**kwargs)
        self.last_modified = kwargs.get('Last-Modified')  # type: ignore [assignment]
        self.creation_time = kwargs.get('x-ms-creation-time')  # type: ignore [assignment]
        self.deleted_time = None
        self.remaining_retention_days = None
        self.encryption_scope = kwargs.get('x-ms-encryption-scope')

        # This is being passed directly not coming from headers
        self.owner = kwargs.get('owner', None)
        self.group = kwargs.get('group', None)
        self.permissions = kwargs.get('permissions', None)
        self.acl = kwargs.get('acl', None)


class FileProperties(DictMixin):
    """File properties class."""

    name: str
    """The name of the file."""
    etag: str
    """The ETag contains a value that you can use to perform operations conditionally."""
    deleted: Optional[bool]
    """Whether the currently file is mark as deleted."""
    metadata: Dict[str, str]
    """Name-value pairs associated with the file as metadata."""
    lease: LeaseProperties
    """Stores all the lease information for the file."""
    last_modified: "datetime"
    """A datetime object representing the last time the file was modified."""
    creation_time: "datetime"
    """A datetime object representing when the file was created, in UTC."""
    size: int
    """The size of the file."""
    deleted_time: Optional["datetime"] = None
    """A datetime object representing when the file was deleted, in UTC."""
    expiry_time: Optional["datetime"] = None
    """A datetime object representing when the file's immutability policy is set to expire."""
    remaining_retention_days: Optional[int] = None
    """The number of days that the file will be retained before being permanently deleted by the service."""
    content_settings: ContentSettings
    """Stores all the content settings for the file."""
    encryption_scope: Optional[str] = None
    """A predefined encryption scope used to encrypt the data on the service. An encryption
        scope can be created using the Management API and referenced here by name. If a default
        encryption scope has been defined at the file system, this value will override it if the
        file system level scope is configured to allow overrides. Otherwise an error will be raised."""
    encryption_context: Optional[str] = None
    """Specifies the encryption context to set on the file."""
    owner: Optional[str] = None
    """The owner of the file or directory."""
    group: Optional[str] = None
    """The owning group of the file or directory."""
    permissions: Optional[str] = None
    """The permissions that are set for user, group, and other on the file or directory.
        Each individual permission is in [r,w,x,-]{3} format."""
    acl: Optional[str] = None
    """The POSIX ACL permissions of the file or directory."""

    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs.get('name')  # type: ignore [assignment]
        self.etag = kwargs.get('ETag')  # type: ignore [assignment]
        self.deleted = False
        self.metadata = kwargs.get('metadata')  # type: ignore [assignment]
        self.lease = LeaseProperties(**kwargs)
        self.last_modified = kwargs.get('Last-Modified')  # type: ignore [assignment]
        self.creation_time = kwargs.get('x-ms-creation-time')  # type: ignore [assignment]
        self.size = kwargs.get('Content-Length')  # type: ignore [assignment]
        self.deleted_time = None
        self.expiry_time = kwargs.get("x-ms-expiry-time")
        self.remaining_retention_days = None
        self.content_settings = ContentSettings(**kwargs)
        self.encryption_scope = kwargs.get('x-ms-encryption-scope')

        # This is being passed directly not coming from headers
        self.encryption_context = kwargs.get('encryption_context')
        self.owner = kwargs.get('owner', None)
        self.group = kwargs.get('group', None)
        self.permissions = kwargs.get('permissions', None)
        self.acl = kwargs.get('acl', None)


class PathProperties(DictMixin):
    """Path properties listed by get_paths api.

    :ivar str encryption_scope:
        A predefined encryption scope used to encrypt the data on the service. An encryption
        scope can be created using the Management API and referenced here by name. If a default
        encryption scope has been defined at the file system, this value will override it if the
        file system level scope is configured to allow overrides. Otherwise an error will be raised.
    :ivar str encryption_context: Specifies the encryption context to set on the file.
    """

    name: str
    """The full path for a file or directory."""
    owner: str
    """The owner of the file or directory."""
    group: str
    """The owning group of the file or directory."""
    permissions: str
    """The permissions that are set for user, group, and other on the file or directory.
        Each individual permission is in [r,w,x,-]{3} format."""
    last_modified: "datetime"
    """A datetime object representing the last time the directory/file was modified."""
    is_directory: bool
    """Whether the path a directory."""
    etag: str
    """The ETag contains a value that you can use to perform operations conditionally."""
    content_length: int
    """The size of file if the path is a file."""
    creation_time: "datetime"
    """The creation time of the file/directory."""
    expiry_time: Optional["datetime"] = None
    """The expiry time of the file/directory."""
    encryption_scope: Optional[str] = None
    """A predefined encryption scope used to encrypt the data on the service. An encryption
        scope can be created using the Management API and referenced here by name. If a default
        encryption scope has been defined at the file system, this value will override it if the
        file system level scope is configured to allow overrides. Otherwise an error will be raised."""
    encryption_context: Optional[str] = None
    """Specifies the encryption context to set on the file."""

    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs.pop('name', None)  # type: ignore [assignment]
        self.owner = kwargs.get('owner', None)  # type: ignore [assignment]
        self.group = kwargs.get('group', None)  # type: ignore [assignment]
        self.permissions = kwargs.get('permissions', None)  # type: ignore [assignment]
        self.last_modified = kwargs.get('last_modified', None)  # type: ignore [assignment]
        self.is_directory = kwargs.get('is_directory', False)  # type: ignore [assignment]
        self.etag = kwargs.get('etag', None)  # type: ignore [assignment]
        self.content_length = kwargs.get('content_length', None)  # type: ignore [assignment]
        self.creation_time = kwargs.get('creation_time', None)  # type: ignore [assignment]
        self.expiry_time = kwargs.get('expiry_time', None)
        self.encryption_scope = kwargs.get('x-ms-encryption-scope', None)
        self.encryption_context = kwargs.get('x-ms-encryption-context', None)

    @classmethod
    def _from_generated(cls, generated):
        path_prop = PathProperties()
        path_prop.name = generated.name
        path_prop.owner = generated.owner
        path_prop.group = generated.group
        path_prop.permissions = generated.permissions
        path_prop.last_modified = _rfc_1123_to_datetime(generated.last_modified)
        path_prop.is_directory = bool(generated.is_directory)
        path_prop.etag = generated.additional_properties.get('etag')
        path_prop.content_length = generated.content_length
        path_prop.creation_time = _filetime_to_datetime(generated.creation_time)
        path_prop.expiry_time = _filetime_to_datetime(generated.expiry_time)
        path_prop.encryption_scope = generated.encryption_scope
        path_prop.encryption_context = generated.encryption_context
        return path_prop


class ResourceTypes(BlobResourceTypes):
    """
    Specifies the resource types that are accessible with the account SAS.

    :param bool service:
        Access to service-level APIs (e.g.List File Systems).
    :param bool file_system:
        Access to file_system-level APIs (e.g., Create/Delete file system, List Directories/Files).
    :param bool object:
        Access to object-level APIs for files(e.g. Create File, etc.).
    """

    def __init__(
        self, service: bool = False,
        file_system: bool = False,
        object: bool = False  # pylint: disable=redefined-builtin
    ) -> None:
        super(ResourceTypes, self).__init__(service=service, container=file_system, object=object)


class UserDelegationKey(BlobUserDelegationKey):
    """
    Represents a user delegation key, provided to the user by Azure Storage
    based on their Azure Active Directory access token.

    The fields are saved as simple strings since the user does not have to interact with this object;
    to generate an identify SAS, the user can simply pass it to the right API.
    """

    @classmethod
    def _from_generated(cls, generated):
        delegation_key = cls()
        delegation_key.signed_oid = generated.signed_oid
        delegation_key.signed_tid = generated.signed_tid
        delegation_key.signed_start = generated.signed_start
        delegation_key.signed_expiry = generated.signed_expiry
        delegation_key.signed_service = generated.signed_service
        delegation_key.signed_version = generated.signed_version
        delegation_key.value = generated.value
        return delegation_key


class PublicAccess(str, Enum, metaclass=CaseInsensitiveEnumMeta):
    """
    Specifies whether data in the file system may be accessed publicly and the level of access.
    """

    FILE = 'blob'
    """
    Specifies public read access for files. file data within this file system can be read
    via anonymous request, but file system data is not available. Clients cannot enumerate
    files within the container via anonymous request.
    """

    FILESYSTEM = 'container'
    """
    Specifies full public read access for file system and file data. Clients can enumerate
    files within the file system via anonymous request, but cannot enumerate file systems
    within the storage account.
    """

    @classmethod
    def _from_generated(cls, public_access):
        if public_access == "blob":  # pylint: disable=no-else-return
            return cls.File
        elif public_access == "container":
            return cls.FileSystem

        return None


class LocationMode:
    """
    Specifies the location the request should be sent to. This mode only applies
    for RA-GRS accounts which allow secondary read access. All other account types
    must use PRIMARY.
    """

    PRIMARY = 'primary'  #: Requests should be sent to the primary location.
    SECONDARY = 'secondary'  #: Requests should be sent to the secondary location, if possible.


class DelimitedJsonDialect(BlobDelimitedJSON):
    """Defines the input or output JSON serialization for a datalake query.

    :keyword str delimiter: The line separator character, default value is '\\\\n'.
    """


class DelimitedTextDialect(BlobDelimitedTextDialect):
    """Defines the input or output delimited (CSV) serialization for a datalake query request.

    :keyword str delimiter:
        Column separator, defaults to ','.
    :keyword str quotechar:
        Field quote, defaults to '"'.
    :keyword str lineterminator:
        Record separator, defaults to '\\\\n'.
    :keyword str escapechar:
        Escape char, defaults to empty.
    :keyword bool has_header:
        Whether the blob data includes headers in the first line. The default value is False, meaning that the
        data will be returned inclusive of the first line. If set to True, the data will be returned exclusive
        of the first line.
    """


class ArrowDialect(BlobArrowDialect):
    """field of an arrow schema.

    All required parameters must be populated in order to send to Azure.

    :param str type: Required.
    :keyword str name: The name of the field.
    :keyword int precision: The precision of the field.
    :keyword int scale: The scale of the field.
    """


class CustomerProvidedEncryptionKey(BlobCustomerProvidedEncryptionKey):
    """
    All data in Azure Storage is encrypted at-rest using an account-level encryption key.
    In versions 2021-06-08 and newer, you can manage the key used to encrypt file contents
    and application metadata per-file by providing an AES-256 encryption key in requests to the storage service.

    When you use a customer-provided key, Azure Storage does not manage or persist your key.
    When writing data to a file, the provided key is used to encrypt your data before writing it to disk.
    A SHA-256 hash of the encryption key is written alongside the file contents,
    and is used to verify that all subsequent operations against the file use the same encryption key.
    This hash cannot be used to retrieve the encryption key or decrypt the contents of the file.
    When reading a file, the provided key is used to decrypt your data after reading it from disk.
    In both cases, the provided encryption key is securely discarded
    as soon as the encryption or decryption process completes.

    :param str key_value:
        Base64-encoded AES-256 encryption key value.
    :param str key_hash:
        Base64-encoded SHA256 of the encryption key.
    """


class QuickQueryDialect(str, Enum, metaclass=CaseInsensitiveEnumMeta):
    """Specifies the quick query input/output dialect."""

    DELIMITEDTEXT = 'DelimitedTextDialect'
    DELIMITEDJSON = 'DelimitedJsonDialect'
    PARQUET = 'ParquetDialect'


class ArrowType(str, Enum, metaclass=CaseInsensitiveEnumMeta):

    INT64 = "int64"
    BOOL = "bool"
    TIMESTAMP_MS = "timestamp[ms]"
    STRING = "string"
    DOUBLE = "double"
    DECIMAL = 'decimal'


class DataLakeFileQueryError:
    """The error happened during quick query operation."""

    error: Optional[str] = None
    """The name of the error."""
    is_fatal: bool
    """If true, this error prevents further query processing. More result data may be returned,
        but there is no guarantee that all of the original data will be processed.
        If false, this error does not prevent further query processing."""
    description: Optional[str] = None
    """A description of the error."""
    position: Optional[int] = None
    """The blob offset at which the error occurred."""

    def __init__(
        self, error: Optional[str] = None,
        is_fatal: bool = False,
        description: Optional[str] = None,
        position: Optional[int] = None
    ) -> None:
        self.error = error
        self.is_fatal = is_fatal
        self.description = description
        self.position = position


class AccessControlChangeCounters(DictMixin):
    """AccessControlChangeCounters contains counts of operations that change Access Control Lists recursively."""

    directories_successful: int
    """Number of directories where Access Control List has been updated successfully."""
    files_successful: int
    """Number of files where Access Control List has been updated successfully."""
    failure_count: int
    """Number of paths where Access Control List update has failed."""

    def __init__(self, directories_successful: int, files_successful: int, failure_count: int) -> None:
        self.directories_successful = directories_successful
        self.files_successful = files_successful
        self.failure_count = failure_count


class AccessControlChangeResult(DictMixin):
    """AccessControlChangeResult contains result of operations that change Access Control Lists recursively."""

    counters: Optional[AccessControlChangeCounters] = None
    """Contains counts of paths changed from start of the operation."""
    continuation: Optional[str]
    """Continuation token. Value is present when operation is split into 
        multiple batches and can be used to resume progress."""

    def __init__(self, counters: Optional[AccessControlChangeCounters], continuation: Optional[str]) -> None:
        self.counters = counters
        self.continuation = continuation


class AccessControlChangeFailure(DictMixin):
    """Represents an entry that failed to update Access Control List."""

    name: str
    """Name of the entry."""
    is_directory: bool
    """Indicates whether the entry is a directory."""
    error_message: str
    """Indicates the reason why the entry failed to update."""

    def __init__(self, name: str, is_directory: bool, error_message: str) -> None:
        self.name = name
        self.is_directory = is_directory
        self.error_message = error_message


class AccessControlChanges(DictMixin):
    """
    AccessControlChanges contains batch and cumulative counts of operations
    that change Access Control Lists recursively.
    Additionally it exposes path entries that failed to update while these operations progress.
    """

    batch_counters: AccessControlChangeCounters
    """Contains counts of paths changed within single batch."""
    aggregate_counters: AccessControlChangeCounters
    """Contains counts of paths changed from start of the operation."""
    batch_failures: List[AccessControlChangeFailure]
    """List of path entries that failed to update Access Control List within single batch."""
    continuation: Optional[str]
    """An opaque continuation token that may be used to resume the operations in case of failures."""

    def __init__(
        self, batch_counters: AccessControlChangeCounters,
        aggregate_counters: AccessControlChangeCounters,
        batch_failures: List[AccessControlChangeFailure],
        continuation: Optional[str]
    ) -> None:
        self.batch_counters = batch_counters
        self.aggregate_counters = aggregate_counters
        self.batch_failures = batch_failures
        self.continuation = continuation


class DeletedPathProperties(DictMixin):
    """Properties populated for a deleted path."""

    name: str
    """The name of the file in the path."""
    deleted_time: Optional["datetime"]
    """A datetime object representing the time at which the path was deleted."""
    remaining_retention_days: Optional[int]
    """The number of days that the path will be retained before being permanently deleted by the service."""
    deletion_id: Optional[str]
    """The id associated with the deleted path."""
    file_system: Optional[str]
    """The filesystem associated with the deleted path."""

    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs.get('name')  # type: ignore [assignment]
        self.deleted_time = None
        self.remaining_retention_days = None
        self.deletion_id = None
        self.file_system = None


class AnalyticsLogging(GenLogging):
    """Azure Analytics Logging settings."""

    version: str
    """The version of Storage Analytics to configure. The default value is 1.0."""
    delete: bool
    """Indicates whether all delete requests should be logged. The default value is `False`."""
    read: bool
    """Indicates whether all read requests should be logged. The default value is `False`."""
    write: bool
    """Indicates whether all write requests should be logged. The default value is `False`."""
    retention_policy: RetentionPolicy = RetentionPolicy()
    """Determines how long the associated data should persist. If not specified the retention
        policy will be disabled by default."""

    def __init__(self, **kwargs: Any) -> None:
        self.version = kwargs.get('version', '1.0')
        self.delete = kwargs.get('delete', False)
        self.read = kwargs.get('read', False)
        self.write = kwargs.get('write', False)
        self.retention_policy = kwargs.get('retention_policy') or RetentionPolicy()

    @classmethod
    def _from_generated(cls, generated):
        if not generated:
            return cls()
        return cls(
            version=generated.version,
            delete=generated.delete,
            read=generated.read,
            write=generated.write,
            retention_policy=RetentionPolicy._from_generated(generated.retention_policy)  # pylint: disable=protected-access
        )


class StaticWebsite(GenStaticWebsite):
    """The properties that enable an account to host a static website.

    :keyword bool enabled:
        Indicates whether this account is hosting a static website.
        The default value is `False`.
    :keyword str index_document:
        The default name of the index page under each directory.
    :keyword str error_document404_path:
        The absolute path of the custom 404 page.
    :keyword str default_index_document_path:
        Absolute path of the default index page.
    """

    enabled: bool
    """Indicates whether this account is hosting a static website. The default value is `False`."""
    index_document: Optional[str]
    """The default name of the index page under each directory."""
    error_document404_path: Optional[str]
    """The absolute path of the custom 404 page."""
    default_index_document_path: Optional[str]
    """Absolute path of the default index page."""

    def __init__(self, **kwargs: Any) -> None:
        self.enabled = kwargs.get('enabled', False)
        if self.enabled:
            self.index_document = kwargs.get('index_document')
            self.error_document404_path = kwargs.get('error_document404_path')
            self.default_index_document_path = kwargs.get('default_index_document_path')
        else:
            self.index_document = None
            self.error_document404_path = None
            self.default_index_document_path = None

    @classmethod
    def _from_generated(cls, generated):
        if not generated:
            return cls()
        return cls(
            enabled=generated.enabled,
            index_document=generated.index_document,
            error_document404_path=generated.error_document404_path,
            default_index_document_path=generated.default_index_document_path
        )
