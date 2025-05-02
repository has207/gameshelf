from typing import Dict, List, Type, Set, Optional, Callable

from gi.repository import Gtk, Adw, Gio, GObject, GLib

from data_mapping import (
    Platforms, AgeRatings, Features, Genres, Regions,
    InvalidPlatformError, InvalidAgeRatingError, InvalidFeatureError, InvalidGenreError, InvalidRegionError
)
from controllers.common import get_template_path


class MetadataSelectionDialog(Adw.Window):
    """Dialog for selecting multiple metadata items from an enum list"""

    __gsignals__ = {
        'metadata-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, parent, title: str, enum_class, current_selections: Optional[List] = None):
        """Initialize the dialog

        Args:
            parent: The parent window
            title: The title of the dialog
            enum_class: The enum class to display (Platforms, AgeRatings, etc.)
            current_selections: Optional list of currently selected enum values
        """
        super().__init__()

        self.set_title(title)
        self.set_default_size(400, 500)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_hide_on_close(True)

        self.enum_class = enum_class
        self.selected_items = set()

        # Add current selections to the set if provided
        if current_selections:
            self.selected_items = set(current_selections)

        # Create a wrapper class for the enum values with a toggle property
        self.enum_values = []
        for value in self.enum_class:
            self.enum_values.append({
                'enum': value,
                'selected': value in self.selected_items,
                'name': value.value
            })

        # Sort enum values by name for better display
        self.enum_values.sort(key=lambda x: x['name'])

        # Create main layout
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_show_start_title_buttons(False)
        header_bar.set_show_end_title_buttons(False)

        # Cancel button
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", self.on_cancel_clicked)
        header_bar.pack_start(cancel_button)

        # Title
        title_widget = Adw.WindowTitle()
        title_widget.set_title(title)
        header_bar.set_title_widget(title_widget)

        # Apply button
        self.apply_button = Gtk.Button(label="Apply")
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.connect("clicked", self.on_apply_clicked)
        header_bar.pack_end(self.apply_button)

        self.content_box.append(header_bar)

        # Scrolled window for list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        # Create a ListBox for displaying enum values
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_margin_top(12)
        self.list_box.set_margin_bottom(12)
        self.list_box.set_margin_start(12)
        self.list_box.set_margin_end(12)

        # Add enum values as rows
        self._populate_list_box()

        scrolled.set_child(self.list_box)
        self.content_box.append(scrolled)

        # Set the content
        self.set_content(self.content_box)

    def _populate_list_box(self):
        """Populate the list box with enum values as selectable rows"""
        for item in self.enum_values:
            # Create a row with a check button for each enum value
            row = Adw.ActionRow()
            row.set_title(item['name'])

            check = Gtk.CheckButton()
            check.set_active(item['selected'])
            check.connect("toggled", self.on_check_toggled, item)

            row.add_prefix(check)
            row.set_activatable_widget(check)

            self.list_box.append(row)

    def on_check_toggled(self, check_button, item):
        """Handle check button toggle

        Args:
            check_button: The check button that was toggled
            item: The enum value item dict that was toggled
        """
        item['selected'] = check_button.get_active()

        # Update selected_items set
        if item['selected']:
            self.selected_items.add(item['enum'])
        else:
            self.selected_items.discard(item['enum'])

    def on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.destroy()

    def on_apply_clicked(self, button):
        """Handle apply button click"""
        # Convert set to list for return
        selected_list = list(self.selected_items)

        # Emit signal with selected items
        self.emit("metadata-selected", selected_list)

        # Close dialog
        self.destroy()