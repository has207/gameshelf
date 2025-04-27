import os
from typing import Optional, Any, List, Dict, Callable
from gi.repository import Gtk, Gio, GdkPixbuf, GObject
from data_handler import Game, Runner


def show_error_dialog(parent: Gtk.Window, title: str, message: str) -> None:
    """
    Show an error dialog.

    Args:
        parent: The parent window
        title: The dialog title
        message: The error message
    """
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=title,
        secondary_text=message
    )
    dialog.connect("response", lambda dialog, response: dialog.destroy())
    dialog.show()

def show_confirmation_dialog(
    parent: Gtk.Window,
    title: str,
    message: str,
    callback: Callable
) -> None:
    """
    Show a confirmation dialog.

    Args:
        parent: The parent window
        title: The dialog title
        message: The confirmation message
        callback: Function to call with the response
    """
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=title,
        secondary_text=message
    )
    dialog.connect("response", callback)
    dialog.show()

def get_template_path(filename: str) -> str:
    """
    Get the absolute path to a UI template file.

    Args:
        filename: The filename of the template

    Returns:
        The absolute path to the template file
    """
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", filename)

def show_image_chooser_dialog(parent_window, callback, title="Select Image"):
    """
    Shows a file chooser dialog for selecting images.

    Args:
        parent_window: The parent window for the dialog
        callback: Function to call with the selected file path or None if canceled
        title: Optional title for the file chooser
    """
    dialog = Gtk.FileChooserDialog(
        title=title,
        action=Gtk.FileChooserAction.OPEN,
        transient_for=parent_window,
        modal=True
    )

    # Add buttons
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Select", Gtk.ResponseType.ACCEPT)

    # Add filters
    filter_images = Gtk.FileFilter()
    filter_images.set_name("Images")
    filter_images.add_mime_type("image/jpeg")
    filter_images.add_mime_type("image/png")
    dialog.add_filter(filter_images)

    def on_response(dialog, response):
        path = None
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                path = file.get_path()

        callback(path)
        dialog.destroy()

    dialog.connect("response", on_response)
    dialog.show()


