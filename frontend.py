from __future__ import annotations

import os
import sys
import time
import pathlib
import datetime
import sqlite3

from threading import Thread

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Signal

import pyperclip


# Get the path to the data directory
PATH = pathlib.Path(os.path.expanduser('~')) / '.ClipIT'

# Queryset class
class Queryset:
    def __init__(self, database: Database, items: list[ClipboardItem] = []):
        self.database = database
        self.items = items

    def append(self, item: ClipboardItem):
        self.items.append(item)
        
    def filter(self, key, value):
        return Queryset(self.database, [item for item in self.items if getattr(item, key) == value])
    
    def all(self) -> list[ClipboardItem]:
        return self.items
    
    def first(self) -> ClipboardItem:
        return self.items[0]
    
    def sort(self, key, reverse=False):
        return Queryset(self.database, sorted(self.items, key=lambda item: getattr(item, key), reverse=reverse))

# Communication class
class Communicate(QtCore.QObject):
    new_item = Signal(int)

# Database Monitor class
class DatabaseMonitor(Thread):

    def __init__(self, database: Database):
        super(DatabaseMonitor, self).__init__()
        self.database = database
        self.running = True
        self.communicate = Communicate()


    def run(self):
        # Create a new cursor
        conn = sqlite3.connect(self.database.database)
        cursor = conn.cursor()

        # Remember the last items found
        last_items = []

        while self.running:
            # Fetch the items from the database
            cursor.execute('SELECT * FROM clipboard;')

            result = cursor.fetchall()

            items = []
            for row in result:
                items.append(row[0])

            
            # Check if there are new items
            for item in items:
                if item not in last_items:
                    self.communicate.new_item.emit(item)
            
            # Update the last items
            last_items = items

            # Sleep for 10ms
            time.sleep(0.10)
        cursor.close()

class Database:
    def __init__(self, database_path: str):
        self.database = database_path
        self.connection = sqlite3.connect(database_path)
        self.cursor = self.connection.cursor()

    def insert(self, item: ClipboardItem):
        self.cursor.execute('INSERT INTO clipboard (type, data, date, filepath) VALUES (?, ?, ?, ?)', (item.type, item.data, item.date, item.file_path))
        self.connection.commit()

    def fetch(self, type: str | None = None, data: str | None = None, date: int | None = None, file_path: str | None = None, item_id: int | None = None)-> Queryset:
        # Build a dictionary of the kwargs
        kwargs = {
            'type': type,
            'data': data,
            'date': date,
            'filepath': file_path,
            'id': item_id
        }
        # Initialize a queryset
        result = Queryset(self, [])

        # Forge the query
        query = 'SELECT * FROM clipboard'
        if any(kwargs.values()):
            query += ' WHERE ' + ' AND '.join([f'{key} = "{value}"' for key, value in kwargs.items() if value])
        query += ';'
        

        print(query)

        # Execute the query
        self.cursor.execute(query)

        # Parse the results
        for row in self.cursor.fetchall():
            item = ClipboardItem(row[1], row[2], int(row[3]), row[4])
            item.id = row[0]
            result.append(item)

        return result
    
    def delete(self, item: ClipboardItem):
        self.cursor.execute('DELETE FROM clipboard WHERE id = ?', (item.id,))
        self.connection.commit()

    def close(self):
        self.connection.close()

    def save(self, item: ClipboardItem):
        if item.id:
            self.cursor.execute('UPDATE clipboard SET type = ?, data = ?, date = ?, filepath = ? WHERE id = ?', (item.type, item.data, item.date, item.file_path, item.id))
            self.connection.commit()
        else:
            self.cursor.execute('INSERT INTO clipboard (type, data, date, filepath) VALUES (?, ?, ?, ?)', (item.type, item.data, item.date, item.file_path))
            self.connection.commit()

            # Fetch the id of the last inserted item
            self.cursor.execute('SELECT last_insert_rowid();')
            item.id = self.cursor.fetchone()[0]

    def __del__(self):
        self.connection.close()

# Clipboard item model
class ClipboardItem:
    def __init__(self, type: str, data: str, date: int, file_path: str = None):
        self.type = type
        self.data = data
        self.date = date
        self.file_path = file_path

        # Declare the id of the item (attrited by the database at insertion)
        self.id = None

    # Return the item data as a string
    def __str__(self):
        return self.file_path if self.type == "image" else self.data
    
    def get_date(self):
        return datetime.datetime.fromtimestamp(self.date).strftime('%Y-%d-%m %H:%M:%S')
    

