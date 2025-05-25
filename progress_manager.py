import logging
import threading
from typing import Optional, Callable, Any, Dict, Union
from enum import Enum
from dataclasses import dataclass

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gtk, GLib, GObject

logger = logging.getLogger(__name__)


class ProgressType(Enum):
    """Types of progress operations"""
    DETERMINATE = "determinate"  # Known total (progress bar)
    INDETERMINATE = "indeterminate"  # Unknown total (spinner)


@dataclass
class ProgressState:
    """Current state of a progress operation"""
    operation_id: str
    operation_name: str
    progress_type: ProgressType
    current: int = 0
    total: int = 100
    message: str = ""
    phase: str = ""
    cancellable: bool = False
    cancelled: bool = False
    completed: bool = False
    error: Optional[str] = None


class ProgressCallback:
    """Thread-safe progress callback wrapper"""

    def __init__(self, progress_manager: 'ProgressManager', operation_id: str):
        self.progress_manager = progress_manager
        self.operation_id = operation_id

    def __call__(self, current: int, total: int, message: str = "", phase: str = ""):
        """
        Update progress (thread-safe)

        Args:
            current: Current progress value
            total: Total progress value
            message: Current operation message
            phase: Current phase of operation
        """
        # Use GLib.idle_add for thread safety
        GLib.idle_add(
            self.progress_manager._update_progress,
            self.operation_id,
            current,
            total,
            message,
            phase
        )

    def update_message(self, message: str, phase: str = ""):
        """Update just the message without changing progress values"""
        GLib.idle_add(
            self.progress_manager._update_message,
            self.operation_id,
            message,
            phase
        )

    def set_indeterminate(self, message: str = ""):
        """Switch to indeterminate progress mode"""
        GLib.idle_add(
            self.progress_manager._set_indeterminate,
            self.operation_id,
            message
        )

    def complete(self, message: str = "Complete"):
        """Mark operation as completed"""
        GLib.idle_add(
            self.progress_manager._complete_operation,
            self.operation_id,
            message
        )

    def error(self, error_message: str):
        """Mark operation as failed"""
        GLib.idle_add(
            self.progress_manager._error_operation,
            self.operation_id,
            error_message
        )


