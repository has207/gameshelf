GameShelf is a game library manager / launcher for Linux.

Features:

* ability to manage your entire collection, including various digital libraries, local installs and emulators
* supports multiple accounts for Xbox, PSN, Steam, GOG and Epic
* use a variety of metadata sources for game details and imagery
* search / filter / hide games
* watch game trailers

## Dependencies

GameShelf requires the following Python packages:

* PyGObject (for GTK4/Adw)
* pyyaml
* requests (for API calls)
* vdf (for Steam library support)
* isodate

System tray requires AyatanaAppIndicator3 (libayatana-appindicator on Arch and gir1.2-ayatanaappindicator3-0.1 on Ubuntu)
