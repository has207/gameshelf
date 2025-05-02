import gi
from typing import Callable, Dict, List, Optional, Set, Any, Tuple

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk, GObject, GLib

from controllers.common import get_template_path
from data_mapping import CompletionStatus


class FilterItem(GObject.GObject):
    """Base class for filter items in the sidebar"""
    name = GObject.Property(type=str)
    icon_name = GObject.Property(type=str)

    def __init__(self, name: str, icon_name: str = "applications-games-symbolic"):
        super().__init__()
        self.name = name
        self.icon_name = icon_name


class CategoryItem(FilterItem):
    """Category filter item (like 'Runner' or 'Status')"""

    def __init__(self, name: str, icon_name: str = "folder-symbolic",
                 expanded: bool = True, category_id: str = None):
        super().__init__(name, icon_name)
        self.expanded = expanded
        self.category_id = category_id or name.lower()
        self.values = []  # Will store the value items for this category


class ValueItem(FilterItem):
    """Value filter item (like 'Steam' under 'Runner' category)"""

    def __init__(self, name: str, icon_name: str = "applications-games-symbolic",
                 count: int = 0, value_id: str = None, parent_category: str = None):
        super().__init__(name, icon_name)
        self.count = count
        self.value_id = value_id or name
        self.parent_category = parent_category


@Gtk.Template(filename=get_template_path("filter_category_row.ui"))
class FilterCategoryRow(Gtk.Box):
    __gtype_name__ = "FilterCategoryRow"

    icon: Gtk.Image = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()
    expand_button: Gtk.Button = Gtk.Template.Child()
    values_container: Gtk.Box = Gtk.Template.Child()
    header_box: Gtk.Box = Gtk.Template.Child()

    def __init__(self, category_item: CategoryItem, on_toggle_collapse: Callable = None):
        super().__init__()
        self.category_item = category_item
        self.on_toggle_collapse = on_toggle_collapse

        # Set up UI elements
        self.label.set_label(category_item.name)
        self.icon.set_from_icon_name(category_item.icon_name)

        # Add tooltip explaining multi-selection
        tooltip_text = "Left-click to select a filter value. Right-click to add or remove from multiple selections."
        self.set_tooltip_text(tooltip_text)
        self.header_box.set_tooltip_text(tooltip_text)

        # Apply initial expanded state
        self._update_expand_button()
        self.values_container.set_visible(category_item.expanded)

        # Connect header click to toggle expanded state
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_header_clicked)
        self.header_box.add_controller(click_gesture)

        # Connect button click to toggle expanded state
        self.expand_button.connect("clicked", self._on_expand_button_clicked)

        print(f"Created category row for {category_item.name} with expanded={category_item.expanded}")

    def is_expanded(self) -> bool:
        return self.category_item.expanded

    def set_expanded(self, expanded: bool):
        self.category_item.expanded = expanded
        self._update_expand_button()
        self.values_container.set_visible(expanded)

    def toggle_expanded(self):
        self.set_expanded(not self.category_item.expanded)
        if self.on_toggle_collapse:
            self.on_toggle_collapse(self.category_item)

    def _update_expand_button(self):
        if self.category_item.expanded:
            self.expand_button.set_icon_name("pan-down-symbolic")
        else:
            self.expand_button.set_icon_name("pan-end-symbolic")

    def _on_header_clicked(self, gesture, n_press, x, y):
        self.toggle_expanded()

    def _on_expand_button_clicked(self, button):
        self.toggle_expanded()

    def add_value_row(self, value_row: Gtk.Widget):
        self.values_container.append(value_row)

    def clear_values(self):
        """Remove all value widgets from the container"""
        while True:
            child = self.values_container.get_first_child()
            if child:
                self.values_container.remove(child)
            else:
                break


@Gtk.Template(filename=get_template_path("filter_value_row.ui"))
class FilterValueRow(Gtk.Box):
    __gtype_name__ = "FilterValueRow"

    icon: Gtk.Image = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()
    count_label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, value_item: ValueItem):
        super().__init__()
        self.value_item = value_item

        # Set up UI elements
        self.label.set_label(value_item.name)
        self.icon.set_from_icon_name(value_item.icon_name)

        # Set count if available
        # Always display count, even if 0
        count = value_item.count if value_item.count > 0 else 0
        self.count_label.set_label(str(count))

        # Set alignment through GTK properties
        self.count_label.set_xalign(0.5)  # Horizontally centered
        self.count_label.set_yalign(0.5)  # Vertically centered

        # Add tooltip explaining multi-selection
        self.set_tooltip_text("Left-click to select. Right-click to toggle selection without affecting other selected values.")


def get_completion_status_icon(status: CompletionStatus) -> str:
    """Return an appropriate icon name for a completion status"""
    if status == CompletionStatus.NOT_PLAYED:
        return "media-playback-stop-symbolic"
    elif status == CompletionStatus.PLAN_TO_PLAY:
        return "starred-symbolic"
    elif status == CompletionStatus.PLAYING:
        return "media-playback-start-symbolic"
    elif status == CompletionStatus.ON_HOLD:
        return "media-playback-pause-symbolic"
    elif status == CompletionStatus.ABANDONED:
        return "user-trash-symbolic"
    elif status == CompletionStatus.PLAYED:
        return "content-loading-symbolic"
    elif status == CompletionStatus.BEATEN:
        return "emblem-ok-symbolic"
    elif status == CompletionStatus.COMPLETED:
        return "emblem-default-symbolic"
    else:
        return "dialog-question-symbolic"
