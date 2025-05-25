import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk

from progress_manager import get_progress_manager, ProgressType


@Gtk.Template(filename="layout/progress_dialog.ui")
class ProgressDialog(Gtk.Dialog):
    __gtype_name__ = "ProgressDialog"

    progress_container = Gtk.Template.Child()

    def __init__(self, operation_id: str, operation_name: str, progress_type: ProgressType, **kwargs):
        super().__init__(**kwargs)

        self.operation_id = operation_id
        self.progress_manager = get_progress_manager()
        self.dialog_active = True

        # Set dialog title
        self.set_title(f"Scanning {operation_name}")

        # Ensure proper dialog positioning - GTK4 should handle this automatically with transient_for

        # Start progress operation
        self.progress_callback = self.progress_manager.start_operation(
            operation_id=operation_id,
            operation_name=operation_name,
            progress_type=progress_type,
            cancellable=True
        )

        # Create and add progress widget
        progress_widget = self.progress_manager.create_progress_widget(operation_id)
        self.progress_container.append(progress_widget)

        # Remove dialog default margins and action area
        try:
            # Hide the action area that creates bottom margin
            action_area = self.get_action_area()
            if action_area:
                action_area.set_visible(False)
        except Exception as e:
            print(f"Could not hide action area: {e}")

        # Remove content area margins
        try:
            content_area = self.get_content_area()
            if content_area:
                content_area.set_margin_top(0)
                content_area.set_margin_bottom(0)
                content_area.set_margin_start(0)
                content_area.set_margin_end(0)
        except Exception as e:
            print(f"Could not modify content area: {e}")

        # Connect signals
        self.connect("response", self._on_response)
        self.connect("show", self._on_show)

    def _on_show(self, dialog):
        """Handle dialog show event to ensure proper positioning"""
        # Try to center the dialog on the parent window
        parent = self.get_transient_for()
        if parent:
            # Ensure proper window relationship
            self.set_modal(False)

            # Try to position dialog centered on parent
            try:
                parent_surface = parent.get_surface()
                dialog_surface = self.get_surface()

                if parent_surface and dialog_surface:
                    # Get the display
                    display = parent.get_display()
                    if display:
                        # Get monitor geometry
                        monitor = display.get_monitor_at_surface(parent_surface)
                        if monitor:
                            geometry = monitor.get_geometry()

                            # Simple centering on screen
                            dialog_width = 450  # From template
                            dialog_height = 200  # Estimate

                            x = geometry.x + (geometry.width - dialog_width) // 2
                            y = geometry.y + (geometry.height - dialog_height) // 2

                            # Note: This may not work on Wayland
                            if hasattr(dialog_surface, 'move'):
                                dialog_surface.move(x, y)

            except Exception:
                # Positioning failed, but dialog will still show
                pass

    def _on_response(self, dialog, response_id):
        """Handle dialog response"""
        self.dialog_active = False
        if response_id == Gtk.ResponseType.CLOSE:
            self.progress_manager.cancel_operation(self.operation_id)
        self.destroy()

    def get_progress_callback(self):
        """Get the progress callback for this dialog"""
        return self.progress_callback

    def is_active(self):
        """Check if dialog is still active"""
        return self.dialog_active


@Gtk.Template(filename="layout/error_dialog.ui")
class ErrorDialog(Gtk.Dialog):
    __gtype_name__ = "ErrorDialog"

    ok_button = Gtk.Template.Child()
    content_area = Gtk.Template.Child()
    error_icon = Gtk.Template.Child()
    message_label = Gtk.Template.Child()

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)

        # Set the error message
        self.message_label.set_text(message)

        # Connect signals
        self.connect("response", self._on_response)

    def _on_response(self, dialog, response_id):
        """Handle dialog response"""
        self.destroy()


@Gtk.Template(filename="layout/scan_errors_dialog.ui")
class ScanErrorsDialog(Gtk.Dialog):
    __gtype_name__ = "ScanErrorsDialog"

    ok_button = Gtk.Template.Child()
    content_area = Gtk.Template.Child()
    header_label = Gtk.Template.Child()
    error_scroll = Gtk.Template.Child()
    error_text = Gtk.Template.Child()

    def __init__(self, errors: list, **kwargs):
        super().__init__(**kwargs)

        # Set title and header
        self.set_title(f"Scan completed with {len(errors)} errors")
        self.header_label.set_markup(f"<b>The scan completed but encountered {len(errors)} errors:</b>")

        # Set error text
        error_text_content = "\\n".join([f"• {error}" for error in errors])
        text_buffer = self.error_text.get_buffer()
        text_buffer.set_text(error_text_content)

        # Connect signals
        self.connect("response", self._on_response)

    def _on_response(self, dialog, response_id):
        """Handle dialog response"""
        self.destroy()