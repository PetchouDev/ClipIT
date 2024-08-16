from __future__ import annotations

import os
import sys
import time
import pathlib
import datetime
import sqlite3
import subprocess   
import io

from threading import Thread

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Signal

import pyperclip
import keyboard

from PIL import Image

# Get the path to the data directory
PATH = pathlib.Path(os.path.expanduser('~')) / '.ClipIT'

# Get the path to the file (script if development, executable if compiled)
if getattr(sys, 'frozen', False):
    # If the application is frozen (compiled)
    BASE_DIR = pathlib.Path(sys._MEIPASS).parent

else:
    # If the application is not frozen (development)
    BASE_DIR = pathlib.Path(__file__).resolve().parent

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
        
        self.delete_queue = []


    def run(self):
        # Create a new cursor
        conn = sqlite3.connect(self.database.database)
        
        cursor = conn.cursor()
        # Remember the last items found
        last_items = []

        while self.running:
            # Delete the items in the delete queue
            for item in self.delete_queue:
                self.database.delete(item, connection=conn)
            
            # Clear the delete queue
            self.delete_queue = []

            # Fetch the items from the database
            cursor.execute('SELECT * FROM clipboard;')

            result = cursor.fetchall()

            items = []
            for row in result:
                # If the item is an image, check if the file still exists
                if row[1] == 'image' and not os.path.exists(row[4]):
                    self.database.delete(self.database.fetch(item_id=row[0], cursor=cursor).first(), connection=conn)
                    continue
                items.append(row[0])

            
            # Check if there are new items
            for item in items:
                if item not in last_items:
                    self.communicate.new_item.emit(item)
            
            # Update the last items
            last_items = items

            # Sleep for 10ms
            time.sleep(0.01)
        cursor.close()

class Database:
    def __init__(self, database_path: str):
        self.database = database_path
        self.connection = sqlite3.connect(database_path)
        self.cursor = self.connection.cursor()

    def insert(self, item: ClipboardItem):
        self.cursor.execute('INSERT INTO clipboard (type, data, date, filepath) VALUES (?, ?, ?, ?)', (item.type, item.data, item.date, item.file_path))
        self.connection.commit()

    def fetch(self, type: str | None = None, data: str | None = None, date: int | None = None, file_path: str | None = None, item_id: int | None = None, cursor: sqlite3.Cursor = None) -> Queryset:
        # Use the provided cursor if any
        if not cursor:
            cursor = self.cursor
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
        cursor.execute(query)

        # Parse the results
        for row in cursor.fetchall():
            item = ClipboardItem(row[1], row[2], int(row[3]), row[4])
            item.id = row[0]
            result.append(item)

        return result
    
    def delete(self, item: ClipboardItem, connection: sqlite3.Connection = None):
        # Use the provided connection if any
        if not connection:
            connection = self.connection
        
        # Create a cursor
        cursor = connection.cursor()
        cursor.execute('DELETE FROM clipboard WHERE id = ?', (item.id,))
        connection.commit()
        cursor.close()

        if item.type == 'image':
            try:
                os.remove(item.file_path)
            except FileNotFoundError:
                pass

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
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # make the main window 95% of screen width and 20% of the screen height (use the screen the mouse is on)
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.geometry()

        self.setGeometry(
            screen_geometry.x() + screen_geometry.width() * 0.025,
            screen_geometry.y() + screen_geometry.height() * 0.75 - 35,
            screen_geometry.width() * 0.95,
            screen_geometry.height() * 0.25
        )

        self.setObjectName('mainWindow')
        self.setStyleSheet(
            '''
            QMainWindow#mainWindow {
                background-color: rgba(0, 0, 0, 0);
                border: 2.5px solid cyan;
            }
            '''
        )

        # Create a expandable widget as the central widget
        self.central_widget = QtWidgets.QWidget()
        self.central_widget.setObjectName('centralWidget')
        self.central_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setCentralWidget(self.central_widget)

        self.central_widget.setStyleSheet(
            '''
            #centralWidget {
                background-color: rgba(5, 5, 5, 0.8);
                border: 2.5px solid #a9a9a9;
                border-radius: 20px;
                padding: 5px;
                padding-bottom: 8px;
            }
            '''
        )

        # Set the main layout
        layout = QtWidgets.QVBoxLayout()
        self.central_widget.setLayout(layout)

        # Make a header for the title, the purge button and the close button
        header = QtWidgets.QWidget()
        header_layout = QtWidgets.QHBoxLayout()
        header.setLayout(header_layout)
        header.setObjectName('header')
        header_layout.setSpacing(15)

        header.setStyleSheet(
            '''
            #header {
                background-color: transparent;
            }
            '''
        )

        # Create the title label
        title = QtWidgets.QLabel('ClipIT')
        title.setObjectName('title')
        header_layout.addWidget(title)

        title.setStyleSheet(
            '''
            #title {
                color: #a9a9a9;
                font-size: 30px;
                font-weight: bold;
                font-family: Courier New;
            }
            '''
        )

        # Add a spacer
        header_layout.addStretch(1)

        # Load the font awesome file to allow use of icons
        print(BASE_DIR / 'font.ttf')
        font = QtGui.QFontDatabase.addApplicationFont(str(BASE_DIR / 'font.ttf'))
        self.fontawesome = QtGui.QFontDatabase.applicationFontFamilies(font)[0]

        # Create the purge button
        purge_button = QtWidgets.QPushButton('')
        purge_button.setFont(QtGui.QFont(self.fontawesome))
        purge_button.setObjectName('purge_button')
        purge_button.clicked.connect(self.purge_clipboard)
        purge_button.setFixedSize(30, 30)
        header_layout.addWidget(purge_button)

        purge_button.setStyleSheet(
            '''
            #purge_button {
                background-color: transparent;
                color: #a9a9a9;
                border: none;
                font-size: 25px;
                padding: 0px;
                font-weight: bold;
            }
            #purge_button:hover {
                color: #bb2626;
            }
            '''
        )

        # Create the close button
        close_button = QtWidgets.QPushButton('')
        close_button.setFont(QtGui.QFont(self.fontawesome))
        close_button.setObjectName('close_button')
        close_button.clicked.connect(self.hibernate)
        close_button.setFixedSize(30, 30)
        header_layout.addWidget(close_button)

        close_button.setStyleSheet(
            '''
            #close_button {
                background-color: transparent;
                color: #a9a9a9;
                border: none;
                font-size: 30px;
                padding: 0px;
                font-weight: bold;
            }
            #close_button:hover {
                color: #bb2626;
            }
            '''
        )

        # Add the header to the main layout
        layout.addWidget(header)


        # Create a scrollable frame for the logs (horizontal, hide the scrollbar)
        clipboardScroll = QtWidgets.QScrollArea()
        clipboardScroll.setWidgetResizable(True)
        clipboardScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        clipboardScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        layout.addWidget(clipboardScroll)

        clipboardScroll.setStyleSheet(
            '''
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 0px;
            }
            '''
        )

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
        clipboardWidget.setObjectName('clipboard_widget')

        clipboardWidget.setStyleSheet(
            '''
            QWidget#clipboard_widget {
                background-color: transparent;
                border: none;
                margin: 0px;
                margin-left: 4px;
            }
            '''
        )

        # Save the clipboard data into a dictionary
        self.clipboard_data: dict[int, ClipboardItem] = {}

        # Tray icon
        self.tray_icon = QtWidgets.QSystemTrayIcon(self)
        self.tray_icon.setIcon(QtGui.QIcon(str(BASE_DIR / 'assets' / 'ClipIT.png')))

        self.tray_icon.setToolTip('ClipIT service')
        tray_menu = QtWidgets.QMenu()
        quit_action = QtGui.QAction('Quit', self)
        quit_action.triggered.connect(self.exit)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # Start the database monitor
        self.monitor = DatabaseMonitor(self.database)
        self.monitor.communicate.new_item.connect(self.new_item)
        self.monitor.start()

        # Set the sleeping state to false
        self.sleeping = False

        # Add the hotkey to show the window
        keyboard.add_hotkey('ctrl+alt+v', self.wake_up)

        # Start the application in the background
        self.hibernate()

    @QtCore.Slot(int)
    def new_item(self, item_id):
        # Create a frame for the item
        frame = QtWidgets.QFrame()
        frame.setObjectName(f'clipboard_frame_{item_id}')

        bg_color = "#1a1b1c"
        is_image = False

        # Expand height to content
        frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        frame.setFixedSize(350, 180)

        # Create a layout for the frame
        frame_layout = QtWidgets.QVBoxLayout()
        frame.setLayout(frame_layout)

        # Remove the margins and spacing of the layout
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        # Fetch the item from the database
        item = self.database.fetch(item_id=item_id).first()
        self.clipboard_data[item_id] = item

        # Create a label for the date
        date = QtWidgets.QLabel(item.get_date())
        date.setObjectName('clipboard_date')
        date.setFixedWidth(180)
        date.setStyleSheet(
            '''
            #clipboard_date {
                color: #cbcbcb;
                font-size: 13px;
                font-family: Courier New;
                font-weight: bold;
                background-color: rgba(26, 27, 28, 0.8);
                border-radius: 9px;
                text-align: center;
                padding-left: 7px;
                padding-right: 7px;
                padding-top: 2px;
                padding-bottom: 2px;
                margin: 0px;
                margin-left: 1px;
                margin-bottom: 1px;
            }
            '''
        )
        date.adjustSize()
        
        # If the item is an image, set it as the background of the frame
        if item.type == 'image':
            # Prevent background color from showing
            is_image = True

            # Create a frame for the image that expands to cover the whole frame
            image_frame = QtWidgets.QFrame()
            image_frame.setObjectName('image_frame')
            image_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

            #  Convert the image path to a URL format
            file_path = item.file_path.replace('\\', '/')

            # Add a layout to the image frame
            image_layout = QtWidgets.QVBoxLayout()

            # Set the layout to the image frame
            image_frame.setLayout(image_layout)

            # Add the image frame to the frame layout
            frame_layout.addWidget(image_frame)

            # Add a stretch to the layout so the date is at the bottom
            image_layout.addStretch(1)

            # Add the date to the frame layout
            image_layout.addWidget(date)

            # Set the margins/padding of the image frame to 0 to remove the border
            image_layout.setContentsMargins(0, 0, 0, 0)
            image_layout.setSpacing(0)
            

        
        # If the if a tetx/url/mail, create a TextEdit for the item data (not editable or scrollable)
        elif item.type != 'color':

            # Create a TextEdit for the item data (not editable or scrollable)
            data = QtWidgets.QTextEdit()
            data.setObjectName('clipboard_data')
            data.setReadOnly(True)
            data.setPlainText(str(item))
            data.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

            # Disable scroll
            data.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

            # Make if transparent for the mouse
            data.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

            # Set the style of the text edit
            data.setStyleSheet(
                '''
                #clipboard_data {
                    color: #cbcbcb;
                    font-size: 16px;
                    font-weight: bold;
                    font-family: Courier New;
                    background-color: transparent;
                    border: none;
                }
                '''
            )

            # Add the data to the frame layout
            frame_layout.addWidget(data)

            # Add the date to the frame layout
            frame_layout.addWidget(date)

            # If the item is not raw text, add a latout at the bottom to display an action button near the date
            if item.type != 'text':
                action_frame = QtWidgets.QFrame()
                action_frame.setObjectName('action_frame')
                frame_layout.addWidget(action_frame)

                action_layout = QtWidgets.QHBoxLayout()
                action_frame.setLayout(action_layout)

                action_layout.addWidget(date)

                # Add a stretch to the layout so the date is at the bottom
                action_layout.addStretch(4)

                # Create a button to copy the item to the clipboard
                action_button = QtWidgets.QPushButton('' if (item.type == 'mail' or item.data.startswith('mailto:')) else '')

                # Set the method on button click
                action_button.clicked.connect(lambda: os.system(f"start {'mailto://' if item.type == 'mail' else ''}{item.data}"))

                # Set the style of the button
                action_button.setObjectName('action_button')
                action_button.setFixedSize(20, 20)
                action_button.setStyleSheet(
                    '''
                    #action_button {
                        background-color: transparent;
                        color: #a9a9a9;
                        border: none;
                        font-size: 20px;
                        padding: 0px;
                        font-weight: bold;
                        margin-top: -3px;
                    }
                    #action_button:hover {
                        color: #2089c9;
                    }
                    '''
                )

                # Add the button to the layout
                action_layout.addWidget(action_button)

                action_layout.addStretch(1)

        # If the item is a color, create a frame with the color as the background (remove the alpha channel)
        else:
            color = item.data
            # If the color is in the format #RRGGBBAA, remove the alpha channel
            if color.startswith('#') and len(color) == 9:
                color = color[:7]
            
            # Else, if there is  4 values (3 ','), remove the alpha channel
            elif color.count(',') == 3:
                color = color[:color.rfind(',')] + ')'
                print(color)

            # Set the background color of the frame
            bg_color = color

            # Add a stretch to the layout so the date is at the bottom
            frame_layout.addStretch(1)

            # Add an horizontal layout to the frame to center the color label
            color_layout = QtWidgets.QHBoxLayout()


            # Create a label for the color
            color_label = QtWidgets.QLabel(color)
            color_label.setObjectName('color_label')
            color_label.setStyleSheet(
                '''
                #color_label {
                    padding: 10px;
                    background-color: rgba(5, 5, 5, 0.6);
                    border-radius: 10px;
                    font-size: 20px;
                    font-family: Courier New;
                    font-weight: bold;
                }
                '''
            )

            # Add the color label to the layout
            color_layout.addStretch(1)
            color_layout.addWidget(color_label)
            color_layout.addStretch(1)

            # Add the color layout to the frame layout
            frame_layout.addLayout(color_layout)

            # Add a stretch to the layout so the date is at the bottom
            frame_layout.addStretch(1)

            # Add the date to the frame layout
            frame_layout.addWidget(date)

        # Set the background color of the frame
        if not is_image:
            print(item_id, bg_color, item.type)
            frame.setStyleSheet(
                f'''
                QFrame#clipboard_frame_{item_id} {'{'}
                    background-color: {bg_color};
                    border: 1.5px solid #a9a9a9;
                    border-radius: 10px;
                    padding: 0px;
                    padding-top: 3px;
                    margin-left: 5px;
                    margin-right: 5px;
                {'}'}
                QFrame#clipboard_frame_{item_id}:hover {'{'}
                    border: 2.5px solid white;

                {'}'}
            ''')

        # Apply the style to the frame for image items
        else:
            # Convert the file path to a URL format
            file_path = item.file_path.replace('\\', '/')

            # Apply the stylesheet with proper settings
            frame.setStyleSheet(
                f'''
                #clipboard_frame_{item_id} {{
                    

                    border: 2.5px solid #a9a9a9;
                    border-radius: 10px;
                    padding: 0px;
                    margin-left: 5px;
                    margin-right: 5px;

                }}
                QFrame#clipboard_frame_{item_id}:hover {{
                    border: 3.5px solid white;
                }}
                '''
            )

            # Set the background image of the frame
            image_frame.setStyleSheet(
                f'''
                #image_frame {{
                    border: 1.5px solid #a9a9a9;
                    border-image: url({file_path}) 0 0 0 0 stretch stretch;
                    border-radius: 10px;
                    padding: 0px;
                    margin: 0px;
                }}
                '''
            )

        # Set the method on frame click
        frame.mousePressEvent = lambda event: self.push_clipboard(item.id, frame)

        # Add the date to the frame layout
        #frame_layout.addWidget(date)

        # Add the frame to the clipboard layout
        self.clipboardLayout.insertWidget(0, frame)

        # Update the UI
        self.update()

    def purge_clipboard(self):
        # Delete all the items from the database
        for item in self.clipboard_data.values():
            self.monitor.delete_queue.append(item)

        # Delete all the items from the clipboard layout
        for i in range(self.clipboardLayout.count()):
            self.clipboardLayout.itemAt(i).widget().deleteLater()

    def push_clipboard(self, item_id, frame):
        # Get the item from the clipboard data
        item = self.clipboard_data[item_id]

        # Copy the item data to the clipboard
        if item.type == 'image':
            if sys.platform == 'win32':
                copy_image_windows(item.file_path)
            elif sys.platform == 'darwin':
                copy_image_macos(item.file_path)
            else:
                copy_image_linux(item.file_path)
            
        else:
            pyperclip.copy(item.data)

        self.hibernate()

        # Delete the item from the database
        self.database.delete(item)

        # wait a bit to let the clipboard update
        time.sleep(0.4)

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

    # If win + v is pressed, show the window
    def hibernate(self):
        # Hide the window
        self.hide()

        # Set the sleeping state to true
        self.sleeping = True

        # Wait for a signal to wake up
        while self.sleeping:
            time.sleep(0.1)

        # Show the window
        self.show()
        self.activateWindow()

    def wake_up(self):
        self.sleeping = False
        print('Waking up')


    def exit(self):
        self.tray_icon.hide()
        print('Tray icon terminated')
        self.close()
        print('GUI terminated')
        QtCore.QCoreApplication.instance().quit()
        print('Application terminated')
        sys.exit()


# Stretch a QPixmap to fit a QSize from the center while keeping the aspect ratio
def get_centered_scaled_pixmap(image_path, size):
    # Charger l'image
    image = QtGui.QImage()
    image.load(image_path)

    print(image_path)

    # Créer un QPixmap à partir de l'image
    pixmap = QtGui.QPixmap.fromImage(image)

    # Redimensionner l'image pour qu'elle remplisse le QFrame tout en gardant les proportions
    scaled_pixmap = pixmap.scaled(size, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)

    # Créer une image de destination vide (pleinement remplie de transparence)
    result_image = QtGui.QImage(size, QtGui.QImage.Format_ARGB32)
    result_image.fill(QtCore.Qt.transparent)

    # Créer un QPainter pour dessiner l'image redimensionnée au centre
    painter = QtGui.QPainter(result_image)
    x_offset = (size.width() - scaled_pixmap.width()) // 2
    y_offset = (size.height() - scaled_pixmap.height()) // 2
    painter.drawPixmap(x_offset, y_offset, scaled_pixmap)
    painter.end()

    # Retourner un QPixmap basé sur l'image finale centrée
    return QtGui.QPixmap.fromImage(result_image)

def copy_image_windows(img_path):
    os.system(f"{BASE_DIR /'nircmd.exe'} clipboard copyimage {img_path}")

def copy_image_macos(img_path):
    os.system(f"osascript -e 'set the clipboard to (read (POSIX file \"{img_path}\") as PNG picture)'")

def copy_image_linux(img_path):
    os.system(f"xclip -selection clipboard -t image/png <\"{img_path}\"")

if __name__ == '__main__':
    # Create the application
    app = QtWidgets.QApplication(sys.argv)
    main_window = ApplicationWindow(Database(PATH / 'clipboard.db'))
    sys.exit(app.exec())
