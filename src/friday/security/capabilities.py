"""
Capability scope system for defining and managing enabled capabilities (Principle B).
"""
from __future__ import annotations

from enum import Enum


class CapabilityScope(str, Enum):
    SYSTEM_READ = "system.read"
    SYSTEM_CONTROL = "system.control"
    WINDOWS_OBSERVE = "windows.observe"
    WINDOWS_INTERACT = "windows.interact"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    FILESYSTEM_DELETE = "filesystem.delete"
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_READ = "browser.read"
    BROWSER_SUBMIT = "browser.submit"
    GMAIL_READ = "gmail.read"
    GMAIL_SEND = "gmail.send"
    CALENDAR_READ = "calendar.read"
    CALENDAR_WRITE = "calendar.write"
    TERMINAL_SANDBOX = "terminal.sandbox"
    TERMINAL_HOST = "terminal.host"


class CapabilityRegistry:
    def __init__(self, is_online: bool = True):
        self._scopes: set[CapabilityScope] = set()
        self._is_online = is_online

    def enable(self, scope: CapabilityScope) -> None:
        self._scopes.add(scope)

    def disable(self, scope: CapabilityScope) -> None:
        self._scopes.discard(scope)
        
    def set_online_status(self, is_online: bool) -> None:
        self._is_online = is_online

    def check_scope(self, scope: CapabilityScope) -> bool:
        if scope not in self._scopes:
            return False
        
        # Network-aware: online scopes disabled when offline
        online_scopes = {
            CapabilityScope.BROWSER_NAVIGATE,
            CapabilityScope.BROWSER_READ,
            CapabilityScope.BROWSER_SUBMIT,
            CapabilityScope.GMAIL_READ,
            CapabilityScope.GMAIL_SEND,
            CapabilityScope.CALENDAR_READ,
            CapabilityScope.CALENDAR_WRITE
        }
        
        if scope in online_scopes and not self._is_online:
            return False
            
        return True