# Application Main Window
class ApplicationWindow(QtWidgets.QMainWindow):
    def __init__(self, database: Database):
        super(ApplicationWindow, self).__init__()
        self.database = database
        
        # Set the window transparent and frameless
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint | 
            QtCore.Qt.FramelessWindowHint  
        )

        # make the main window 95% of screen width and 20% of the screen height (use the screen the mouse is on)
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.geometry()

        self.setGeometry(
            screen_geometry.x() + screen_geometry.width() * 0.025,
            screen_geometry.y() + screen_geometry.height() * 0.75 - 35,
            screen_geometry.width() * 0.95,
            screen_geometry.height() * 0.25
        )

        # Create a expandable widget as the central widget
        self.central_widget = QtWidgets.QWidget()
        self.central_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setCentralWidget(self.central_widget)

        # Set the main layout
        layout = QtWidgets.QVBoxLayout()
        self.central_widget.setLayout(layout)

        # Make a header for the title, the purge button and the close button
        header = QtWidgets.QWidget()
        header_layout = QtWidgets.QHBoxLayout()
        header.setLayout(header_layout)

        # Create the title label
        title = QtWidgets.QLabel('ClipIT')
        title.setObjectName('title')
        header_layout.addWidget(title)

        # Add a spacer
        header_layout.addStretch(1)

        # Create the purge button
        purge_button = QtWidgets.QPushButton('🗑')
        purge_button.setObjectName('purge_button')
        header_layout.addWidget(purge_button)

        # Create the close button
        close_button = QtWidgets.QPushButton('X')
        close_button.setObjectName('close_button')
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button)

        # Add the header to the main layout
        layout.addWidget(header)


        # Create a scrollable frame for the logs (horizontal, hide the scrollbar)
        clipboardScroll = QtWidgets.QScrollArea()
        clipboardScroll.setWidgetResizable(True)
        clipboardScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        layout.addWidget(clipboardScroll)

        # Create a QWheelEvent for the scroll area to scroll horizontally
        clipboardScroll.wheelEvent = lambda event: clipboardScroll.horizontalScrollBar().setValue(clipboardScroll.horizontalScrollBar().value() - event.angleDelta().y()*.5)

        self.clipboardLayout = QtWidgets.QHBoxLayout()
        self.clipboardLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.clipboardLayout.setSpacing(0)
        self.clipboardLayout.setContentsMargins(0, 0, 0, 0)

        clipboardWidget = QtWidgets.QWidget()
        clipboardWidget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        clipboardWidget.setFixedHeight(200)
        clipboardWidget.setLayout(self.clipboardLayout)
        clipboardScroll.setWidget(clipboardWidget)

        # Save the clipboard data into a dictionary
        self.clipboard_data: dict[int, ClipboardItem] = {}

        # Start the database monitor
        self.monitor = DatabaseMonitor(self.database)
        self.monitor.communicate.new_item.connect(self.new_item)
        self.monitor.start()

    @QtCore.Slot(int)
    def new_item(self, item_id):
        # Create a frame for the item
        frame = QtWidgets.QFrame()
        frame.setObjectName('clipboard_frame')

        # Expand height to content
        frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        frame.setFixedWidth(350)

        # Create a layout for the frame
        frame_layout = QtWidgets.QVBoxLayout()
        frame.setLayout(frame_layout)

        # Fetch the item from the database
        item = self.database.fetch(item_id=item_id).first()
        self.clipboard_data[item_id] = item

        # Create a TextEdit for the item data (not editable or scrollable)
        data = QtWidgets.QTextEdit()
        data.setObjectName('clipboard_data')
        data.setReadOnly(True)
        data.setPlainText(str(item))
        data.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # Disable scroll
        data.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        # Add the data to the frame layout
        frame_layout.addWidget(data)

        # Create a label for the date
        date = QtWidgets.QLabel(item.get_date())

        # Set the method on frame click
        frame.mousePressEvent = lambda event: self.push_clipboard(item.id, frame)

        # Add the date to the frame layout
        frame_layout.addWidget(date)

        # Add the frame to the clipboard layout
        self.clipboardLayout.insertWidget(0, frame)

        # Update the UI
        self.update()

    def push_clipboard(self, item_id, frame):
        # Get the item from the clipboard data
        item = self.clipboard_data[item_id]

        # Copy the item data to the clipboard
        pyperclip.copy(item.data)

        # Delete the item from the database
        self.database.delete(item)

        # Delete the item from the clipboard layout
        self.clipboardLayout.removeWidget(frame)

        # Delete some objects to free memory
        del self.clipboard_data[item_id]
        frame.deleteLater()
        del item

        # Update all the UI
        self.update()



    def closeEvent(self, event):
        self.monitor.running = False
        self.monitor.join()
        self.database.close()
        event.accept()

app = QtWidgets.QApplication(sys.argv)
main_window = ApplicationWindow(Database(PATH / 'clipboard.db'))
main_window.show()
sys.exit(app.exec())