class ProgressManager(GObject.Object):
    """
    Centralized progress management system

    Provides unified progress tracking with consistent UI patterns,
    thread safety, and operation cancellation support.
    """

    __gsignals__ = {
        'operation-started': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'operation-updated': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'operation-completed': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'operation-cancelled': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        'operation-error': (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
    }

    def __init__(self):
        super().__init__()
        self._operations: Dict[str, ProgressState] = {}
        self._ui_widgets: Dict[str, Dict[str, Gtk.Widget]] = {}
        self._lock = threading.Lock()

    def start_operation(self,
                       operation_id: str,
                       operation_name: str,
                       progress_type: ProgressType = ProgressType.DETERMINATE,
                       cancellable: bool = False,
                       total: int = 100) -> ProgressCallback:
        """
        Start a new progress operation

        Args:
            operation_id: Unique identifier for this operation
            operation_name: Human-readable name for the operation
            progress_type: Type of progress (determinate/indeterminate)
            cancellable: Whether operation can be cancelled
            total: Total progress value (for determinate operations)

        Returns:
            ProgressCallback instance for updating progress
        """
        with self._lock:
            state = ProgressState(
                operation_id=operation_id,
                operation_name=operation_name,
                progress_type=progress_type,
                total=total,
                cancellable=cancellable
            )
            self._operations[operation_id] = state

        self.emit('operation-started', operation_id)
        return ProgressCallback(self, operation_id)

    def cancel_operation(self, operation_id: str) -> bool:
        """
        Cancel a running operation

        Args:
            operation_id: ID of operation to cancel

        Returns:
            True if operation was cancelled, False if not cancellable or not found
        """
        with self._lock:
            if operation_id not in self._operations:
                return False

            state = self._operations[operation_id]
            if not state.cancellable or state.completed or state.cancelled:
                return False

            state.cancelled = True
            state.message = "Cancelling..."

        self.emit('operation-cancelled', operation_id)
        return True

    def get_operation_state(self, operation_id: str) -> Optional[ProgressState]:
        """Get current state of an operation"""
        with self._lock:
            return self._operations.get(operation_id)

    def is_operation_cancelled(self, operation_id: str) -> bool:
        """Check if an operation has been cancelled"""
        with self._lock:
            state = self._operations.get(operation_id)
            return state.cancelled if state else False

    def remove_operation(self, operation_id: str):
        """Remove a completed/cancelled operation"""
        with self._lock:
            self._operations.pop(operation_id, None)
            self._ui_widgets.pop(operation_id, None)

    def create_progress_widget(self, operation_id: str,
                             show_cancel_button: bool = True,
                             show_title: bool = True) -> Gtk.Box:
        """
        Create a standard progress widget for an operation

        Args:
            operation_id: ID of the operation
            show_cancel_button: Whether to show cancel button
            show_title: Whether to show operation title

        Returns:
            Gtk.Box containing progress UI elements
        """
        state = self.get_operation_state(operation_id)
        if not state:
            raise ValueError(f"Operation {operation_id} not found")

        # Create main container
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        container.add_css_class("progress-container")

        # Operation name label (optional)
        name_label = None
        if show_title:
            name_label = Gtk.Label(label=state.operation_name)
            name_label.add_css_class("progress-title")
            container.append(name_label)

        # Progress bar or spinner
        if state.progress_type == ProgressType.DETERMINATE:
            progress_widget = Gtk.ProgressBar()
            progress_widget.set_show_text(True)
        else:
            progress_widget = Gtk.Spinner()
            progress_widget.start()

        container.append(progress_widget)

        # Status label
        status_label = Gtk.Label(label=state.message)
        status_label.add_css_class("progress-status")
        container.append(status_label)

        # Cancel button
        cancel_button = None
        if show_cancel_button and state.cancellable:
            cancel_button = Gtk.Button(label="Cancel")
            cancel_button.connect("clicked", lambda btn: self.cancel_operation(operation_id))
            container.append(cancel_button)

        # Store widget references
        widgets = {
            'container': container,
            'name_label': name_label,
            'progress_widget': progress_widget,
            'status_label': status_label,
            'cancel_button': cancel_button
        }

        with self._lock:
            self._ui_widgets[operation_id] = widgets

        # Connect to updates
        self.connect('operation-updated', self._on_operation_updated)
        self.connect('operation-completed', self._on_operation_completed)
        self.connect('operation-cancelled', self._on_operation_cancelled)
        self.connect('operation-error', self._on_operation_error)

        return container

    def _update_progress(self, operation_id: str, current: int, total: int,
                        message: str, phase: str) -> bool:
        """Update progress (called via GLib.idle_add)"""
        with self._lock:
            if operation_id not in self._operations:
                return False

            state = self._operations[operation_id]
            if state.cancelled or state.completed:
                return False

            state.current = current
            state.total = total
            state.message = message
            state.phase = phase

        self.emit('operation-updated', operation_id)
        return False  # Don't repeat

    def _update_message(self, operation_id: str, message: str, phase: str) -> bool:
        """Update message only (called via GLib.idle_add)"""
        with self._lock:
            if operation_id not in self._operations:
                return False

            state = self._operations[operation_id]
            if state.cancelled or state.completed:
                return False

            state.message = message
            state.phase = phase

        self.emit('operation-updated', operation_id)
        return False

    def _set_indeterminate(self, operation_id: str, message: str) -> bool:
        """Switch to indeterminate mode (called via GLib.idle_add)"""
        with self._lock:
            if operation_id not in self._operations:
                return False

            state = self._operations[operation_id]
            if state.cancelled or state.completed:
                return False

            state.progress_type = ProgressType.INDETERMINATE
            state.message = message

        self.emit('operation-updated', operation_id)
        return False

    def _complete_operation(self, operation_id: str, message: str) -> bool:
        """Complete operation (called via GLib.idle_add)"""
        with self._lock:
            if operation_id not in self._operations:
                return False

            state = self._operations[operation_id]
            state.completed = True
            state.current = state.total
            state.message = message

        self.emit('operation-completed', operation_id)
        return False

    def _error_operation(self, operation_id: str, error_message: str) -> bool:
        """Mark operation as failed (called via GLib.idle_add)"""
        with self._lock:
            if operation_id not in self._operations:
                return False

            state = self._operations[operation_id]
            state.error = error_message
            state.completed = True
            state.message = f"Error: {error_message}"

        self.emit('operation-error', operation_id, error_message)
        return False

    def _on_operation_updated(self, manager, operation_id: str):
        """Handle operation updates"""
        self._update_ui_widgets(operation_id)

    def _on_operation_completed(self, manager, operation_id: str):
        """Handle operation completion"""
        self._update_ui_widgets(operation_id)

        # Disable cancel button
        widgets = self._ui_widgets.get(operation_id, {})
        if widgets.get('cancel_button'):
            widgets['cancel_button'].set_sensitive(False)

    def _on_operation_cancelled(self, manager, operation_id: str):
        """Handle operation cancellation"""
        self._update_ui_widgets(operation_id)

        # Disable cancel button
        widgets = self._ui_widgets.get(operation_id, {})
        if widgets.get('cancel_button'):
            widgets['cancel_button'].set_sensitive(False)

    def _on_operation_error(self, manager, operation_id: str, error_message: str):
        """Handle operation errors"""
        self._update_ui_widgets(operation_id)

        # Disable cancel button and show error styling
        widgets = self._ui_widgets.get(operation_id, {})
        if widgets.get('cancel_button'):
            widgets['cancel_button'].set_sensitive(False)
        if widgets.get('status_label'):
            widgets['status_label'].add_css_class("error")

    def _update_ui_widgets(self, operation_id: str):
        """Update UI widgets for an operation"""
        state = self.get_operation_state(operation_id)
        widgets = self._ui_widgets.get(operation_id, {})

        if not state or not widgets:
            return

        # Update progress widget
        progress_widget = widgets.get('progress_widget')
        if progress_widget:
            if isinstance(progress_widget, Gtk.ProgressBar):
                if state.progress_type == ProgressType.DETERMINATE and state.total > 0:
                    fraction = state.current / state.total
                    progress_widget.set_fraction(fraction)
                    progress_widget.set_text(f"{state.current}/{state.total} ({fraction*100:.0f}%)")
                else:
                    progress_widget.pulse()
                    progress_widget.set_text(state.message)
            elif isinstance(progress_widget, Gtk.Spinner):
                if state.completed or state.cancelled:
                    progress_widget.stop()
                else:
                    progress_widget.start()

        # Update status label
        status_label = widgets.get('status_label')
        if status_label:
            display_message = state.message
            if state.phase:
                display_message = f"{state.phase}: {state.message}"
            status_label.set_text(display_message)


# Global progress manager instance
_progress_manager = None

def get_progress_manager() -> ProgressManager:
    """Get the global progress manager instance"""
    global _progress_manager
    if _progress_manager is None:
        _progress_manager = ProgressManager()
    return _progress_manager