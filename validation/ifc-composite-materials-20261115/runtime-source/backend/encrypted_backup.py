"""Versioned streaming AES-256-GCM envelope around the validated cold backup.

Fixed scrypt work factor, random salt/nonce, authenticated header, full 128-bit tag.
Plaintext is only consumed after finalize() authenticates it, inside private staging.
"""
import hashlib
import os
import re
import struct
from contextlib import contextmanager

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import backup, core
from .private_storage import private_open, private_temporary, verify_private
from .runtime_lock import safe_path

MAGIC = b'VRAENC02'
HEADER = struct.Struct('>8s16s12sQ')
TAG_BYTES = 16
CHUNK = 1024*1024
MAX_PLAIN = backup.MAX_BYTES + backup.MAX_MANIFEST + 10*1024**2


def _password(value):
    if not isinstance(value, bytes) or not 16 <= len(value) <= 1024 or any(c in value for c in (b'\x00',b'\r',b'\n')):
        raise ValueError('Backup passphrase must be 16–1024 UTF-8 bytes without NUL/newlines')
    return value


def _key(password, salt):
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(_password(password))


def encrypt_file(source, destination, password):
    """Internal envelope operation; caller must validate the inner backup first."""
    source,destination=safe_path(source),safe_path(destination)
    _password(password)
    with source.open('rb') as plain:
        length=os.fstat(plain.fileno()).st_size
        if not 0 < length <= MAX_PLAIN:
            raise ValueError('Plain backup exceeds encryption size budget')
        salt,nonce=os.urandom(16),os.urandom(12)
        header=HEADER.pack(MAGIC,salt,nonce,length)
        encryptor=Cipher(algorithms.AES(_key(password,salt)),modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(header)
        consumed=0
        with private_open(destination) as output:
            output.write(header)
            while chunk:=plain.read(CHUNK):
                consumed+=len(chunk)
                if consumed>length:raise ValueError('Plain backup changed during encryption')
                output.write(encryptor.update(chunk))
            if consumed!=length:raise ValueError('Plain backup changed during encryption')
            output.write(encryptor.finalize())
            output.write(encryptor.tag)
            output.flush();os.fsync(output.fileno())
    return {'encrypted':True,'format':'vra-encrypted-backup-2','cipher':'AES-256-GCM','kdf':'scrypt-N131072-r8-p1',
            'archive_sha256':core.sha(destination),'ciphertext_bytes':destination.stat().st_size,
            'storage_protection':verify_private(destination)}


@contextmanager
def decrypted_archive(archive, password, expected_sha256, staging_parent):
    archive=safe_path(archive);_password(password)
    if not isinstance(expected_sha256,str) or not re.fullmatch('[a-f0-9]{64}',expected_sha256):
        raise ValueError('A previously recorded encrypted archive SHA-256 is required')
    with archive.open('rb') as encrypted:
        size=os.fstat(encrypted.fileno()).st_size
        if not HEADER.size+TAG_BYTES<size<=HEADER.size+MAX_PLAIN+TAG_BYTES:
            raise ValueError('Encrypted backup size invalid')
        if hashlib.file_digest(encrypted,'sha256').hexdigest()!=expected_sha256:
            raise ValueError('Encrypted backup hash mismatch')
        encrypted.seek(0);header=encrypted.read(HEADER.size)
        magic,salt,nonce,length=HEADER.unpack(header)
        if magic!=MAGIC or not 0<length<=MAX_PLAIN or size!=HEADER.size+length+TAG_BYTES:
            raise ValueError('Unsupported/truncated encrypted backup; plaintext requires explicit legacy mode')
        encrypted.seek(-TAG_BYTES,os.SEEK_END);tag=encrypted.read(TAG_BYTES)
        encrypted.seek(HEADER.size)
        decryptor=Cipher(algorithms.AES(_key(password,salt)),modes.GCM(nonce,tag,min_tag_length=TAG_BYTES)).decryptor()
        decryptor.authenticate_additional_data(header)
        with private_temporary(staging_parent) as directory:
            plain=directory/'authenticated-backup.zip'
            with private_open(plain) as output:
                remaining=length
                while remaining:
                    chunk=encrypted.read(min(CHUNK,remaining))
                    if not chunk:raise ValueError('Truncated encrypted backup')
                    remaining-=len(chunk);output.write(decryptor.update(chunk))
                try:output.write(decryptor.finalize())
                except InvalidTag:
                    raise ValueError('Backup authentication failed: incorrect passphrase or altered data') from None
                output.flush();os.fsync(output.fileno())
            encrypted.seek(0)
            if hashlib.file_digest(encrypted,'sha256').hexdigest()!=expected_sha256:
                raise ValueError('Encrypted backup changed during verification')
            # No ZIP/database parsing or destination directory before full GCM authentication.
            yield plain,core.sha(plain)


def create_encrypted(source, archive, password):
    source,archive=safe_path(source),safe_path(archive)
    _password(password)
    if archive.exists() or archive.is_relative_to(source) or not archive.parent.is_dir():
        raise ValueError('Use a new encrypted archive outside the source under an existing parent')
    with private_temporary(archive.parent) as stage:
        plain=stage/'snapshot.zip'
        snapshot=backup.create_backup(source,plain)
        result=encrypt_file(plain,archive,password)
        # Exercise authentication/inner validation before claiming creation succeeded.
        verify_encrypted(archive,password,result['archive_sha256'])
    return {**result,'files':snapshot['files'],'provider_credentials_included':False}


def verify_encrypted(archive, password, expected_sha256):
    archive=safe_path(archive)
    with decrypted_archive(archive,password,expected_sha256,archive.parent) as (plain,digest):
        result=backup.verify_backup(plain,digest)
    return {**result,'format':'vra-encrypted-backup-2','encrypted':True,'authenticated':True,'archive_sha256':expected_sha256}


def restore_encrypted(archive, target, password, expected_sha256):
    target=safe_path(target)
    if target.exists() or not target.parent.is_dir():
        raise ValueError('Restore requires a NEW destination; no overwrite')
    with decrypted_archive(archive,password,expected_sha256,target.parent) as (plain,digest):
        # Both content/envelope identities are recorded BEFORE the directory is published.
        return backup.restore_backup(plain,target,digest,authenticated_envelope=expected_sha256)
