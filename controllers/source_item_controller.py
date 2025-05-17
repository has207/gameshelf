import gi
from typing import Optional

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from data import Source, SourceType
from data_mapping import Platforms


@Gtk.Template(filename="layout/source_item.ui")
class SourceItem(Gtk.Box):
    __gtype_name__ = "SourceItem"

    name_label = Gtk.Template.Child()
    path_label = Gtk.Template.Child()
    source_icon = Gtk.Template.Child()
    active_switch = Gtk.Template.Child()
    edit_button = Gtk.Template.Child()
    delete_button = Gtk.Template.Child()

    def __init__(self, source: Optional[Source], source_handler, **kwargs):
        super().__init__(**kwargs)

        self.source = source
        self.source_handler = source_handler

        # Set default values
        self.name_label.set_text("")
        self.path_label.set_text("")
        self.active_switch.set_active(True)

        # Set icon based on source type (default)
        icon_name = "folder-symbolic"
        self.source_icon.set_from_icon_name(icon_name)

        # Only set up UI elements if source is provided
        if source is not None:
            self.name_label.set_text(source.name)

            # Show platform information in the path label
            if source.config and "platform" in source.config:
                platform_value = source.config["platform"]
                self.path_label.set_text(f"Platform: {platform_value}")
            else:
                self.path_label.set_text("")

            self.active_switch.set_active(source.active)

        # Connect signal handlers
        self.active_switch.connect("state-set", self._on_active_toggled)
        self.edit_button.connect("clicked", self._on_edit_clicked)
        self.delete_button.connect("clicked", self._on_delete_clicked)

    def _on_active_toggled(self, switch, state):
        if self.source is not None:
            self.source.active = state
            self.source_handler.save_source(self.source)
        return False  # Allow the state to change

    def _on_edit_clicked(self, button):
        # Signal to parent to handle edit
        if self.source is not None:
            self.emit("edit-source", self.source)

    def _on_delete_clicked(self, button):
        # Signal to parent to handle delete
        if self.source is not None:
            self.emit("delete-source", self.source)

    # Define custom signals
    __gsignals__ = {
        "edit-source": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "delete-source": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }