import gi
from typing import List, Optional

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, GObject

from controllers.common import get_template_path

class FileSelectionDialog(Adw.Window):
    """Dialog for selecting a file from a list of game files"""

    __gsignals__ = {
        'file-selected': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, parent, directory: str, files: List[str]):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Select Game File")
        self.set_default_size(400, 300)

        # Store files
        self.directory = directory
        self.files = files
        self.selected_file = None

        # Create the UI
        self._setup_ui()

    def _setup_ui(self):
        # Create a box for the content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(content_box)

        # Add a header bar
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        content_box.append(header)

        # Add cancel button to header bar
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", self._on_cancel_clicked)
        header.pack_start(cancel_button)

        # Add a title widget
        title_widget = Adw.WindowTitle()
        title_widget.set_title("Select Game File")
        title_widget.set_subtitle("Choose a file to launch")
        header.set_title_widget(title_widget)

        # Add select button to header bar
        select_button = Gtk.Button(label="Select")
        select_button.add_css_class("suggested-action")
        select_button.connect("clicked", self._on_select_clicked)
        select_button.set_sensitive(False)
        self.select_button = select_button
        header.pack_end(select_button)

        # Add main content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        content_box.append(scrolled)

        # Add a list box for the files
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        list_box.set_show_separators(True)
        list_box.add_css_class("boxed-list")
        list_box.connect("row-selected", self._on_file_selected)
        self.list_box = list_box
        scrolled.set_child(list_box)

        # Add a label showing the directory
        dir_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        dir_box.set_margin_top(12)
        dir_box.set_margin_bottom(12)
        dir_box.set_margin_start(12)
        dir_box.set_margin_end(12)

        dir_label = Gtk.Label(label="Directory:")
        dir_label.set_xalign(0)
        dir_box.append(dir_label)

        dir_value = Gtk.Label(label=self.directory)
        dir_value.set_xalign(0)
        dir_value.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        dir_value.set_hexpand(True)
        dir_box.append(dir_value)

        content_box.append(dir_box)

        # Add a separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content_box.append(separator)

        # Add all files to the list box
        for file_path in self.files:
            row = Adw.ActionRow()
            row.set_title(file_path)
            row.set_activatable(True)

            # Store the file path with the row
            row.file_path = file_path

            # Add an icon
            icon = Gtk.Image.new_from_icon_name("document-open-symbolic")
            row.add_prefix(icon)

            # Add the row to the list box
            list_box.append(row)

        # If there's only one file, select it automatically
        if len(self.files) == 1:
            list_box.select_row(list_box.get_row_at_index(0))

    def _on_file_selected(self, list_box, row):
        """Handle selection of a file from the list"""
        if row:
            self.selected_file = row.file_path
            self.select_button.set_sensitive(True)
        else:
            self.selected_file = None
            self.select_button.set_sensitive(False)

    def _on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.close()

    def _on_select_clicked(self, button):
        """Handle select button click"""
        if self.selected_file:
            # Emit the signal with the selected file
            self.emit("file-selected", self.selected_file)
        self.close()