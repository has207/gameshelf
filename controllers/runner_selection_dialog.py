import gi
from typing import List, Optional

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, GObject

from data import Runner
from controllers.common import get_template_path

class RunnerSelectionDialog(Adw.Window):
    """Dialog for selecting a runner from a list of compatible runners"""

    __gsignals__ = {
        'runner-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, parent, runners: List[Runner]):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title("Select Runner")
        self.set_default_size(400, 300)

        # Store runners
        self.runners = runners
        self.selected_runner = None

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
        title_widget.set_title("Select Runner")
        title_widget.set_subtitle("Choose a runner to launch the game")
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

        # Add a list box for the runners
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        list_box.set_show_separators(True)
        list_box.add_css_class("boxed-list")
        list_box.connect("row-selected", self._on_runner_selected)
        self.list_box = list_box
        scrolled.set_child(list_box)

        # Add all runners to the list box
        for runner in self.runners:
            row = Adw.ActionRow()
            row.set_title(runner.title)
            if runner.command:
                row.set_subtitle(f"Command: {runner.command}")
            row.set_activatable(True)

            # Store the runner object with the row
            row.runner = runner

            # Add an icon if the runner has one
            if runner.image:
                icon = Gtk.Image.new_from_icon_name("applications-games-symbolic")
                row.add_prefix(icon)

            # Add the row to the list box
            list_box.append(row)

        # If there's only one runner, select it automatically
        if len(self.runners) == 1:
            list_box.select_row(list_box.get_row_at_index(0))

    def _on_runner_selected(self, list_box, row):
        """Handle selection of a runner from the list"""
        if row:
            self.selected_runner = row.runner
            self.select_button.set_sensitive(True)
        else:
            self.selected_runner = None
            self.select_button.set_sensitive(False)

    def _on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.close()

    def _on_select_clicked(self, button):
        """Handle select button click"""
        if self.selected_runner:
            # Emit the signal with the selected runner
            self.emit("runner-selected", self.selected_runner)
        self.close()